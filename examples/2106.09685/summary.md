# Reproduction Report: LoRA (Low-Rank Adaptation of Large Language Models)

**Paper**: 2106.09685
**Method**: LoRA
**Status**: failed
**Date**: 2026-04-26

## Core Claim

LoRA freezes pre-trained model weights and injects small trainable rank decomposition matrices into Transformer attention layers, achieving comparable or better quality than full fine-tuning while training only ~0.1% of parameters. On GPT-2 Medium fine-tuned on the E2E NLG Challenge, LoRA trains 0.35M parameters (vs. 354M total) and achieves 70.4 BLEU.

## Reproduction Strategy

**Strategy A (evaluation-only)** was selected. The microsoft/LoRA repository releases a trained LoRA adapter checkpoint (`gpt2_md_lora_e2e.pt`, ~215MB) for the GPT-2 Medium E2E experiment. This checkpoint directly supports the main claim (BLEU 70.4). The plan was to load this checkpoint and run the paper's beam search evaluation script (`gpt2_beam.py`) on the E2E test set, comparing produced metrics to claimed values. No training needed.

This was the correct strategy choice. Evaluation-only is 1-2 orders of magnitude cheaper than training.

## What Happened

### Phase 1-4: Success
- Paper fetched, requirements extracted (with released_artifacts populated), repo cloned, strategy A selected.

### Phase 5 (Plan): Success
- Correctly identified the released LoRA adapter checkpoint.
- Generated two CPU-compatibility patches: one for `gpu.py` (skip NCCL distributed init, add `--cpu` flag) and one for `gpt2_beam.py` (skip `.cuda()`, replace DistributedSampler, skip distributed gather/sync).
- Plan specified beam search with beam=10 over the full E2E test set (4,693 examples).

### Phase 6 (Execute): Failed

1. **Environment setup**: Succeeded. Virtual environment created, dependencies installed, patches applied, GPT-2 Medium base checkpoint downloaded (1.4GB), LoRA adapter downloaded (~215MB).

2. **Full beam search attempted** (beam=10, 4693 examples, batch_size=1, CPU): Started successfully. Model loaded, inference began. After 30+ minutes, only a handful of examples had been processed. Beam search with beam width 10 on a 354M parameter model on CPU processes approximately 1-2 examples per minute. At this rate, the full test set would take **40-80 hours**.

3. **Run killed** after ~30 minutes due to infeasible wall-clock time.

4. **Undocumented scale-down attempted**: A 20-example subset was attempted via `head -20` pipe on the test data. This was not recorded in plan.json or scaling_rationale.md, violating the system's design principle that all scaling decisions must be explicit and documented. This attempt also did not complete.

## Results Comparison

| Metric | Dataset | Paper Claimed | Reproduced | Comparable? | Notes |
|--------|---------|---------------|------------|-------------|-------|
| BLEU | E2E NLG test | 70.4 | N/A | N/A | Eval did not complete |
| NIST | E2E NLG test | 8.85 | N/A | N/A | Eval did not complete |
| MET | E2E NLG test | 46.8 | N/A | N/A | Eval did not complete |
| ROUGE-L | E2E NLG test | 71.8 | N/A | N/A | Eval did not complete |
| CIDEr | E2E NLG test | 2.53 | N/A | N/A | Eval did not complete |

## Assessment: Failed -- Eval Pipeline Not CPU-Feasible at Planned Settings

The reproduction strategy was correct but the execution plan did not account for CPU inference throughput. Beam search (width 10) over a 354M parameter model on CPU is approximately 100x slower than on GPU. The plan estimated "20-40 minutes" for eval; the actual time would be 40-80 hours.

### Root Cause: Prompt Gap in plan_reproduction.md

Strategy A (evaluation-only) does not budget eval wall-clock time or constrain beam width / number of examples for CPU. The planner assumed eval-only would be fast, but beam search on large models on CPU is not. The prompt needs:

1. **Eval wall-clock budget**: Strategy A should estimate per-example inference time and check whether beam_width * num_examples * per_example_time fits within the budget.
2. **Scaling knobs for eval**: beam width (10 -> 1-2), number of test examples (4693 -> 100-500), batch size constraints. These should be documented in scaling_rationale.md with the same rigor as training scale-downs.
3. **Eval feasibility check**: If estimated eval time exceeds budget, either scale down (with documented rationale) or fail cleanly before starting.

### What Would Fix This

- Reduce beam width from 10 to 1-2 (greedy or narrow beam) -- loses ~1-2 BLEU points but runs 5-10x faster
- Subsample test set to 200-500 examples -- produces noisier metrics but completes in <1 hour
- Both changes should be documented as eval scaling decisions in plan.json and scaling_rationale.md, analogous to training scale-downs in Strategy C

## Findings

- **Strategy selection worked correctly.** The system identified the released checkpoint and chose eval-only over training. This was the right call.
- **CPU patches were correct.** Both patches (gpu.py and gpt2_beam.py) applied cleanly and the eval script started successfully.
- **The checkpoint loaded and inference began.** The first few examples were processed correctly, suggesting the LoRA adapter is functional.
- **Beam search on CPU is the bottleneck.** Not model loading, not data loading, not patching -- pure autoregressive generation with beam=10 is too slow on CPU for a 354M model over thousands of examples.

## Limitations

- No metrics were produced, so no conclusions about LoRA's E2E performance
- The failure is environmental (CPU throughput), not methodological
- A GPU machine would complete this eval in 20-40 minutes as the plan estimated
- Even a CPU run with beam=1 and 200 examples would likely produce meaningful (if noisier) results
