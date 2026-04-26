#!/usr/bin/env python3
"""Standalone test script for arxiv_fetch.

Usage:
    python test_cli.py 2106.09685
    python test_cli.py "https://arxiv.org/abs/2106.09685"
    python test_cli.py "Low-Rank Adaptation"
    python test_cli.py "10.48550/arXiv.2106.09685"
"""

import json
import sys
import tempfile
import os

# Use a temp directory so tests don't pollute the real papers dir
_test_dir = tempfile.mkdtemp(prefix="arxiv_fetch_test_")
os.environ["PAPER_REPRO_PAPERS_DIR"] = _test_dir

from server import arxiv_fetch_impl, _classify_identifier


def test_classifier():
    """Quick smoke test for identifier classification."""
    cases = [
        ("2106.09685", ("arxiv_id", "2106.09685")),
        ("2106.09685v2", ("arxiv_id", "2106.09685v2")),
        ("https://arxiv.org/abs/2106.09685", ("arxiv_id", "2106.09685")),
        ("https://arxiv.org/pdf/2106.09685v1", ("arxiv_id", "2106.09685v1")),
        ("hep-th/9901001", ("arxiv_id", "hep-th/9901001")),
        ("10.48550/arXiv.2106.09685", ("doi", "10.48550/arXiv.2106.09685")),
        ("DOI: 10.1234/example", ("doi", "10.1234/example")),
        ("Low-Rank Adaptation", ("title", "Low-Rank Adaptation")),
    ]
    passed = 0
    for inp, expected in cases:
        result = _classify_identifier(inp)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            print(f"  {status}: classify({inp!r}) = {result}, expected {expected}")
        else:
            passed += 1
    print(f"Classifier tests: {passed}/{len(cases)} passed")


def test_fetch(identifier: str):
    """Fetch a paper and display results."""
    print(f"\nFetching: {identifier!r}")
    print(f"Papers dir: {_test_dir}")
    print("-" * 60)

    result = arxiv_fetch_impl(identifier)
    print(json.dumps(result, indent=2))

    if result.get("success"):
        from pathlib import Path
        paper_dir = Path(_test_dir) / result["paper_id"]
        print(f"\nFiles in {paper_dir}:")
        for p in sorted(paper_dir.rglob("*")):
            if p.is_file():
                size = p.stat().st_size
                print(f"  {p.relative_to(paper_dir)}  ({size:,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    identifier = sys.argv[1]

    if identifier == "--test-classify":
        test_classifier()
    else:
        test_classifier()
        test_fetch(identifier)
