---
inputs:
  - name: requirements_json
    type: json
    description: Extracted requirements from the paper
  - name: repo_structure
    type: string
    description: Output of `find <repo> -type f` showing repo file layout
  - name: repo_readme
    type: string
    description: README.md from the repo
  - name: repo_config_files
    type: string
    description: Contents of config files found in the repo (YAML, JSON, argparse defaults)
outputs:
  - name: plan_json
    type: json
    description: Execution plan with scaled and faithful tracks
  - name: scaling_rationale_md
    type: markdown
    description: Explanation of scaling decisions
---

# Plan Paper Reproduction

You are creating an execution plan to reproduce an ML paper's results. You have the extracted requirements from the paper and access to the paper's code repository. You must produce two outputs: `plan.json` (the machine-readable execution plan) and `scaling_rationale.md` (human-readable explanation of scaling decisions).

## Input

1. **requirements_json**: Structured requirements extracted from the paper (see requirements.schema.json).
2. **repo_structure**: File listing of the repository.
3. **repo_readme**: The repository's README.
4. **repo_config_files**: Contents of all config files (YAML, JSON, TOML, argparse defaults in Python files).

## Phase 0: Strategy Selection (DO THIS FIRST)

Before any repo analysis or scaling decisions, select a reproduction strategy based on `requirements_json.released_artifacts` and the nature of the paper's main claim.

### Strategy A — Evaluation-only

**Use when:** `released_artifacts.checkpoints` contains at least one checkpoint with `supports_main_claim: true`, AND the paper's main claim is about model performance at inference (accuracy, BLEU, perplexity, success rate, etc.).

**What this produces:** Load the released checkpoint, run the paper's eval script (or equivalent), compare produced metrics to the paper's claimed values. No training at all.

**HARD CONSTRAINTS for CPU evaluation:**

These are non-negotiable. If you cannot fit your eval within these constraints, choose Strategy C (from-scratch) at toy scale instead, or mark the paper infeasible.

1. `eval.num_examples`: MAXIMUM 50. Default 25. Even if the paper evaluates on the full test set, evaluate on at most 50 examples for the scaled track. The faithful track can specify the full set, but it must be marked `feasible_on_cpu: false`.

2. `eval.decoding_method`: MUST be `"greedy"` for the scaled track. Beam search of any width is forbidden in the scaled track on CPU — beam search multiplies inference cost by O(beam_width). The faithful track may specify beam search, but again only if marked `feasible_on_cpu: false`.

3. `eval.max_output_tokens`: MAXIMUM 32 for the scaled track. Default 16. Long generations multiply per-example time linearly.

4. `eval.estimated_wall_clock_minutes`: MUST be calculated and included in plan.json. Estimate as: `num_examples * (model_params_M / 50) * max_output_tokens / 30` where `model_params_M` is the model size in millions. If estimate > 30 minutes, reduce `num_examples` until it fits. If even at `num_examples=10` the estimate exceeds 30 min, the model is too large for CPU evaluation — mark infeasible.

5. plan.json MUST include an `"eval_constraints"` object explicitly listing all five values above. The execution layer will reject plans that omit these.

**Exception for non-generative eval:** If the eval task does not involve text generation (e.g., embedding similarity, classification, regression), constraints 2 and 3 do not apply. Constraint 1 still applies unless per-example cost is sub-second (embeddings, cosine similarity), in which case up to the full test set is permitted. Constraint 4 still applies — calculate and include the estimate.

The scaled track produces metrics with a sample-size caveat. The report should explicitly say "metric on N=X examples, not N=Y as in the paper. Directional comparison only." Honest scoping is required.

**plan.json must include:**
- `"strategy": "evaluation"`
- `eval_script`: path to the evaluation entry point
- `eval_args`: command-line arguments to run evaluation with the checkpoint
- `checkpoint_path`: path to the released checkpoint (or download command)
- `eval_constraints`: object with `num_examples`, `decoding_method`, `max_output_tokens`, `estimated_wall_clock_minutes`, `feasible_on_cpu`
- `metrics_to_capture`: same as other strategies
- No `train_script`, `train_args`, or `scaled_config` needed.

