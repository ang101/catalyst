---
inputs:
  - name: requirements_json
    type: json
    description: Original extracted requirements
  - name: plan_json
    type: json
    description: The execution plan that was used
  - name: scaling_rationale_md
    type: markdown
    description: Why each scaling decision was made
  - name: results_json
    type: json
    description: Metrics captured from the run
  - name: status
    type: string
    description: Final status (ok/timeout/failed)
  - name: all_patches
    type: string
    description: All patches applied (including debug loop patches)
  - name: run_log_tail
    type: string
    description: Last 200 lines of the run log
outputs:
  - name: summary_md
    type: markdown
    description: Main findings report
  - name: variables_md
    type: markdown
    description: Every config knob with paper vs. used vs. safe range
  - name: runbook_md
    type: markdown
    description: Literal commands and patches to reproduce this run
---

# Write Reproduction Report

You are writing the final report for an ML paper reproduction attempt. You have the original requirements, the execution plan, the scaling rationale, the results, and the run logs. You must produce three documents: `summary.md`, `variables.md`, and `runbook.md`.

## Critical Principles

1. **Never quote the paper directly.** Paraphrase all claims. This is for legal safety and because exact quotes without context can be misleading.

2. **Be honest about what the scaled run can and cannot show.** A 500-step run on 1% of data cannot "reproduce" a claim about final perplexity. It CAN show that the training pipeline works, loss decreases, and the method is implemented correctly.

3. **Distinguish between "could not reproduce" and "did not attempt to reproduce."** If a claim was outside the scope of the scaled run, say so. Do not label it as "could not reproduce."

4. **Numbers must be exact.** Report the precise values from results_json. Do not round. Do not say "approximately" when you have the exact number.

5. **If the run failed, the report is still valuable.** Document what went wrong, how far the run got, and what that tells us.

---

## Document 1: summary.md

### Structure

```markdown
# Reproduction Report: [Paper Title / Method Name]

**Paper**: [paper_id]
**Method**: [method_name]
**Status**: [ok / timeout / failed]
**Date**: [YYYY-MM-DD]

## Core Claim

[Paraphrase the paper's core claim in 1-2 sentences. Do NOT quote.]

## Reproduction Scope

[Explain what was actually run: scaled track, how much was cut, what this can vs. cannot tell us. 
Be blunt. Example: "This reproduction used 1% of the training data and ran for 500 steps 
(vs. 100k in the paper) on a 2-layer model (vs. 12-layer). Results are directional only 
and cannot confirm absolute metric values."]

## Results Comparison

| Metric | Dataset | Paper Claimed | Reproduced (scaled) | Comparable? | Notes |
|--------|---------|---------------|---------------------|-------------|-------|
| perplexity | WikiText-103 test | 29.1 | 847.3 | No | Scaled model, 500 steps, expected to be much worse |
| train_loss | — | not reported | 4.23 (final) | — | Loss decreased from 11.1 to 4.23 over 500 steps |

For each row:
- **Comparable?** is "Yes" only if the run used the same model size, same dataset (or full dataset), and trained to convergence. Otherwise "No" or "Partial".
- **Notes** explains why the values differ or why they're not comparable.

## Assessment

[One of these verdicts, with justification:]

### Fully Reproduced
Use when: All primary metrics match within expected variance (typically ±2% relative for deterministic setups, ±5% for stochastic). Same model, same data, same training duration.

### Partially Reproduced  
Use when: Some metrics match, others don't. Or the training curve shape matches but absolute values differ. Explain which parts reproduced and which didn't.

### Could Not Reproduce
Use when: The run completed but results diverge significantly from claims, at a configuration where they should be comparable. Explain the discrepancy.

### Inconclusive — Scaling Too Aggressive
Use when: The scaled configuration is too different from the paper's to draw meaningful conclusions. This is the MOST COMMON verdict for CPU-scaled runs. Be honest about this.

### Failed — Did Not Complete
Use when: The run errored out. Describe how far it got and what the failure tells us about the code quality / reproducibility.

## Findings

[Bullet list of specific observations:]

- [Observation about training stability]
- [Observation about code quality / documentation]
- [Observation about any discrepancies found during planning]
- [Observation about patches needed and what they reveal]

## Limitations

[What this report does NOT tell you. Be specific:]

- This run used [X]% of training data, so absolute metric values are not meaningful
- Model was scaled from [X] to [Y] parameters, which may change qualitative behavior
- [Other limitations specific to this reproduction]
```

