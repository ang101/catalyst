# Paper Reader Scheduled Pipeline

Process N papers from a topic search through the interactive reader pipeline.

## Steps

1. **Parse input** — Read the topic string and count (default 2).
   :checkpoint

2. **Search arxiv** — Search arxiv API for recent papers matching the topic. Pick the top N by recency. Delegate to claude_code:
   ```
   Search arxiv for papers matching the topic. Use the arxiv API:
   curl "http://export.arxiv.org/api/query?search_query=all:{topic}&sortBy=submittedDate&sortOrder=descending&max_results={count}"
   Parse the XML response. Extract arxiv IDs for the top N results.
   Output the list of IDs.
   ```
   :checkpoint

3. **Process each paper** — For each arxiv ID from step 2, run:
   ```
   python3 /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/run_pipeline.py <arxiv_id>
   ```
   This handles: fetch paper -> extract PDF -> classify -> extract data -> build reader -> refresh catalog.
   If a paper fails, log the error and continue to the next one.
   :checkpoint

4. **Report** — Summarize results:
   - How many papers succeeded vs. failed
   - Classification of each (Case A/B/C)
   - Link to catalog: /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/readers/catalog.html
   :checkpoint