### Strategy B — Finetune
**Use when:** `released_artifacts.checkpoints` has a base/pretrained checkpoint but NOT a task-specific one for the main claim, AND the paper's claim is specifically about finetuning behavior (low-rank adaptation, prompt tuning, PEFT methods, etc.).

**What this produces:** Brief finetuning run from the base checkpoint, then evaluation.

**plan.json must include:**
- `"strategy": "finetune"`
- Both training and evaluation fields, but training starts from the released checkpoint (not random init).

### Strategy C — Scaled from-scratch
**Use when:** No released checkpoint exists, OR the paper's claim is specifically about training dynamics (scaling laws, emergence, convergence behavior, data efficiency).

**What this produces:** Aggressive scale-down of training config, then evaluation.

**plan.json must include:**
- `"strategy": "from_scratch"`
- Full training and evaluation fields with scaling rationale.

### Decision rule
1. Check `released_artifacts.checkpoints` for any entry with `supports_main_claim: true`. If found → Strategy A.
2. Else, check if a base checkpoint exists AND the claim is about finetuning. If so → Strategy B.
3. Else → Strategy C.

**State your strategy choice and reasoning in `scaling_rationale.md` before any other content.**

## Phase 1: Repo Analysis

Before planning, you must understand the codebase. Answer these questions by examining the inputs:

### Find the training entry point
- Look for files named: `train.py`, `main.py`, `run.py`, `run_training.py`, `train_*.py`
- Check the README for "How to run" or "Training" sections
- Check `Makefile`, `scripts/`, or `bin/` for wrapper scripts
- Check `setup.py` / `pyproject.toml` for console_scripts entry points

### Find the config system
Repos use one of these patterns (identify which):

| Pattern | How to detect | How to set hyperparameters |
|---------|--------------|---------------------------|
| argparse | `argparse.ArgumentParser` in train.py | `--flag value` CLI args |
| Hydra/OmegaConf | `@hydra.main`, `config/` dir with YAML | `key=value` overrides or YAML file |
| ML Collections | `config_flags`, `ml_collections` import | `--config.field=value` |
| Custom config class | dataclass or dict in `config.py` | Varies — may need code edit |
| HuggingFace Trainer | `TrainingArguments`, `Trainer` | `--per_device_train_batch_size` etc. |
| PyTorch Lightning | `LightningModule`, `Trainer` | CLI args or YAML via `LightningCLI` |
| Hardcoded | Values directly in train.py | Must patch the source code |

### Find the model definition
- Look for: `model.py`, `models/`, `modeling_*.py`, `architecture.py`
- Identify which model class matches the paper's architecture

### Find the data loading
- Look for: `data.py`, `dataset.py`, `data/`, `dataloader.py`
- Identify how datasets are loaded and whether they auto-download

### Find the evaluation
- Look for: `eval.py`, `evaluate.py`, `test.py`, metrics computation in train.py
- Identify what metrics are computed and where they're logged

## Phase 2: Hyperparameter Mapping

This is the most error-prone step. You must map each paper hyperparameter to the exact CLI argument or config key in the repo.

For every value in requirements_json.training and requirements_json.model.key_hyperparameters, find the corresponding repo parameter.

**Example mapping table** (include one like this in your analysis):

| Paper parameter | Paper value | Repo parameter | How to set |
|----------------|-------------|---------------|------------|
| learning_rate | 3e-4 | `--lr` | `--lr 3e-4` |
| batch_size | 512 | `--batch_size` (per-GPU) | `--batch_size 64 --gradient_accumulation_steps 8` (for 1 GPU) |
| n_layers | 12 | `model.n_layer` in config.yaml | `model.n_layer=12` |
| weight_decay | 0.1 | `--weight_decay` | `--weight_decay 0.1` |
| max_seq_len | 1024 | `--block_size` | `--block_size 1024` |

Watch for these common traps:
- **Batch size decomposition**: Paper says effective batch size 512, but repo takes per-GPU batch size. You must compute: `per_gpu_bs = effective_bs / (n_gpus * grad_accum_steps)`.
- **Learning rate naming**: `--lr`, `--learning_rate`, `--learning-rate`, `training_args.learning_rate` — repos are inconsistent.
- **Epoch vs. step**: Paper says "100k steps" but repo takes `--num_train_epochs`. You need to compute: `epochs = steps * batch_size / dataset_size`.
- **Implicit defaults**: Repo may default to values different from the paper. Check defaults in argparse or config files.
- **Nested configs**: Hydra configs may have `model.d_model` vs. flat `--d_model`. Get the nesting right.

