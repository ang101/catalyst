"""
Builds catalog.html from all extracted paper data in data/ directory.
Scans data/*.json, reads metadata, produces readers/catalog.html.
"""

import json
import html as html_mod
import time
from pathlib import Path

READER_DIR = Path(__file__).parent.resolve()
DATA_DIR = READER_DIR / "data"
READERS_DIR = READER_DIR / "readers"


def esc(s):
    return html_mod.escape(str(s))


def build_catalog():
    data_files = sorted(DATA_DIR.glob("*.json"))
    if not data_files:
        print("No extracted papers found in data/")
        return

    papers = []
    for f in data_files:
        try:
            d = json.loads(f.read_text())
            c = d.get("classification", {})
            e = d.get("extraction", {})
            p = e.get("paper", {})
            dps = e.get("data_points", [])
            n_paper = sum(1 for dp in dps if dp.get("source_cell"))
            n_total = len(dps)
            quality = round(100 * n_paper / n_total) if n_total > 0 else 0

            paper_id = f.stem
            reader_exists = (READERS_DIR / f"{paper_id}.html").exists()

            papers.append({
                "id": paper_id,
                "title": p.get("title", paper_id),
                "authors": p.get("authors", []),
                "year": p.get("year", ""),
                "case": c.get("case", "?"),
                "reasoning": c.get("reasoning", ""),
                "n_data_points": n_total,
                "n_paper_cited": n_paper,
                "quality_pct": quality,
                "n_variables": len(e.get("variables", [])),
                "n_metrics": len(e.get("metrics", [])),
                "extracted_at": d.get("extracted_at", ""),
                "reader_exists": reader_exists,
                "limited_quality": quality < 30 and n_total > 0,
            })
        except Exception as ex:
            print(f"Warning: skipping {f.name}: {ex}")

    # Build cards
    cards_html = ""
    for p in papers:
        case_colors = {"A": "#22c55e", "B": "#f59e0b", "C": "#6b7280"}
        case_labels = {"A": "Interactive", "B": "Sparse", "C": "Theoretical"}
        case_color = case_colors.get(p["case"], "#9ca3af")
        case_label = case_labels.get(p["case"], "Unknown")

        quality_bar_color = "#22c55e" if p["quality_pct"] >= 70 else "#f59e0b" if p["quality_pct"] >= 30 else "#ef4444"
        limited_flag = ' <span style="color:#ef4444;font-size:11px;">limited extraction</span>' if p["limited_quality"] else ""

        reader_link = f'<a href="{p["id"]}.html" class="reader-link">Open Reader</a>' if p["reader_exists"] else '<span class="no-reader">Reader not built</span>'

        authors_short = ", ".join(p["authors"][:3])
        if len(p["authors"]) > 3:
            authors_short += f" +{len(p['authors'])-3} more"

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <span class="case-badge" style="background:{case_color}">Case {p['case']}: {case_label}</span>
                {reader_link}
            </div>
            <h3><a href="https://arxiv.org/abs/{esc(p['id'])}" target="_blank">{esc(p['title'])}</a></h3>
            <div class="card-meta">{esc(authors_short)} ({p['year']}) &mdash; arXiv:{esc(p['id'])}</div>
            <div class="card-stats">
                <div class="stat">
                    <div class="stat-value">{p['n_data_points']}</div>
                    <div class="stat-label">Data Points</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{p['n_variables']}</div>
                    <div class="stat-label">Variables</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{p['n_metrics']}</div>
                    <div class="stat-label">Metrics</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{p['quality_pct']}%</div>
                    <div class="stat-label">Cited{limited_flag}</div>
                </div>
            </div>
            <div class="quality-bar"><div class="quality-fill" style="width:{p['quality_pct']}%;background:{quality_bar_color}"></div></div>
            <div class="card-footer">{esc(p.get('reasoning', ''))}</div>
        </div>"""

    catalog_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paper Reader Catalog</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; color: #1a1a1a; line-height: 1.5; }}
.container {{ max-width: 1000px; margin: 0 auto; padding: 24px; }}
h1 {{ font-size: 26px; margin-bottom: 4px; }}
.subtitle {{ color: #6b7280; font-size: 14px; margin-bottom: 24px; }}
.filters {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
.filter-btn {{ padding: 6px 14px; border: 1px solid #d1d5db; border-radius: 20px; background: #fff; cursor: pointer; font-size: 13px; }}
.filter-btn.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 16px; }}
.card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 18px; transition: box-shadow 0.2s; }}
.card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
.card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
.case-badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; color: #fff; font-size: 11px; font-weight: 600; }}
.reader-link {{ font-size: 13px; font-weight: 600; color: #2563eb; text-decoration: none; padding: 4px 12px; border: 1px solid #2563eb; border-radius: 6px; }}
.reader-link:hover {{ background: #2563eb; color: #fff; }}
.no-reader {{ font-size: 12px; color: #9ca3af; }}
.card h3 {{ font-size: 15px; margin-bottom: 4px; }}
.card h3 a {{ color: inherit; text-decoration: none; }}
.card h3 a:hover {{ color: #2563eb; }}
.card-meta {{ font-size: 12px; color: #6b7280; margin-bottom: 12px; }}
.card-stats {{ display: flex; gap: 16px; margin: 8px 0; }}
.stat {{ text-align: center; flex: 1; }}
.stat-value {{ font-size: 18px; font-weight: 700; color: #111827; }}
.stat-label {{ font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }}
.quality-bar {{ height: 4px; background: #f3f4f6; border-radius: 2px; margin: 8px 0; overflow: hidden; }}
.quality-fill {{ height: 100%; border-radius: 2px; transition: width 0.3s; }}
.card-footer {{ font-size: 12px; color: #6b7280; font-style: italic; }}
.add-form {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; margin-bottom: 20px; display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }}
.add-form label {{ font-size: 13px; font-weight: 600; color: #374151; }}
.add-form input {{ padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 14px; width: 200px; }}
.add-form button {{ padding: 6px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; }}
.add-form button:hover {{ background: #1d4ed8; }}
.note {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px; margin: 24px 0; font-size: 13px; }}
.legend {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
</style>
</head>
<body>
<div class="container">

<h1>Paper Reader Catalog</h1>
<div class="subtitle">{len(papers)} papers extracted &mdash; Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}</div>

<div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>Case A: Interactive (ablation tables, sliders)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div>Case B: Sparse (limited data, static view)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#6b7280"></div>Case C: Theoretical (claims only)</div>
</div>

<div class="add-form">
    <form id="addForm" onsubmit="processForm(event)">
        <label for="arxivInput">Add paper by arXiv ID:</label>
        <input type="text" id="arxivInput" name="arxiv_id" placeholder="e.g. 2005.14165" required>
        <button type="submit">Process</button>
    </form>
    <div id="formMsg" style="display:none;margin-top:8px;font-size:13px;padding:8px;border-radius:4px;"></div>
</div>

<div class="filters">
    <button class="filter-btn active" onclick="filterCards('all')">All ({len(papers)})</button>
    <button class="filter-btn" onclick="filterCards('A')">Case A ({sum(1 for p in papers if p['case']=='A')})</button>
    <button class="filter-btn" onclick="filterCards('B')">Case B ({sum(1 for p in papers if p['case']=='B')})</button>
    <button class="filter-btn" onclick="filterCards('C')">Case C ({sum(1 for p in papers if p['case']=='C')})</button>
</div>

<div class="grid" id="grid">{cards_html}</div>

<div class="note">
<strong>Integrity:</strong> All values in interactive readers use a four-tier badge system.
<strong>[PAPER]</strong> (green) = directly from paper with table citation.
<strong>[INTERP]</strong> (yellow) = linear interpolation between paper points.
<strong>[LOW CONFIDENCE]</strong> (orange striped) = LLM estimate, visually distinct.
<strong>[N/A]</strong> (gray) = not characterized.
Papers with &lt;30% cited values are flagged as "limited extraction quality."
</div>

</div>
<script>
function processForm(e) {{
    e.preventDefault();
    const id = document.getElementById('arxivInput').value.trim();
    const msg = document.getElementById('formMsg');
    if (!id) return;
    msg.style.display = '';
    msg.style.background = '#dbeafe';
    msg.style.color = '#1e40af';
    msg.textContent = 'Processing ' + id + '... This takes 60-120 seconds. Refresh the page when done.';
    fetch('/process', {{method:'POST', headers:{{'Content-Type':'application/x-www-form-urlencoded'}}, body:'arxiv_id='+encodeURIComponent(id)}})
        .then(r => r.json())
        .then(d => {{ msg.textContent = d.message || 'Started. Refresh in 60-120s.'; }})
        .catch(() => {{
            msg.style.background = '#fef3c7';
            msg.style.color = '#92400e';
            msg.textContent = 'Server not running. Use CLI: python3 reader/run_pipeline.py ' + id;
        }});
}}
function filterCards(c) {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('.card').forEach(card => {{
        if (c === 'all') {{ card.style.display = ''; return; }}
        const badge = card.querySelector('.case-badge');
        card.style.display = badge && badge.textContent.includes('Case ' + c) ? '' : 'none';
    }});
}}
</script>
</body>
</html>"""

    READERS_DIR.mkdir(parents=True, exist_ok=True)
    out = READERS_DIR / "catalog.html"
    out.write_text(catalog_html)
    print(f"Catalog: {out} ({len(papers)} papers)")
    return out


if __name__ == "__main__":
    build_catalog()
