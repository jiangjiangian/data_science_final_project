#!/usr/bin/env python3
"""Build a self-contained HTML of reports/00_final_report.md.

stdlib only (專案 code-style: stdlib-only where feasible). Every image
is base64-inlined → single UTF-8 file, CJK-safe, no pandoc/LaTeX/CJK
font. Open in any browser; print-to-PDF for submission.

Usage:  python3 reports/build_report_html.py
"""
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # reports/
SRC = HERE / "00_final_report.md"
OUT = HERE / "00_final_report.html"

CSS = """
:root{--fg:#1a1a1a;--mut:#666;--line:#ddd;--accent:#0b5fa5;--bg:#fff}
*{box-sizing:border-box}
body{max-width:860px;margin:2.2rem auto;padding:0 1.2rem;color:var(--fg);
background:var(--bg);font:16px/1.7 -apple-system,"PingFang TC",
"Microsoft JhengHei","Noto Sans CJK TC",sans-serif}
h1{font-size:1.9rem;border-bottom:3px solid var(--accent);padding-bottom:.3em}
h2{font-size:1.45rem;margin-top:2.2em;border-bottom:1px solid var(--line);
padding-bottom:.2em}
h3{font-size:1.18rem;margin-top:1.8em}h4{font-size:1.03rem}
code{background:#f4f4f4;padding:.12em .35em;border-radius:3px;
font:.88em SFMono-Regular,Consolas,monospace}
pre{background:#f6f8fa;padding:1em;border-radius:6px;overflow:auto}
pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:1.1em 0;font-size:.94em}
th,td{border:1px solid var(--line);padding:.5em .7em;text-align:left;
vertical-align:top}
th{background:#f4f7fa}tr:nth-child(even) td{background:#fafbfc}
blockquote{margin:1.1em 0;padding:.6em 1.1em;border-left:4px solid var(--accent);
background:#f6f9fc;color:#333}
img{max-width:100%;height:auto;display:block;margin:1.2em auto;
border:1px solid var(--line);border-radius:4px}
a{color:var(--accent)}hr{border:0;border-top:1px solid var(--line);margin:2em 0}
em.fig{display:block;text-align:center;color:var(--mut);font-size:.88em;
margin:-0.6em 0 1.6em}
@media print{body{max-width:none;margin:0;font-size:11pt}
h2{page-break-after:avoid}img,table,pre,blockquote{page-break-inside:avoid}}
"""


def data_uri(ref: str) -> str:
    p = (HERE / ref).resolve()
    if not p.is_file():
        sys.stderr.write(f"WARN missing image: {ref} -> {p}\n")
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def inline(t: str) -> str:
    """Inline MD on an already HTML-escaped string."""
    # images first: ![alt](path) -> base64 <img> + caption
    def img(m):
        alt = m.group(1)
        uri = data_uri(m.group(2))
        if not uri:
            return f"<em class='fig'>[缺圖 {alt}]</em>"
        cap = f"<em class='fig'>{alt}</em>" if alt else ""
        return f"<img alt=\"{alt}\" src=\"{uri}\">{cap}"
    t = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", img, t)
    # links [text](url)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               r'<a href="\2">\1</a>', t)
    # autolink <url> (escaped form &lt;http...&gt;)
    t = re.sub(r"&lt;(https?://[^&\s]+)&gt;",
               r'<a href="\1">\1</a>', t)
    # code span
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # bold then italic
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
    return t


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def convert(md: str) -> str:
    lines = md.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        # fenced code
        if ln.startswith("```"):
            buf = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                buf.append(esc(lines[i]))
                i += 1
            i += 1
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue
        # blank
        if not ln.strip():
            i += 1
            continue
        # hr (exact ---, not a table sep)
        if re.fullmatch(r"-{3,}", ln.strip()):
            out.append("<hr>")
            i += 1
            continue
        # heading
        m = re.match(r"(#{1,6})\s+(.*)", ln)
        if m:
            lv = len(m.group(1))
            out.append(f"<h{lv}>{inline(esc(m.group(2)))}</h{lv}>")
            i += 1
            continue
        # table: consecutive lines starting & ending with |
        if ln.lstrip().startswith("|") and ln.rstrip().endswith("|"):
            tbl = []
            while (i < n and lines[i].lstrip().startswith("|")
                   and lines[i].rstrip().endswith("|")):
                tbl.append(lines[i].strip())
                i += 1
            cells = [[c.strip() for c in row.strip("|").split("|")]
                     for row in tbl]
            sep = lambda r: all(re.fullmatch(r":?-{2,}:?", c.strip())
                                for c in r if c.strip())
            html_t = ["<table>"]
            body_started = False
            for r, row in enumerate(cells):
                if sep(row):
                    body_started = True
                    continue
                tag = "th" if (r == 0 or not body_started
                               and r == 0) else "td"
                tag = "th" if r == 0 else "td"
                html_t.append("<tr>" + "".join(
                    f"<{tag}>{inline(esc(c))}</{tag}>" for c in row)
                    + "</tr>")
            html_t.append("</table>")
            out.append("\n".join(html_t))
            continue
        # blockquote (consecutive > lines)
        if ln.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i][1:].lstrip())
                i += 1
            out.append("<blockquote>"
                       + inline(esc(" ".join(buf).strip()))
                       + "</blockquote>")
            continue
        # list (- item, with 2-space continuation lines)
        if re.match(r"-\s+", ln):
            items = []
            while i < n and (re.match(r"-\s+", lines[i])
                             or (lines[i].startswith("  ")
                                 and lines[i].strip()
                                 and items)):
                if re.match(r"-\s+", lines[i]):
                    items.append(re.sub(r"^-\s+", "", lines[i]).strip())
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append("<ul>" + "".join(
                f"<li>{inline(esc(it))}</li>" for it in items)
                + "</ul>")
            continue
        # paragraph (gather until blank / block marker)
        buf = []
        while i < n and lines[i].strip() and not re.match(
                r"(#{1,6}\s|>|\||```|-{3,}\s*$|-\s+)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        out.append("<p>" + inline(esc(" ".join(buf))) + "</p>")
    return "\n".join(out)


def main():
    if not SRC.is_file():
        sys.exit(f"missing {SRC}")
    md = SRC.read_text(encoding="utf-8")
    body = convert(md)
    n_img = body.count("data:image")
    doc = (f"<!doctype html><html lang=\"zh-Hant\"><head>"
           f"<meta charset=\"utf-8\">"
           f"<meta name=\"viewport\" content=\"width=device-width,"
           f"initial-scale=1\">"
           f"<title>CPBL 主客場勝率預測 — 期末報告</title>"
           f"<style>{CSS}</style></head><body>{body}</body></html>")
    OUT.write_text(doc, encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT}  ({kb:.0f} KB, {n_img} images inlined)")
    if n_img < 9:
        sys.exit(f"ERROR expected 9 inlined images, got {n_img}")


if __name__ == "__main__":
    main()
