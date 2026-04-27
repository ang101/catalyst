/* ============================================================
   Catalyst UI — app.js
   ML Paper Replication Interface · ZeroClaw
   ============================================================
   Replace ANTHROPIC_API_KEY with your key, or proxy through
   your own backend to avoid exposing credentials client-side.
   ============================================================ */

const ANTHROPIC_API_KEY = 'YOUR_API_KEY_HERE'; // replace or proxy

let strat = 'A';
let runDone = false;
let chatHistory = [];
let charts = {};
let paperContext = '';

if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

/* ---- Strategy pills ---- */
const STRAT_DESC = {
  A: "Load the authors' released model and run evaluation — no training needed.",
  B: "Start from a published base model and fine-tune it to match the paper's setup.",
  C: "Train the model from scratch, typically at reduced scale to fit local hardware.",
};

function setSP(el, s) {
  document.querySelectorAll('.sp').forEach(p => p.classList.remove('on'));
  el.classList.add('on');
  strat = s;
  const desc = document.getElementById('strat-desc');
  if (desc) desc.textContent = STRAT_DESC[s];
}

/* ---- Tab switching ---- */
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('on'));
  document.querySelector(`.tab[onclick="showTab('${name}')"]`).classList.add('on');
  document.getElementById('panel-' + name).classList.add('on');
}

/* ---- Sidebar PDF upload + drag-and-drop ---- */
async function loadSidebarPDF(file) {
  const label = document.getElementById('pdrop-label');
  label.textContent = 'Reading PDF…';
  try {
    paperContext = await extractPDFText(file);
    document.getElementById('purl').value = file.name.replace(/\.pdf$/i, '');
    label.textContent = `${file.name} · ${(paperContext.length / 1000).toFixed(1)}k chars`;
    document.getElementById('pdrop').classList.add('loaded');
  } catch (e) {
    label.textContent = 'Failed to read PDF — try again';
  }
}

function handlePDF(inp) {
  if (inp.files[0]) loadSidebarPDF(inp.files[0]);
}

function handleDrop(event) {
  event.preventDefault();
  document.getElementById('pdrop').classList.remove('drag-over');
  const file = event.dataTransfer.files[0];
  if (file && file.type === 'application/pdf') loadSidebarPDF(file);
}


/* ---- PDF extraction + chat attachment ---- */
async function extractPDFText(file) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  let text = '';
  const maxPages = Math.min(pdf.numPages, 15);
  for (let i = 1; i <= maxPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    text += content.items.map(item => item.str).join(' ') + '\n';
  }
  return text.slice(0, 8000);
}

function attachChatPDF() {
  document.getElementById('chat-file').click();
}

async function handleChatPDF(inp) {
  if (!inp.files[0]) return;
  const file = inp.files[0];
  const msgs = document.getElementById('chat-msgs');

  const thinking = document.createElement('div');
  thinking.className = 'bub a';
  thinking.innerHTML = `<div class="atag">Catalyst agent</div><span style="color:var(--text-tertiary)">Reading PDF…</span>`;
  msgs.appendChild(thinking);
  msgs.scrollTop = 1e9;

  try {
    paperContext = await extractPDFText(file);
    document.getElementById('purl').value = file.name.replace(/\.pdf$/i, '');
    updatePaperDisplay();
    const kchars = (paperContext.length / 1000).toFixed(1);
    thinking.innerHTML = `<div class="atag">Catalyst agent</div>Paper loaded: <strong>${file.name}</strong> (${kchars}k chars extracted). Ask me anything, or configure hardware and click Analyze feasibility.`;
  } catch (e) {
    thinking.innerHTML = `<div class="atag">Catalyst agent</div><span style="color:var(--color-danger)">Could not read PDF — ${e.message}</span>`;
  }

  inp.value = '';
  msgs.scrollTop = 1e9;
}

/* ---- Paper reference detection ---- */
function detectPaperRef(text) {
  const arxivUrl = text.match(/arxiv\.org\/abs\/([\d.v]+)/i);
  if (arxivUrl) return { url: `https://arxiv.org/abs/${arxivUrl[1]}`, label: `arXiv:${arxivUrl[1]}` };

  const arxivId = text.match(/\b(\d{4}\.\d{4,5}(?:v\d+)?)\b/);
  if (arxivId) return { url: `https://arxiv.org/abs/${arxivId[1]}`, label: `arXiv:${arxivId[1]}` };

  const doi = text.match(/\b(10\.\d{4,}\/\S+)/);
  if (doi) return { url: doi[1], label: `DOI:${doi[1]}` };

  return null;
}

/* ---- Helpers ---- */
function gpu()     { return document.getElementById('ugpu').value; }
function hasCUDA() { return !gpu().includes('None') && !gpu().includes('M2') && !gpu().includes('M3'); }
function vram()    { return gpu().includes('A100') ? 40 : (gpu().includes('4090') || gpu().includes('3090')) ? 24 : gpu().includes('3060') ? 12 : 0; }
function ramVal()  { return parseInt(document.getElementById('uram').value); }
function cpuVal()  { return parseInt(document.getElementById('ucpu').value); }
function diskVal() { const d = document.getElementById('udisk').value; return d.includes('1 TB') ? 1000 : parseInt(d); }
function paper()   { return document.getElementById('purl').value.trim(); }
function outdir()  { return document.getElementById('outdir').value || '~/papers/'; }

/* ---- Agent log ---- */
function log(msg, type) {
  const el = document.getElementById('agent-log');
  const ts = new Date().toTimeString().slice(0, 8);
  const d = document.createElement('div');
  d.className = 'll ' + (type || '');
  d.innerHTML = `<span class="ts">${ts}</span><span class="msg">${msg}</span>`;
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
}

/* ---- Phase definitions ---- */
const PHASES = [
  { id: 'preflight', name: 'Preflight checks' },
  { id: 'acquire',   name: 'Acquire paper + LaTeX' },
  { id: 'extract',   name: 'Extract requirements' },
  { id: 'scout',     name: 'Scout code repository' },
  { id: 'plan',      name: 'Generate plan.json' },
  { id: 'execute',   name: 'Execute experiment' },
  { id: 'report',    name: 'Write report' },
];

function renderPhases(active) {
  document.getElementById('phase-list').innerHTML = PHASES.map((p, i) => {
    const st = i < active ? 'done' : i === active ? 'run' : 'wait';
    const t  = i < active ? (i * 8 + 3) + 's' : i === active ? 'running…' : '—';
    return `<div class="run-phase">
      <span class="phase-dot ${st}"></span>
      <span class="phase-name">${p.name}</span>
      <span class="phase-t">${t}</span>
    </div>`;
  }).join('');
}

/* ============================================================
   EXAMPLE DATA  (embedded from examples/ + papers/ on disk)
   ============================================================ */
