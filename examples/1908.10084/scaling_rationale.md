# Scaling Rationale for Sentence-BERT (1908.10084)

## Strategy Selection: A — Evaluation-only

**Reasoning:** The paper's released artifacts include two HuggingFace checkpoints (`sentence-transformers/bert-base-nli-mean-tokens` and `sentence-transformers/bert-large-nli-mean-tokens`) that directly support the main claim (Table 1: unsupervised STS via cosine similarity). These are fully fine-tuned task-specific checkpoints, not base models requiring additional training. The paper's main claim is about model performance at inference (Spearman correlation on STS benchmarks). Strategy A applies.

## Overview

Sentence-BERT (SBERT) fine-tunes BERT with siamese/triplet network structures to produce fixed-size sentence embeddings. The core claim is that SBERT embeddings, compared via cosine similarity, outperform prior sentence embedding methods (InferSent, USE) on Semantic Textual Similarity (STS) benchmarks by 11.7 and 5.5 Spearman correlation points respectively. Since pre-trained checkpoints are available on HuggingFace, we reproduce the evaluation only: load the checkpoint, encode sentence pairs, compute cosine similarity, and measure Spearman correlation against gold labels.

**Constraint profile:** This is a non-generative evaluation task. The model produces fixed-size embeddings (768-d for BERT-base) via a single forward pass per sentence. Per-example cost is sub-second on CPU. The non-generative exception in the eval constraints permits using the full test set.

## Scaling Decisions

### 1. Datasets: 7 STS datasets -> 1 (STSb test)

- **Cut (scaled track only):** Evaluate on STSbenchmark test set (1,379 pairs) instead of all 7 datasets (STS12-16, STSb, SICK-R, ~8000 pairs total)
- **Rationale:** STSb is the most widely-cited STS benchmark and the paper reports per-dataset scores. Matching STSb alone is strong evidence that the checkpoint is correct. The faithful track runs all 7 datasets.
- **Impact on claims:** The scaled track can verify the STSb-specific claim (77.03 Spearman). It cannot compute the 7-dataset average (74.89). The faithful track verifies both.
- **Confidence:** HIGH — if STSb matches, the other datasets will almost certainly match too since they use the same model and evaluation procedure.

### 2. Model: No reduction

- **Cut:** None. BERT-base (110M parameters) is used as-is.
- **Rationale:** This is evaluation-only. BERT-base fits comfortably in CPU memory (~440MB in FP32). Reducing model size would invalidate the reproduction since we'd be evaluating a different model than the paper's checkpoint.

### 3. Batch size: 16 (unchanged)

- **Cut:** None. The paper uses batch_size=16 for training, and the eval example uses the same default.
- **Rationale:** Batch size 16 with BERT-base is ~50MB per batch on CPU — well within 16GB RAM. No need to reduce.

### 4. Precision: FP32 (unchanged)

- **Cut:** None. Using the default FP32 precision.
- **Rationale:** The original evaluation was done in FP32. Using lower precision could change correlation values.

## What This Evaluation CAN Tell Us

- Whether the released SBERT-NLI-base checkpoint reproduces the claimed 77.03 Spearman correlation on STSb test (scaled track)
- Whether the checkpoint reproduces all 7 per-dataset Spearman scores from Table 1 (faithful track)
- Whether the checkpoint produces 768-dimensional sentence embeddings with expected cosine similarity behavior
- Whether the sentence-transformers library correctly loads and runs the legacy checkpoint

## What This Evaluation CANNOT Tell Us

- Whether training from scratch on SNLI+MultiNLI for 1 epoch with the paper's hyperparameters produces equivalent results
- Whether the training dynamics (loss curves, convergence) match the paper's description
- Whether the ablation results (pooling strategies, concatenation modes) hold
- Whether SBERT-NLI-large achieves the claimed 76.55 average (we only evaluate base in the scaled track)

## Recommendation

The scaled evaluation run is fully sufficient to verify the paper's main quantitative claim for SBERT-NLI-base on STSb. Since this is a non-generative embedding task with sub-second per-example cost, even the faithful track (all 7 datasets) is CPU-feasible within 10-15 minutes. We recommend running the faithful track as the primary reproduction, with the scaled track serving as a quick sanity check. No training, GPU, or scaling compromises are needed.
