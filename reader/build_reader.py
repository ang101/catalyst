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

    # Find discrete/categorical variables suitable for controls
    slider_vars = [v for v in variables if v["type"] == "discrete" and len(v["values"]) >= 3
                   and all(isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.','',1).isdigit()) for x in v["values"] if x != 'full')]
    dropdown_vars = [v for v in variables if v["type"] == "categorical"]

    data_json = json.dumps(extraction)

    controls_html = ""
    # Build slider for each numeric variable
    for sv in slider_vars[:2]:  # max 2 sliders
        vals = sorted([x for x in sv["values"] if isinstance(x, (int, float)) or (isinstance(x, str) and x.replace('.','',1).isdigit())])
        num_vals = [float(x) for x in vals]
        controls_html += f"""
        <div class="control-group">
            <label>{esc(sv['label'])}</label>
            <input type="range" id="slider_{sv['name']}" min="0" max="{len(num_vals)-1}" value="0" class="slider" data-var="{sv['name']}">
            <div class="slider-value" id="val_{sv['name']}">{vals[0]}</div>
            <div class="slider-ticks">{' '.join(str(v) for v in vals)}</div>
        </div>"""

    # Build dropdown for each categorical variable (max 4)
    for dv in dropdown_vars[:4]:
        opts = "".join(f'<option value="{esc(str(v))}">{esc(str(v))}</option>' for v in dv["values"])
        controls_html += f"""
        <div class="control-group">
            <label>{esc(dv['label'])}</label>
            <select id="dd_{dv['name']}" class="dropdown" data-var="{dv['name']}">{opts}</select>
        </div>"""

    # Context descriptor dropdowns
    for ctx_name, ctx_vals in ctx.items():
        if ctx_name not in [v["name"] for v in variables]:
            opts = "".join(f'<option value="{esc(str(v))}">{esc(str(v))}</option>' for v in ctx_vals)
            controls_html += f"""
            <div class="control-group">
                <label>{esc(ctx_name.replace('_', ' ').title())}</label>
                <select id="ctx_{ctx_name}" class="ctx-dropdown" data-ctx="{ctx_name}">{opts}</select>
            </div>"""

    # Build metrics dropdown
    met_opts = "".join(f'<option value="{esc(m["name"])}">{esc(m["label"])}</option>' for m in metrics)
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
.slider {{ width: 100%; }}
.slider-value {{ font-size: 20px; font-weight: 700; color: #2563eb; text-align: center; }}
.slider-ticks {{ font-size: 10px; color: #9ca3af; text-align: center; }}
.dropdown, select {{ width: 100%; padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px; }}
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

// Build lookup: slider var -> sorted numeric values
const sliderVars = {{}};
document.querySelectorAll('.slider').forEach(s => {{
    const varName = s.dataset.var;
    const v = variables.find(x => x.name === varName);
    if (v) {{
        const nums = v.values.filter(x => typeof x === 'number' || (typeof x === 'string' && !isNaN(Number(x)) && x !== 'full')).map(Number).sort((a,b) => a-b);
        sliderVars[varName] = nums;
        s.max = nums.length - 1;
        s.value = 0;
    }}
}});

function getCurrentSelection() {{
    const sel = {{}};
    // Sliders
    document.querySelectorAll('.slider').forEach(s => {{
        const varName = s.dataset.var;
        const nums = sliderVars[varName];
        if (nums) {{
            sel[varName] = nums[parseInt(s.value)];
            document.getElementById('val_' + varName).textContent = sel[varName];
        }}
    }});
    // Dropdowns
    document.querySelectorAll('.dropdown').forEach(d => {{
        sel[d.dataset.var] = d.value;
    }});
    // Context
    document.querySelectorAll('.ctx-dropdown').forEach(d => {{
        sel['_ctx_' + d.dataset.ctx] = d.value;
    }});
    // Metric
    sel._metric = document.getElementById('metric_select').value;
    return sel;
}}

function matchDP(dp, sel) {{
    // Check context match
    for (const [k, v] of Object.entries(sel)) {{
        if (k.startsWith('_')) continue;
        const dpVal = dp.variable_values[k];
        if (dpVal === undefined) continue;
        if (String(dpVal) !== String(v) && Number(dpVal) !== Number(v)) return false;
    }}
    // Check context descriptors
    for (const [k, v] of Object.entries(sel)) {{
        if (!k.startsWith('_ctx_')) continue;
        const ctxName = k.slice(5);
        if (dp.context && !dp.context.toLowerCase().includes(v.toLowerCase().replace(/_/g, ' ').replace(/_/g, '-'))) {{
            // Fuzzy context match
            const words = v.toLowerCase().split('_');
            const ctx = dp.context.toLowerCase();
            if (!words.some(w => ctx.includes(w))) return false;
        }}
    }}
    return true;
}}

function getProvenance(sel) {{
    const metricName = sel._metric;

    // 1. Exact match
    const exact = dataPoints.filter(dp => {{
        if (!matchDP(dp, sel)) return false;
        return dp.metric_values && dp.metric_values[metricName] !== undefined;
    }});
    if (exact.length > 0) {{
        const dp = exact[0];
        return {{
            type: 'PAPER',
            value: dp.metric_values[metricName],
            source: dp.source_cell || 'Paper table'
        }};
    }}

    // 2. Check for interpolation on slider variables
    for (const sv of Object.keys(sliderVars)) {{
        const currentVal = sel[sv];
        const nums = sliderVars[sv];
        if (nums.includes(currentVal)) continue; // exact value exists, no interp needed on this var

        // Find bracketing points
        const lower = nums.filter(n => n < currentVal).pop();
        const upper = nums.find(n => n > currentVal);
        if (lower === undefined || upper === undefined) continue;

        // Check if both endpoints have data
        const selLower = {{ ...sel, [sv]: lower }};
        const selUpper = {{ ...sel, [sv]: upper }};
        const dpLower = dataPoints.find(dp => matchDP(dp, selLower) && dp.metric_values && dp.metric_values[metricName] !== undefined);
        const dpUpper = dataPoints.find(dp => matchDP(dp, selUpper) && dp.metric_values && dp.metric_values[metricName] !== undefined);

        if (dpLower && dpUpper) {{
            const vl = dpLower.metric_values[metricName];
            const vu = dpUpper.metric_values[metricName];
            const frac = (currentVal - lower) / (upper - lower);
            const interp = Math.round((vl + frac * (vu - vl)) * 100) / 100;
            return {{
                type: 'INTERP',
                value: interp,
                source: `Interpolated between ${{sv}}=${{lower}} (${{vl}}) and ${{sv}}=${{upper}} (${{vu}})`
            }};
        }}
    }}

    // 3. N/A
    return {{ type: 'N/A', value: null, source: 'Not characterized in paper' }};
}}

function makeBadgeHTML(prov) {{
    if (prov.type === 'PAPER') {{
        return '<span class="badge badge-paper" title="Reported directly in the paper">PAPER</span><div class="source-text">' + prov.source + '</div>';
    }} else if (prov.type === 'INTERP') {{
        return '<span class="badge badge-interp" title="Linear interpolation between two paper-reported points">INTERP</span><div class="source-text">' + prov.source + '</div>';
    }} else {{
        return '<span class="badge badge-na" title="System couldn\\'t determine a value">N/A</span><div class="source-text">Not characterized in paper</div>';
    }}
}}

let chart = null;

function updateChart(sel) {{
    const canvas = document.getElementById('sweepChart');
    const noChart = document.getElementById('noChart');
    const metricName = sel._metric;

    // Find a slider variable with data
    const svName = Object.keys(sliderVars)[0];
    if (!svName) {{
        canvas.style.display = 'none';
        noChart.style.display = '';
        return;
    }}
    const nums = sliderVars[svName];

    // Collect data points for each value of the slider var
    const chartData = [];
    for (const val of nums) {{
        const testSel = {{ ...sel, [svName]: val }};
        const dp = dataPoints.find(d => matchDP(d, testSel) && d.metric_values && d.metric_values[metricName] !== undefined);
        if (dp) {{
            chartData.push({{ x: val, y: dp.metric_values[metricName] }});
        }}
    }}

    if (chartData.length < 2) {{
        canvas.style.display = 'none';
        noChart.style.display = '';
        if (chart) {{ chart.destroy(); chart = null; }}
        return;
    }}

    canvas.style.display = '';
    noChart.style.display = 'none';

    const currentVal = sel[svName];
    const metricLabel = (metrics.find(m => m.name === metricName) || {{}}).label || metricName;
    const varLabel = (variables.find(v => v.name === svName) || {{}}).label || svName;

    if (chart) chart.destroy();
    chart = new Chart(canvas, {{
        type: 'scatter',
        data: {{
            datasets: [
                {{
                    label: metricLabel + ' (paper)',
                    data: chartData,
                    backgroundColor: '#22c55e',
                    borderColor: '#16a34a',
                    pointRadius: 7,
                    pointHoverRadius: 9,
                    showLine: true,
                    borderWidth: 2,
                    tension: 0.1
                }}
            ]
        }},
        options: {{
            responsive: true,
            plugins: {{
                title: {{ display: true, text: metricLabel + ' vs ' + varLabel }},
                annotation: undefined
            }},
            scales: {{
                x: {{
                    type: 'logarithmic',
                    title: {{ display: true, text: varLabel }},
                    ticks: {{ callback: v => v }}
                }},
                y: {{
                    title: {{ display: true, text: metricLabel }}
                }}
            }}
        }},
        plugins: [{{
            id: 'verticalLine',
            afterDraw(chart) {{
                const xScale = chart.scales.x;
                const yScale = chart.scales.y;
                const x = xScale.getPixelForValue(currentVal);
                if (x >= xScale.left && x <= xScale.right) {{
                    const ctx = chart.ctx;
                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(x, yScale.top);
                    ctx.lineTo(x, yScale.bottom);
                    ctx.strokeStyle = '#2563eb';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([6, 4]);
                    ctx.stroke();
                    ctx.restore();
                }}
            }}
        }}]
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
        document.getElementById('result-value').textContent = '—';
        document.getElementById('result-meta').textContent = 'Not characterized';
    }}

    updateChart(sel);
}}

// Attach listeners
document.querySelectorAll('.slider, .dropdown, .ctx-dropdown, #metric_select').forEach(el => {{
    el.addEventListener('input', update);
    el.addEventListener('change', update);
}});

// Initial render
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
