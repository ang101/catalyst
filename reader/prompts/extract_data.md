You are extracting structured quantitative data from a research paper for an interactive reader.

Read the paper text below. Output a JSON object matching this schema:

```json
{
  "paper": {
    "title": "string",
    "authors": ["string"],
    "year": int,
    "arxiv_id": "string"
  },
  "main_claims": ["string — each a falsifiable 1-sentence paraphrase, not a quote"],
  "variables": [
    {
      "name": "short_name (e.g. 'rank', 'model_size', 'weight_type')",
      "label": "Human-readable label (e.g. 'LoRA Rank r')",
      "type": "discrete | continuous | categorical",
      "values": ["list of values tested in the paper"],
      "unit": "string or null"
    }
  ],
  "metrics": [
    {
      "name": "short_name (e.g. 'bleu', 'accuracy', 'spearman')",
      "label": "Human-readable (e.g. 'BLEU Score')",
      "higher_is_better": true/false
    }
  ],
  "data_points": [
    {
      "variable_values": {"var_name": "value", ...},
      "metric_values": {"metric_name": number, ...},
      "source_cell": "Table X, row Y, column Z",
      "context": "e.g. 'GPT-3 175B on WikiSQL'"
    }
  ],
  "context_descriptors": {
    "grouping_variable_name": ["value1", "value2"]
  }
}
```

## Rules

1. **Every data_point MUST have a non-empty source_cell.** The source_cell must identify the specific table and location (row/column) where the value appears. If you cannot locate the exact source in the paper, EXCLUDE the data point. Never guess a citation.

2. **Variables are parameters the paper varies.** If the paper tests rank r at {1, 2, 4, 8, 64}, then "rank" is a variable with those values. If the paper only ever uses one value of a parameter, it's NOT a variable — it's a constant (mention it in context).

3. **Metrics are outcomes the paper measures.** Accuracy, BLEU, perplexity, loss, Spearman correlation, etc.

4. **Context descriptors group data points.** If the paper tests multiple models (GPT-2, GPT-3) on multiple tasks (WikiSQL, MNLI), then "model" and "task" are context descriptors. Data points within a context share the same model+task but vary on the variables.

5. **Main claims must be paraphrased, not quoted.** Each must be falsifiable in one sentence. "LoRA matches full fine-tuning on GLUE" is good. "We propose LoRA" is bad (not falsifiable).

6. **Extract ALL quantitative data points with clear citations.** Include main results tables, ablation tables, and appendix tables. Do not limit yourself to the "most important" results — capture everything that has a clear table citation.

7. **For multi-metric tables** (e.g., a row reports BLEU, NIST, ROUGE-L simultaneously), create ONE data_point with multiple entries in metric_values.

8. **Handle baselines:** Include baseline methods (Full FT, Adapter, etc.) as data points. Use a variable like "method" with values ["LoRA", "Full FT", "Adapter", etc.] to distinguish them.

9. **Numeric precision:** Use exact values from the paper. If the paper says "87.5±0.3", record 87.5 (the mean). Note the variance in a "notes" field if needed.

10. If the paper has fewer than 5 data points with clear citations, output the JSON with an empty data_points array and add a `"reason": "insufficient extractable data"` field.

Output JSON only. No markdown fences. No prose before or after the JSON.