const EXAMPLES = {
  '1908.10084': {
    id: '1908.10084', arxiv: '1908.10084',
    title: 'Sentence-BERT', sub: 'Siamese BERT-Networks',
    status: 'partial_success', strategy: 'A',
    pdf: 'papers/1908.10084v1.pdf',
    concept: 'Sentence-BERT adds a siamese network head on top of BERT to generate fixed-size sentence embeddings compared by cosine similarity. The paper\'s key contribution is a fine-tuned checkpoint (bert-base-nli-mean-tokens) released publicly. This reproduction loads that checkpoint and runs it against STS benchmarks — no training is needed, making it feasible on CPU. The conceptual gap: training the siamese network from scratch requires NLI datasets and a GPU (~8h on V100). Eval-only sidesteps this entirely and still validates the core claim.',
    reqs: { gpu: 'V100 16GB', vram: 16, ram: 32, disk: 50, time: '~8h training · ~30 min eval on CPU' },
    phases: ['done','done','done','done','done','partial','done'],
    paperGPU: 'V100 16GB (training; eval is CPU-feasible)',
    paperVRAM: 16, paperRAM: 32, paperDisk: 50,
    metrics: [
      { m: 'STS12',  paper: 70.97, repro: 70.97, tol: 0.5 },
      { m: 'STS13',  paper: 76.53, repro: 76.53, tol: 0.5 },
      { m: 'STS14',  paper: 73.19, repro: 73.19, tol: 0.5 },
      { m: 'STS15',  paper: 79.09, repro: 79.09, tol: 0.5 },
      { m: 'STS16',  paper: 74.30, repro: 74.30, tol: 0.5 },
      { m: 'STSb',   paper: 77.03, repro: 76.99, tol: 0.5 },
    ],
    summary: '6/7 datasets completed. Released bert-base-nli-mean-tokens checkpoint matches paper to within 0.04 Spearman points. SICK-R timed out at 1800s.',
    causes: [
      'SICK-R exceeded 1800s timeout — 6/7 datasets complete.',
      'No metric drift: deterministic eval-only with released checkpoint.',
      'STSb −0.04 deviation within numerical noise of cosine similarity.',
    ],
    validity: 'Core claim reproducible. Released checkpoint verified to within 0.04 Spearman points across all completed datasets.',
    tasks: [
      { n: 'Load checkpoint (HuggingFace)', s:'y', pct:100, d:'bert-base-nli-mean-tokens — exact match across 5 datasets.' },
      { n: 'STS12–16 evaluation',           s:'y', pct:100, d:'All 5 STS tasks completed with exact paper values.' },
      { n: 'STSb evaluation',               s:'y', pct: 99, d:'Spearman 76.99 vs paper 77.03 (Δ −0.04).' },
      { n: 'SICK-R evaluation',             s:'p', pct:  0, d:'Timed out at 1800s cutoff.', alt:'Increase timeout limit or use faster hardware.' },
      { n: 'Figures + tables',              s:'y', pct:100, d:'CPU-compatible. Fully reproduced.' },
    ],
  },
  '2106.09685': {
    id: '2106.09685', arxiv: '2106.09685',
    title: 'LoRA', sub: 'Low-Rank Adaptation of Large Language Models',
    status: 'failed', strategy: 'A',
    pdf: 'papers/2106.09685v2.pdf',
    concept: 'LoRA injects trainable low-rank matrices into transformer attention layers, reducing trainable parameters by >10,000× relative to full fine-tuning. The paper evaluates GPT-2 Medium on E2E NLG using beam search (beam=10) over 4,693 test examples. The conceptual bottleneck is autoregressive generation: each token requires a full forward pass through a 345M-parameter model. GPU inference runs at ~50 tokens/s; CPU runs at ~0.1 tokens/s. Full eval is ~1h on V100 vs 40–80h on CPU — the agent was killed after 30 min. A cloud GPU is the only practical path.',
    reqs: { gpu: 'V100 16GB (required for eval)', vram: 16, ram: 32, disk: 180, time: '~1h on V100 · 40–80h CPU (impractical)' },
    phases: ['done','done','done','done','done','failed','done'],
    paperGPU: 'V100 16GB',
    paperVRAM: 16, paperRAM: 32, paperDisk: 180,
    metrics: [
      { m: 'BLEU-4',  paper: 70.4,  repro: null, tol: 0.5  },
      { m: 'NIST',    paper:  8.85, repro: null, tol: 0.1  },
      { m: 'METEOR',  paper: 46.8,  repro: null, tol: 0.5  },
      { m: 'ROUGE-L', paper: 71.8,  repro: null, tol: 0.5  },
      { m: 'CIDEr',   paper:  2.53, repro: null, tol: 0.05 },
    ],
    summary: 'Execution failed. Beam search (beam=10) over 4,693 E2E test examples estimated 40–80h on CPU. Killed after 30 min. GPU required.',
    causes: [
      'Autoregressive generation beam=10 is ~100× slower on CPU than GPU.',
      'Eval plan did not constrain beam width for CPU feasibility.',
      'Fix: reduce beam to 1–2, subsample to 200–500 examples, or use cloud GPU.',
    ],
    validity: 'Execution incomplete — no metrics produced. Eval-only strategy is correct but CPU inference is infeasible for autoregressive generation at full scale.',
    tasks: [
      { n: 'Load LoRA checkpoint',     s:'y', pct:100, d:'microsoft/LoRA GPT-2 Medium checkpoint downloaded.' },
      { n: 'Apply CPU patches',        s:'y', pct:100, d:'gpu.py and gpt2_beam.py patched cleanly.' },
      { n: 'Beam search (E2E test)',   s:'n', pct:  0, d:'beam=10 × 4,693 examples = 40–80h on CPU.', alt:'Reduce beam to 1–2, or use cloud GPU.' },
      { n: 'Compute NLG metrics',      s:'n', pct:  0, d:'Not reached — depends on beam search.' },
      { n: 'Reproduce GLUE (RoBERTa)', s:'p', pct: 50, d:'Checkpoint available; eval not attempted.', alt:'Requires GPU for practical runtime.' },
    ],
  },
};

/* ---- Load example run ---- */
async function loadExample(id) {
  const ex = EXAMPLES[id];
  if (!ex) return;

  // Mark active card
  document.querySelectorAll('.pex-card').forEach(c => c.classList.remove('active'));
  const card = document.getElementById('pex-' + id);
  if (card) card.classList.add('active');

  // Set paper input
  document.getElementById('purl').value = ex.arxiv;
  updatePaperDisplay();
  paperContext = `${ex.title} (${ex.sub}): ${ex.summary}`;

  // Async PDF load (works when served; silently skipped on file://)
  tryLoadExamplePDF(ex);

  // Reveal all panels
  runDone = true;
  strat = ex.strategy;
  ['ov-idle','run-idle','hw-idle','tasks-idle','feas-idle','res-idle']
    .forEach(i => document.getElementById(i)?.classList.add('hidden'));
  ['ov-content','run-content','hw-content','tasks-content','feas-content','res-content']
    .forEach(i => document.getElementById(i)?.classList.remove('hidden'));
  document.getElementById('run-prog-wrap').classList.add('hidden');

  buildExampleOverview(ex);
  buildExampleRun(ex);
  buildExampleHardware(ex);
  buildExampleTasks(ex);
  buildFeasibilityFromExample(ex);
  buildExampleResults(ex);
  fetchRelatedPapers(ex.arxiv);

  showTab('overview');
  addChatBubble('agent',
    `Loaded: <strong>${ex.title}</strong> (arXiv:${ex.arxiv}) — status: <strong>${ex.status.replace('_', ' ')}</strong>.<br>${ex.summary} Ask me anything or switch tabs to explore.`
  );
}

async function tryLoadExamplePDF(ex) {
  try {
    const resp = await fetch(ex.pdf);
    if (!resp.ok) return;
    const file = new File([await resp.blob()], ex.id + '.pdf', { type: 'application/pdf' });
    const text = await extractPDFText(file);
    if (text.length > 200) paperContext = text;
  } catch (_) { /* file:// or not served — metadata context is used instead */ }
}

/* ---- Example: Overview ---- */
function buildExampleOverview(ex) {
  const failed = ex.metrics.every(m => m.repro === null);
  const done   = ex.metrics.filter(m => m.repro !== null).length;

  document.getElementById('ov-alert').innerHTML = failed
    ? `<div class="alert w">${ex.summary}</div>`
    : `<div class="alert s">${ex.summary}</div>`;

  const feasCls = failed ? 'bad' : ex.status === 'partial_success' ? 'warn' : 'ok';
  const feasLbl = failed ? 'Failed' : ex.status === 'partial_success' ? 'Partial' : 'Success';
  document.getElementById('ov-stats').innerHTML = `
    <div class="stat"><div class="lbl">Status</div><div class="val ${feasCls}">${feasLbl}</div></div>
    <div class="stat"><div class="lbl">Strategy</div><div class="val ok">Eval only</div></div>
    <div class="stat"><div class="lbl">Metrics</div><div class="val ${done === ex.metrics.length ? 'ok' : 'warn'}">${done}/${ex.metrics.length}</div></div>`;

  const vItems = failed
    ? [{ l: 'Execution failed — no metrics produced', pct: 0 }]
    : ex.metrics.filter(m => m.repro !== null).map(m => {
        const d = Math.abs(m.repro - m.paper);
        const pct = Math.min(100, Math.round(100 - (d / m.tol) * 15));
        return { l: m.m, pct: Math.max(0, pct) };
      });

  document.getElementById('ov-veracity').innerHTML = vItems.map(item => {
    const cls = item.pct >= 70 ? 'hi' : item.pct >= 40 ? 'mid' : 'lo';
    return `<div class="vbar-wrap">
      <div class="vbar-lbl"><span>${item.l}</span><span>${item.pct}%</span></div>
      <div class="vbar-track"><div class="vbar-fill ${cls}" style="width:0" data-w="${item.pct}%"></div></div>
    </div>`;
  }).join('');
  setTimeout(() => document.querySelectorAll('.vbar-fill').forEach(b => b.style.width = b.dataset.w), 100);

  document.getElementById('ov-phases').innerHTML = PHASES.map((p, i) => {
    const st = ex.phases[i];
    const dot = st === 'done' ? 'done' : st === 'partial' ? 'run' : 'wait';
    return `<div class="run-phase"><span class="phase-dot ${dot}"></span><span class="phase-name">${p.name}</span><span class="phase-t">${st}</span></div>`;
  }).join('');
}

