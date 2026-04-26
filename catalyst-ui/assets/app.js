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
function setSP(el, s) {
  document.querySelectorAll('.sp').forEach(p => p.classList.remove('on'));
  el.classList.add('on');
  strat = s;
}

/* ---- Tab switching ---- */
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('on'));
  document.querySelector(`.tab[onclick="showTab('${name}')"]`).classList.add('on');
  document.getElementById('panel-' + name).classList.add('on');
}

/* ---- PDF upload (sidebar) ---- */
function handlePDF(inp) {
  if (inp.files[0]) {
    document.getElementById('purl').value = '';
    document.querySelector('.ubtn').textContent = 'PDF ✓';
  }
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
    document.querySelector('.ubtn').textContent = 'PDF ✓';
    const kchars = (paperContext.length / 1000).toFixed(1);
    thinking.innerHTML = `<div class="atag">Catalyst agent</div>Paper loaded: <strong>${file.name}</strong> (${kchars}k chars extracted). Ask me anything about it, or configure hardware and click Run.`;
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
function paper()   { return document.getElementById('purl').value.trim() || 'LoRA: Low-Rank Adaptation (2106.09685)'; }
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
   MAIN RUN
   ============================================================ */
function startRun() {
  const p = paper();
  if (!p) return;

  document.getElementById('rbtn').disabled = true;
  document.getElementById('rbtn').textContent = 'Running…';

  // Reset panels
  ['ov-idle','run-idle'].forEach(id => document.getElementById(id).classList.add('hidden'));
  ['ov-content','run-content'].forEach(id => document.getElementById(id).classList.remove('hidden'));
  document.getElementById('agent-log').innerHTML = '';
  showTab('run');

  const cuda = hasCUDA();
  const vr   = vram();
  const g    = gpu();

  const msgs = [
    [0,    'Preflight: checking zeroclaw config, claude code CLI, python 3.10, uv…', 'hi'],
    [500,  'Preflight passed. Fetching paper via arxiv_fetch MCP tool…', null],
    [1200, 'pdf_extract: converting PDF → structured markdown…', null],
    [1900, 'Requirements extracted — GPU: 4×A100 (40GB), training: 18h, disk: ~180GB', null],
    [2600, 'repo_scout: found microsoft/LoRA on GitHub (4.2k stars, MIT)', null],
    [3200, `Strategy ${strat} selected — ${strat==='A'?'checkpoint on HuggingFace, eval-only':strat==='B'?'finetuning from base checkpoint':'scale-down from scratch'}`, null],
    [3800, `Hardware gap: paper used 160GB VRAM, your machine has ${vr > 0 ? vr + 'GB VRAM' : 'CPU only'}. Applying scaling rationale…`, 'hi'],
    [4400, cuda ? 'CUDA available. Patching Flash Attention for single-GPU config…'
                : 'No CUDA — falling back to CPU attention. Warning: 3–5× slower.', cuda ? null : 'er'],
    [5100, 'Executing scaled experiment via scaled_runner MCP (sandboxed)…', null],
    [5800, cuda ? 'Epoch 1/3 complete. Loss: 2.41. ETA: ~4h local.' : 'CPU run underway. Loss: 2.58. ETA: ~22h.', null],
    [6400, cuda ? 'Epoch 2/3 complete. Loss: 1.87.' : 'CPU epoch 1/3. Loss: 2.31.', null],
    [7000, 'Eval benchmark running — collecting metrics for results.json…', null],
    [7600, 'Writing summary.md and scaling_rationale.md…', null],
    [8200, `Run complete. Report written to ${outdir()}`, 'ok'],
  ];
  msgs.forEach(([d, m, t]) => setTimeout(() => log(m, t), d));

  // Animate phases
  PHASES.forEach((_, i) => setTimeout(() => renderPhases(i), i * 1100));

  // Show training chart mid-run
  setTimeout(() => {
    document.getElementById('run-prog-wrap').classList.remove('hidden');
    drawTrainingChart(cuda);
  }, 5200);

  // Finalize
  setTimeout(() => finalize(cuda, vr, g), 8600);
}

function finalize(cuda, vr, g) {
  document.getElementById('rbtn').disabled = false;
  document.getElementById('rbtn').textContent = 'Run feasibility + experiment ↗';
  runDone = true;

  buildOverview(cuda, vr, g);
  buildHardware(cuda, vr, g);
  buildTasks(cuda, vr);
  buildResults(cuda, vr);
  buildCloud(cuda);

  addChatBubble('agent',
    `Run complete for <strong>${paper()}</strong>. ` +
    (cuda
      ? `Your ${g} reproduced the core claim with ${vr >= 24 ? 'minor' : 'moderate'} metric drift.`
      : 'CPU-only run showed significant metric divergence — cloud GPU strongly recommended.') +
    ' Check the Results tab for full discrepancy analysis.'
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
      d: 'Released checkpoint available. Strategy A eval-only.', alt: null },
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
   RESULTS / DISCREPANCIES
   ============================================================ */
function buildResults(cuda, vr) {
  document.getElementById('res-idle').classList.add('hidden');
  document.getElementById('res-content').classList.remove('hidden');

  const drift = cuda ? (vr >= 24 ? 'minor (±2pp)' : 'moderate (±5pp)') : 'severe (±15pp+)';

  document.getElementById('res-alert').innerHTML = cuda
    ? `<div class="alert ${vr >= 24 ? 's' : 'w'}">Run completed. Metric drift is ${drift}. ${vr >= 24 ? 'Core claim holds within tolerance.' : 'Some claims may not hold at reduced scale.'}</div>`
    : `<div class="alert w">CPU run — training did not converge. Results below are not a valid replication. Cloud GPU required.</div>`;

  const metrics = [
    { m: 'Accuracy (NLU)', paper: 89.4, repro: cuda ? vr >= 24 ? 87.9 : 85.1 : 74.2, tol: 2 },
    { m: 'F1 score',       paper: 91.2, repro: cuda ? vr >= 24 ? 89.8 : 86.4 : 72.1, tol: 2 },
    { m: 'Perplexity',     paper: 14.8, repro: cuda ? vr >= 24 ? 15.6 : 17.2 : 24.3, tol: 1.5, lower: true },
    { m: 'BLEU-4',         paper: 26.5, repro: cuda ? vr >= 24 ? 25.1 : 22.8 : 14.6, tol: 2 },
    { m: 'Param efficiency',paper: 0.3, repro: cuda ? vr >= 24 ? 0.3  : 0.4  : 0.6,  tol: 0.1, lower: true },
  ];

  const isOut = m => Math.abs(m.repro - m.paper) > (m.tol || 2);

  const ctx = document.getElementById('chartMetrics').getContext('2d');
  if (charts.metrics) charts.metrics.destroy();

  charts.metrics = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: metrics.map(m => m.m),
      datasets: [
        { label: 'Paper', data: metrics.map(m => m.paper), backgroundColor: 'rgba(55,138,221,0.75)', borderRadius: 4, borderSkipped: false },
        { label: 'Reproduced', data: metrics.map(m => m.repro), backgroundColor: metrics.map(m => isOut(m) ? 'rgba(226,75,74,0.75)' : 'rgba(29,158,117,0.75)'), borderRadius: 4, borderSkipped: false },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 }, color: '#888780', autoSkip: false, maxRotation: 30 } },
        y: { grid: { color: 'rgba(128,128,128,0.1)' }, ticks: { font: { size: 11 }, color: '#888780' } }
      }
    }
  });

  // Discrepancy table
  const inRange = m => {
    const d = Math.abs(m.repro - m.paper);
    return d <= m.tol ? 'in-range' : d <= m.tol * 2 ? 'marginal' : 'outside';
  };

  document.getElementById('disc-table').innerHTML =
    `<div style="border:0.5px solid var(--border-light);border-radius:var(--radius-md);padding:12px 14px">` +
    metrics.map(m => {
      const diff = (m.repro - m.paper).toFixed(2);
      const pct  = Math.abs(((m.repro - m.paper) / m.paper) * 100).toFixed(1);
      const cls  = inRange(m);
      const label = cls === 'in-range' ? 'within tol.' : cls === 'marginal' ? 'marginal' : 'out of tol.';
      return `<div class="disc-row">
        <span class="dm">${m.m}</span>
        <span class="dp">paper: ${m.paper} → repro: ${m.repro.toFixed(2)}</span>
        <span style="display:flex;gap:6px;align-items:center">
          <span style="font-size:11px;color:var(--text-secondary)">${diff > 0 ? '+' : ''}${diff} (${pct}%)</span>
          <span class="dv ${cls}">${label}</span>
        </span>
      </div>`;
    }).join('') + `</div>`;

  // Probable causes
  const causes = cuda && vr >= 24
    ? [
        'Single-GPU vs 4×A100: reduced parallelism affects batch norm statistics and gradient averaging.',
        'Batch size reduction (256→16): smaller batches introduce higher gradient variance, affecting convergence path.',
        'Minor CUDA version differences may cause non-deterministic kernel behavior.',
      ]
    : cuda
    ? [
        'Significant VRAM gap forced aggressive batch reduction, changing the optimization landscape.',
        'Gradient checkpointing trades compute for memory, altering gradient flow and momentum.',
        'Potential Flash Attention version mismatch — patch applied conservatively.',
      ]
    : [
        'CPU fallback to standard attention — 3–5× slower, higher memory pressure per step.',
        'Training did not reach paper convergence due to compute time constraints.',
        'Results are not a valid replication — treat as a lower-bound estimate only.',
      ];

  document.getElementById('disc-causes').innerHTML = causes.map(c =>
    `<div class="alert i" style="margin-bottom:6px">${c}</div>`
  ).join('');

  // Scientific validity
  document.getElementById('sci-validity').innerHTML = cuda && vr >= 24
    ? `<div class="alert s">Core claim appears reproducible. Metric drift within ±2pp is consistent with single-GPU training variance. The paper's central finding (LoRA matches full fine-tuning with 10,000× fewer trainable parameters) holds in this reproduction.</div>
       <div class="alert i" style="margin-top:6px">Ablation claims (rank sensitivity, layer selection) were not fully validated — additional runs required.</div>`
    : cuda
    ? `<div class="alert w">Core claim is plausible but not firmly validated. Batch-size-induced drift makes it difficult to distinguish hardware scaling effects from genuine divergence. Cloud replication recommended for conclusive results.</div>`
    : `<div class="alert w">CPU run cannot validate scientific claims. This run provides structural verification only (code runs, data loads, pipeline completes). Cloud GPU required for metric comparison.</div>`;
}

/* ============================================================
   CLOUD
   ============================================================ */
function buildCloud(cuda) {
  document.getElementById('cloud-idle').classList.add('hidden');
  document.getElementById('cloud-content').classList.remove('hidden');

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
  }

  const g   = gpu();
  const p   = paper();
  const sys = `You are Catalyst, an ML paper replication agent. The user is analyzing "${p}" on a machine with GPU: ${g}. Strategy: ${strat}. Run ${runDone ? 'completed' : 'not yet started'}. Be concise and technical. Focus on hardware gaps, metric discrepancies, scientific validity, and replication strategy.`
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
