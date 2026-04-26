"""pdf_extract MCP tool — extract paper PDF/LaTeX into structured markdown."""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pdf_extract")


def _papers_dir() -> Path:
    default = Path.home() / ".zeroclaw" / "workspace" / "paper-repro" / "papers"
    return Path(os.environ.get("PAPER_REPRO_PAPERS_DIR", str(default)))


def _update_status(paper_dir: Path, outcome: str, artifacts: list[str], error: str | None):
    """Read existing STATUS.json and append an extract phase entry."""
    status_path = paper_dir / "STATUS.json"
    if status_path.exists():
        status = json.loads(status_path.read_text())
    else:
        status = {"paper_id": paper_dir.name, "phases": []}

    status["phases"].append({
        "phase": "extract",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": outcome,
        "artifacts": artifacts,
        "error": error,
    })
    status_path.write_text(json.dumps(status, indent=2))


def _find_main_tex(source_dir: Path) -> Path | None:
    """Find the main .tex file by looking for documentclass or begin{document}."""
    tex_files = list(source_dir.rglob("*.tex"))
    if not tex_files:
        return None

    # Prefer file with \documentclass
    for tf in tex_files:
        try:
            content = tf.read_text(errors="replace")
            if r"\documentclass" in content or r"\begin{document}" in content:
                return tf
        except OSError:
            continue

    # Fall back to first .tex file
    return tex_files[0]


def _latex_table_to_markdown(table_block: str) -> str:
    """Best-effort conversion of a LaTeX tabular to markdown table."""
    # Extract tabular content
    m = re.search(r"\\begin\{tabular\}.*?\n(.*?)\\end\{tabular\}", table_block, re.DOTALL)
    if not m:
        # Return as a code block if we can't parse it
        return f"\n```latex\n{table_block.strip()}\n```\n"

    body = m.group(1)
    rows = []
    for line in body.split(r"\\"):
        line = line.strip()
        if not line or line.startswith(r"\hline") or line.startswith(r"\toprule"):
            continue
        line = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|cline\{[^}]*\})", "", line)
        line = line.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split("&")]
        rows.append(cells)

    if not rows:
        return f"\n```latex\n{table_block.strip()}\n```\n"

    # Build markdown table
    lines = []
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
    for row in rows[1:]:
        # Pad row to match header length
        while len(row) < len(rows[0]):
            row.append("")
        lines.append("| " + " | ".join(row[:len(rows[0])]) + " |")

    return "\n" + "\n".join(lines) + "\n"


def _convert_latex_math(text: str) -> str:
    """Keep $...$ and $$...$$ as-is (already markdown-compatible).
    Convert \\( \\) to $ and \\[ \\] to $$."""
    text = re.sub(r"\\\((.+?)\\\)", r"$\1$", text)
    text = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
    # Convert \begin{equation}...\end{equation} to $$...$$
    text = re.sub(
        r"\\begin\{(?:equation|align|gather)\*?\}(.*?)\\end\{(?:equation|align|gather)\*?\}",
        r"$$\1$$", text, flags=re.DOTALL
    )
    return text


def _extract_from_latex(source_dir: Path) -> str | None:
    """Parse LaTeX source and produce structured markdown."""
    main_tex = _find_main_tex(source_dir)
    if main_tex is None:
        return None

    try:
        content = main_tex.read_text(errors="replace")
    except OSError:
        return None

    # Also read \input files
    def resolve_inputs(text: str, base_dir: Path, depth: int = 0) -> str:
        if depth > 5:
            return text

        def replacer(m):
            fname = m.group(1)
            if not fname.endswith(".tex"):
                fname += ".tex"
            fpath = base_dir / fname
            if fpath.exists():
                try:
                    return resolve_inputs(fpath.read_text(errors="replace"), fpath.parent, depth + 1)
                except OSError:
                    pass
            return m.group(0)

        return re.sub(r"\\input\{([^}]+)\}", replacer, text)

    content = resolve_inputs(content, main_tex.parent)

    # Strip preamble
    doc_match = re.search(r"\\begin\{document\}", content)
    if doc_match:
        content = content[doc_match.end():]
    end_match = re.search(r"\\end\{document\}", content)
    if end_match:
        content = content[:end_match.start()]

    # Convert tables
    content = re.sub(
        r"\\begin\{table\}.*?\\end\{table\}",
        lambda m: _latex_table_to_markdown(m.group(0)),
        content, flags=re.DOTALL
    )

    # Convert sections to markdown headers
    content = re.sub(r"\\section\*?\{([^}]+)\}", r"\n# \1\n", content)
    content = re.sub(r"\\subsection\*?\{([^}]+)\}", r"\n## \1\n", content)
    content = re.sub(r"\\subsubsection\*?\{([^}]+)\}", r"\n### \1\n", content)
    content = re.sub(r"\\paragraph\*?\{([^}]+)\}", r"\n#### \1\n", content)

    # Convert math
    content = _convert_latex_math(content)

    # Strip common LaTeX commands but keep their content
    content = re.sub(r"\\(?:textbf|textit|emph|text)\{([^}]*)\}", r"\1", content)
    content = re.sub(r"\\(?:cite|citep|citet|ref|label|eqref)\{[^}]*\}", "", content)
    content = re.sub(r"\\(?:begin|end)\{(?:itemize|enumerate|description)\}", "", content)
    content = re.sub(r"\\item\s*", "- ", content)

    # Convert figures to placeholders
    content = re.sub(
        r"\\begin\{figure\}.*?\\end\{figure\}",
        "\n[Figure omitted]\n", content, flags=re.DOTALL
    )

    # Strip remaining LaTeX commands (conservative)
    content = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", content)

    # Clean up excessive whitespace
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = re.sub(r"[ \t]+", " ", content)

    return content.strip()