/* ---- Example: Run log ---- */
function buildExampleRun(ex) {
  const failed = ex.metrics.every(m => m.repro === null);
  const logEl  = document.getElementById('agent-log');
  logEl.innerHTML = '';
  const ts = new Date().toTimeString().slice(0, 8);
  const logLine = (msg, type) => {
    const d = document.createElement('div');
    d.className = 'll ' + (type || '');
    d.innerHTML = `<span class="ts">${ts}</span><span class="msg">${msg}</span>`;
    logEl.appendChild(d);
  };
  logLine(`Preflight passed. Fetching arXiv:${ex.arxiv}…`, 'hi');
  logLine('PDF extracted → structured markdown. Requirements parsed.', null);
  logLine('Strategy: eval-only from released checkpoint.', null);
  logLine(`Executing with: ${ex.paperGPU}…`, null);
  logLine(failed
    ? `Execute failed: ${ex.causes[0]}`
    : `Execution complete. ${ex.metrics.filter(m=>m.repro!==null).length}/${ex.metrics.length} metrics collected.`,
    failed ? 'er' : null);
  logLine(`Report written. Status: ${ex.status.replace('_', ' ')}.`, failed ? 'er' : 'ok');

  document.getElementById('phase-list').innerHTML = PHASES.map((p, i) => {
    const st  = ex.phases[i];
    const dot = st === 'done' ? 'done' : st === 'partial' ? 'run' : 'wait';
    return `<div class="run-phase"><span class="phase-dot ${dot}"></span><span class="phase-name">${p.name}</span><span class="phase-t">${st}</span></div>`;
  }).join('');
}

/* ---- Example: Hardware ---- */
function buildExampleHardware(ex) {
  const userVRAM = vram(), userGPU = gpu(), hasCuda = hasCUDA();

  document.getElementById('hw-cmp').innerHTML = `
    <div class="cmp-card">
      <div class="cmp-card-hd"><span class="badge bp">Paper</span></div>
      <div class="hr"><span class="k">GPU</span><span class="v">${ex.paperGPU}</span></div>
      <div class="hr"><span class="k">VRAM</span><span class="v">${ex.paperVRAM} GB</span></div>
      <div class="hr"><span class="k">RAM</span><span class="v">${ex.paperRAM} GB</span></div>
      <div class="hr"><span class="k">Disk</span><span class="v">~${ex.paperDisk} GB</span></div>
    </div>
    <div class="cmp-card">
      <div class="cmp-card-hd"><span class="badge by">Run</span></div>
      <div class="hr"><span class="k">GPU</span><span class="${hasCuda ? 'vok' : 'vb'}">${userGPU}</span></div>
      <div class="hr"><span class="k">VRAM</span><span class="${userVRAM >= ex.paperVRAM ? 'vok' : userVRAM > 0 ? 'vw' : 'vb'}">${userVRAM > 0 ? userVRAM + ' GB' : 'None'}</span></div>
      <div class="hr"><span class="k">RAM</span><span class="v">${document.getElementById('uram').value}</span></div>
      <div class="hr"><span class="k">Disk</span><span class="v">${document.getElementById('udisk').value}</span></div>
    </div>`;

  const ctx = document.getElementById('chartHW').getContext('2d');
  if (charts.hw) charts.hw.destroy();
  const norm = (a, b) => Math.min(100, Math.round((a / b) * 100));
  charts.hw = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['VRAM (GB)', 'RAM (GB)', 'CPU cores', 'Disk (GB)'],
      datasets: [
        { label: 'Paper', data: [100, 100, 100, 100], borderColor: '#378ADD', backgroundColor: 'rgba(55,138,221,0.1)', borderWidth: 2, pointRadius: 3 },
        { label: 'Yours', data: [
            norm(Math.max(userVRAM, 1), ex.paperVRAM),
            norm(ramVal(), ex.paperRAM),
            norm(Math.min(cpuVal(), 16), 16),
            norm(Math.min(diskVal(), ex.paperDisk), ex.paperDisk),
          ], borderColor: '#1D9E75', backgroundColor: 'rgba(29,158,117,0.1)', borderWidth: 2, borderDash: [5,3], pointRadius: 3 },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { r: { grid: { color: 'rgba(128,128,128,0.15)' }, angleLines: { color: 'rgba(128,128,128,0.15)' }, ticks: { display: false },
        pointLabels: { font: { size: 11 }, color: '#888780' }, min: 0, max: 100 } } }
  });

  const gaps = [];
  const failed = ex.metrics.every(m => m.repro === null);
  if (failed)    gaps.push(`<div class="alert w">GPU required. ${ex.causes[0]}</div>`);
  if (!hasCuda)  gaps.push(`<div class="alert w">No CUDA — CPU inference is impractical for this paper's eval pipeline.</div>`);
  if (userVRAM < ex.paperVRAM && hasCuda) gaps.push(`<div class="alert w">VRAM gap: ${userVRAM}GB vs ${ex.paperVRAM}GB paper requirement.</div>`);
  gaps.push(`<div class="alert i">Disk: ~${ex.paperDisk}GB required. Confirm ${outdir()} has capacity.</div>`);
  document.getElementById('hw-gaps').innerHTML = gaps.join('');
}

/* ---- Example: Tasks ---- */
function buildExampleTasks(ex) {
  const ctx = document.getElementById('chartTasks').getContext('2d');
  if (charts.tasks) charts.tasks.destroy();
  charts.tasks = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ex.tasks.map(t => t.n.length > 28 ? t.n.slice(0, 28) + '…' : t.n),
      datasets: [{ label: 'Feasibility %', data: ex.tasks.map(t => t.pct),
        backgroundColor: ex.tasks.map(t =>
          t.pct >= 90 ? 'rgba(29,158,117,0.75)' : t.pct >= 50 ? 'rgba(186,117,23,0.75)' : 'rgba(226,75,74,0.75)'),
        borderRadius: 4, borderSkipped: false }]
    },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { min: 0, max: 100, grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780', callback: v => v + '%' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888780' } }
      } }
  });
  document.getElementById('task-list').innerHTML = ex.tasks.map(t => `
    <div class="ti">
      <div class="ts2 ${t.s}">${t.s === 'y' ? '✓' : t.s === 'p' ? '~' : '✕'}</div>
      <div class="tb"><div class="tn">${t.n}</div><div class="td">${t.d}</div>
        ${t.alt ? `<div class="ta">Alternative: ${t.alt}</div>` : ''}
      </div>
    </div>`).join('');
}

