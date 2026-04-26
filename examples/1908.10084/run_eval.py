#!/usr/bin/env python3
"""
Evaluation script for Sentence-BERT (1908.10084) reproduction.

Loads a pre-trained SBERT checkpoint and evaluates on STS benchmarks
using cosine similarity + Spearman correlation, matching Table 1 of the paper.

Usage:
  # Scaled track (STSb only):
  python3 run_eval.py --model sentence-transformers/bert-base-nli-mean-tokens --datasets STSb

  # Faithful track (all 7 datasets):
  python3 run_eval.py --model sentence-transformers/bert-base-nli-mean-tokens --datasets STS12 STS13 STS14 STS15 STS16 STSb SICK-R
"""

import argparse
import json
import logging
import sys
import time

import torch
from scipy.stats import spearmanr, pearsonr

logging.basicConfig(
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Limit torch threads for CPU efficiency
torch.set_num_threads(4)


def load_stsb(split="test"):
    """Load STSbenchmark from HuggingFace datasets."""
    from datasets import load_dataset
    ds = load_dataset("sentence-transformers/stsb", split=split)
    return ds["sentence1"], ds["sentence2"], ds["score"]


def load_sts_dataset(name, split="test"):
    """Load an STS dataset by name. Returns (sentences1, sentences2, scores)."""
    if name == "STSb":
        return load_stsb(split)
    else:
        # STS12-16 and SICK-R are available via mteb/stsbenchmark-sts or individual HF datasets
        # Try loading from the standard HuggingFace sources
        from datasets import load_dataset

        dataset_map = {
            "STS12": ("mteb/sts12-sts", "test"),
            "STS13": ("mteb/sts13-sts", "test"),
            "STS14": ("mteb/sts14-sts", "test"),
            "STS15": ("mteb/sts15-sts", "test"),
            "STS16": ("mteb/sts16-sts", "test"),
            "SICK-R": ("mteb/sickr-sts", "test"),
        }

        if name not in dataset_map:
            raise ValueError(f"Unknown dataset: {name}. Supported: {list(dataset_map.keys()) + ['STSb']}")

        hf_name, hf_split = dataset_map[name]
        ds = load_dataset(hf_name, split=hf_split)
        # MTEB STS datasets use score on 0-5 scale; normalize to 0-1
        scores = [s / 5.0 for s in ds["score"]]
        return ds["sentence1"], ds["sentence2"], scores


def evaluate_model_on_dataset(model, sentences1, sentences2, gold_scores, batch_size=16):
    """Encode sentences and compute Spearman/Pearson correlation with cosine similarity."""
    import numpy as np

    logger.info(f"Encoding {len(sentences1)} sentence pairs...")
    emb1 = model.encode(sentences1, batch_size=batch_size, show_progress_bar=True, convert_to_numpy=True)
    emb2 = model.encode(sentences2, batch_size=batch_size, show_progress_bar=True, convert_to_numpy=True)

    # Compute cosine similarity for each pair
    cos_sims = []
    for a, b in zip(emb1, emb2):
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        cos_sims.append(dot / norm if norm > 0 else 0.0)

    cos_sims = np.array(cos_sims)
    gold = np.array(gold_scores)

    pearson_val, _ = pearsonr(gold, cos_sims)
    spearman_val, _ = spearmanr(gold, cos_sims)

    return pearson_val, spearman_val


def main():
    parser = argparse.ArgumentParser(description="SBERT STS Evaluation")
    parser.add_argument("--model", type=str, default="sentence-transformers/bert-base-nli-mean-tokens",
                        help="HuggingFace model name or path")
    parser.add_argument("--datasets", nargs="+", default=["STSb"],
                        help="Datasets to evaluate on (STSb, STS12-16, SICK-R)")
    parser.add_argument("--batch_size", type=int, default=16, help="Encoding batch size")
    parser.add_argument("--output", type=str, default=None, help="Path to write results JSON")
    args = parser.parse_args()

    # Paper-reported values for SBERT-NLI-base (Table 1), Spearman x100
    paper_values = {
        "STS12": 70.97,
        "STS13": 76.53,
        "STS14": 73.19,
        "STS15": 79.09,
        "STS16": 74.30,
        "STSb": 77.03,
        "SICK-R": 72.91,
    }

    logger.info(f"Loading model: {args.model}")
    start = time.time()
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    load_time = time.time() - start
    logger.info(f"Model loaded in {load_time:.1f}s")

    results = {}
    total_start = time.time()

    for ds_name in args.datasets:
        logger.info(f"\n{'='*60}")
        logger.info(f"Evaluating on {ds_name}")
        logger.info(f"{'='*60}")

        s1, s2, scores = load_sts_dataset(ds_name)
        logger.info(f"Loaded {len(s1)} sentence pairs")

        ds_start = time.time()
        pearson_val, spearman_val = evaluate_model_on_dataset(model, s1, s2, scores, args.batch_size)
        ds_time = time.time() - ds_start

        spearman_x100 = spearman_val * 100
        pearson_x100 = pearson_val * 100

        logger.info(f"Cosine-Similarity:\tPearson: {pearson_val:.4f}\tSpearman: {spearman_val:.4f}")
        logger.info(f"Spearman x100: {spearman_x100:.2f}")

        if ds_name in paper_values:
            paper_val = paper_values[ds_name]
            diff = spearman_x100 - paper_val
            logger.info(f"Paper reports: {paper_val:.2f} | Reproduced: {spearman_x100:.2f} | Diff: {diff:+.2f}")

        results[ds_name] = {
            "pearson_cosine": round(pearson_val, 4),
            "spearman_cosine": round(spearman_val, 4),
            "spearman_x100": round(spearman_x100, 2),
            "paper_value_x100": paper_values.get(ds_name),
            "num_pairs": len(s1),
            "eval_time_seconds": round(ds_time, 1),
        }

    total_time = time.time() - total_start

    # Compute average if multiple datasets
    if len(results) > 1:
        avg_spearman = sum(r["spearman_x100"] for r in results.values()) / len(results)
        logger.info(f"\n{'='*60}")
        logger.info(f"Average Spearman x100 across {len(results)} datasets: {avg_spearman:.2f}")
        if len(results) == 7:
            logger.info(f"Paper reports average: 74.89")
        results["average"] = {"spearman_x100": round(avg_spearman, 2)}

    logger.info(f"\nTotal evaluation time: {total_time:.1f}s")

    # Write results
    output_path = args.output or f"papers/1908.10084/eval_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "model": args.model,
            "datasets_evaluated": args.datasets,
            "results": results,
            "total_time_seconds": round(total_time, 1),
        }, f, indent=2)
    logger.info(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
