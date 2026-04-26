#!/usr/bin/env bash
set -uo pipefail

# E2E test for paper-repro infrastructure
# Test paper: LoRA (arXiv 2106.09685) - small, official Microsoft repo, testable claims

PAPERS_DIR="${PAPER_REPRO_PAPERS_DIR:-$HOME/.zeroclaw/workspace/paper-repro/papers}"
TOOLS_DIR="$HOME/.zeroclaw/workspace/paper-repro/tools"
PAPER_ID="2106.09685"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
check_file() { [[ -f "$1" ]] && pass "$2" || fail "$2: $1 not found"; }
check_json() { python3 -c "import json; json.load(open('$1'))" 2>/dev/null && pass "$2" || fail "$2: invalid JSON"; }

echo "=== Paper Repro E2E Test ==="
echo "Paper: LoRA ($PAPER_ID)"
echo ""

# Clean previous test run
rm -rf "$PAPERS_DIR/$PAPER_ID"

# Phase 1: arxiv_fetch
echo "[1/4] Testing arxiv_fetch..."
python3 "$TOOLS_DIR/arxiv_fetch/server.py" --cli "$PAPER_ID"
check_file "$PAPERS_DIR/$PAPER_ID/source.pdf" "PDF downloaded"
check_json "$PAPERS_DIR/$PAPER_ID/metadata.json" "metadata.json valid"
check_json "$PAPERS_DIR/$PAPER_ID/STATUS.json" "STATUS.json created"

# Phase 2: pdf_extract
echo "[2/4] Testing pdf_extract..."
python3 "$TOOLS_DIR/pdf_extract/server.py" --cli "$PAPER_ID"
check_file "$PAPERS_DIR/$PAPER_ID/paper.md" "paper.md created"
# Check it has some content
[[ $(wc -c < "$PAPERS_DIR/$PAPER_ID/paper.md") -gt 1000 ]] && pass "paper.md has content" || fail "paper.md too small"

# Phase 3: repo_scout
echo "[3/4] Testing repo_scout..."
python3 "$TOOLS_DIR/repo_scout/server.py" --cli "$PAPER_ID"
check_json "$PAPERS_DIR/$PAPER_ID/candidates.json" "candidates.json valid"
# Check that microsoft/LoRA or similar is in candidates
python3 -c "
import json
candidates = json.load(open('$PAPERS_DIR/$PAPER_ID/candidates.json'))
urls = [c['url'].lower() for c in candidates]
found = any('microsoft' in u and 'lora' in u for u in urls)
print('  PASS: Microsoft LoRA repo found' if found else '  FAIL: Microsoft LoRA repo not in candidates')
"

# Phase 4: scaled_runner (dry run with toy script)
echo "[4/4] Testing scaled_runner (toy script)..."
python3 "$TOOLS_DIR/scaled_runner/test_cli.py"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] && echo "All tests passed!" && exit 0 || echo "Some tests failed." && exit 1
