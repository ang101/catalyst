# Paper Reproduction SOP

Autonomous end-to-end reproduction of ML/AI research papers on CPU-only hardware.

## Steps

1. **Preflight** — Verify prerequisites are available.
   Run these shell commands and check results:
   - `which uv` — REQUIRED. Abort if missing.
   - `which bwrap` — Optional. Warn if missing (sandbox degrades).
   - `python3 -c "import marker"` — Optional. Warn if missing (PDF extraction falls back to pymupdf).
   - `test -w /home/hchadha1/.zeroclaw/workspace/paper-repro/papers || mkdir -p /home/hchadha1/.zeroclaw/workspace/paper-repro/papers` — REQUIRED.
   Write a preflight entry to `papers/{paper_id}/STATUS.json`.
   :checkpoint

2. **Acquire** — Fetch the paper using the `arxiv_fetch` MCP tool.
   Call `arxiv_fetch` with the input identifier.
   The tool writes `source.pdf`, `source/` (LaTeX), `metadata.json`, and `STATUS.json` to `papers/{paper_id}/`.
   Verify `STATUS.json` shows outcome "success" for the acquire phase. If not, STOP.
   :checkpoint

3. **Extract** — Convert paper to markdown and extract structured requirements.
   First, call `pdf_extract` with the paper_id. This produces `papers/{paper_id}/paper.md`.
   Then delegate the requirements extraction to `claude_code` with this prompt:
   ```
   Read these three files:
   1. /home/hchadha1/.zeroclaw/workspace/paper-repro/prompts/extract_requirements.md (the extraction instructions)
   2. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/paper.md (the paper content)
   3. /home/hchadha1/.zeroclaw/workspace/paper-repro/prompts/requirements.schema.json (the output schema)

   Follow the instructions in extract_requirements.md exactly. Read the full paper.md. Extract structured requirements and output ONLY valid JSON matching the schema in requirements.schema.json. Write the JSON to /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/requirements.json

   After writing, validate the output: python3 -c "import json; d=json.load(open('/home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/requirements.json')); print('Valid JSON with keys:', list(d.keys()))"
   ```
   Verify that `requirements.json` was written and is valid JSON. If not, STOP.
   Update `STATUS.json` with the extract phase result.
   :checkpoint

4. **Scout** — Find the official code repository.
   Call `repo_scout` with the paper_id. This produces `papers/{paper_id}/candidates.json`.
   Read the candidates. If no candidate has confidence > 0.3, STOP with message: "No repository found. This system requires an existing code repository."
   Otherwise, take the top candidate URL. Clone it:
   `git clone --depth 1 {url} /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/repo/`
   Update `STATUS.json` with the scout phase result.
   :checkpoint

5. **Plan** — Generate a scaled execution plan via claude_code.
   Delegate to `claude_code` with this prompt:
   ```
   Read these files:
   1. /home/hchadha1/.zeroclaw/workspace/paper-repro/prompts/plan_reproduction.md (the planning instructions)
   2. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/requirements.json (extracted requirements)
   3. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/repo/README.md (repo readme)

   Then run: find /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/repo/ -type f | head -200
   Also read any config files: pyproject.toml, setup.py, requirements*.txt, *.yaml, *.yml in the repo root and examples/ directory.

   Follow plan_reproduction.md exactly. Generate two output files:
   1. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/plan.json — execution plan with scaled (CPU-feasible) and faithful tracks
   2. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/scaling_rationale.md — explanation of each scaling decision with claim_preservation section

   If code patches are needed to run on CPU (e.g. removing .cuda() calls, fixing hardcoded GPU references), generate .patch files in /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/patches/

   After writing, validate: python3 -c "import json; p=json.load(open('/home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/plan.json')); print('Plan keys:', list(p.keys()))"
   ```
   Verify plan.json exists and is valid JSON. Verify scaling_rationale.md exists and is non-empty. If either is missing, STOP.
   Update `STATUS.json` with the plan phase result.
   :checkpoint

6. **Execute** — Run the scaled experiment via claude_code with debug loop.
   Delegate the entire execution to `claude_code` with this prompt:
   ```
   You are running a scaled ML experiment for paper 2106.09685.

   Working directory: /home/hchadha1/.zeroclaw/workspace/paper-repro

   Step 1: Read papers/2106.09685/plan.json to understand the execution plan.
   Step 2: Apply any patches in papers/2106.09685/patches/ to the repo:
     cd papers/2106.09685/repo && for p in ../patches/*.patch; do git apply "$p" 2>&1 || echo "Patch $p failed or already applied"; done
   Step 3: Run the scaled_runner tool via CLI:
     cd /home/hchadha1/.zeroclaw/workspace/paper-repro && python3 tools/scaled_runner/server.py --cli 2106.09685
     The tool reads plan.json from the paper directory automatically.
   Step 4: If the run fails (status != "ok"):
     a. Read /home/hchadha1/.zeroclaw/workspace/paper-repro/prompts/debug_loop.md
     b. Read the last 200 lines of the failed run's output log
     c. Read source files mentioned in the traceback
     d. Read all existing patches in papers/2106.09685/patches/
     e. Following debug_loop.md, generate a minimal unified diff patch
     f. Write it to papers/2106.09685/patches/NNN-fix-description.patch (next number in sequence)
     g. Apply: cd papers/2106.09685/repo && git apply ../patches/NNN-*.patch
     h. Retry: python3 /home/hchadha1/.zeroclaw/workspace/paper-repro/tools/scaled_runner/server.py --cli 2106.09685
     i. Maximum 3 retries. If all fail, report all attempted patches.
   Step 5: If timeout, do not retry.
   Step 6: Report the final status (ok/failed/timeout), metrics if any, and path to results.json.
   ```
   Verify the outcome. Update `STATUS.json` with the execute phase result.
   :checkpoint

7. **Report** — Generate the reproduction report via claude_code.
   Delegate to `claude_code` with this prompt:
   ```
   Read these files:
   1. /home/hchadha1/.zeroclaw/workspace/paper-repro/prompts/write_report.md (report instructions)
   2. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/requirements.json
   3. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/plan.json
   4. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/scaling_rationale.md
   5. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/STATUS.json

   Also read if they exist:
   - /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/runs/*/results.json (latest run)
   - All .patch files in /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/patches/
   - Last 200 lines of the latest run log in /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/runs/*/output.log

   Follow write_report.md exactly. Generate three output files:
   1. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/summary.md
   2. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/variables.md
   3. /home/hchadha1/.zeroclaw/workspace/paper-repro/papers/{paper_id}/runbook.md
   ```
   Verify all three files exist and are non-empty. If any are missing, STOP.
   Update `STATUS.json` with the report phase result.
   :checkpoint