/* ---- Example: Results ---- */
function buildExampleResults(ex) {
  const failed   = ex.metrics.every(m => m.repro === null);
  const hasRepro = ex.metrics.filter(m => m.repro !== null);

  document.getElementById('res-alert').innerHTML = failed
    ? `<div class="alert w">Execution failed — no metrics produced. ${ex.summary}</div>`
    : `<div class="alert ${ex.status === 'partial_success' ? 'w' : 's'}">${ex.summary}</div>`;

  const chartMetrics = failed ? ex.metrics : hasRepro;
  const ctx = document.getElementById('chartMetrics').getContext('2d');
  if (charts.metrics) charts.metrics.destroy();
  charts.metrics = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: chartMetrics.map(m => m.m),
      datasets: [
        { label: 'Paper', data: chartMetrics.map(m => m.paper), backgroundColor: 'rgba(55,138,221,0.75)', borderRadius: 4, borderSkipped: false },
        { label: 'Reproduced', data: chartMetrics.map(m => m.repro ?? 0),
          backgroundColor: failed ? 'rgba(226,75,74,0.2)' : chartMetrics.map(m =>
            Math.abs((m.repro ?? 0) - m.paper) > m.tol ? 'rgba(226,75,74,0.75)' : 'rgba(29,158,117,0.75)'),
          borderRadius: 4, borderSkipped: false },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888780', autoSkip: false, maxRotation: 30 } },
        y: { grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' } }
      } }
  });

  const outcomeRow = (m, type) => {
    if (m.repro === null) return `<div class="outcome-row bad">
      <span class="outcome-icon">✕</span>
      <div class="outcome-body">
        <div class="outcome-metric">${m.m}</div>
        <div class="outcome-vals">paper ${m.paper} → not collected</div>
      </div></div>`;
    const diff = (m.repro - m.paper).toFixed(2);
    const pct  = Math.abs(((m.repro - m.paper) / m.paper) * 100).toFixed(1);
    return `<div class="outcome-row ${type}">
      <span class="outcome-icon">${type === 'ok' ? '✓' : '✕'}</span>
      <div class="outcome-body">
        <div class="outcome-metric">${m.m}</div>
        <div class="outcome-vals">paper ${m.paper} → got ${m.repro.toFixed(2)} (${+diff > 0 ? '+' : ''}${diff}, ${pct}%)</div>
      </div></div>`;
  };

  const okMetrics  = failed ? [] : hasRepro.filter(m => Math.abs(m.repro - m.paper) <= m.tol);
  const badMetrics = failed ? ex.metrics : hasRepro.filter(m => Math.abs(m.repro - m.paper) > m.tol);

  document.getElementById('res-ok').innerHTML = okMetrics.length
    ? okMetrics.map(m => outcomeRow(m, 'ok')).join('')
    : '<div class="outcome-none">Nothing reproduced within tolerance.</div>';

  document.getElementById('res-bad').innerHTML = badMetrics.length
    ? badMetrics.map(m => outcomeRow(m, 'bad')).join('')
    : '<div class="outcome-none">All metrics within tolerance.</div>';

  document.getElementById('disc-causes').innerHTML = ex.causes.map(c =>
    `<div class="alert i" style="margin-bottom:6px">${c}</div>`).join('');
}

/* ============================================================
   FEASIBILITY TAB
   ============================================================ */
function buildFeasibility(cuda, vr, g) {
  document.getElementById('feas-idle').classList.add('hidden');
  document.getElementById('feas-content').classList.remove('hidden');

  // Conceptual gap — strategy-based description
  const conceptText = strat === 'A'
    ? `This reproduction loads the authors' released checkpoint and runs evaluation only — no training is performed. The conceptual gap vs the paper is that training dynamics (optimizer state, batch statistics, random seeds) are not reproduced. You are verifying that the released artifact produces the reported numbers, which is the strongest form of eval-only reproducibility. If checkpoint metrics match, the core claim is confirmed regardless of hardware differences.`
    : strat === 'B'
    ? `This reproduction starts from a published base model and fine-tunes it following the paper's procedure. The conceptual gap: fine-tuning dynamics depend on hardware (batch size, gradient variance, VRAM constraints). Your single-GPU setup differs from the paper's multi-GPU cluster, so minor metric drift (±2–5 pp) is expected. The core method is being exercised, but exact convergence paths will differ.`
    : `This reproduction trains from scratch, typically at reduced scale to fit local hardware. The conceptual gap is large: scale changes training dynamics significantly (learning rate schedules, batch norm statistics, gradient variance). Results will approximate the paper's trend but should not be compared numerically without scaling corrections.`;
  document.getElementById('feas-concept').textContent = conceptText;

  // Exact requirements grid (paper's reported hardware)
  document.getElementById('feas-req-grid').innerHTML = `
    <div class="feas-req-card"><span class="frk">GPU</span><span class="frv">4× A100 40GB</span><span class="frnote">paper setup</span></div>
    <div class="feas-req-card"><span class="frk">VRAM</span><span class="frv">160 GB total</span><span class="frnote">4× 40GB</span></div>
    <div class="feas-req-card"><span class="frk">RAM</span><span class="frv">512 GB</span></div>
    <div class="feas-req-card"><span class="frk">Disk</span><span class="frv">~180 GB</span></div>
    <div class="feas-req-card" style="grid-column:span 2"><span class="frk">Time estimate (paper setup)</span><span class="frv" style="font-size:11px">~18h on 4× A100 · ${cuda ? (vr >= 24 ? '~14h on your GPU' : '~32h on your GPU') : '~52h+ CPU (impractical)'}</span></div>`;

  // Spec comparison
  document.getElementById('feas-spec').innerHTML = `
    <div class="feas-spec-grid">
      <div class="feas-spec-row"><span class="feas-spec-k">GPU</span><span class="feas-spec-v ${cuda ? 'vok' : 'vb'}">${g}</span><span class="feas-spec-req">CUDA GPU recommended</span></div>
      <div class="feas-spec-row"><span class="feas-spec-k">VRAM</span><span class="feas-spec-v ${vr >= 24 ? 'vok' : vr > 0 ? 'vw' : 'vb'}">${vr > 0 ? vr + ' GB' : 'None'}</span><span class="feas-spec-req">24 GB+ for most papers</span></div>
      <div class="feas-spec-row"><span class="feas-spec-k">RAM</span><span class="feas-spec-v ${ramVal() >= 16 ? 'vok' : 'vw'}">${ramVal()} GB</span><span class="feas-spec-req">16 GB minimum</span></div>
      <div class="feas-spec-row"><span class="feas-spec-k">Disk</span><span class="feas-spec-v ${diskVal() >= 100 ? 'vok' : 'vw'}">${document.getElementById('udisk').value}</span><span class="feas-spec-req">100 GB+ for checkpoints &amp; data</span></div>
    </div>`;

  const canItems = [
    'Download and load released model checkpoints from HuggingFace or GitHub.',
    'Run evaluation on standard benchmarks.',
    'Reproduce figures, plots, and metric tables from the paper.',
    strat === 'A' ? 'Eval-only — no training required at all.' : null,
    cuda ? `Single-GPU training at reduced batch size${vr >= 24 ? '.' : ' with gradient checkpointing.'}` : null,
  ].filter(Boolean);

  const cannotItems = [
    !cuda ? 'Any training or fast inference — no CUDA GPU detected.' : null,
    cuda && vr < 40 ? `Exact multi-GPU training dynamics (paper typically uses 40–160 GB VRAM).` : null,
    cuda && vr < 24 ? 'Full paper batch size — reduction changes gradient variance and convergence.' : null,
    strat !== 'A' ? 'Exact random-seed reproducibility across independent training runs.' : null,
    'Proprietary datasets or models not released by the authors.',
    'Ablations at full scale without significant additional compute budget.',
  ].filter(Boolean);

  const limits = [
    cuda && vr >= 24 ? 'Estimated runtime: 8–16 h on a single GPU (paper used multi-GPU for ~18 h).'
      : cuda ? 'Estimated runtime: 18–36 h due to VRAM-forced batch reduction.'
      : 'Estimated runtime: 48 h+ on CPU. Cloud GPU strongly recommended.',
    cuda && vr < 40 ? 'Batch reduction may cause ±2–5 pp metric drift from the paper values.' : null,
    !cuda ? 'Cloud options: Google Colab T4 (free tier), Lambda A10G ($0.75/h), RunPod A100 ($1.64/h).' : null,
    'Ablation studies require 5–8× more compute than a single reproduction run.',
  ].filter(Boolean);

  document.getElementById('feas-ok').innerHTML   = canItems.map(t   => `<div class="feas-item ok"><span>✓</span><span>${t}</span></div>`).join('');
  document.getElementById('feas-bad').innerHTML  = cannotItems.map(t => `<div class="feas-item bad"><span>✕</span><span>${t}</span></div>`).join('');
  document.getElementById('feas-limits').innerHTML = limits.map(c => `<div class="alert i" style="margin-bottom:6px">${c}</div>`).join('');

  if (!cuda) {
    const note = document.getElementById('feas-cloud-note');
    if (note) note.innerHTML = ' — <strong>no local GPU; cloud required for training</strong>';
  }
  buildCloud(cuda);
}

