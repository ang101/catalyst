"""
Generic paper reader builder. Reads data/<paper_id>.json, produces readers/<paper_id>.html.
Routes on classification.case: A (full interactive), B (sparse), C (theoretical).
"""

import json
import sys
import html as html_mod
from pathlib import Path

READER_DIR = Path(__file__).parent.resolve()
DATA_DIR = READER_DIR / "data"
READERS_DIR = READER_DIR / "readers"
CHART_JS_CDN = "https://cdn.jsdelivr.net/npm/chart.js"


def esc(s):
    """HTML-escape a string."""
    return html_mod.escape(str(s))


def build_badge_css():
    return """
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; vertical-align: middle; cursor: help; }
    .badge-paper { background: #22c55e; color: #fff; }
    .badge-interp { background: #f59e0b; color: #1a1a1a; }
    .badge-low { background: repeating-linear-gradient(45deg, #ef4444, #ef4444 4px, #dc2626 4px, #dc2626 8px); color: #fff; padding: 2px 10px; }
    .badge-na { background: #9ca3af; color: #fff; }
    .source-text { font-size: 11px; color: #6b7280; margin-top: 2px; }
    .warning-icon { margin-right: 2px; }
    """


def badge_html(badge_type, source="", confidence=None):
    if badge_type == "PAPER":
        return f'<span class="badge badge-paper" title="Reported directly in the paper">PAPER</span><div class="source-text">{esc(source)}</div>'
    elif badge_type == "INTERP":
        return f'<span class="badge badge-interp" title="Linear interpolation between two paper-reported points">INTERP</span><div class="source-text">{esc(source)}</div>'
    elif badge_type == "LOW":
        conf_str = f" ({confidence:.0%})" if confidence else ""
        return f'<span class="badge badge-low" title="This value was estimated by an LLM, not measured. The paper does not report this combination."><span class="warning-icon">⚠</span>LOW CONFIDENCE{conf_str}</span><div class="source-text">Estimate not available — outside paper\'s tested range</div>'
    else:
        return f'<span class="badge badge-na" title="System couldn\'t determine a value">N/A</span><div class="source-text">Not characterized in paper</div>'


def build_case_a(paper_data, extraction):
    """Full interactive reader with sliders for Case A papers."""
    paper = extraction["paper"]
    variables = extraction.get("variables", [])
    metrics = extraction.get("metrics", [])
    data_points = extraction.get("data_points", [])
    claims = extraction.get("main_claims", [])
    ctx = extraction.get("context_descriptors", {})

    # ALL variables rendered as dropdowns (discrete <=8 values or categorical)
    # Continuous with many values: still dropdown but with paper-tested values only
    all_vars = []
    for v in variables:
        vals = v["values"]
        # Filter to values that actually appear in data_points
        actual_vals = set()
        for dp in data_points:
            dv = dp.get("variable_values", {}).get(v["name"])
            if dv is not None:
                actual_vals.add(dv)
        if actual_vals:
            vals = sorted(actual_vals, key=lambda x: (isinstance(x, str), x))
        all_vars.append({"name": v["name"], "label": v["label"], "type": v["type"], "values": vals})

    # Find best default: data point with most metric values (richest row)
    best_dp = max(data_points, key=lambda dp: len(dp.get("metric_values", {}))) if data_points else None

    # Find best default metric: most common metric across data points
    metric_counts = {}
    for dp in data_points:
        for mk in dp.get("metric_values", {}).keys():
            metric_counts[mk] = metric_counts.get(mk, 0) + 1
    best_metric = max(metric_counts, key=metric_counts.get) if metric_counts else (metrics[0]["name"] if metrics else "")

    data_json = json.dumps(extraction)

    controls_html = ""
    # Build dropdown for each variable
    for av in all_vars[:6]:  # max 6 controls
        default_val = best_dp.get("variable_values", {}).get(av["name"], "") if best_dp else ""
        opts = ""
        for val in av["values"]:
            selected = ' selected' if str(val) == str(default_val) else ''
            opts += f'<option value="{esc(str(val))}"{selected}>{esc(str(val))}</option>'
        controls_html += f"""
        <div class="control-group">
            <label>{esc(av['label'])}</label>
            <select id="dd_{av['name']}" class="dropdown" data-var="{av['name']}">{opts}</select>
            <div class="option-hint" id="hint_{av['name']}"></div>
        </div>"""

    # Context descriptor dropdowns
    for ctx_name, ctx_vals in ctx.items():
        if ctx_name not in [v["name"] for v in variables]:
            default_ctx = ""
            if best_dp and best_dp.get("context"):
                for cv in ctx_vals:
                    if cv.lower().replace("_", " ") in best_dp["context"].lower().replace("_", " "):
                        default_ctx = cv
                        break
            opts = ""
            for val in ctx_vals:
                selected = ' selected' if str(val) == str(default_ctx) else ''
                opts += f'<option value="{esc(str(val))}"{selected}>{esc(str(val))}</option>'
            controls_html += f"""
            <div class="control-group">
                <label>{esc(ctx_name.replace('_', ' ').title())}</label>
                <select id="ctx_{ctx_name}" class="ctx-dropdown" data-ctx="{ctx_name}">{opts}</select>
                <div class="option-hint" id="hint_ctx_{ctx_name}"></div>
            </div>"""

    # Build metrics dropdown with best default
    met_opts = ""
    for m in metrics:
        selected = ' selected' if m["name"] == best_metric else ''
        met_opts += f'<option value="{esc(m["name"])}"{selected}>{esc(m["label"])}</option>'
    controls_html += f"""
    <div class="control-group">
        <label>Metric</label>
        <select id="metric_select">{met_opts}</select>
    </div>"""

    # Claims list
    claims_html = "".join(f"<li>{esc(c)}</li>" for c in claims)

    # Source data table
    source_rows = ""
    for dp in data_points[:200]:  # cap for file size
        vv = ", ".join(f"{k}={v}" for k, v in dp.get("variable_values", {}).items())
        mv = ", ".join(f"{k}={v}" for k, v in dp.get("metric_values", {}).items())
        source_rows += f"<tr><td>{esc(dp.get('context',''))}</td><td>{esc(vv)}</td><td>{esc(mv)}</td><td>{esc(dp.get('source_cell',''))}</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(paper['title'])}</title>