def _extract_with_marker(pdf_path: Path) -> str | None:
    """Use marker-pdf to convert PDF to markdown."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.config.parser import ConfigParser

        config_parser = ConfigParser({"output_format": "markdown"})
        converter = PdfConverter(config=config_parser.generate_config_dict())
        result = converter(str(pdf_path))
        # result is a tuple: (markdown_text, metadata, images)
        if isinstance(result, tuple):
            md_text = result[0]
        else:
            md_text = str(result)

        if hasattr(md_text, "markdown"):
            return md_text.markdown
        return str(md_text) if md_text else None
    except (ImportError, RuntimeError, Exception) as exc:
        print(f"[pdf_extract] marker failed: {exc}")
        return None


def _extract_with_pymupdf(pdf_path: Path) -> str | None:
    """Use pymupdf4llm as fallback PDF extraction."""
    try:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(str(pdf_path))
        return md if md else None
    except (ImportError, Exception) as exc:
        print(f"[pdf_extract] pymupdf4llm failed: {exc}")
        return None


def _find_sections(markdown: str) -> list[str]:
    """Extract section headers from markdown text."""
    headers = re.findall(r"^(#{1,4})\s+(.+)$", markdown, re.MULTILINE)
    return [title.strip() for _, title in headers]


def pdf_extract_impl(paper_id: str) -> dict:
    """Core implementation — returns a result dict."""
    paper_dir = _papers_dir() / paper_id

    if not paper_dir.exists():
        return {
            "success": False,
            "paper_id": paper_id,
            "error": f"Paper directory not found: {paper_dir}",
        }

    pdf_path = paper_dir / "source.pdf"
    source_dir = paper_dir / "source"
    markdown = None
    method_used = None

    # Strategy 1: LaTeX source
    if source_dir.exists() and list(source_dir.rglob("*.tex")):
        markdown = _extract_from_latex(source_dir)
        if markdown:
            method_used = "latex"

    # Strategy 2: marker-pdf
    if markdown is None and pdf_path.exists():
        markdown = _extract_with_marker(pdf_path)
        if markdown:
            method_used = "marker"

    # Strategy 3: pymupdf4llm fallback
    if markdown is None and pdf_path.exists():
        markdown = _extract_with_pymupdf(pdf_path)
        if markdown:
            method_used = "pymupdf4llm"

    # All methods failed
    if markdown is None:
        error_msg = "All extraction methods failed"
        if not pdf_path.exists() and not source_dir.exists():
            error_msg = "No source.pdf or source/ directory found"
        _update_status(paper_dir, "failed", [], error_msg)
        return {
            "success": False,
            "paper_id": paper_id,
            "error": error_msg,
        }

    # Write output
    output_path = paper_dir / "paper.md"
    output_path.write_text(markdown)

    sections = _find_sections(markdown)
    _update_status(paper_dir, "success", ["paper.md"], None)

    return {
        "success": True,
        "paper_id": paper_id,
        "output_path": str(output_path),
        "method_used": method_used,
        "sections_found": sections,
    }


@mcp.tool()
def pdf_extract(paper_id: str) -> str:
    """Extract a paper's PDF or LaTeX source into structured markdown.

    Given a paper_id, converts the paper to markdown preserving tables and
    equations. Tries LaTeX source first, then marker-pdf, then pymupdf4llm.

    Args:
        paper_id: The paper identifier (directory name under papers/).
    """
    result = pdf_extract_impl(paper_id)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="pdf_extract tool")
    parser.add_argument("paper_id", nargs="?", help="Paper ID to extract")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode (non-MCP)")
    args = parser.parse_args()

    if args.paper_id or args.cli:
        pid = args.paper_id or input("Enter paper ID: ")
        result = pdf_extract_impl(pid)
        print(json.dumps(result, indent=2))
    else:
        mcp.run()