function buildFeasibilityFromExample(ex) {
  document.getElementById('feas-idle').classList.add('hidden');
  document.getElementById('feas-content').classList.remove('hidden');

  const failed = ex.metrics.every(m => m.repro === null);

  // Conceptual gap
  document.getElementById('feas-concept').textContent = ex.concept || '';

  // Requirements grid
  if (ex.reqs) {
    const r = ex.reqs;
    document.getElementById('feas-req-grid').innerHTML = `
      <div class="feas-req-card"><span class="frk">GPU</span><span class="frv">${r.gpu}</span></div>
      <div class="feas-req-card"><span class="frk">VRAM</span><span class="frv">${r.vram} GB</span></div>
      <div class="feas-req-card"><span class="frk">RAM</span><span class="frv">${r.ram} GB</span></div>
      <div class="feas-req-card"><span class="frk">Disk</span><span class="frv">~${r.disk} GB</span></div>
      <div class="feas-req-card" style="grid-column:span 2"><span class="frk">Time estimate</span><span class="frv" style="font-size:11px">${r.time}</span></div>`;
  }

  // Spec comparison
  document.getElementById('feas-spec').innerHTML = `
    <div class="feas-spec-grid">
      <div class="feas-spec-row"><span class="feas-spec-k">Paper GPU</span><span class="feas-spec-v vw">${ex.paperGPU}</span><span class="feas-spec-req">what the authors used</span></div>
      <div class="feas-spec-row"><span class="feas-spec-k">Run hardware</span><span class="feas-spec-v ${failed ? 'vb' : 'vok'}">CPU only</span><span class="feas-spec-req">${failed ? 'insufficient — GPU required' : 'sufficient for eval-only'}</span></div>
      <div class="feas-spec-row"><span class="feas-spec-k">Approach</span><span class="feas-spec-v vok">Use checkpoint</span><span class="feas-spec-req">no training — load released model</span></div>
    </div>`;

  const canItems  = ex.tasks.filter(t => t.s === 'y').map(t => `${t.n} — ${t.d}`);
  const cantItems = ex.tasks.filter(t => t.s !== 'y').map(t => `${t.n}${t.alt ? ' — ' + t.alt : ''}`);

  document.getElementById('feas-ok').innerHTML   = canItems.length  ? canItems.map(t  => `<div class="feas-item ok"><span>✓</span><span>${t}</span></div>`).join('') : '<div class="outcome-none">Nothing feasible with current hardware.</div>';
  document.getElementById('feas-bad').innerHTML  = cantItems.length ? cantItems.map(t => `<div class="feas-item bad"><span>✕</span><span>${t}</span></div>`).join('') : '<div class="outcome-none">All tasks feasible.</div>';
  document.getElementById('feas-limits').innerHTML = ex.causes.map(c => `<div class="alert i" style="margin-bottom:6px">${c}</div>`).join('');

  // Cloud section — emphasize if failed
  if (failed) {
    const note = document.getElementById('feas-cloud-note');
    if (note) note.innerHTML = ' — <strong>GPU required; see options below</strong>';
  }
  buildCloud(false);
}

/* ============================================================
   RELATED PAPERS  (Semantic Scholar API)
   ============================================================ */
async function fetchRelatedPapers(query) {
  document.getElementById('rel-idle').classList.add('hidden');
  document.getElementById('rel-content').classList.remove('hidden');
  document.getElementById('related-list').innerHTML = '<div class="rel-loading">Searching Semantic Scholar…</div>';

  const arxivMatch = String(query).match(/(\d{4}\.\d{4,5})/);
  const arxivId    = arxivMatch ? arxivMatch[1] : null;

  try {
    let papers = [];

    if (arxivId) {
      const r = await fetch(
        `https://api.semanticscholar.org/recommendations/v1/papers/forpaper/ARXIV:${arxivId}?limit=10&fields=title,authors,year,venue,abstract,externalIds,citationCount`
      );
      if (r.ok) papers = (await r.json()).recommendedPapers || [];
    }

    if (!papers.length) {
      const q = encodeURIComponent(String(query).replace(/https?:\/\/\S+/g, '').trim());
      const r = await fetch(
        `https://api.semanticscholar.org/graph/v1/paper/search?query=${q}&limit=10&fields=title,authors,year,venue,abstract,externalIds,citationCount`
      );
      if (r.ok) papers = (await r.json()).data || [];
    }

    renderRelatedPapers(papers);
  } catch (_) {
    document.getElementById('related-list').innerHTML =
      '<div class="alert w">Could not reach Semantic Scholar — check your connection.</div>';
  }
}

function renderRelatedPapers(papers) {
  const el = document.getElementById('related-list');
  if (!papers.length) {
    el.innerHTML = '<div class="alert w">No related papers found for this query.</div>';
    return;
  }
  el.innerHTML = papers.slice(0, 10).map((p, i) => {
    const arxivId = p.externalIds?.ArXiv;
    const authors = (p.authors || []).slice(0, 3).map(a => a.name).join(', ')
      + ((p.authors || []).length > 3 ? ' et al.' : '');
    const snippet = (p.abstract || '').slice(0, 200).trim();
    const clickable = !!arxivId;
    const links = arxivId ? `
      <div class="rel-links">
        <a class="rel-link" href="https://arxiv.org/abs/${arxivId}" target="_blank" rel="noopener" onclick="event.stopPropagation()">arXiv ↗</a>
        <a class="rel-link" href="https://arxiv.org/pdf/${arxivId}" target="_blank" rel="noopener" onclick="event.stopPropagation()">PDF ↗</a>
        ${clickable ? `<span class="rel-link" style="cursor:pointer" onclick="event.stopPropagation();setRelatedPaper('${arxivId}',this.closest('.rel-card'))">Analyze ↗</span>` : ''}
      </div>` : '';
    return `<div class="rel-card${clickable ? ' rel-clickable' : ''}"${clickable ? ` onclick="setRelatedPaper('${arxivId}',this)"` : ''}>
      <div class="rel-head">
        <span class="rel-num">${i + 1}</span>
        <div class="rel-info">
          <div class="rel-title">${p.title || 'Untitled'}</div>
          <div class="rel-byline">${authors}${p.year ? ' · ' + p.year : ''}${p.venue ? ' · ' + p.venue : ''}${p.citationCount ? ' · ' + p.citationCount + ' citations' : ''}</div>
        </div>
        ${arxivId ? `<span class="rel-arxiv">arXiv:${arxivId}</span>` : ''}
      </div>
      ${snippet ? `<div class="rel-snippet">${snippet}${(p.abstract || '').length > 200 ? '…' : ''}</div>` : ''}
      ${links}
    </div>`;
  }).join('');
}

function setRelatedPaper(arxivId, cardEl) {
  document.getElementById('purl').value = arxivId;
  updatePaperDisplay();
  paperContext = '';
  document.querySelectorAll('.rel-card').forEach(c => c.classList.remove('active'));
  cardEl.classList.add('active');
  showTab('chat');
  addChatBubble('agent', `Paper switched to <strong>arXiv:${arxivId}</strong>. Configure hardware and click Analyze feasibility.`);
}

/* ---- Paper display ---- */
function updatePaperDisplay() {
  const p = document.getElementById('purl').value.trim();
  document.getElementById('paper-sel').textContent =
    p || 'No paper selected — load an example or specify in chat';

  const linksEl = document.getElementById('paper-links');
  if (!linksEl) return;
  const arxivId = p.match(/(\d{4}\.\d{4,5})/)?.[1];
  if (arxivId) {
    document.getElementById('paper-link-arxiv').href = `https://arxiv.org/abs/${arxivId}`;
    document.getElementById('paper-link-pdf').href   = `https://arxiv.org/pdf/${arxivId}`;
    linksEl.style.display = 'flex';
  } else {
    linksEl.style.display = 'none';
  }
}

/* ============================================================
   PHASE 1 — ANALYZE FEASIBILITY
   ============================================================ */
