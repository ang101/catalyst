You are estimating a metric value at a parameter combination NOT reported in a research paper.

You will be given:
- The paper's main claims
- All [PAPER]-verified data points (with their source citations)
- A target parameter combination that the paper does NOT report

Estimate the metric value at the target combination.

## Rules

1. Output JSON: `{"value": number|null, "confidence": float|null, "reasoning": "string"}`

2. Confidence scale:
   - 0.0-0.2: Wild guess, very far from any reported data
   - 0.3-0.5: Educated guess based on general trends
   - 0.6-0.8: Reasonable estimate, target is near reported points and trends are clear
   - 0.9-1.0: NEVER use this range. Only [PAPER] values deserve >0.8 confidence.

3. Confidence < 0.3 if the target is far from any reported point OR the paper shows non-monotonic behavior in the relevant region.

4. Confidence > 0.6 ONLY if the target is bracketed by reported points AND the paper shows clear monotonic trends in that region.

5. Provide a one-sentence reasoning explaining your estimate.

6. NEVER claim this estimate is from the paper. NEVER cite a table or figure. Your reasoning must say "estimated based on..." not "reported in...".

7. If you cannot make a defensible estimate, return `{"value": null, "confidence": null, "reasoning": "Cannot estimate — insufficient nearby data points"}`.

8. For categorical variables (e.g., weight type), return null unless there's a clear analogical basis.

Output JSON only. No markdown fences. No prose.
