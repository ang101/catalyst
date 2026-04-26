"""arxiv_fetch MCP tool — resolve, download, and catalog arXiv papers."""

import argparse
import json
import os
import re
import tarfile
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from defusedxml import ElementTree as ET
from mcp.server.fastmcp import FastMCP

ARXIV_API = "http://export.arxiv.org/api/query"
ARXIV_PDF = "https://arxiv.org/pdf/{id}"
ARXIV_EPRINT = "https://arxiv.org/e-print/{id}"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper"
REQUEST_DELAY = 3  # seconds between arXiv requests

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

mcp = FastMCP("arxiv_fetch")


def _papers_dir() -> Path:
    default = Path.home() / ".zeroclaw" / "workspace" / "paper-repro" / "papers"
    return Path(os.environ.get("PAPER_REPRO_PAPERS_DIR", str(default)))


def _normalize_id(arxiv_id: str) -> str:
    """Strip version suffix and replace / with _ for directory naming."""
    return re.sub(r"v\d+$", "", arxiv_id).replace("/", "_")


def _classify_identifier(identifier: str) -> tuple[str, str]:
    """Return (kind, value) where kind is 'arxiv_id', 'doi', or 'title'."""
    identifier = identifier.strip()

    # Full arXiv URL
    m = re.search(r"arxiv\.org/(?:abs|pdf|e-print)/(\d{4}\.\d{4,5}(?:v\d+)?)", identifier)
    if m:
        return "arxiv_id", m.group(1)

    # Old-style arXiv URL (e.g. arxiv.org/abs/hep-th/9901001)
    m = re.search(r"arxiv\.org/(?:abs|pdf|e-print)/([\w\-]+/\d{7}(?:v\d+)?)", identifier)
    if m:
        return "arxiv_id", m.group(1)

    # Bare arXiv ID (new-style)
    if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", identifier):
        return "arxiv_id", identifier

    # Bare arXiv ID (old-style)
    if re.fullmatch(r"[\w\-]+/\d{7}(?:v\d+)?", identifier):
        return "arxiv_id", identifier

    # DOI
    if identifier.startswith("10.") or identifier.lower().startswith("doi:"):
        doi = re.sub(r"^doi:\s*", "", identifier, flags=re.IGNORECASE)
        return "doi", doi

    return "title", identifier


def _query_semantic_scholar(query_type: str, value: str) -> str | None:
    """Use Semantic Scholar to resolve a DOI or title to an arXiv ID."""
    try:
        if query_type == "doi":
            url = f"{SEMANTIC_SCHOLAR_API}/{value}"
            params = {"fields": "externalIds"}
        else:
            url = f"{SEMANTIC_SCHOLAR_API}/search"
            params = {"query": value, "limit": 1, "fields": "externalIds"}

        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if query_type == "title":
            papers = data.get("data", [])
            if not papers:
                return None
            data = papers[0]

        ext = data.get("externalIds", {})
        return ext.get("ArXiv")
    except Exception:
        return None


def _fetch_arxiv_metadata(arxiv_id: str) -> dict:
    """Query arXiv Atom API and return parsed metadata dict."""
    resp = requests.get(ARXIV_API, params={"id_list": arxiv_id}, timeout=15)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        raise ValueError(f"No entry found for arXiv ID {arxiv_id}")

    # Check for arXiv error
    id_el = entry.find("atom:id", ATOM_NS)
    if id_el is not None and "api/errors" in (id_el.text or ""):
        summary = entry.find("atom:summary", ATOM_NS)
        msg = summary.text.strip() if summary is not None else "Unknown arXiv API error"
        raise ValueError(msg)

    title = (entry.findtext("atom:title", "", ATOM_NS) or "").strip().replace("\n", " ")
    abstract = (entry.findtext("atom:summary", "", ATOM_NS) or "").strip()
    published = entry.findtext("atom:published", "", ATOM_NS) or ""
    year = published[:4] if len(published) >= 4 else ""

    authors = []
    for author_el in entry.findall("atom:author", ATOM_NS):
        name = author_el.findtext("atom:name", "", ATOM_NS)
        if name:
            authors.append(name.strip())

    # Extract links from abstract (URLs)
    links = re.findall(r"https?://[^\s)}>]+", abstract)

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "arxiv_id": arxiv_id,
        "abstract": abstract,
        "links": links,
    }


