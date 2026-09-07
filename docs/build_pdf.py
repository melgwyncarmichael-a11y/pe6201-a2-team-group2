#!/usr/bin/env python3
"""
Build docs/HOW_IT_WORKS.pdf from docs/HOW_IT_WORKS.md.

Chain, all local, no network:
  1. pull the ```mermaid block out of the markdown, render it to PNG with mmdc
  2. markdown -> HTML (python `markdown`), with the mermaid block swapped for
     an <img> of the rendered diagram
  3. HTML -> PDF via the chrome-headless-shell that mermaid-cli already cached

Run:  python3 docs/build_pdf.py
"""
import base64
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "HOW_IT_WORKS.md")
PNG = os.path.join(HERE, "_flow.png")
HTML = os.path.join(HERE, "_how_it_works.html")
PDF = os.path.join(HERE, "HOW_IT_WORKS.pdf")

CSS = """
@page { size: A4; margin: 20mm 18mm; }
body { font: 11pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif;
       color: #1a1a1a; max-width: 100%; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 14pt; margin: 22pt 0 6pt; border-bottom: 1px solid #ddd;
     padding-bottom: 3pt; }
h1 + p em, h2 + p em { color: #555; }
code { font: 10pt "SF Mono", Menlo, Consolas, monospace;
       background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
pre { background: #f4f4f4; padding: 10pt; border-radius: 5px; overflow-x: auto;
      font-size: 9.5pt; }
pre code { background: none; padding: 0; }
img { max-width: 100%; display: block; margin: 10pt auto; }
ul, ol { padding-left: 20pt; }
li { margin: 3pt 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 18pt 0; }
strong { color: #000; }
"""


def find_headless_shell():
    pats = [
        os.path.expanduser("~/.cache/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell"),
        os.path.expanduser("~/Library/Caches/puppeteer/chrome-headless-shell/*/*/chrome-headless-shell"),
    ]
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits[-1]
    return None


def main():
    if not os.path.exists(MD):
        sys.exit("missing %s" % MD)
    src = open(MD, encoding="utf-8").read()

    m = re.search(r"```mermaid\n(.*?)\n```", src, re.S)
    if not m:
        sys.exit("no ```mermaid block found in the markdown")
    mermaid_src = m.group(1)

    mmd = os.path.join(HERE, "_flow.mmd")
    open(mmd, "w", encoding="utf-8").write(mermaid_src)
    pcfg = os.path.join(HERE, "_puppeteer.json")
    open(pcfg, "w").write('{"args":["--no-sandbox"]}')
    print("rendering mermaid -> png ...")
    subprocess.run(
        ["mmdc", "-i", mmd, "-o", PNG, "-b", "white", "-s", "2",
         "-p", pcfg],
        check=True, cwd=HERE)

    # markdown -> html, mermaid block replaced by the rendered image (inlined
    # as a data URI so the html file is self-contained)
    b64 = base64.b64encode(open(PNG, "rb").read()).decode()
    src_no_mermaid = src[:m.start()] + \
        '<img src="data:image/png;base64,%s" alt="agent flow">' % b64 + \
        src[m.end():]

    import markdown
    body = markdown.markdown(
        src_no_mermaid,
        extensions=["fenced_code", "tables", "sane_lists"])
    html = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<style>%s</style></head><body>%s</body></html>" % (CSS, body))
    open(HTML, "w", encoding="utf-8").write(html)

    shell = find_headless_shell()
    if not shell:
        sys.exit("no chrome-headless-shell found under ~/.cache/puppeteer - "
                 "run `npm i -g @mermaid-js/mermaid-cli` once to populate it")
    print("html -> pdf via %s" % os.path.basename(shell))
    subprocess.run(
        [shell, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer",
         "--print-to-pdf=%s" % PDF, "file://%s" % HTML],
        check=True)

    for tmp in (mmd, pcfg, HTML, PNG):
        try:
            os.remove(tmp)
        except OSError:
            pass
    print("wrote %s (%.0f KB)" % (PDF, os.path.getsize(PDF) / 1024))


if __name__ == "__main__":
    main()