### Assessment Guidelines

When writing the assessment, consider:

**Signs the reproduction is working (even at scale)**:
- Loss decreases monotonically in early training
- Loss curve shape matches expected pattern (fast initial decrease, then plateau)
- No NaN/Inf in training
- Gradients are reasonable magnitude
- If multiple methods are compared, their relative ranking matches the paper

**Red flags (even at scale)**:
- Loss does not decrease
- Loss oscillates wildly with no downward trend
- NaN/Inf appear early in training
- The code required extensive patching to run at all
- Key hyperparameters were missing from the paper and had to be guessed

---

## Document 2: variables.md

### Structure

```markdown
# Variable Reference: [Method Name]

Every configuration variable with paper value, value used in this reproduction, and safe range estimates.

## Model Architecture

| Variable | Paper Value | Used Value | Safe Range | Impact | Source |
|----------|-------------|------------|------------|--------|--------|
| n_layers | 12 | 2 | 1-24 | High — directly affects capacity | Table 1 |
| d_model | 768 | 128 | 64-1024 | High — affects all parameter counts | Table 1 |
| n_heads | 12 | 2 | 1-16 (must divide d_model) | Medium | Table 1 |
| dropout | 0.1 | 0.1 | 0.0-0.3 | Low at small scale | Appendix B |
| activation | GELU | GELU | GELU/SiLU/ReLU | Low | Section 3.1 |

## Training Configuration

| Variable | Paper Value | Used Value | Safe Range | Impact | Source |
|----------|-------------|------------|------------|--------|--------|
| learning_rate | 3e-4 | 3e-4 | 1e-4 to 1e-3 | Very High | Section 4.1 |
| batch_size | 512 | 8 | 4-1024 | Medium (coupled with lr) | Section 4.1 |
| optimizer | AdamW | AdamW | AdamW/Adam | High | Section 4.1 |
| weight_decay | 0.1 | 0.1 | 0.01-0.3 | Medium | Appendix B |
| warmup_steps | 2000 | 50 | 10-10000 | Medium | Appendix B |
| max_steps | 100000 | 500 | — | Very High for final metrics | Section 4.1 |
| gradient_clipping | 1.0 | 1.0 | 0.5-5.0 | Medium | Appendix B |

## Data Configuration

| Variable | Paper Value | Used Value | Safe Range | Impact | Source |
|----------|-------------|------------|------------|--------|--------|
| dataset | OpenWebText (full) | OpenWebText (1%) | >10% for reliable metrics | High | Section 4.1 |
| seq_length | 1024 | 128 | 64-2048 | High for attention models | Section 4.1 |
| vocab_size | 50257 | 50257 | — (must match tokenizer) | N/A | — |

## Column Definitions

- **Paper Value**: Exactly as stated in the paper. "null" if not stated.
- **Used Value**: What was actually used in this reproduction run.
- **Safe Range**: Estimated range where the paper's qualitative results likely still hold. Based on the paper's own ablations (preferred) or general ML knowledge (fallback). "—" if no reasonable estimate.
- **Impact**: How sensitive results are to this variable. "Very High" = wrong value will definitely change results. "High" = likely to change results. "Medium" = may change results. "Low" = unlikely to matter.
- **Source**: Where in the paper this value was found. "default" if using repo default. "inferred" if computed from other values.
```

### Guidelines for Safe Range

- If the paper includes an ablation for a variable, use the ablation's range.
- If the paper doesn't ablate it, use standard ranges from ML practice:
  - Learning rate: typically within 3x of stated value
  - Batch size: 2x-8x change usually fine with lr scaling
  - Model size: qualitative results often hold across 2-4x size changes
  - Dropout: 0 to 0.3 usually safe
  - Training steps: relative rankings often emerge within 10-20% of full training