def _download_pdf(arxiv_id: str, dest: Path) -> bool:
    url = ARXIV_PDF.format(id=arxiv_id)
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        return False
    dest.write_bytes(resp.content)
    return True


def _download_source(arxiv_id: str, dest_dir: Path) -> bool:
    url = ARXIV_EPRINT.format(id=arxiv_id)
    resp = requests.get(url, timeout=60)
    if resp.status_code != 200:
        return False
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        buf = BytesIO(resp.content)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            tar.extractall(path=str(dest_dir), filter="data")
        return True
    except (tarfile.TarError, Exception):
        # Sometimes source is a single TeX file, not a tarball
        single = dest_dir / "source.tex"
        dest_dir.mkdir(parents=True, exist_ok=True)
        single.write_bytes(resp.content)
        return True


def _write_status(paper_dir: Path, paper_id: str, outcome: str, artifacts: list[str], error: str | None):
    status_path = paper_dir / "STATUS.json"
    status = {
        "paper_id": paper_id,
        "phases": [
            {
                "phase": "acquire",
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "outcome": outcome,
                "artifacts": artifacts,
                "error": error,
            }
        ],
    }
    status_path.write_text(json.dumps(status, indent=2))


def arxiv_fetch_impl(identifier: str) -> dict:
    """Core implementation — returns a result dict."""
    kind, value = _classify_identifier(identifier)

    # Resolve to arXiv ID if needed
    arxiv_id = None
    if kind == "arxiv_id":
        arxiv_id = value
    else:
        arxiv_id = _query_semantic_scholar(kind, value)
        if not arxiv_id:
            return {"success": False, "error": f"Could not resolve {kind} '{value}' to an arXiv ID"}

    norm_id = _normalize_id(arxiv_id)
    paper_dir = _papers_dir() / norm_id
    paper_dir.mkdir(parents=True, exist_ok=True)

    artifacts: list[str] = []
    try:
        # 1. Metadata
        metadata = _fetch_arxiv_metadata(arxiv_id)
        meta_path = paper_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2))
        artifacts.append("metadata.json")

        time.sleep(REQUEST_DELAY)

        # 2. PDF
        pdf_path = paper_dir / "source.pdf"
        if _download_pdf(arxiv_id, pdf_path):
            artifacts.append("source.pdf")

        time.sleep(REQUEST_DELAY)

        # 3. LaTeX source
        source_dir = paper_dir / "source"
        if _download_source(arxiv_id, source_dir):
            artifacts.append("source/")

        # 4. STATUS.json
        _write_status(paper_dir, arxiv_id, "success", artifacts, None)
        artifacts.append("STATUS.json")

        return {"success": True, "paper_id": norm_id, "arxiv_id": arxiv_id, "artifacts": artifacts}

    except Exception as exc:
        error_msg = str(exc)
        _write_status(paper_dir, arxiv_id, "failed", artifacts, error_msg)
        return {"success": False, "paper_id": norm_id, "error": error_msg}


@mcp.tool()
def arxiv_fetch(identifier: str) -> str:
    """Fetch an arXiv paper by ID, URL, DOI, or title.

    Downloads the PDF and LaTeX source, extracts metadata, and initializes
    a STATUS.json tracking file. Returns a JSON result with the paper_id.

    Args:
        identifier: arXiv ID (e.g. "2106.09685"), full URL, DOI, or paper title.
    """
    result = arxiv_fetch_impl(identifier)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="arxiv_fetch tool")
    parser.add_argument("identifier", nargs="?", help="arXiv ID, URL, DOI, or title")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode (non-MCP)")
    args = parser.parse_args()

    if args.identifier or args.cli:
        ident = args.identifier or input("Enter paper identifier: ")
        result = arxiv_fetch_impl(ident)
        print(json.dumps(result, indent=2))
    else:
        mcp.run()
