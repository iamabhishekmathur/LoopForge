#!/usr/bin/env python3
"""Render the LoopForge product spec Markdown into a standalone HTML reading view."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "product-spec.md"
OUTPUT = ROOT / "docs" / "product-spec.html"


@dataclass
class Heading:
    level: int
    text: str
    slug: str


def slugify(text: str, used: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug or "section"
    original = slug
    counter = 2
    while slug in used:
        slug = f"{original}-{counter}"
        counter += 1
    used.add(slug)
    return slug


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def is_table_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def close_paragraph(parts: list[str], out: list[str]) -> None:
    if parts:
        out.append(f"<p>{inline_markdown(' '.join(parts))}</p>")
        parts.clear()


def close_list(kind: str | None, out: list[str]) -> None:
    if kind:
        out.append(f"</{kind}>")


def render_markdown(markdown_text: str) -> tuple[str, list[Heading]]:
    out: list[str] = []
    headings: list[Heading] = []
    paragraph: list[str] = []
    list_kind: str | None = None
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    used_slugs: set[str] = set()
    lines = markdown_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        if in_code:
            if line.startswith("```"):
                language_class = f' class="language-{html.escape(code_lang)}"' if code_lang else ""
                out.append(f"<pre><code{language_class}>{html.escape(chr(10).join(code_lines))}</code></pre>")
                in_code = False
                code_lang = ""
                code_lines = []
            else:
                code_lines.append(line)
            i += 1
            continue

        if line.startswith("```"):
            close_paragraph(paragraph, out)
            close_list(list_kind, out)
            list_kind = None
            in_code = True
            code_lang = line.strip().strip("`").strip()
            i += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            close_paragraph(paragraph, out)
            close_list(list_kind, out)
            list_kind = None
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            slug = slugify(text, used_slugs)
            headings.append(Heading(level=level, text=text, slug=slug))
            out.append(f'<h{level} id="{slug}">{inline_markdown(text)}</h{level}>')
            i += 1
            continue

        if line.strip().startswith("|") and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            close_paragraph(paragraph, out)
            close_list(list_kind, out)
            list_kind = None
            headers = split_table_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            out.append("<div class=\"table-wrap\"><table>")
            out.append("<thead><tr>")
            for header in headers:
                out.append(f"<th>{inline_markdown(header)}</th>")
            out.append("</tr></thead>")
            out.append("<tbody>")
            for row in rows:
                out.append("<tr>")
                for cell in row:
                    out.append(f"<td>{inline_markdown(cell)}</td>")
                out.append("</tr>")
            out.append("</tbody></table></div>")
            continue

        unordered_match = re.match(r"^\s*-\s+(.+)$", line)
        ordered_match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if unordered_match or ordered_match:
            close_paragraph(paragraph, out)
            desired_kind = "ul" if unordered_match else "ol"
            if list_kind != desired_kind:
                close_list(list_kind, out)
                out.append(f"<{desired_kind}>")
                list_kind = desired_kind
            item_text = (unordered_match or ordered_match).group(1)
            out.append(f"<li>{inline_markdown(item_text)}</li>")
            i += 1
            continue

        if not line.strip():
            close_paragraph(paragraph, out)
            close_list(list_kind, out)
            list_kind = None
            i += 1
            continue

        close_list(list_kind, out)
        list_kind = None
        paragraph.append(line.strip())
        i += 1

    close_paragraph(paragraph, out)
    close_list(list_kind, out)
    return "\n".join(out), headings


def render_toc(headings: list[Heading]) -> str:
    items = []
    for heading in headings:
        if heading.level > 3:
            continue
        indent_class = f"toc-level-{heading.level}"
        items.append(
            f'<a class="{indent_class}" href="#{heading.slug}">{html.escape(heading.text)}</a>'
        )
    return "\n".join(items)


def render_html(body: str, headings: list[Heading]) -> str:
    toc = render_toc(headings)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LoopForge Product Specification</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f3;
      --panel: #ffffff;
      --text: #19201f;
      --muted: #61706d;
      --line: #d9dfd9;
      --accent: #176b5d;
      --accent-2: #9a4d1f;
      --code-bg: #eef2ee;
      --shadow: 0 18px 60px rgba(21, 32, 30, 0.12);
    }}

    * {{
      box-sizing: border-box;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 16px/1.65 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    a {{
      color: var(--accent);
      text-decoration-thickness: 1px;
      text-underline-offset: 3px;
    }}

    .shell {{
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
      gap: 32px;
      max-width: 1480px;
      margin: 0 auto;
      padding: 28px;
    }}

    aside {{
      position: sticky;
      top: 28px;
      align-self: start;
      max-height: calc(100vh - 56px);
      overflow: auto;
      padding: 22px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}

    .brand {{
      margin: 0 0 4px;
      font-size: 24px;
      line-height: 1.15;
      letter-spacing: 0;
    }}

    .subtitle {{
      margin: 0 0 22px;
      color: var(--muted);
      font-size: 14px;
    }}

    .toc {{
      display: grid;
      gap: 4px;
      font-size: 14px;
    }}

    .toc a {{
      display: block;
      padding: 5px 0;
      color: #30413e;
      text-decoration: none;
    }}

    .toc a:hover {{
      color: var(--accent);
    }}

    .toc-level-3 {{
      padding-left: 16px !important;
      color: var(--muted) !important;
      font-size: 13px;
    }}

    main {{
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 56px min(7vw, 92px);
    }}

    article {{
      max-width: 920px;
      margin: 0 auto;
    }}

    h1, h2, h3, h4, h5, h6 {{
      line-height: 1.2;
      letter-spacing: 0;
      scroll-margin-top: 32px;
    }}

    h1 {{
      margin: 0 0 20px;
      font-size: 44px;
    }}

    h2 {{
      margin: 56px 0 14px;
      padding-top: 8px;
      border-top: 1px solid var(--line);
      font-size: 27px;
    }}

    h3 {{
      margin: 32px 0 10px;
      font-size: 20px;
      color: #223432;
    }}

    p {{
      margin: 0 0 16px;
    }}

    ul, ol {{
      margin: 0 0 20px;
      padding-left: 24px;
    }}

    li {{
      margin: 5px 0;
    }}

    code {{
      padding: 2px 5px;
      border-radius: 4px;
      background: var(--code-bg);
      color: #263533;
      font: 0.92em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}

    pre {{
      overflow: auto;
      margin: 18px 0 24px;
      padding: 18px;
      border: 1px solid var(--line);
      background: #101817;
      color: #edf6f2;
      line-height: 1.5;
    }}

    pre code {{
      padding: 0;
      background: transparent;
      color: inherit;
      font-size: 13px;
    }}

    .table-wrap {{
      overflow-x: auto;
      margin: 22px 0 28px;
      border: 1px solid var(--line);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
      font-size: 14px;
      line-height: 1.45;
    }}

    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }}

    th {{
      background: #edf2ee;
      color: #223432;
      font-weight: 700;
    }}

    tr:last-child td {{
      border-bottom: 0;
    }}

    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 32px;
    }}

    .meta span {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 4px 10px;
      border: 1px solid var(--line);
      background: #fbfcfa;
      color: var(--muted);
      font-size: 13px;
    }}

    @media (max-width: 980px) {{
      .shell {{
        display: block;
        padding: 0;
      }}

      aside {{
        position: static;
        max-height: none;
        border-width: 0 0 1px;
        box-shadow: none;
      }}

      .toc {{
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      }}

      main {{
        border: 0;
        box-shadow: none;
        padding: 34px 20px 56px;
      }}

      h1 {{
        font-size: 34px;
      }}
    }}

    @media print {{
      body {{
        background: #fff;
      }}

      .shell {{
        display: block;
        padding: 0;
      }}

      aside {{
        display: none;
      }}

      main {{
        border: 0;
        box-shadow: none;
        padding: 0;
      }}

      a {{
        color: inherit;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <h1 class="brand">LoopForge</h1>
      <p class="subtitle">Product specification reading view</p>
      <nav class="toc" aria-label="Table of contents">
        {toc}
      </nav>
    </aside>
    <main>
      <article>
        <div class="meta">
          <span>Draft 0.1</span>
          <span>Generated from docs/product-spec.md</span>
          <span>Local-first OSS harness loop</span>
        </div>
        {body}
      </article>
    </main>
  </div>
</body>
</html>
"""


def main() -> None:
    body, headings = render_markdown(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(render_html(body, headings), encoding="utf-8")
    print(f"Rendered {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

