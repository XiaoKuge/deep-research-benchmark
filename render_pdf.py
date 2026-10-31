"""把论文工作稿 research-plan/paper.md 排成 A4 的 PDF（research-plan/paper.pdf）。

用法：python3 render_pdf.py
先生成白底的打印版网页 notes/paper-print.html，再用 Chrome 无界面模式打印成 PDF。
修改 paper.md 之后重新运行一次即可。
"""
import os
import re
import subprocess

import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "research-plan", "paper.md")
HTML = os.path.join(ROOT, "notes", "paper-print.html")
PDF = os.path.join(ROOT, "research-plan", "paper.pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
  @page { size: A4; margin: 22mm 20mm 22mm 20mm; }
  body { margin: 0; background: #fff; color: #000;
    font: 10.5pt/1.75 "Songti SC", "STSong", "Noto Serif CJK SC", serif; }
  h1, h2, h3, h4, th, strong { font-family: "Heiti SC", "PingFang SC", "STHeiti", sans-serif; }
  h1 { font-size: 17pt; text-align: center; margin: 0 0 6pt; line-height: 1.4; }
  .front p { text-align: center; margin: 3pt 0; }
  h2 { font-size: 13pt; margin: 18pt 0 6pt; page-break-after: avoid; }
  h3 { font-size: 11pt; margin: 12pt 0 4pt; page-break-after: avoid; }
  p { margin: 5pt 0; text-align: justify; }
  ul, ol { margin: 4pt 0; padding-left: 20pt; } li { margin: 2pt 0; }
  strong { font-weight: 600; }
  hr { border: 0; margin: 8pt 0; }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.8pt; line-height: 1.5; }
  th, td { border: 0.6pt solid #555; padding: 3pt 5pt; text-align: left; vertical-align: top; }
  th { background: #eee; font-weight: 600; }
  tr { page-break-inside: avoid; }
  pre { background: #f4f4f4; border: 0.5pt solid #ccc; padding: 6pt 8pt; font-size: 9pt;
    white-space: pre-wrap; font-family: "Menlo", "PingFang SC", monospace; page-break-inside: avoid; }
  code { font-family: "Menlo", "PingFang SC", monospace; font-size: 9pt; }
  .refs p { font-size: 9pt; margin: 2pt 0; text-align: left; padding-left: 2.2em; text-indent: -2.2em; }
"""


def build_html():
    with open(SRC, encoding="utf-8") as f:
        text = f.read()
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    body = md.convert(text)
    # 题名之后、第一条分隔线之前的英文题名、作者、日期居中
    body = re.sub(r"(</h1>)(.*?)(<hr />)", r'\1<div class="front">\2</div>\3', body, count=1, flags=re.S)
    # 参考文献部分用悬挂缩进
    body = re.sub(r'(<h2[^>]*>参考文献.*?</h2>)(.*)$', r'\1<div class="refs">\2</div>', body, count=1, flags=re.S)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", body).group(1)
    html = (f'<!DOCTYPE html>\n<html lang="zh"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{CSS}</style></head><body>{body}</body></html>\n")
    tmp = HTML + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, HTML)


def print_pdf():
    tmp = PDF + ".tmp.pdf"
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={tmp}", "file://" + HTML],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    os.replace(tmp, PDF)
    print("wrote", os.path.relpath(PDF, ROOT))


if __name__ == "__main__":
    build_html()
    print_pdf()
