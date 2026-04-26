---
inputs:
  - name: paper_md
    type: string
    description: Full paper text as markdown
  - name: metadata_json
    type: string
    description: Paper metadata JSON
outputs:
  - name: requirements_json
    type: json
    description: Structured requirements matching requirements.schema.json
---

# Extract Reproduction Requirements from Paper

You are extracting structured experimental requirements from an ML/AI research paper. Your output will be used to automatically reproduce this paper's results. Accuracy is critical: a wrong hyperparameter wastes hours of compute; a missing one causes silent divergence.

## Input

You are given:
1. **paper_md**: The full paper text converted to markdown.
2. **metadata_json**: Bibliographic metadata (title, authors, arXiv ID, etc.).

## Output

Produce a single JSON object conforming to `requirements.schema.json`. Nothing else — no markdown wrapping, no commentary outside the JSON.

## Extraction Protocol

### Step 1: Identify the core claim

Read the abstract and conclusion. The core claim is the central empirical argument, not a description of the method. It must be falsifiable.

**Good core claim**: "Mamba achieves the same perplexity as a Transformer++ of equal size on The Pile while being 5x faster at inference on sequences of length 8192."

**Bad core claim**: "We propose Mamba, a selective state space model." (This is a description, not a claim.)

**Bad core claim**: "Mamba is better than Transformers." (Too vague; on what metric? On what data? At what scale?)

### Step 2: Extract datasets

Search the entire paper for dataset mentions. Check:
- Section 3/4 (Experiments/Setup) — primary datasets
- Appendices — additional datasets, preprocessing details
- Tables and figures — datasets may only appear in table headers
- Related work — sometimes baselines use different datasets

For each dataset, record the name exactly as the paper uses it. For preprocessing, look for:
- Tokenization (BPE, SentencePiece, WordPiece; vocab size)
- Sequence length / truncation
- Filtering or deduplication
- Train/val/test split details
- Data augmentation

### Step 3: Extract model architecture

Look for architecture details in:
- Section 2/3 (Method) — primary architecture description
- Tables listing model configurations (often Table 1)
- Appendices — full hyperparameter tables
- Code listings in the paper

Extract every stated structural parameter. Common ones to look for:

| Parameter | Where to look |
|-----------|--------------|
| n_layers | Method section, config table |
| n_heads | Method section, config table |
| d_model / hidden_size | Method section, config table |
| d_ff / intermediate_size | Method section (often 4x d_model but check) |
| dropout | Often in appendix or "implementation details" |
| activation | Method section (GELU, SiLU, ReLU) |
| normalization | Method section (LayerNorm, RMSNorm, pre-norm vs post-norm) |
| positional encoding | Method section (sinusoidal, RoPE, ALiBi, learned) |
| vocab_size | Tokenizer section or appendix |
| max_seq_len | Training details or config table |
| tie_embeddings | Often only in appendix or code |

### Step 4: Extract training configuration

This is where papers are most inconsistent. Search aggressively:

1. **Main text "Implementation Details" or "Training Details"** — usually has optimizer, lr, batch size
2. **Appendix** — often has the FULL config that the main text omits. CHECK THE APPENDIX.
3. **Footnotes** — sometimes critical details like "we use gradient clipping of 1.0" appear only in footnotes
4. **Figure captions** — learning rate schedules sometimes only appear in lr-curve figure captions
5. **"We follow [X]"** — if the paper says "we follow the training recipe of [Y]", note this but still try to find explicit values

Specific parameters that are commonly buried:

| Parameter | Common hiding spots |
|-----------|-------------------|
| learning_rate | Main text, appendix table |
| lr_schedule | Appendix, figure captions. Look for: warmup steps, decay type (cosine, linear, constant), min lr |
| weight_decay | Appendix. Often 0.1 for AdamW but verify. |
| warmup | Appendix. Count of steps or fraction of training. |
| beta1, beta2 | Appendix. Defaults are 0.9/0.999 but many papers use 0.9/0.95. |
| gradient_clipping | Appendix or footnotes. |
| dropout | Appendix or model description. Some papers use 0.0 and state it explicitly. |
| batch_size | Be careful: is this per-GPU or effective? Look for gradient accumulation. |
| mixed_precision | Training details, often bf16 or fp16. |

### Step 5: Extract metrics

Go through every table and figure in the results section. For each reported number:
- Record the exact metric name as used in the paper
- Record the exact numerical value (not rounded)
- Record which dataset and split it was measured on
- Record the table/figure reference
- Record conditions (zero-shot, few-shot, fine-tuned, ensemble, etc.)
- Determine if higher is better

**Crucially, mark `is_main_claim`:** Read the abstract and introduction. Identify the 1-5 metrics that the paper most prominently claims as its main results — the numbers the paper's argument rests on. Mark ONLY these as `"is_main_claim": true`. All other metrics (ablations, supplementary experiments, additional model sizes, baselines) get `"is_main_claim": false`.

The main claim metrics should be the smallest set of numbers that, if reproduced, would validate the paper's core argument. If the abstract says "we achieve X on dataset Y", that metric is a main claim. If a metric only appears in an appendix table, it is not.

