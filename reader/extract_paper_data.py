"""
Generic paper data extractor for the interactive reader system.
Calls claude -p for classification and extraction.
"""

import sys
import json
import subprocess
import time
from pathlib import Path

READER_DIR = Path(__file__).parent.resolve()
PAPERS_DIR = Path.home() / ".zeroclaw" / "workspace" / "paper-repro" / "papers"
PROMPTS_DIR = READER_DIR / "prompts"
DATA_DIR = READER_DIR / "data"


def call_claude(prompt_text: str, timeout: int = 300) -> str:
    """Call claude -p with the given prompt, return stdout. Uses stdin for large prompts."""
    result = subprocess.run(
        ["claude", "-p", "-", "--output-format", "json"],
        input=prompt_text, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        print(f"claude -p failed (exit {result.returncode}): {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    # claude --output-format json wraps output in a JSON envelope
    try:
        envelope = json.loads(result.stdout)
        # The actual text is in the 'result' field
        text = envelope.get("result", result.stdout)
    except json.JSONDecodeError:
        text = result.stdout

    return text.strip()


def parse_json_from_text(text: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences."""
    # Strip markdown fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last fence lines
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        cleaned = "\n".join(lines[start:end])

    return json.loads(cleaned)


def classify(paper_text: str) -> dict:
    """Classify paper into case A/B/C."""
    prompt = (PROMPTS_DIR / "classify_paper.md").read_text()
    full_prompt = f"{prompt}\n\n---PAPER---\n{paper_text}"
    raw = call_claude(full_prompt, timeout=120)
    return parse_json_from_text(raw)


def extract_data(paper_text: str) -> dict:
    """Extract structured data from paper."""
    prompt = (PROMPTS_DIR / "extract_data.md").read_text()
    full_prompt = f"{prompt}\n\n---PAPER---\n{paper_text}"
    raw = call_claude(full_prompt, timeout=600)
    return parse_json_from_text(raw)


def extract(paper_id: str) -> dict:
    """Full extraction pipeline for a paper."""
    paper_md = PAPERS_DIR / paper_id / "paper.md"
    if not paper_md.exists():
        sys.exit(f"paper.md not found at {paper_md}")

    paper_text = paper_md.read_text()
    print(f"Paper: {paper_id} ({len(paper_text)} chars)")

    # Step 1: Classify
    print("Step 1/2: Classifying paper...")
    t0 = time.time()
    classification = classify(paper_text)
    t1 = time.time()
    print(f"  Case {classification['case']}: {classification.get('reasoning', '')}")
    print(f"  Tables: {classification.get('tables_found', '?')}, "
          f"Ablation tables: {classification.get('ablation_tables_found', '?')}, "
          f"Est. data points: {classification.get('estimated_data_points', '?')}")
    print(f"  ({t1 - t0:.1f}s)")

    # Step 2: Extract data
    print("Step 2/2: Extracting structured data...")
    t2 = time.time()
    data = extract_data(paper_text)
    t3 = time.time()
    n_dp = len(data.get("data_points", []))
    n_vars = len(data.get("variables", []))
    n_metrics = len(data.get("metrics", []))
    print(f"  {n_dp} data points, {n_vars} variables, {n_metrics} metrics")
    print(f"  ({t3 - t2:.1f}s)")

    # Step 3: Combine and write
    output = {
        "classification": classification,
        "extraction": data,
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{paper_id}.json"
    out_path.write_text(json.dumps(output, indent=2))

    # Quality summary
    n_paper = sum(1 for dp in data.get("data_points", []) if dp.get("source_cell"))
    n_total = n_dp
    quality_pct = round(100 * n_paper / n_total, 1) if n_total > 0 else 0
    print(f"\nOutput: {out_path}")
    print(f"Quality: {n_paper}/{n_total} data points have source citations ({quality_pct}%)")
    print(f"Total time: {t3 - t0:.1f}s")

    return output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_paper_data.py <paper_id>")
        print("  paper_id: arxiv ID (e.g., 2106.09685)")
        sys.exit(1)
    extract(sys.argv[1])