## Phase 3: Build Two Tracks

### Track 1: `faithful`

Matches the paper's configuration exactly. This track:
- Uses the exact hyperparameters from the paper
- May require multiple GPUs or days of training
- Serves as reference — we record the config but may not run it
- Includes the full dataset, full model size, full training duration

### Track 2: `scaled`

CPU-feasible version that preserves as much scientific validity as possible. Apply scaling cuts in this priority order (cut from the top first, only go further if needed):

1. **Dataset fraction** (safest cut): Use 1-10% of training data. This preserves the training dynamics and model architecture. The absolute metric values will be worse, but relative comparisons (method A vs. B) often hold.

2. **Training steps** (safe cut): Train for 100-1000 steps instead of full convergence. Enough to verify the loss decreases and training is stable. Early-training behavior often predicts final ranking.

3. **Model size** (moderate cut): If the paper tests multiple sizes, use the smallest. If only one size, reduce n_layers and d_model proportionally (e.g., 12 layers -> 2 layers, 768 hidden -> 128 hidden). This changes the model fundamentally but can still verify the code runs and the method "works" directionally.

4. **Sequence length** (moderate cut): Reduce from 1024/2048 to 128-256. Affects attention patterns and positional encodings but saves memory quadratically for attention-based models.

5. **Number of seeds** (minor cut): Run 1 seed instead of 3-5.

**Scaling budget target**: The scaled track must complete in under 30 minutes on a single CPU core with 16GB RAM.

### Smoke test config

Also create a `smoke_config` that runs 10 training steps on a tiny data slice. This is used to verify the code runs at all before committing to the full scaled run. It should complete in under 60 seconds.

## Phase 4: Identify Patches Needed

Examine the repo for issues that will prevent running on CPU:

### Common patches needed

1. **CUDA hardcoding**: `model.cuda()`, `.to('cuda')`, `device = 'cuda'`
   - Patch: Replace with `device = 'cuda' if torch.cuda.is_available() else 'cpu'`
   - Or: Add `--device cpu` argument if not present

2. **GPU-only operations**: `apex.amp`, `torch.cuda.amp`, NCCL init
   - Patch: Wrap in `if torch.cuda.is_available()` or remove

3. **Hardcoded paths**: `/data/datasets/`, `/home/user/`, absolute paths
   - Patch: Make paths relative or configurable

4. **Missing `if __name__ == '__main__'`**: Distributed training launchers need this
   - Patch: Add the guard

5. **Distributed training assumptions**: `torch.distributed.init_process_group` called unconditionally
   - Patch: Skip or mock when `WORLD_SIZE` is 1

6. **Hardcoded batch sizes that cause OOM on CPU**: batch_size * seq_len * d_model > available RAM
   - Patch: Override via config, not code change

7. **Dataset auto-download that hangs or requires auth**
   - Patch: Document manual download steps