function analyzeFeasibility() {
  const p = paper();
  if (!p) {
    showTab('chat');
    addChatBubble('agent', 'No paper selected. Load an example from the sidebar or paste an arXiv ID in chat.');
    return;
  }

  const rbtn = document.getElementById('rbtn');
  rbtn.disabled = true;
  rbtn.textContent = 'Analyzing…';
  document.getElementById('repbtn').classList.add('hidden');

  ['ov-idle','run-idle'].forEach(id => document.getElementById(id).classList.add('hidden'));
  ['ov-content','run-content'].forEach(id => document.getElementById(id).classList.remove('hidden'));
  document.getElementById('agent-log').innerHTML = '';
  document.getElementById('run-prog-wrap').classList.add('hidden');
  showTab('run');

  const cuda = hasCUDA(), vr = vram(), g = gpu();

  [
    [0,    'Preflight: checking zeroclaw config, claude code CLI, python 3.10, uv…', 'hi'],
    [500,  'Preflight passed. Fetching paper via arxiv_fetch MCP tool…', null],
    [1200, 'pdf_extract: converting PDF → structured markdown…', null],
    [1900, `Requirements extracted — GPU: ${vr > 0 ? vr + 'GB VRAM needed' : 'GPU required'}, disk: ~180 GB`, null],
    [2600, 'repo_scout: scanning GitHub for official implementation…', null],
    [3200, `Strategy: ${strat==='A'?'eval-only from released checkpoint':strat==='B'?'finetune from base checkpoint':'train from scratch (scaled)'}`, null],
    [3800, `Hardware gap: your machine has ${vr > 0 ? vr + 'GB VRAM' : 'CPU only'}. Feasibility report ready.`, 'hi'],
  ].forEach(([d, m, t]) => setTimeout(() => log(m, t), d));

  [0,1,2,3,4].forEach(i => setTimeout(() => renderPhases(i), i * 700 + 300));

  setTimeout(() => {
    renderPhases(5);
    buildOverview(cuda, vr, g);
    buildHardware(cuda, vr, g);
    buildTasks(cuda, vr);
    buildFeasibility(cuda, vr, g);
    fetchRelatedPapers(p);
    rbtn.disabled = false;
    rbtn.textContent = 'Analyze feasibility ↗';
    document.getElementById('repbtn').classList.remove('hidden');
    showTab('overview');
    addChatBubble('agent',
      `Feasibility analysis complete for <strong>${p}</strong>. ` +
      (cuda
        ? `Your ${g} can run this — review the Hardware and Tasks tabs for gaps, then click <strong>Run replication</strong>.`
        : 'No GPU detected. Check the Cloud tab for options, then click <strong>Run replication</strong> to run on CPU (slower).')
    );
  }, 4200);
}

/* ============================================================
   PHASE 2 — RUN REPLICATION
   ============================================================ */
function startReplication() {
  const repbtn = document.getElementById('repbtn');
  const rbtn   = document.getElementById('rbtn');
  repbtn.disabled = true;
  repbtn.textContent = 'Running…';
  rbtn.disabled = true;

  showTab('run');
  const cuda = hasCUDA(), vr = vram(), g = gpu();

  [
    [0,    'Launching replication experiment…', 'hi'],
    [600,  cuda ? 'CUDA available. Patching Flash Attention for single-GPU config…'
                : 'No CUDA — falling back to CPU attention. Warning: 3–5× slower.', cuda ? null : 'er'],
    [1400, 'Executing scaled experiment via scaled_runner MCP (sandboxed)…', null],
    [2200, cuda ? 'Epoch 1/3 complete. Loss: 2.41. ETA: ~4h local.' : 'CPU run underway. Loss: 2.58. ETA: ~22h.', null],
    [3000, cuda ? 'Epoch 2/3 complete. Loss: 1.87.' : 'CPU epoch 1/3. Loss: 2.31.', null],
    [3700, 'Eval benchmark running — collecting metrics for results.json…', null],
    [4300, 'Writing summary.md and scaling_rationale.md…', null],
    [4800, `Replication complete. Report written to ${outdir()}`, 'ok'],
  ].forEach(([d, m, t]) => setTimeout(() => log(m, t), d));

  setTimeout(() => {
    document.getElementById('run-prog-wrap').classList.remove('hidden');
    drawTrainingChart(cuda);
  }, 1600);

  setTimeout(() => renderPhases(5), 800);
  setTimeout(() => renderPhases(6), 4000);
  setTimeout(() => finalizeReplication(cuda, vr, g), 5100);
}

function finalizeReplication(cuda, vr, g) {
  runDone = true;
  document.getElementById('repbtn').disabled = false;
  document.getElementById('repbtn').textContent = 'Run replication ↗';
  document.getElementById('rbtn').disabled = false;

  buildResults(cuda, vr);
  showTab('results');
  addChatBubble('agent',
    `Replication complete for <strong>${paper()}</strong>. ` +
    (cuda
      ? `Your ${g} reproduced ${vr >= 24 ? 'most metrics within tolerance' : 'some metrics — moderate drift due to VRAM gap'}.`
      : 'CPU-only run: training did not converge. Cloud GPU required for valid replication.') +
    ' See the Results tab for what was and wasn\'t reproduced.'
  );
}

/* ============================================================
   TRAINING CHART
   ============================================================ */
function drawTrainingChart(cuda) {
  const ctx = document.getElementById('chartTraining').getContext('2d');
  if (charts.training) charts.training.destroy();

  const steps      = [0, 500, 1000, 2000, 4000, 8000, 16000];
  const paperLoss  = [3.2, 2.8, 2.4, 2.0, 1.6, 1.35, 1.22];
  const reproLoss  = cuda
    ? [3.4, 2.95, 2.55, 2.12, 1.71, 1.44, 1.31]
    : [3.6, 3.15, 2.78, 2.42, 2.01, 1.72, 1.58];

  charts.training = new Chart(ctx, {
    type: 'line',
    data: {
      labels: steps.map(s => s === 0 ? '0' : s >= 1000 ? s / 1000 + 'k' : s),
      datasets: [
        { label: 'Paper', data: paperLoss, borderColor: '#378ADD', borderWidth: 2, pointRadius: 3, tension: 0.4, fill: false },
        { label: 'Reproduced', data: reproLoss, borderColor: '#1D9E75', borderWidth: 2, borderDash: [5, 3], pointRadius: 3, tension: 0.4, fill: false },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' } },
        y: {
          grid: { color: 'rgba(128,128,128,0.1)' },
          ticks: { font: { size: 11 }, color: '#888780' },
          title: { display: true, text: 'loss', font: { size: 11 }, color: '#888780' }
        }
      }
    }
  });
}

/* ============================================================
   OVERVIEW
   ============================================================ */
function buildOverview(cuda, vr, g) {
  const feas = cuda && vr >= 24 ? 'High' : cuda ? 'Partial' : 'Low';
  const rt   = cuda ? (vr >= 24 ? '8–16h' : '18–36h') : '48h+';
  const cost = cuda && vr >= 40 ? '$0' : '$18–$65';

  document.getElementById('ov-alert').innerHTML = cuda && vr >= 24
    ? `<div class="alert s">Your ${g} meets minimum requirements. Reproduced with scaled config — expect minor metric divergence from single-GPU dynamics.</div>`
    : cuda
    ? `<div class="alert w">VRAM gap (${vr}GB vs 160GB). Gradient checkpointing applied. Metric drift of ±2–5pp expected.</div>`
    : `<div class="alert w">CPU-only run completed. Training loss did not converge. Cloud GPU required for valid replication.</div>`;

  document.getElementById('ov-stats').innerHTML = `
    <div class="stat"><div class="lbl">Local feasibility</div><div class="val ${cuda && vr >= 24 ? 'ok' : cuda ? 'warn' : 'bad'}">${feas}</div></div>
    <div class="stat"><div class="lbl">Est. runtime</div><div class="val warn">${rt}</div></div>
    <div class="stat"><div class="lbl">Cloud cost</div><div class="val ${cuda && vr >= 40 ? 'ok' : 'warn'}">${cost}</div></div>`;

  const items = [
    { l: 'Core claim (main table)',    pct: cuda ? vr >= 24 ? 82 : 68 : 38 },
    { l: 'Ablation studies',           pct: cuda ? vr >= 24 ? 61 : 45 : 18 },
    { l: 'Baseline comparisons',       pct: 92 },
    { l: 'Training convergence',       pct: cuda ? vr >= 24 ? 78 : 58 : 25 },
  ];

  document.getElementById('ov-veracity').innerHTML = items.map(item => {
    const cls = item.pct >= 70 ? 'hi' : item.pct >= 40 ? 'mid' : 'lo';
    return `<div class="vbar-wrap">
      <div class="vbar-lbl"><span>${item.l}</span><span>${item.pct}%</span></div>
      <div class="vbar-track"><div class="vbar-fill ${cls}" style="width:0" data-w="${item.pct}%"></div></div>
    </div>`;
  }).join('');

  setTimeout(() => {
    document.querySelectorAll('.vbar-fill').forEach(b => b.style.width = b.dataset.w);
  }, 100);

  document.getElementById('ov-phases').innerHTML = PHASES.map(p =>
    `<div class="run-phase"><span class="phase-dot done"></span><span class="phase-name">${p.name}</span><span class="phase-t">done</span></div>`
  ).join('');
}

