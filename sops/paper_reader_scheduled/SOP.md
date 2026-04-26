# Paper Reader Scheduled Pipeline

Process papers from configured topics through the interactive reader pipeline. Classifies candidates before full extraction to prioritize high-value papers.

## Steps

1. **Read config** — Load topics and settings from reader/topics.json.
   :checkpoint

2. **Delegate to claude_code** — Pass the full search + classify + select + process pipeline:
   ```
   You are running the scheduled paper reader pipeline.

   Step 1: Read the config file:
   cat /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/topics.json

   Step 2: Get the list of already-processed papers (to deduplicate):
   ls /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/data/*.json 2>/dev/null | xargs -n1 basename | sed 's/.json//'
   Save this list as EXISTING_IDS.

   Step 3: For each topic in the config, search arxiv for the 5 most recent papers:
   curl -s "http://export.arxiv.org/api/query?search_query=all:<topic>&sortBy=submittedDate&sortOrder=descending&max_results=5"
   Parse the XML to extract arxiv IDs and titles. Use python3 with xml.etree.ElementTree.

   Step 4: Collect all candidate IDs across topics. Remove duplicates. Remove any ID that appears in EXISTING_IDS. This is the CANDIDATE_LIST.

   Step 5: For each candidate in CANDIDATE_LIST (up to max_candidates_to_classify from config):
   a. Fetch the paper:
      cd /home/hchadha1/.zeroclaw/workspace/paper-repro && python3 tools/arxiv_fetch/server.py --cli <arxiv_id>
      python3 tools/pdf_extract/server.py --cli <arxiv_id>
   b. Classify it (lightweight — just classification, not full extraction):
      Read the classify_paper.md prompt and paper.md, output the case (A/B/C) and estimated_data_points.
      Use: python3 -c "
      import json, subprocess
      prompt = open('/home/hchadha1/.zeroclaw/workspace/paper-repro/reader/prompts/classify_paper.md').read()
      paper = open('/home/hchadha1/.zeroclaw/workspace/paper-repro/papers/<arxiv_id>/paper.md').read()
      r = subprocess.run(['claude', '-p', '-', '--output-format', 'json'], input=prompt + '\n\n---PAPER---\n' + paper, capture_output=True, text=True, timeout=120)
      env = json.loads(r.stdout)
      text = env.get('result', r.stdout)
      c = json.loads(text.strip().strip('\`\`\`').strip('json').strip())
      print(json.dumps(c))
      "
   c. Record: arxiv_id, title, case, estimated_data_points
   d. If fetch or classification fails, mark the candidate as FAILED and skip it.

   Step 6: Filter and rank candidates STRICTLY:

   First, filter OUT:
   - Case C candidates (theoretical, no quantitative data)
   - Case B candidates with estimated_data_points < 5
   - Any candidate where fetch or classification failed

   Report each filtered candidate and the reason it was filtered.

   Then sort the remaining candidates:
   - Case A first (sorted by estimated_data_points descending)
   - Then Case B with >=5 data points (also by data_points desc)
   - Within ties, more recent = higher rank

   Take EXACTLY papers_per_day candidates from the top of this sorted list.
   If fewer qualifying candidates exist than papers_per_day, take what's available.
   Do NOT run pipeline on filtered-out candidates to "make up the count."

   Step 7: Run the full pipeline ONLY for the candidates picked in step 6:
   python3 /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/run_pipeline.py <arxiv_id>
   Do NOT process candidates that were filtered out or didn't make the top papers_per_day.

   Step 8: Refresh catalog:
   python3 /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/index_builder.py

   Step 9: Report:
   - Total candidates found across all topics
   - How many were skipped (already processed)
   - How many were classified
   - How many were filtered out (with reason for each: Case C / Case B <5 pts / fetch failed)
   - The papers_per_day that were picked (with case + estimated_data_points for each)
   - Pipeline success/failure for each picked paper
   - Final catalog count
   ```
   :checkpoint

3. **Verify** — Check catalog updated: `ls /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/readers/`
   :checkpoint
