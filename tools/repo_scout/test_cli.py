#!/usr/bin/env python3
"""Standalone test script for repo_scout.

Usage:
    python test_cli.py 2106.09685

Expects papers/<paper_id>/paper.md and metadata.json to exist
(run arxiv_fetch first). Prints ranked repo candidates.

For the LoRA paper (2106.09685), the top hit should be microsoft/LoRA.
"""

import json
import sys
import os

from pathlib import Path

# Allow overriding papers dir; default uses the real papers dir
if "PAPER_REPRO_PAPERS_DIR" not in os.environ:
    default = Path.home() / ".zeroclaw" / "workspace" / "paper-repro" / "papers"
    os.environ["PAPER_REPRO_PAPERS_DIR"] = str(default)

from server import repo_scout_impl, _normalize_url, _urls_from_text


def test_normalize_url():
    """Smoke test for URL normalization."""
    cases = [
        ("https://github.com/microsoft/LoRA/", "https://github.com/microsoft/lora"),
        ("https://github.com/microsoft/LoRA.git", "https://github.com/microsoft/lora"),
        ("https://GITHUB.com/Foo/Bar", "https://github.com/foo/bar"),
        ("https://github.com/a/b?tab=readme", "https://github.com/a/b"),
    ]
    passed = 0
    for inp, expected in cases:
        result = _normalize_url(inp)
        if result == expected:
            passed += 1
        else:
            print(f"  FAIL: normalize({inp!r}) = {result!r}, expected {expected!r}")
    print(f"URL normalization tests: {passed}/{len(cases)} passed")


def test_extract_urls():
    """Test GitHub URL extraction from text."""
    text = """
    Our code is available at https://github.com/microsoft/LoRA.
    See also https://github.com/huggingface/transformers for the base model.
    """
    results = _urls_from_text(text)
    urls = [r["url"] for r in results]
    assert len(results) == 2, f"Expected 2 URLs, got {len(results)}"
    assert "https://github.com/microsoft/lora" in urls
    print(f"URL extraction test: PASS ({len(results)} URLs found)")


def test_scout(paper_id: str):
    """Run the full scout pipeline and display results."""
    papers_dir = Path(os.environ["PAPER_REPRO_PAPERS_DIR"])
    paper_dir = papers_dir / paper_id

    if not paper_dir.exists():
        print(f"ERROR: Paper directory not found: {paper_dir}")
        print("Run arxiv_fetch first:  cd ../arxiv_fetch && python server.py --cli " + paper_id)
        sys.exit(1)

    if not (paper_dir / "metadata.json").exists():
        print(f"WARNING: metadata.json not found in {paper_dir}")

    print(f"\nScouting repos for paper: {paper_id}")
    print(f"Papers dir: {papers_dir}")
    print("-" * 60)

    result = repo_scout_impl(paper_id)
    candidates = result.get("candidates", [])

    if not candidates:
        print("No candidates found.")
    else:
        print(f"Found {len(candidates)} candidate(s):\n")
        for i, c in enumerate(candidates, 1):
            official = " [OFFICIAL]" if c["is_official"] else ""
            print(f"  {i}. {c['url']}")
            print(f"     confidence: {c['confidence']:.2f}  source: {c['source']}{official}")
            print()

    # Check artifacts were written
    cand_path = paper_dir / "candidates.json"
    status_path = paper_dir / "STATUS.json"
    if cand_path.exists():
        print(f"candidates.json written ({cand_path.stat().st_size} bytes)")
    if status_path.exists():
        status = json.loads(status_path.read_text())
        scout_phases = [p for p in status.get("phases", []) if p["phase"] == "scout"]
        print(f"STATUS.json updated ({len(scout_phases)} scout phase(s))")

    # LoRA-specific assertion
    if "2106.09685" in paper_id and candidates:
        top_url = candidates[0]["url"]
        if "microsoft" in top_url and "lora" in top_url:
            print("\nLoRA check: PASS (microsoft/LoRA is top candidate)")
        else:
            print(f"\nLoRA check: WARN (top candidate is {top_url}, expected microsoft/lora)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    paper_id = sys.argv[1]

    test_normalize_url()
    test_extract_urls()
    test_scout(paper_id)