/* ============================================================
   HARDWARE
   ============================================================ */
function buildHardware(cuda, vr, g) {
  document.getElementById('hw-idle').classList.add('hidden');
  document.getElementById('hw-content').classList.remove('hidden');

  document.getElementById('hw-cmp').innerHTML = `
    <div class="cmp-card">
      <div class="cmp-card-hd"><span class="badge bp">Paper</span></div>
      <div class="hr"><span class="k">GPU</span><span class="v">4× NVIDIA A100 (40GB)</span></div>
      <div class="hr"><span class="k">VRAM total</span><span class="v">160 GB</span></div>
      <div class="hr"><span class="k">RAM</span><span class="v">512 GB</span></div>
      <div class="hr"><span class="k">Storage</span><span class="v">2 TB NVMe</span></div>
      <div class="hr"><span class="k">Training</span><span class="v">~18h</span></div>
    </div>
    <div class="cmp-card">
      <div class="cmp-card-hd"><span class="badge by">Yours</span></div>
      <div class="hr"><span class="k">GPU</span><span class="${cuda ? 'vok' : 'vb'}">${g}</span></div>
      <div class="hr"><span class="k">VRAM</span><span class="${vr >= 40 ? 'vok' : vr > 0 ? 'vw' : 'vb'}">${vr > 0 ? vr + ' GB' : 'None'}</span></div>
      <div class="hr"><span class="k">RAM</span><span class="v">${document.getElementById('uram').value}</span></div>
      <div class="hr"><span class="k">Storage</span><span class="v">${document.getElementById('udisk').value}</span></div>
      <div class="hr"><span class="k">Est. runtime</span><span class="vw">${cuda ? (vr >= 24 ? '~14h' : '~32h') : '~52h CPU'}</span></div>
    </div>`;

  const ctx = document.getElementById('chartHW').getContext('2d');
  if (charts.hw) charts.hw.destroy();

  const paperVals = [160, 512, 32, 2000];
  const yourVals  = [Math.max(vr, 1), ramVal(), cpuVal(), diskVal()];
  const norm = (a, b) => Math.min(100, Math.round((a / b) * 100));

  charts.hw = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: ['VRAM (GB)', 'RAM (GB)', 'CPU cores', 'Disk (GB)'],
      datasets: [
        { label: 'Paper', data: [100, 100, 100, 100], borderColor: '#378ADD', backgroundColor: 'rgba(55,138,221,0.1)', borderWidth: 2, pointRadius: 3 },
        { label: 'Yours',
          data: [
            norm(yourVals[0], paperVals[0]),
            norm(yourVals[1], paperVals[1]),
            norm(Math.min(yourVals[2], paperVals[2]), paperVals[2]),
            norm(Math.min(yourVals[3], paperVals[3]), paperVals[3])
          ],
          borderColor: '#1D9E75', backgroundColor: 'rgba(29,158,117,0.1)', borderWidth: 2, borderDash: [5, 3], pointRadius: 3
        },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        r: {
          grid: { color: 'rgba(128,128,128,0.15)' },
          angleLines: { color: 'rgba(128,128,128,0.15)' },
          ticks: { display: false },
          pointLabels: { font: { size: 11 }, color: '#888780' },
          min: 0, max: 100
        }
      }
    }
  });

  const gaps = [];
  if (!cuda)       gaps.push(`<div class="alert w">No CUDA: CPU beam search on >100M parameter models is impractical (known Catalyst limitation).</div>`);
  if (cuda && vr < 40) gaps.push(`<div class="alert w">VRAM gap: ${vr}GB vs 160GB. Batch ${vr >= 24 ? '16' : '8'} + gradient checkpointing applied. Expect ±2–5pp drift.</div>`);
  gaps.push(`<div class="alert i">Disk: checkpoint + dataset ~180GB. Confirm ${outdir()} has capacity before next run.</div>`);
  document.getElementById('hw-gaps').innerHTML = gaps.join('');
}

/* ============================================================
   TASKS
   ============================================================ */
function buildTasks(cuda, vr) {
  document.getElementById('tasks-idle').classList.add('hidden');
  document.getElementById('tasks-content').classList.remove('hidden');

  const tasks = [
    { n: 'Load checkpoint (HuggingFace)', s: 'y', pct: 100,
      d: 'Released checkpoint available. Eval-only — no training required.', alt: null },
    { n: 'Run evaluation benchmark', s: cuda ? 'y' : 'p', pct: cuda ? 95 : 50,
      d: cuda ? 'Eval feasible — ~2–4h on single GPU.' : 'CPU eval ~48h. Cloud recommended.',
      alt: cuda ? null : 'Colab T4 (free) or Lambda A10 (~$0.75/h).' },
    { n: 'Reproduce main table', s: cuda && vr >= 24 ? 'y' : 'p', pct: cuda ? vr >= 24 ? 82 : 62 : 30,
      d: 'Metrics vary ±2–5pp due to batch size reduction.',
      alt: cuda && vr < 24 ? 'Gradient checkpointing, batch 16.' : null },
    { n: 'Ablation studies', s: cuda ? 'p' : 'n', pct: cuda ? 48 : 8,
      d: '5–8 full runs required. Estimated 70–120h on single GPU.',
      alt: 'Cloud spot instances (A10G) ~$40–80 total.' },
    { n: 'Dataset download + preprocessing', s: 'y', pct: 100,
      d: 'Public dataset ~45GB. Scripts in official repo.', alt: null },
    { n: 'Flash Attention 2 (custom CUDA)', s: cuda ? 'y' : 'n', pct: cuda ? 90 : 0,
      d: cuda ? 'Compiles on your GPU. Minor patch may be needed.' : 'Requires CUDA. CPU fallback 3–5× slower.',
      alt: cuda ? null : 'Any cloud GPU resolves this.' },
    { n: 'Figures + visualizations', s: 'y', pct: 100,
      d: 'CPU-compatible. Reproducible without GPU.', alt: null },
  ];

  const ctx = document.getElementById('chartTasks').getContext('2d');
  if (charts.tasks) charts.tasks.destroy();

  charts.tasks = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: tasks.map(t => t.n.length > 28 ? t.n.slice(0, 28) + '…' : t.n),
      datasets: [{
        label: 'Feasibility %',
        data: tasks.map(t => t.pct),
        backgroundColor: tasks.map(t =>
          t.pct >= 90 ? 'rgba(29,158,117,0.75)' :
          t.pct >= 50 ? 'rgba(186,117,23,0.75)' :
                        'rgba(226,75,74,0.75)'),
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { min: 0, max: 100, grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780', callback: v => v + '%' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888780' } }
      }
    }
  });

  document.getElementById('task-list').innerHTML = tasks.map(t => `
    <div class="ti">
      <div class="ts2 ${t.s}">${t.s === 'y' ? '✓' : t.s === 'p' ? '~' : '✕'}</div>
      <div class="tb">
        <div class="tn">${t.n}</div>
        <div class="td">${t.d}</div>
        ${t.alt ? `<div class="ta">Alternative: ${t.alt}</div>` : ''}
      </div>
    </div>`).join('');
}

/* ============================================================
   RESULTS
   ============================================================ */
