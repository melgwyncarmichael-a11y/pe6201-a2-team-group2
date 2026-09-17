#!/usr/bin/env python3
"""
Build docs/CHANGELOG.pdf from docs/CHANGELOG.md. No diagram to render, so
this is the simple half of build_pdf.py's chain: markdown -> HTML -> PDF via
the chrome-headless-shell mermaid-cli already cached locally.

Run:  python3 docs/build_changelog_pdf.py
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "CHANGELOG.md")
HTML = os.path.join(HERE, "_changelog.html")
PDF = os.path.join(HERE, "CHANGELOG.pdf")

CSS = """
@page { size: A4; margin: 20mm 18mm; }
body { font: 11pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif;
       color: #1a1a1a; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 20pt 0 6pt; border-bottom: 1px solid #ddd;
     padding-bottom: 3pt; }
code { font: 10pt "SF Mono", Menlo, Consolas, monospace;
       background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
pre { background: #f4f4f4; padding: 10pt; border-radius: 5px; overflow-x: auto;
      font-size: 9pt; }
pre code { background: none; padding: 0; }
ul, ol { padding-left: 20pt; }
li { margin: 3pt 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 16pt 0; }
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

    import markdown
    body = markdown.markdown(src, extensions=["fenced_code", "tables", "sane_lists"])
    html = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<style>%s</style></head><body>%s</body></html>" % (CSS, body))
    open(HTML, "w", encoding="utf-8").write(html)

    shell = find_headless_shell()
    if not shell:
        sys.exit("no chrome-headless-shell found under ~/.cache/puppeteer")
    subprocess.run(
        [shell, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer",
         "--print-to-pdf=%s" % PDF, "file://%s" % HTML],
        check=True)

    os.remove(HTML)
    print("wrote %s (%.0f KB)" % (PDF, os.path.getsize(PDF) / 1024))


if __name__ == "__main__":
    main()
