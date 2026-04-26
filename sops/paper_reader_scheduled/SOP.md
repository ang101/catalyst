# Paper Reader Scheduled Pipeline

Process N papers from a topic search through the interactive reader pipeline.

## Steps

1. **Parse input** — Read topic and count (default 2).
   :checkpoint

2. **Delegate to claude_code** — Pass the entire pipeline to claude_code with this prompt:
   ```
   You are running the paper reader pipeline. Topic: {topic}. Count: {count}.

   Step 1: Search arxiv for recent papers matching the topic.
   Run: curl -s "http://export.arxiv.org/api/query?search_query=all:{topic}&sortBy=submittedDate&sortOrder=descending&max_results={count}" | python3 -c "
   import sys
   from xml.etree import ElementTree as ET
   root = ET.parse(sys.stdin).getroot()
   ns = {'a': 'http://www.w3.org/2005/Atom'}
   for entry in root.findall('a:entry', ns):
       aid = entry.find('a:id', ns).text.split('/')[-1].split('v')[0]
       title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
       print(f'{aid} | {title}')
   "

   Step 2: For each arxiv ID from step 1, run the pipeline:
   python3 /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/run_pipeline.py <arxiv_id>

   Process each paper sequentially. If one fails, log the error and continue to the next.

   Step 3: Report results. For each paper, state: arxiv ID, title, case classification, number of data points, success/failure.
   ```
   :checkpoint

3. **Verify** — Check that new readers appear in the catalog:
   `ls /home/hchadha1/.zeroclaw/workspace/paper-repro/reader/readers/`
   :checkpoint
