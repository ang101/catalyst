"""
End-to-end pipeline: fetch paper -> extract -> build reader -> refresh catalog.
Usage: python3 run_pipeline.py <arxiv_id>
"""

import sys
import subprocess
import time
from pathlib import Path

BASE = Path("/home/hchadha1/.zeroclaw/workspace/paper-repro")


def run(paper_id):
    t0 = time.time()

    # 1. Fetch paper if needed
    paper_md = BASE / f"papers/{paper_id}/paper.md"
    if not paper_md.exists():
        print(f"[1/4] Fetching {paper_id}...")
        subprocess.run(
            ["python3", str(BASE / "tools/arxiv_fetch/server.py"), "--cli", paper_id],
            check=True
        )
        print(f"[1.5/4] Extracting PDF...")
        subprocess.run(
            ["python3", str(BASE / "tools/pdf_extract/server.py"), "--cli", paper_id],
            check=True
        )
    else:
        print(f"[1/4] Paper {paper_id} already fetched")

    # 2. Extract structured data
    print(f"[2/4] Extracting paper data...")
    subprocess.run(
        ["python3", str(BASE / "reader/extract_paper_data.py"), paper_id],
        check=True
    )

    # 3. Build reader
    print(f"[3/4] Building reader HTML...")
    subprocess.run(
        ["python3", str(BASE / "reader/build_reader.py"), paper_id],
        check=True
    )

    # 4. Refresh catalog
    print(f"[4/4] Refreshing catalog...")
    subprocess.run(
        ["python3", str(BASE / "reader/index_builder.py")],
        check=True
    )

    elapsed = time.time() - t0
    catalog_path = BASE / "reader/readers/catalog.html"
    reader_path = BASE / f"reader/readers/{paper_id}.html"
    print(f"\nDone in {elapsed:.0f}s.")
    print(f"  Catalog: {catalog_path}")
    print(f"  Reader:  {reader_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 run_pipeline.py <arxiv_id>")
    run(sys.argv[1])
