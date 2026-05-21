"""Markdown → PDF via WeasyPrint."""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"breaks": True, "html": False}).enable("table")

_STYLE = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Liberation Sans', Arial, sans-serif; font-size: 11pt; line-height: 1.45; color: #1f2937; }
h1 { font-size: 22pt; margin: 0 0 4pt 0; color: #111827; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; border-bottom: 1px solid #e5e7eb; padding-bottom: 2pt; color: #111827; }
h3 { font-size: 11pt; margin: 8pt 0 2pt 0; color: #1f2937; }
strong { color: #111827; }
ul { margin: 4pt 0 8pt 18pt; padding: 0; }
li { margin: 2pt 0; }
p { margin: 4pt 0; }
em { color: #4b5563; }
"""


def markdown_to_pdf(markdown_text: str) -> bytes:
    """Render markdown to PDF bytes. Lazy-imports weasyprint to avoid loading at startup."""
    from weasyprint import HTML

    html_body = _md.render(markdown_text)
    html = f"<html><head><meta charset='utf-8'><style>{_STYLE}</style></head><body>{html_body}</body></html>"
    return HTML(string=html).write_pdf()  # type: ignore[return-value]
