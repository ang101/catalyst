"""repo_scout MCP tool — find GitHub repos for a paper's code implementation."""

import argparse, base64, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP

PWC_API = "https://paperswithcode.com/api/v1/papers"
GH_API = "https://api.github.com"
GH_DELAY = 1  # seconds between GitHub API calls

mcp = FastMCP("repo_scout")


def _papers_dir() -> Path:
    default = Path.home() / ".zeroclaw" / "workspace" / "paper-repro" / "papers"
    return Path(os.environ.get("PAPER_REPRO_PAPERS_DIR", str(default)))


def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"token {tok}"
    return h


def _normalize_url(url: str) -> str:
    """Normalize GitHub URL: lowercase, strip .git / trailing slash / query / punctuation."""
    url = url.strip().rstrip("/")
    # Strip trailing sentence punctuation (period, comma, semicolon, paren)
    url = url.rstrip(".,;:)}")
    if url.endswith(".git"):
        url = url[:-4]
    url = url.split("?")[0].split("#")[0].rstrip("/")
    return url.lower()


def _check_official_readme(repo_url: str) -> bool:
    """Check if repo README mentions 'official implementation/code/repo'."""
    try:
        m = re.match(r"https?://github\.com/([^/]+/[^/]+)", repo_url, re.I)
        if not m:
            return False
        time.sleep(GH_DELAY)
        resp = requests.get(f"{GH_API}/repos/{m.group(1)}/readme", headers=_gh_headers(), timeout=10)
        if resp.status_code != 200:
            return False
        text = base64.b64decode(resp.json().get("content", "")).decode("utf-8", errors="ignore")
        return bool(re.search(r"official\s+(implementation|code|repo)", text, re.I))
    except Exception:
        return False


def _cand(url: str, confidence: float, source: str, is_official: bool) -> dict:
    return {"url": _normalize_url(url), "confidence": confidence,
            "source": source, "is_official": is_official}


def _urls_from_text(text: str) -> list[dict]:
    urls = re.findall(r"https?://github\.com/[\w\-\.]+/[\w\-\.]+", text, re.I)
    seen, out = set(), []
    for u in urls:
        n = _normalize_url(u)
        if n not in seen:
            seen.add(n)
            out.append(_cand(u, 0.95, "paper_text", True))
    return out


def _urls_from_metadata(meta: dict) -> list[dict]:
    out = []
    for link in meta.get("links", []):
        url = link if isinstance(link, str) else str(link)
        if "github.com" in url.lower():
            out.append(_cand(url, 0.90, "metadata_links", True))
    return out


def _search_pwc(arxiv_id: str) -> list[dict]:
    out = []
    try:
        r = requests.get(f"{PWC_API}/", params={"arxiv_id": arxiv_id}, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return []
        pwc_id = results[0].get("id")
        if not pwc_id:
            return []
        r2 = requests.get(f"{PWC_API}/{pwc_id}/repositories/", timeout=15)
        r2.raise_for_status()
        repos = r2.json()
        if isinstance(repos, dict):
            repos = repos.get("results", [])
        for repo in repos:
            url = repo.get("url", "")
            if "github.com" not in url.lower():
                continue
            official = bool(repo.get("is_official", False))
            out.append(_cand(url, 0.85 if official else 0.60, "papers_with_code", official))
    except Exception:
        pass
    return out


def _search_github(title: str, authors: list[str] | None = None) -> list[dict]:
    out = []
    try:
        time.sleep(GH_DELAY)
        r = requests.get(f"{GH_API}/search/repositories",
                         params={"q": title, "sort": "stars", "per_page": 5},
                         headers=_gh_headers(), timeout=15)
        r.raise_for_status()
        author_parts = set()
        for a in (authors or []):
            for p in a.strip().split():
                if len(p) > 2:
                    author_parts.add(p.lower())
        for item in r.json().get("items", []):
            url = item.get("html_url", "")
            if not url:
                continue
            owner = item.get("owner", {}).get("login", "").lower()
            match = any(n in owner for n in author_parts) if author_parts else False
            out.append(_cand(url, 0.50 if match else 0.30, "github_search", False))
    except Exception:
        pass
    return out


def _dedup(candidates: list[dict]) -> list[dict]:
    best = {}
    for c in candidates:
        if c["url"] not in best or c["confidence"] > best[c["url"]]["confidence"]:
            best[c["url"]] = c
    return list(best.values())


def _write_status(paper_dir: Path, paper_id: str, outcome: str, artifacts: list[str], error: str | None):
    status_path = paper_dir / "STATUS.json"
    try:
        status = json.loads(status_path.read_text()) if status_path.exists() else None
    except (json.JSONDecodeError, OSError):
        status = None
    if not isinstance(status, dict):
        status = {"paper_id": paper_id, "phases": []}
    status.setdefault("phases", []).append({
        "phase": "scout",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": outcome, "artifacts": artifacts, "error": error,
    })
    status_path.write_text(json.dumps(status, indent=2))


def repo_scout_impl(paper_id: str) -> dict:
    """Core implementation — returns result dict with ranked candidates."""
    paper_dir = _papers_dir() / paper_id
    if not paper_dir.exists():
        return {"paper_id": paper_id, "candidates": [],
                "error": f"Paper directory not found: {paper_dir}"}

    # Load paper text and metadata
    paper_text = ""
    paper_md = paper_dir / "paper.md"
    if paper_md.exists():
        try:
            paper_text = paper_md.read_text(errors="ignore")
        except OSError:
            pass
    meta = {}
    meta_path = paper_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Gather candidates from all sources
    all_cands = []
    all_cands.extend(_urls_from_text(paper_text))
    all_cands.extend(_urls_from_metadata(meta))
    arxiv_id = meta.get("arxiv_id", paper_id)
    all_cands.extend(_search_pwc(arxiv_id))
    title = meta.get("title", "")
    if title:
        all_cands.extend(_search_github(title, meta.get("authors", [])))

    # Deduplicate, boost official READMEs, sort
    candidates = _dedup(all_cands)
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    for c in candidates[:3]:
        if _check_official_readme(c["url"]):
            c["confidence"] = min(1.0, c["confidence"] + 0.05)
    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    # Write artifacts
    (paper_dir / "candidates.json").write_text(json.dumps(candidates, indent=2))
    outcome = "success" if candidates else "no_repos_found"
    _write_status(paper_dir, paper_id, outcome, ["candidates.json"], None)

    return {"paper_id": paper_id, "candidates": candidates}


@mcp.tool()
def repo_scout(paper_id: str) -> str:
    """Find GitHub repositories containing a paper's code implementation.

    Searches paper text, metadata, Papers with Code, and GitHub to find
    candidate repos ranked by confidence. Writes candidates.json to the
    paper directory.

    Args:
        paper_id: The paper identifier (directory name under papers/).
    """
    return json.dumps(repo_scout_impl(paper_id), indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="repo_scout tool")
    parser.add_argument("paper_id", nargs="?", help="Paper ID (directory under papers/)")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    args = parser.parse_args()
    if args.paper_id or args.cli:
        pid = args.paper_id or input("Enter paper ID: ")
        print(json.dumps(repo_scout_impl(pid), indent=2))
    else:
        mcp.run()
