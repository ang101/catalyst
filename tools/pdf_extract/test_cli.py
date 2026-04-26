#!/usr/bin/env python3
"""Standalone test script for pdf_extract.

Usage:
    python test_cli.py 2106.09685

Expects the paper to already be fetched (via arxiv_fetch).
Prints extraction method used, sections found, and first 500 chars of output.
"""

import json
import sys
from pathlib import Path

from server import pdf_extract_impl, _papers_dir


def test_extract(paper_id: str):
    """Extract a paper and display results."""
    papers_dir = _papers_dir()
    paper_dir = papers_dir / paper_id

    print(f"Paper ID:    {paper_id}")
    print(f"Papers dir:  {papers_dir}")
    print(f"Paper dir:   {paper_dir}")
    print(f"PDF exists:  {(paper_dir / 'source.pdf').exists()}")
    print(f"LaTeX exists:{(paper_dir / 'source').exists()}")
    print("-" * 60)

    result = pdf_extract_impl(paper_id)
    print(f"\nSuccess:     {result.get('success')}")
    print(f"Method used: {result.get('method_used', 'N/A')}")

    if result.get("success"):
        sections = result.get("sections_found", [])
        print(f"Sections ({len(sections)}):")
        for s in sections:
            print(f"  - {s}")

        output_path = Path(result["output_path"])
        text = output_path.read_text()
        print(f"\nOutput size: {len(text):,} chars")
        print(f"\nFirst 500 chars:")
        print("-" * 60)
        print(text[:500])
        print("-" * 60)

        # Verify STATUS.json was updated
        status_path = paper_dir / "STATUS.json"
        if status_path.exists():
            status = json.loads(status_path.read_text())
            extract_phases = [p for p in status.get("phases", []) if p["phase"] == "extract"]
            print(f"\nSTATUS.json extract phases: {len(extract_phases)}")
            if extract_phases:
                print(f"  Latest: {json.dumps(extract_phases[-1], indent=4)}")
    else:
        print(f"Error:       {result.get('error', 'unknown')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    test_extract(sys.argv[1])
