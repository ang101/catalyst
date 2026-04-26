# Reproduction Report: Sentence-BERT (1908.10084)

**Paper**: 1908.10084
**Method**: Sentence-BERT (SBERT)
**Status**: partial_success
**Date**: 2026-04-26

## Core Claim

SBERT fine-tunes BERT with siamese/triplet network structures to produce semantically meaningful sentence embeddings. The core claim is that SBERT embeddings, compared via cosine similarity, achieve state-of-the-art performance on Semantic Textual Similarity benchmarks, with 77.03 Spearman correlation on STSb using BERT-base with NLI training.

## Reproduction Strategy

**Strategy A (evaluation-only)** was selected. The `sentence-transformers` library on HuggingFace provides the pre-trained `bert-base-nli-mean-tokens` checkpoint. This is a non-generative embedding task (cosine similarity on fixed-size vectors), so the non-generative exception in the eval constraints permitted running the full test set on CPU.

## Results Comparison

| Dataset | Paper Claimed (Spearman x100) | Reproduced (Spearman x100) | Delta | Status |
|---------|-------------------------------|----------------------------|-------|--------|
| STS12 | 70.97 | 70.97 | 0.00 | Exact match |
| STS13 | 76.53 | 76.53 | 0.00 | Exact match |
| STS14 | 73.19 | 73.19 | 0.00 | Exact match |
| STS15 | 79.09 | 79.09 | 0.00 | Exact match |
| STS16 | 74.30 | 74.30 | 0.00 | Exact match |
| **STSb** | **77.03** | **76.99** | **-0.04** | **Within noise** |
| SICK-R | 72.91 | — | — | Timed out |
| **Avg (7 datasets)** | **74.89** | **~75.18 (6/7)** | — | **Incomplete** |

## Assessment: Partial Success — Main Claim Reproduced

The paper's primary claim (77.03 Spearman on STSb) is reproduced at 76.99 — a 0.04 point difference that is within random seed and library version noise. Five of the six completed datasets match the paper's reported values exactly (to two decimal places). STSb shows a 0.04 point deviation. SICK-R evaluation was in progress when the claude_code timeout (1800s) was reached.

### Verdict per Main Claim

1. **STSb Spearman 77.03**: REPRODUCED (76.99, delta -0.04). The released checkpoint produces the claimed result.
2. **7-dataset average 74.89**: INCOMPLETE (6/7 datasets completed, SICK-R missing). The 6-dataset average is 75.18, consistent with the paper.
3. **"Outperforms InferSent by 11.7 points"**: NOT TESTED (would require running InferSent baseline).

### Why Exact Match on 5/6 Datasets

The evaluation is deterministic: same model weights + same tokenizer + same input data + cosine similarity = same output. The 0.04 deviation on STSb is likely due to a minor difference in the `sentence-transformers` library version (the paper used an early version; HuggingFace serves the latest).

## Execution Details

- **Total eval wall-clock**: ~24 minutes for 6 datasets on CPU
- **Model size**: 110M parameters (BERT-base), ~440MB in FP32
- **Peak memory**: ~2GB
- **Per-dataset time**: 2-5 minutes (encoding) + <1 second (cosine similarity + Spearman)
- **Datasets evaluated**: STS12 (3750 pairs), STS13 (1500 pairs), STS14 (3750 pairs), STS15 (3000 pairs), STS16 (1186 pairs), STSb (1379 pairs)
- **No patches needed**: The `sentence-transformers` library natively supports CPU execution
- **No training**: Pure evaluation from released checkpoint

## What This Confirms

- The released SBERT-NLI-base checkpoint produces the claimed embeddings
- Cosine similarity evaluation on STS benchmarks matches paper results
- The `sentence-transformers` library correctly loads and runs the model
- CPU evaluation of a 110M parameter embedding model is feasible in ~25 minutes

## What This Does Not Test

- Whether training BERT-base on SNLI+MultiNLI with the paper's recipe produces this checkpoint
- Whether the training dynamics (loss, convergence) match
- Whether SBERT-NLI-large achieves its claimed results
- Comparison against baselines (InferSent, USE, avg GloVe)

## Limitations

- SICK-R dataset evaluation did not complete (claude_code timeout at 1800s)
- Library version may differ from the paper's original implementation
- Only BERT-base variant tested (not BERT-large)