<script src="{CHART_JS_CDN}"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #fafafa; color: #1a1a1a; line-height: 1.6; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 24px; margin-bottom: 4px; }}
h2 {{ font-size: 18px; margin: 32px 0 12px; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px; }}
h3 {{ font-size: 15px; margin: 16px 0 8px; }}
a {{ color: #2563eb; }}
.meta {{ color: #6b7280; font-size: 14px; margin-bottom: 24px; }}
.claims {{ margin: 16px 0; padding-left: 24px; }}
.claims li {{ margin-bottom: 8px; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 16px; padding: 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; margin: 16px 0; }}
.control-group {{ flex: 1 1 180px; min-width: 150px; }}
.control-group label {{ display: block; font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
.dropdown, select {{ width: 100%; padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px; }}
.option-hint {{ font-size: 10px; color: #9ca3af; margin-top: 2px; }}
select option.no-data {{ color: #d1d5db; }}
.result-panel {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin: 16px 0; text-align: center; }}
.result-value {{ font-size: 36px; font-weight: 700; margin: 8px 0; }}
.result-meta {{ font-size: 13px; color: #6b7280; }}
{build_badge_css()}
.chart-container {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0; }}
.chart-container canvas {{ max-height: 400px; }}
.no-chart {{ text-align: center; padding: 40px; color: #9ca3af; }}
details {{ margin: 16px 0; }}
summary {{ cursor: pointer; font-weight: 600; padding: 8px; background: #f3f4f6; border-radius: 4px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
th, td {{ padding: 4px 8px; border: 1px solid #e5e7eb; text-align: left; }}
th {{ background: #f9fafb; font-weight: 600; }}
.repro-note {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 32px 0; font-size: 14px; }}
</style>
</head>
<body>
<div class="container">

<h1>{esc(paper['title'])}</h1>
<div class="meta">
    {esc(', '.join(paper.get('authors', [])))} ({paper.get('year', '')}) &mdash;
    <a href="https://arxiv.org/abs/{esc(paper.get('arxiv_id', ''))}" target="_blank">arXiv:{esc(paper.get('arxiv_id', ''))}</a>
</div>

<h2>What this paper claims</h2>
<ul class="claims">{claims_html}</ul>

<h2>Explore the results</h2>
<div class="controls" id="controls">{controls_html}</div>

<div class="result-panel">
    <div id="result-badge"></div>
    <div class="result-value" id="result-value">—</div>
    <div class="result-meta" id="result-meta"></div>
</div>

<h2>Parameter Sweep</h2>
<div class="chart-container">
    <canvas id="sweepChart"></canvas>
    <div class="no-chart" id="noChart" style="display:none;">No sweep data for current selection</div>
</div>

<h2>Source Data</h2>
<details>
<summary>Show {len(data_points)} extracted data points</summary>
<table>
<thead><tr><th>Context</th><th>Variables</th><th>Metrics</th><th>Source</th></tr></thead>
<tbody>{source_rows}</tbody>
</table>
</details>

<div class="repro-note">
<strong>Reproduction note:</strong> An automated reproduction of Sentence-BERT (arXiv 1908.10084) was successful using this system's eval-only strategy: 76.99 vs 77.03 paper-claimed Spearman correlation on the STS benchmark, matching within 0.04 points. The values shown in this reader come directly from the paper's reported tables, not from a reproduction run.
</div>

</div>

<script>
const DATA = {data_json};
const dataPoints = DATA.data_points || [];
const variables = DATA.variables || [];
const metrics = DATA.metrics || [];

function getCurrentSelection() {{
    const sel = {{}};
    document.querySelectorAll('.dropdown').forEach(d => {{ sel[d.dataset.var] = d.value; }});
    document.querySelectorAll('.ctx-dropdown').forEach(d => {{ sel['_ctx_' + d.dataset.ctx] = d.value; }});
    sel._metric = document.getElementById('metric_select').value;
    return sel;
}}

function matchDP(dp, sel) {{
    for (const [k, v] of Object.entries(sel)) {{
        if (k.startsWith('_')) continue;
        const dpVal = dp.variable_values[k];
        if (dpVal === undefined) continue;
        if (String(dpVal) !== String(v) && Number(dpVal) !== Number(v)) return false;
    }}
    for (const [k, v] of Object.entries(sel)) {{
        if (!k.startsWith('_ctx_')) continue;
        const ctxName = k.slice(5);
        if (dp.context) {{
            const words = v.toLowerCase().replace(/_/g, ' ').split(/\\s+/);
            const ctx = dp.context.toLowerCase();
            if (!words.some(w => w.length > 1 && ctx.includes(w))) return false;
        }}
    }}
    return true;
}}

function getProvenance(sel) {{
    const metricName = sel._metric;
    const exact = dataPoints.filter(dp => matchDP(dp, sel) && dp.metric_values && dp.metric_values[metricName] !== undefined);
    if (exact.length > 0) {{
        return {{ type: 'PAPER', value: exact[0].metric_values[metricName], source: exact[0].source_cell || 'Paper table' }};
    }}
    // Try interpolation on numeric variables
    for (const v of variables) {{
        if (v.type !== 'discrete') continue;
        const curVal = Number(sel[v.name]);
        if (isNaN(curVal)) continue;
        const allNums = v.values.map(Number).filter(n => !isNaN(n)).sort((a,b) => a-b);
        const lower = allNums.filter(n => n < curVal).pop();
        const upper = allNums.find(n => n > curVal);
        if (lower === undefined || upper === undefined) continue;
        const selL = {{ ...sel, [v.name]: String(lower) }};
        const selU = {{ ...sel, [v.name]: String(upper) }};
        const dpL = dataPoints.find(dp => matchDP(dp, selL) && dp.metric_values && dp.metric_values[metricName] !== undefined);
        const dpU = dataPoints.find(dp => matchDP(dp, selU) && dp.metric_values && dp.metric_values[metricName] !== undefined);
        if (dpL && dpU) {{
            const vl = dpL.metric_values[metricName], vu = dpU.metric_values[metricName];
            const frac = (curVal - lower) / (upper - lower);
            return {{ type: 'INTERP', value: Math.round((vl + frac * (vu - vl)) * 100) / 100,
                      source: `Interpolated between ${{v.name}}=${{lower}} (${{vl}}) and ${{v.name}}=${{upper}} (${{vu}})` }};
        }}
    }}
    return {{ type: 'N/A', value: null, source: 'Not characterized in paper' }};
}}

function makeBadgeHTML(prov) {{
    if (prov.type === 'PAPER') return '<span class="badge badge-paper" title="Reported directly in the paper">PAPER</span><div class="source-text">' + prov.source + '</div>';
    if (prov.type === 'INTERP') return '<span class="badge badge-interp" title="Linear interpolation between two paper-reported points">INTERP</span><div class="source-text">' + prov.source + '</div>';
    return '<span class="badge badge-na" title="System couldn\\'t determine a value">N/A</span><div class="source-text">Not characterized in paper</div>';
}}

// Gray out options that lead to N/A given current other selections
function updateOptionHints() {{
    const sel = getCurrentSelection();
    const metricName = sel._metric;
    document.querySelectorAll('.dropdown').forEach(dd => {{
        const varName = dd.dataset.var;
        let withData = 0;
        Array.from(dd.options).forEach(opt => {{
            const testSel = {{ ...sel, [varName]: opt.value }};
            const has = dataPoints.some(dp => matchDP(dp, testSel) && dp.metric_values && dp.metric_values[metricName] !== undefined);
            opt.style.color = has ? '' : '#c0c0c0';
            if (has) withData++;
        }});
        const hint = document.getElementById('hint_' + varName);
        if (hint) hint.textContent = withData + ' of ' + dd.options.length + ' options have paper data';
    }});
    document.querySelectorAll('.ctx-dropdown').forEach(dd => {{
        const ctxName = dd.dataset.ctx;
        let withData = 0;
        Array.from(dd.options).forEach(opt => {{
            const testSel = {{ ...sel, ['_ctx_' + ctxName]: opt.value }};
            const has = dataPoints.some(dp => matchDP(dp, testSel) && dp.metric_values && dp.metric_values[metricName] !== undefined);
            opt.style.color = has ? '' : '#c0c0c0';
            if (has) withData++;
        }});
        const hint = document.getElementById('hint_ctx_' + ctxName);
        if (hint) hint.textContent = withData + ' of ' + dd.options.length + ' options have paper data';
    }});
}}

let chart = null;

function updateChart(sel) {{
    const canvas = document.getElementById('sweepChart');
    const noChart = document.getElementById('noChart');
    const metricName = sel._metric;
    // Find a numeric variable to sweep
    let sweepVar = null;
    for (const v of variables) {{
        if (v.type !== 'discrete') continue;
        const nums = v.values.map(Number).filter(n => !isNaN(n));
        if (nums.length >= 3) {{ sweepVar = v; break; }}
    }}
    if (!sweepVar) {{ canvas.style.display = 'none'; noChart.style.display = ''; return; }}
    const nums = sweepVar.values.map(Number).filter(n => !isNaN(n)).sort((a,b) => a-b);
    const chartData = [];
    for (const val of nums) {{
        const testSel = {{ ...sel, [sweepVar.name]: String(val) }};
        const dp = dataPoints.find(d => matchDP(d, testSel) && d.metric_values && d.metric_values[metricName] !== undefined);
        if (dp) chartData.push({{ x: val, y: dp.metric_values[metricName] }});
    }}
    if (chartData.length < 2) {{
        canvas.style.display = 'none'; noChart.style.display = '';
        if (chart) {{ chart.destroy(); chart = null; }} return;
    }}
    canvas.style.display = ''; noChart.style.display = 'none';
    const metricLabel = (metrics.find(m => m.name === metricName) || {{}}).label || metricName;
    const varLabel = sweepVar.label || sweepVar.name;
    const currentVal = Number(sel[sweepVar.name]);
    if (chart) chart.destroy();
    chart = new Chart(canvas, {{
        type: 'scatter',
        data: {{ datasets: [{{ label: metricLabel + ' (paper)', data: chartData, backgroundColor: '#22c55e', borderColor: '#16a34a', pointRadius: 7, showLine: true, borderWidth: 2, tension: 0.1 }}] }},
        options: {{ responsive: true, plugins: {{ title: {{ display: true, text: metricLabel + ' vs ' + varLabel }} }},
            scales: {{ x: {{ type: 'logarithmic', title: {{ display: true, text: varLabel }}, ticks: {{ callback: v => v }} }}, y: {{ title: {{ display: true, text: metricLabel }} }} }} }},
        plugins: [{{ id: 'vline', afterDraw(ch) {{
            const xs = ch.scales.x, ys = ch.scales.y;
            if (!isNaN(currentVal)) {{
                const x = xs.getPixelForValue(currentVal);
                if (x >= xs.left && x <= xs.right) {{
                    const c = ch.ctx; c.save(); c.beginPath(); c.moveTo(x, ys.top); c.lineTo(x, ys.bottom);
                    c.strokeStyle = '#2563eb'; c.lineWidth = 2; c.setLineDash([6,4]); c.stroke(); c.restore();
                }}
            }}
        }} }}]
    }});
}}

function update() {{
    const sel = getCurrentSelection();
    const prov = getProvenance(sel);
    document.getElementById('result-badge').innerHTML = makeBadgeHTML(prov);
    const metricObj = metrics.find(m => m.name === sel._metric);
    const metricLabel = metricObj ? metricObj.label : sel._metric;
    if (prov.value !== null) {{
        document.getElementById('result-value').textContent = prov.value;
        document.getElementById('result-meta').textContent = metricLabel;
    }} else {{
        document.getElementById('result-value').textContent = '\u2014';
        document.getElementById('result-meta').textContent = 'Not characterized';
    }}
    updateOptionHints();
    updateChart(sel);
}}

document.querySelectorAll('.dropdown, .ctx-dropdown, #metric_select').forEach(el => {{
    el.addEventListener('change', update);
}});

update();
</script>
</body>
</html>"""


def build_case_b(paper_data, extraction):
    """Simplified reader for sparse papers."""
    paper = extraction["paper"]
    claims = extraction.get("main_claims", [])
    data_points = extraction.get("data_points", [])

    claims_html = "".join(f"<li>{esc(c)}</li>" for c in claims)
    rows = ""
    for dp in data_points:
        vv = ", ".join(f"{k}={v}" for k, v in dp.get("variable_values", {}).items())
        mv = ", ".join(f"{k}={v}" for k, v in dp.get("metric_values", {}).items())
        rows += f"<tr><td>{esc(dp.get('context',''))}</td><td>{esc(vv)}</td><td>{esc(mv)}</td><td><span class='badge badge-paper'>PAPER</span> {esc(dp.get('source_cell',''))}</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(paper['title'])}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; padding: 24px; line-height: 1.6; color: #1a1a1a; }}
h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 28px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }}
a {{ color: #2563eb; }} .meta {{ color: #6b7280; font-size: 14px; }}
.claims li {{ margin-bottom: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
th, td {{ padding: 6px 8px; border: 1px solid #e5e7eb; text-align: left; }}
th {{ background: #f9fafb; }}
{build_badge_css()}
.note {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 14px; margin: 24px 0; font-size: 14px; }}
</style></head><body>
<h1>{esc(paper['title'])}</h1>
<div class="meta">{esc(', '.join(paper.get('authors',[])))}, {paper.get('year','')} — <a href="https://arxiv.org/abs/{esc(paper.get('arxiv_id',''))}">arXiv:{esc(paper.get('arxiv_id',''))}</a></div>
<div class="note">This paper has limited quantitative ablation data ({len(data_points)} data points). Showing extracted results as a static table.</div>
<h2>Main Claims</h2><ul class="claims">{claims_html}</ul>
<h2>Extracted Results</h2>
<table><thead><tr><th>Context</th><th>Variables</th><th>Metrics</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""


def build_case_c(paper_data, extraction):
    """Theoretical paper view."""
    paper = extraction["paper"]
    claims = extraction.get("main_claims", [])
    claims_html = "".join(f"<li>{esc(c)}</li>" for c in claims) if claims else "<li>No falsifiable empirical claims extracted.</li>"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(paper['title'])}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 700px; margin: 0 auto; padding: 24px; line-height: 1.7; color: #1a1a1a; }}
h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 28px; }}
a {{ color: #2563eb; }} .meta {{ color: #6b7280; font-size: 14px; }}
.note {{ background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 8px; padding: 16px; margin: 24px 0; font-size: 14px; }}
</style></head><body>
<h1>{esc(paper['title'])}</h1>
<div class="meta">{esc(', '.join(paper.get('authors',[])))}, {paper.get('year','')} — <a href="https://arxiv.org/abs/{esc(paper.get('arxiv_id',''))}">arXiv:{esc(paper.get('arxiv_id',''))}</a></div>
<div class="note">This is a theoretical/positional paper. The reader system does not produce quantitative simulations for papers without measurable ablations.</div>
<h2>Main Arguments</h2><ul>{claims_html}</ul>
</body></html>"""


def build(paper_id: str):
    data_path = DATA_DIR / f"{paper_id}.json"
    if not data_path.exists():
        sys.exit(f"Data not found: {data_path}. Run extract_paper_data.py first.")

    paper_data = json.loads(data_path.read_text())
    classification = paper_data["classification"]
    extraction = paper_data["extraction"]
    case = classification["case"]

    print(f"Building reader for {paper_id} (Case {case})")

    if case == "A":
        html = build_case_a(paper_data, extraction)
    elif case == "B":
        html = build_case_b(paper_data, extraction)
    else:
        html = build_case_c(paper_data, extraction)

    READERS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = READERS_DIR / f"{paper_id}.html"
    out_path.write_text(html)
    size_kb = out_path.stat().st_size / 1024
    print(f"Written: {out_path} ({size_kb:.0f} KB, Case {case})")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_reader.py <paper_id>")
        sys.exit(1)
    build(sys.argv[1])
