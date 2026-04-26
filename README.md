# Catalyst: Autonomous AI Paper Reproduction on ZeroClaw

Catalyst is infrastructure for autonomously reproducing ML/AI research papers on CPU-only hardware. It runs on [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw), a Rust-based agent runtime, using MCP tool servers for paper fetching, PDF extraction, repo discovery, and experiment execution, with Claude Code handling the LLM-heavy reasoning phases (requirements extraction, planning, debugging, report generation).

## Architecture

```
zeroclaw agent (orchestrator)
  |
  |-- MCP tools (Python, stdio transport)
  |     |-- arxiv_fetch    fetch paper PDF + LaTeX + metadata
  |     |-- pdf_extract    PDF/LaTeX -> structured markdown
  |     |-- repo_scout     find official code repo
  |     |-- scaled_runner  sandboxed experiment execution
  |
  |-- claude_code delegation (Pro subscription, no API rate limits)
  |     |-- extract requirements (paper.md -> requirements.json)
  |     |-- plan reproduction (requirements + repo -> plan.json)
  |     |-- debug loop (error -> patch)
  |     |-- write report (results -> summary.md)
  |
  |-- SOP definition (sops/paper_repro/)
        phases: preflight -> acquire -> extract -> scout -> plan -> execute -> report
        checkpoint/resume via STATUS.json
```

## Reproduction Strategies

The planner selects one of three strategies before any scaling decisions:

- **Strategy A (Evaluation-only)**: Released checkpoint exists for the main claim. Load checkpoint, run eval, compare metrics. 1-2 orders of magnitude cheaper than training.
- **Strategy B (Finetune)**: Base checkpoint exists but no task-specific one. Brief finetuning from base, then eval.
- **Strategy C (Scaled from-scratch)**: No checkpoint available. Aggressive scale-down of training config, then eval.

## Prerequisites

- [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) installed and onboarded (`~/.zeroclaw/`)
- [Claude Code](https://claude.ai/claude-code) CLI installed (`claude` binary on PATH)
- Python 3.10+
- `uv` package manager
- `bwrap` (bubblewrap) for sandboxed execution (optional, degrades gracefully)

## Installation

```bash
# Copy tools and prompts to ZeroClaw workspace
cp -r tools/ ~/.zeroclaw/workspace/paper-repro/tools/
cp -r prompts/ ~/.zeroclaw/workspace/paper-repro/prompts/
cp -r policy/ ~/.zeroclaw/workspace/paper-repro/policy/
cp -r sops/paper_repro/ ~/.zeroclaw/workspace/sops/paper_repro/
mkdir -p ~/.zeroclaw/workspace/paper-repro/papers

# Register MCP servers in ZeroClaw config
# Add to [mcp] section of ~/.zeroclaw/config.toml:
# [[mcp.servers]]
# name = "arxiv_fetch"
# transport = "stdio"
# command = "python3"
# args = ["/path/to/tools/arxiv_fetch/server.py"]
# (repeat for pdf_extract, repo_scout, scaled_runner)

# Enable Claude Code delegation
zeroclaw config set claude-code.enabled true
zeroclaw config set claude-code.timeout-secs 1800
```

## Usage

```bash
zeroclaw agent -m "Run SOP paper_repro for paper 2106.09685"
```

Or with a URL, DOI, or title:
```bash
zeroclaw agent -m "Run SOP paper_repro for paper 'LoRA: Low-Rank Adaptation'"
```

## Testing Tools Standalone

Each MCP tool can be tested independently:

```bash
python tools/arxiv_fetch/server.py --cli 2106.09685
python tools/pdf_extract/server.py --cli 2106.09685
python tools/repo_scout/server.py --cli 2106.09685
python tools/scaled_runner/test_cli.py  # self-contained toy test
```

## Output Structure

After a run, `papers/<id>/` contains:

```
papers/2106.09685/
  STATUS.json            checkpoint/resume state
  metadata.json          paper bibliographic info
  requirements.json      extracted requirements + released_artifacts
  candidates.json        ranked repo candidates
  plan.json              execution plan (strategy + config)
  scaling_rationale.md   why each scaling decision was made
  patches/*.patch        CPU-compatibility patches
  runs/<timestamp>/      execution artifacts
    results.json         captured metrics
    output.log           training/eval output
  summary.md             reproduction report
  variables.md           config variable reference
  runbook.md             step-by-step reproduction commands
```

## Directory Layout

```
catalyst/
  tools/                 4 MCP tool servers (Python)
    arxiv_fetch/         arXiv API + Semantic Scholar fallback
    pdf_extract/         marker-pdf + PyMuPDF + LaTeX extraction
    repo_scout/          GitHub + PapersWithCode + paper text search
    scaled_runner/       uv venv + patching + sandboxed execution
  prompts/               LLM prompt templates
    extract_requirements.md   paper -> requirements.json
    plan_reproduction.md      requirements + repo -> plan.json
    debug_loop.md             error -> patch
    write_report.md           results -> report
    requirements.schema.json  JSON schema for requirements
  sops/paper_repro/      ZeroClaw SOP definition
    SOP.toml             metadata + config
    SOP.md               step-by-step procedure
  policy/                security policy
    command_policy.yaml   network allowlist + sandbox rules
  papers/                runtime artifacts (per-paper)
  examples/              example run artifacts (sanitized)
  tests/                 e2e test script
```

## Known Limitations

- **CPU beam search is slow.** Autoregressive generation with beam search on models >100M parameters is impractical on CPU. The eval strategy planner needs wall-clock budgeting for inference (tracked issue).
- **Papers without public repos fail cleanly.** By design -- no "best-effort reimplementation" path.
- **Sandbox requires bwrap on Linux.** Fallback mode (timeout + ulimit) provides less isolation.
- **ZeroClaw's Anthropic API rate limits** can block the inner agent. Claude Code delegation (Pro subscription) bypasses this for LLM-heavy phases.
- **Debug loop patches are conservative.** Complex build systems or non-standard training loops may need manual intervention.

## License

MIT