For each patch, specify:
- Which file and line(s)
- What to change
- Why it's needed
- Whether it affects numerical results (it shouldn't)

## Output Format

### plan.json

```json
{
  "paper_id": "<from requirements>",
  "repo_analysis": {
    "train_script": "train.py",
    "config_system": "argparse",
    "model_definition": "model.py::TransformerModel",
    "data_loader": "data.py::get_dataset",
    "eval_script": "eval.py",
    "framework": "pytorch",
    "python_version": ">=3.8",
    "key_dependencies": ["torch>=1.12", "transformers>=4.20"]
  },
  "hyperparameter_map": {
    "<paper_param>": {
      "repo_param": "<flag or config key>",
      "paper_value": "<value from paper>",
      "how_to_set": "<exact CLI fragment>"
    }
  },
  "faithful": {
    "train_command": "python train.py --lr 3e-4 --batch_size 512 ...",
    "estimated_time": "48 GPU-hours on A100",
    "hardware_required": "8x A100 80GB"
  },
  "scaled": {
    "train_command": "python train.py --lr 3e-4 --batch_size 8 --max_steps 500 ...",
    "train_args": {
      "--lr": "3e-4",
      "--batch_size": "8",
      "--max_steps": "500",
      "--data_fraction": "0.01"
    },
    "scaled_config": {
      "n_layers": 2,
      "d_model": 128,
      "n_heads": 2,
      "max_seq_len": 128,
      "batch_size": 8,
      "max_steps": 500,
      "data_fraction": 0.01
    },
    "scaling_cuts_applied": [
      {
        "parameter": "data_fraction",
        "original": "1.0 (full dataset)",
        "scaled": "0.01",
        "rationale": "1% of data preserves training dynamics, reduces data load time",
        "claims_preserved": ["training stability", "loss decrease direction"],
        "claims_compromised": ["absolute perplexity value"]
      }
    ],
    "estimated_time": "15 minutes on CPU",
    "estimated_memory": "4GB"
  },
  "smoke_config": {
    "train_command": "python train.py --lr 3e-4 --batch_size 2 --max_steps 10 ...",
    "timeout_seconds": 60,
    "success_criteria": "exit code 0 and loss printed to stdout"
  },
  "metrics_to_capture": [
    {
      "name": "train_loss",
      "log_pattern": "loss[=: ]+([0-9.]+)",
      "capture_group": 1,
      "expected_behavior": "should decrease over training"
    },
    {
      "name": "perplexity",
      "log_pattern": "perplexity[=: ]+([0-9.]+)",
      "capture_group": 1,
      "expected_behavior": "should decrease; paper claims 29.1 on test set"
    }
  ],
  "expected_output_patterns": [
    {
      "pattern": "Training complete|Finished training|Done",
      "description": "Training completion marker",
      "required": true
    },
    {
      "pattern": "eval.*loss|val.*loss|test.*perplexity",
      "description": "Evaluation metrics in output",
      "required": false
    }
  ],
  "patches_needed": [
    {
      "file": "train.py",
      "description": "Replace hardcoded CUDA device with auto-detection",
      "reason": "Running on CPU, no GPU available",
      "affects_numerics": false,
      "diff": "--- a/train.py\n+++ b/train.py\n@@ -15,1 +15,1 @@\n-device = 'cuda'\n+device = 'cuda' if torch.cuda.is_available() else 'cpu'"
    }
  ]
}
```

### scaling_rationale.md

Write a clear document explaining each scaling decision. Structure:

```markdown
# Scaling Rationale for [Paper Name]

## Overview
[1 paragraph: what the paper does, what we're trying to verify, what constraints we face]

## Scaling Decisions

### 1. Dataset: [original] -> [scaled]
- **Cut**: [what exactly was reduced]
- **Rationale**: [why this is the safest cut]
- **Impact on claims**: [which claims survive, which don't]
- **Confidence**: [high/medium/low that relative results still hold]

### 2. Training duration: [original] -> [scaled]
...

## What This Scaled Run CAN Tell Us
- [bullet list of verifiable things]

## What This Scaled Run CANNOT Tell Us
- [bullet list of things that require full-scale training]

## Recommendation
[1 paragraph: is the scaled run sufficient to say anything useful about the paper's claims?]
```

## Critical Rules

1. **The plan must be executable.** Every command must be a real command that could be run. No placeholders like `<path>` or `TODO`. If you don't know a value, flag it in a `"warnings"` field.

2. **Preserve learning rate.** When scaling, do NOT change the learning rate unless batch size changes require it (linear scaling rule). Learning rate is the single most impactful hyperparameter.

3. **Batch size vs. learning rate coupling.** If you reduce batch size, consider whether to also reduce learning rate proportionally (linear scaling rule) or keep it the same (which is fine for small-scale sanity checks).

4. **Don't patch unless necessary.** If the repo already supports `--device cpu`, use it. Only patch when there's no other way.

5. **Check for existing small configs.** Many repos include `config/debug.yaml` or `--small` flags. Use them if they exist — the authors tested them.

6. **Metrics patterns must be tested.** The regex patterns in `metrics_to_capture` must match the repo's actual log format. Look at print/logging statements in the training script to determine the exact format.

7. **Environment reproducibility.** Check `requirements.txt`, `setup.py`, `environment.yml` for pinned versions. Note any unpinned dependencies that could cause issues.