**Good metric extraction**:
```json
{
  "name": "perplexity",
  "claimed_value": 29.1,
  "dataset": "WikiText-103 test",
  "higher_is_better": false,
  "table_or_figure": "Table 2 row 'Ours (125M)'",
  "conditions": "single model, no ensembling",
  "is_main_claim": true
}
```

**Bad metric extraction**:
```json
{
  "name": "performance",
  "claimed_value": "good",
  "dataset": "WikiText",
  "higher_is_better": true,
  "is_main_claim": true
}
```

### Step 6: Extract ablations

Ablation studies tell us which components matter most. For each ablation:
- What was varied?
- What was the conclusion? (Which setting won?)
- How sensitive was the result to the change?

This information is used later to decide which components can be safely scaled down.

### Step 7: Identify released artifacts

Search aggressively for pre-trained checkpoints, released datasets, and evaluation scripts. These determine whether evaluation-only reproduction is possible (1-2 orders of magnitude cheaper than training).

**Where to look for checkpoints:**
- Paper text: "we release our trained models at...", "checkpoints available at...", "model zoo"
- Repo README: links to HuggingFace Hub, Google Drive, S3 buckets, Zenodo
- Repo directories: `pretrained/`, `checkpoints/`, `weights/`, `models/`, `release/`
- Repo scripts: `download_checkpoints.sh`, `download_pretrained.sh`, `download.py`
- HuggingFace: search for `huggingface.co/` URLs in paper or README
- metadata_json: check for model/checkpoint URLs

**For each checkpoint, determine:**
- `supports_main_claim`: True if loading this checkpoint and running evaluation directly produces one of the `is_main_claim` metrics. For example, a trained LoRA adapter for GPT-2 Medium on E2E supports the E2E BLEU claim. A base GPT-2 checkpoint without finetuning does NOT support it.

**Where to look for eval scripts:**
- Repo files: `eval.py`, `evaluate.py`, `test.py`, `generate.py`, `beam_*.py`, `decode.py`
- Repo README: "To evaluate..." or "To reproduce results..." sections
- Shell scripts: `eval.sh`, `run_eval.sh`

If nothing is released, set all arrays to empty `[]`.

### Step 8: Assess compute feasibility

Produce `compute_feasibility_note` as 1-2 sentences. Identify the **cheapest reproduction strategy** that tests the paper's main claim:

- If `released_artifacts.checkpoints` contains a checkpoint with `supports_main_claim: true`, then **evaluation-only** is likely CPU-feasible regardless of model size (inference is much cheaper than training). State this strategy and estimate memory (model size in FP32) and time (~minutes for eval vs. hours for training).
- If only a base checkpoint exists (no task-specific one), finetuning from the base is the next cheapest.
- If no checkpoints exist, scaled from-scratch training is the only option.

Only mark a paper infeasible if even evaluation-only requires GPU/multi-machine resources (e.g., the model doesn't fit in 16GB RAM even for inference, or evaluation requires running thousands of examples through a 70B model).

### Step 9: Find code URL and reproducibility notes

Check these locations for code URLs:
- Abstract ("Code available at...")
- Footnote on first page
- Section titled "Code Availability" or "Reproducibility"
- metadata_json fields (often has a "code" or "repo" URL)
- Paper header/footer

For reproducibility notes, look for:
- "Reproducibility Statement" or "Reproducibility Checklist" (NeurIPS, ICLR papers)
- Mentions of random seeds
- Mentions of variance across runs
- Statements about what is/isn't released

## Critical Rules

1. **If a value is not stated in the paper, use null.** Do not guess, do not use "typical" values, do not infer from other papers. A null tells the downstream system to look it up in code or use a safe default. A wrong value causes silent failure.

2. **Distinguish stated from inferred.** If the paper says "we use the GPT-2 architecture" without specifying n_layers, put the architecture description as "GPT-2 architecture (see reference for details)" and leave n_layers out of key_hyperparameters. Do not fill in 12 because you know GPT-2 has 12 layers.

3. **Use exact numbers.** If the paper says "3e-4", record 0.0003. If it says "~100k steps", record "~100k steps" as a string. Do not round or approximate.

4. **Batch size: effective, not per-GPU.** If the paper says "batch size 32 per GPU on 8 GPUs with 4 gradient accumulation steps", the effective batch size is 32 * 8 * 4 = 1024. Record 1024.

5. **Multiple model sizes?** If the paper tests several model sizes (e.g. 125M, 350M, 1.3B), extract the PRIMARY model — the one the core claim is about. If the core claim spans all sizes, extract the smallest one (most likely to be reproducible) and note the others in reproducibility_notes.

6. **Metrics: be exhaustive, but prioritize.** Extract every numerical result from every table — but mark only the 1-5 metrics that the abstract/introduction most prominently claims as `is_main_claim: true`. The downstream system uses `is_main_claim` to decide what to actually reproduce. Everything else is context.

7. **Read the entire paper including appendices.** The most critical reproducibility details are almost always in the appendix. Skipping it is the most common source of extraction failure.

## Output Format

Return exactly one JSON object. No markdown code fences. No explanation before or after. The JSON must validate against requirements.schema.json.
