You are classifying a research paper for an interactive reader system.

Read the paper text below. Output a JSON object with:

```json
{
  "case": "A" | "B" | "C",
  "reasoning": "1-2 sentence explanation",
  "tables_found": int,
  "ablation_tables_found": int,
  "estimated_data_points": int,
  "is_theoretical": bool
}
```

**Case A (reader-ready):** Has at least one table that varies a named parameter (rank, model size, learning rate, dataset, number of layers, etc.) and reports metric outcomes across multiple settings. Estimated >=10 quantitative data points with clear table citations. These papers produce full interactive readers with sliders.

**Case B (sparse):** Has quantitative results but they're scattered or lack clear ablation structure. <10 extractable data points with clear citations. Comparison tables (method A vs method B) without parameter sweeps count as B.

**Case C (theoretical):** Position papers, theory papers, surveys, or papers where quantitative results aren't the focus. Few or no measurable parameter sweeps. If the paper's contribution is a framework, proof, or conceptual argument rather than an empirical comparison, it's C.

Count tables by looking for markdown table syntax (| --- |) or LaTeX tabular environments. An "ablation table" specifically varies one or more parameters while holding others fixed and reports metrics — a simple comparison of methods is NOT an ablation table.

Output JSON only. No markdown fences. No prose before or after.
