# Scaling Rationale for LoRA: Low-Rank Adaptation of Large Language Models (2106.09685)

## Strategy Selection: Evaluation-Only (Strategy A)

**Decision:** Strategy A (evaluation-only) was selected because `released_artifacts.checkpoints` contains a GPT-2 LoRA checkpoint with `supports_main_claim: true`. This checkpoint provides trained LoRA adapter weights for GPT-2 Medium on the E2E NLG Challenge, which directly supports the paper's main claim of BLEU 70.4 on E2E (Table 3).

**Why not train?** The authors released the exact checkpoint that produced their reported numbers. Re-training would introduce unnecessary variance (different random seeds, potential environment differences) and cost orders of magnitude more compute, all to produce a checkpoint that already exists. Evaluation-only is strictly superior for claim verification when the artifact is available.

## Overview

The LoRA paper claims that injecting trainable low-rank decomposition matrices (rank r=4) into GPT-2 Medium's W_q and W_v attention matrices achieves BLEU 70.4 on the E2E NLG Challenge test set, matching or exceeding full fine-tuning while using only 0.35M trainable parameters (vs. 354.92M). The released checkpoint at `gpt2_md_lora_e2e.pt` (1.5 MB) contains exactly these adapter weights.

Our reproduction loads this checkpoint, runs beam search decoding on the E2E test set, and computes the standard E2E metrics (BLEU, NIST, METEOR, ROUGE-L, CIDEr).

## Claim Preservation Analysis

### What Evaluation-Only CAN Tell Us
- Whether the released checkpoint actually produces the claimed BLEU 70.4 on E2E test
- Whether all five reported metrics (BLEU, NIST, MET, ROUGE-L, CIDEr) match Table 3
- Whether the LoRA adapter integration code works correctly (model loads, generates coherent text)
- Whether the evaluation pipeline is reproducible end-to-end

### What Evaluation-Only CANNOT Tell Us
- Whether training from scratch with the reported hyperparameters converges to the same checkpoint
- Whether the training dynamics (loss curves, convergence speed) match what the paper describes
- Whether 5 epochs with lr=2e-4 and AdamW is truly the optimal recipe
- Whether different random seeds produce the claimed standard deviation (0.1 for BLEU)

### Claim Preservation Confidence: HIGH

Evaluation-only preserves the main claim with the highest possible fidelity. The released checkpoint is a deterministic artifact: given the same model weights and the same test data, beam search decoding is deterministic (no sampling randomness). Therefore, if the checkpoint is authentic, we should reproduce the exact claimed metrics.

This is strictly better than scaled training, which would compromise absolute metric values and could only verify directional behavior (e.g., "LoRA loss decreases, code runs"). Eval-only either confirms or refutes the specific numbers in Table 3.

## Compute Requirements

| Resource | Requirement |
|----------|-------------|
| Model size | 354.92M parameters (~1.4 GB FP32 for base + 1.5 MB LoRA adapter) |
| Peak RAM | ~3-4 GB |
| GPU required | No (CPU-compatible with patches) |
| Estimated time (CPU) | 20-40 minutes for beam search, <1 minute for decoding and metric computation |
| Estimated time (GPU) | 2-5 minutes total |

## Required Patches

Two patches are needed for CPU execution:

1. **gpu.py**: The `parse_gpu()` function assumes CUDA on all code paths and calls `dist.init_process_group(backend='nccl')`. Patch adds `--cpu` flag that sets `device=cpu`, `world_size=1`, and skips distributed init entirely.

2. **gpt2_beam.py**: Three CUDA-dependent lines: (a) `lm_net = lm_net.cuda()` at line 386, (b) `DistributedSampler` at line 359, (c) `distributed_gather`/`distributed_sync` calls at lines 320-323. Patch conditionalizes all three on CUDA availability.

Neither patch affects numerical results. The model weights, beam search algorithm, and decoding logic are identical on CPU and GPU (modulo floating-point precision differences, which are negligible for FP32 inference).

## Recommendation

The evaluation-only approach is the correct strategy for this paper. The released GPT-2 Medium LoRA checkpoint directly supports the main claim. Running evaluation will either confirm BLEU 70.4 (validating the claim) or reveal a discrepancy (raising questions about the artifact). This is a definitive test that no amount of scaled training could improve upon.

If evaluation succeeds, the reproduction should be considered strong evidence for the paper's E2E NLG results. If training-from-scratch reproduction is also desired (to validate the training recipe), that can be pursued separately as a second phase.