- Mark any safe range estimate as uncertain if not backed by the paper's own ablations.

---

## Document 3: runbook.md

### Structure

```markdown
# Runbook: Reproducing [Method Name]

Step-by-step instructions to reproduce this exact run from scratch. Assumes a fresh Linux machine with Python installed.

## Prerequisites

- Python [version]
- [RAM requirement]
- [Disk space requirement]
- [Estimated wall time]

## Step 1: Clone the Repository

```bash
git clone [repo_url]
cd [repo_name]
git checkout [commit_hash]  # Pin to exact commit for reproducibility
```

## Step 2: Set Up Environment

```bash
python -m venv repro_env
source repro_env/bin/activate
pip install -r requirements.txt
# If additional packages needed:
pip install [package1] [package2]
```

## Step 3: Apply Patches

[For each patch, in order:]

### Patch 1: [Description]

**Why**: [1 sentence explaining why this patch is needed]
**Effect on results**: [None / Minor / Significant — explain]

```bash
cat << 'PATCH_EOF' | git apply -
[unified diff content]
PATCH_EOF
```

### Patch 2: [Description]
...

## Step 4: Prepare Data

```bash
[Commands to download/prepare data]
# Expected: [describe what should exist after this step]
```

## Step 5: Run Smoke Test

```bash
[Exact smoke test command from plan_json]
# Expected output: [what success looks like]
# Should complete in: < 60 seconds
```

## Step 6: Run Scaled Reproduction

```bash
[Exact train command from plan_json]
# Expected wall time: [from plan_json]
# Expected peak memory: [from plan_json]
```

## Step 7: Check Results

```bash
# Look for these patterns in the output:
# [metric patterns from plan_json]
```

### Expected Output

If the run succeeds, you should see:
- [Description of expected output]
- Final train_loss around [X] (approximate, will vary)
- [Other expected outputs]

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: [X]` | Missing dependency | `pip install [X]` |
| OOM / Killed | Not enough RAM | Reduce `--batch_size` to [smaller value] |
| Loss is NaN | LR too high for small model | Try `--lr [lower value]` |
| [Other issues encountered during this reproduction] | [cause] | [fix] |

## Environment Details

These exact versions were used in this reproduction:

```
Python: [version]
PyTorch: [version]
[Other key packages with versions]
OS: [from run environment]
Hardware: CPU only, [RAM]
```

## Reproduction Log

Run started: [timestamp]
Run ended: [timestamp]
Final status: [ok/timeout/failed]
Total patches applied: [count]
Debug loop iterations: [count]
```

### Guidelines for the Runbook

1. **Every command must be copy-pasteable.** No `<placeholders>`. No "edit this file manually." Everything is automated via `git apply` or `sed` or direct CLI args.

2. **Pin everything.** Git commit hash, Python version, package versions. A runbook that doesn't pin versions is not a runbook.

3. **Include the smoke test.** If someone follows the runbook and the smoke test fails, they know immediately without waiting for the full run.

4. **Order patches correctly.** If patch B depends on patch A, they must be listed in order. Note dependencies explicitly.

5. **Include failure modes.** The troubleshooting table should cover every error that was actually encountered during this reproduction, plus common ones.

---

## Status-Specific Guidance

### If status is "ok"
Write all three documents fully. The results comparison table is the centerpiece.

### If status is "timeout"
The run didn't finish. Report:
- How far it got (what step/epoch)
- Metrics at the point it stopped
- Whether the training curve looked healthy up to that point
- How much more time was needed (estimate from training speed)

### If status is "failed"
The run errored out after exhausting debug loop attempts. Report:
- The final error that could not be fixed
- All patches that were attempted
- Whether the failure is fundamental (GPU-only code, proprietary dependencies) or likely fixable with more effort
- What this tells us about the paper's code quality and reproducibility

Even for failed runs, produce all three documents. The runbook should document the steps up to failure, and the troubleshooting section should describe the unresolved error.

## Output Format

Return the three documents separated by these exact markers:

```
===== SUMMARY.MD =====
[content]

===== VARIABLES.MD =====
[content]

===== RUNBOOK.MD =====
[content]
```