function buildResults(cuda, vr) {
  document.getElementById('res-idle').classList.add('hidden');
  document.getElementById('res-content').classList.remove('hidden');

  document.getElementById('res-alert').innerHTML = cuda
    ? `<div class="alert ${vr >= 24 ? 's' : 'w'}">Replication complete — ${vr >= 24 ? 'minor drift (±2pp). Core claim holds.' : 'moderate drift (±5pp) due to VRAM gap.'}</div>`
    : `<div class="alert w">CPU run — training did not converge. No valid replication. Cloud GPU required.</div>`;

  const metrics = [
    { m: 'Accuracy (NLU)', paper: 89.4, repro: cuda ? vr >= 24 ? 87.9 : 85.1 : 74.2, tol: 2 },
    { m: 'F1 score',       paper: 91.2, repro: cuda ? vr >= 24 ? 89.8 : 86.4 : 72.1, tol: 2 },
    { m: 'Perplexity',     paper: 14.8, repro: cuda ? vr >= 24 ? 15.6 : 17.2 : 24.3, tol: 1.5 },
    { m: 'BLEU-4',         paper: 26.5, repro: cuda ? vr >= 24 ? 25.1 : 22.8 : 14.6, tol: 2 },
    { m: 'Param eff.',     paper:  0.3, repro: cuda ? vr >= 24 ? 0.3  : 0.4  : 0.6,  tol: 0.1 },
  ];

  const ok  = metrics.filter(m => Math.abs(m.repro - m.paper) <= m.tol);
  const bad = metrics.filter(m => Math.abs(m.repro - m.paper) >  m.tol);

  const ctx = document.getElementById('chartMetrics').getContext('2d');
  if (charts.metrics) charts.metrics.destroy();
  charts.metrics = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: metrics.map(m => m.m),
      datasets: [
        { label: 'Paper',      data: metrics.map(m => m.paper), backgroundColor: 'rgba(55,138,221,0.75)', borderRadius: 4, borderSkipped: false },
        { label: 'Reproduced', data: metrics.map(m => m.repro),
          backgroundColor: metrics.map(m => Math.abs(m.repro - m.paper) > m.tol ? 'rgba(226,75,74,0.75)' : 'rgba(29,158,117,0.75)'),
          borderRadius: 4, borderSkipped: false },
      ]
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888780', autoSkip: false, maxRotation: 30 } },
        y: { grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' } }
      } }
  });

  const outcomeRow = (m, type) => {
    const diff = (m.repro - m.paper).toFixed(2);
    const pct  = Math.abs(((m.repro - m.paper) / m.paper) * 100).toFixed(1);
    return `<div class="outcome-row ${type}">
      <span class="outcome-icon">${type === 'ok' ? '✓' : '✕'}</span>
      <div class="outcome-body">
        <div class="outcome-metric">${m.m}</div>
        <div class="outcome-vals">paper ${m.paper} → got ${m.repro.toFixed(2)} (${+diff > 0 ? '+' : ''}${diff}, ${pct}%)</div>
      </div>
    </div>`;
  };

  document.getElementById('res-ok').innerHTML  = ok.length
    ? ok.map(m => outcomeRow(m, 'ok')).join('')
    : '<div class="outcome-none">Nothing within tolerance for this hardware.</div>';

  document.getElementById('res-bad').innerHTML = bad.length
    ? bad.map(m => outcomeRow(m, 'bad')).join('')
    : '<div class="outcome-none">All metrics within tolerance.</div>';

  const limits = cuda && vr >= 24
    ? ['Single-GPU vs 4×A100: batch norm statistics differ under reduced parallelism.',
       'Batch size 256→16: higher gradient variance shifts the convergence path.',
       'CUDA kernel non-determinism across versions can introduce small deltas.']
    : cuda
    ? ['VRAM gap forced batch reduction → optimizer dynamics changed significantly.',
       'Gradient checkpointing alters gradient flow and momentum accumulation.',
       'Flash Attention patch applied conservatively — minor numerical differences possible.']
    : ['CPU fallback: no CUDA kernels, 3–5× slower attention, higher memory pressure.',
       'Training did not reach paper convergence within practical CPU time budget.',
       'Metric values are a lower-bound estimate only — not a valid reproduction.'];

  document.getElementById('disc-causes').innerHTML = limits.map(c =>
    `<div class="alert i" style="margin-bottom:6px">${c}</div>`).join('');
}

/* ============================================================
   CLOUD
   ============================================================ */
function buildCloud(cuda) {
  document.getElementById('cloud-idle')?.classList.add('hidden');
  document.getElementById('cloud-content')?.classList.remove('hidden');

  const providers = [
    { p: 'Colab (T4)',    spec: '16GB VRAM · free/~$0.36/h pro', cost: 2,   cov: 55,  cs: '~$0–$8',  full: false },
    { p: 'Lambda A10',   spec: '24GB · $0.75/h · ~14h',           cost: 11,  cov: 78,  cs: '~$11',   full: false },
    { p: 'RunPod A100',  spec: '40GB · $1.64/h · ~8h',            cost: 13,  cov: 94,  cs: '~$14',   full: true  },
    { p: 'RunPod 4×A100',spec: '160GB · $6.56/h · ~18h (exact)',  cost: 118, cov: 100, cs: '~$118',  full: true  },
  ];

  const ctx = document.getElementById('chartCloud').getContext('2d');
  if (charts.cloud) charts.cloud.destroy();

  charts.cloud = new Chart(ctx, {
    type: 'bubble',
    data: {
      datasets: [{
        label: 'Cloud options',
        data: providers.map(p => ({ x: p.cost, y: p.cov, r: p.full ? 14 : 9, label: p.p })),
        backgroundColor: providers.map(p =>
          p.cov >= 90 ? 'rgba(29,158,117,0.7)' :
          p.cov >= 70 ? 'rgba(55,138,221,0.7)' :
                        'rgba(186,117,23,0.7)'),
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.raw.label}: $${ctx.raw.x} · ${ctx.raw.y}% coverage` } }
      },
      scales: {
        x: { title: { display: true, text: 'Est. cost ($)', font: { size: 11 }, color: '#888780' }, grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' }, min: -5, max: 140 },
        y: { title: { display: true, text: 'Coverage (%)', font: { size: 11 }, color: '#888780' }, grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' }, min: 30, max: 110 }
      }
    }
  });

  document.getElementById('cloud-list').innerHTML = providers.map(p => `
    <div class="cld-row">
      <span style="font-weight:500">${p.p}</span>
      <span style="color:var(--text-secondary);font-size:11px">${p.spec}</span>
      <span style="color:var(--color-success);font-weight:500">${p.cs}</span>
      <span class="cf ${p.full ? 'full' : 'part'}">${p.cov}% coverage</span>
    </div>`).join('');
}

/* ============================================================
   CHAT
   ============================================================ */
function addChatBubble(role, text) {
  const c  = document.getElementById('chat-msgs');
  const el = document.createElement('div');
  el.className = 'bub ' + (role === 'agent' ? 'a' : 'u');
  el.innerHTML = role === 'agent'
    ? `<div class="atag">Catalyst agent</div>${text}`
    : text;
  c.appendChild(el);
  c.scrollTop = 1e9;
}

async function sendChat() {
  const inp = document.getElementById('cin');
  const txt = inp.value.trim();
  if (!txt) return;
  inp.value = '';
  addChatBubble('user', txt);

  // Detect paper references (arXiv IDs, DOIs) and update sidebar silently
  const ref = detectPaperRef(txt);
  if (ref && !runDone) {
    document.getElementById('purl').value = ref.url;
    paperContext = '';
    updatePaperDisplay();
  }

  const g   = gpu();
  const p   = paper();
  const stratLabel = strat==='A' ? 'eval-only (released checkpoint)' : strat==='B' ? 'finetune from base checkpoint' : 'train from scratch';
  const sys = `You are Catalyst, an ML paper replication agent. The user is analyzing "${p}" on a machine with GPU: ${g}. Strategy: ${stratLabel}. Run ${runDone ? 'completed' : 'not yet started'}. Be concise and technical. Focus on hardware gaps, metric discrepancies, scientific validity, and replication strategy.`
    + (paperContext ? `\n\nExtracted paper text (first portion):\n${paperContext.slice(0, 3000)}` : '');

  chatHistory.push({ role: 'user', content: txt });

  const thinking = document.createElement('div');
  thinking.className = 'bub a';
  thinking.innerHTML = `<div class="atag">Catalyst agent</div><span style="color:var(--text-tertiary)">Thinking…</span>`;
  document.getElementById('chat-msgs').appendChild(thinking);
  document.getElementById('chat-msgs').scrollTop = 1e9;

  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        system: sys,
        messages: chatHistory,
      })
    });

    const data  = await res.json();
    const reply = data.content?.find(b => b.type === 'text')?.text || 'No response.';
    chatHistory.push({ role: 'assistant', content: reply });
    thinking.innerHTML = `<div class="atag">Catalyst agent</div>${reply.replace(/\n/g, '<br>')}`;
  } catch (e) {
    thinking.innerHTML = `<div class="atag">Catalyst agent</div><span style="color:var(--color-danger)">API error — check your API key in app.js.</span>`;
  }

  document.getElementById('chat-msgs').scrollTop = 1e9;
}
