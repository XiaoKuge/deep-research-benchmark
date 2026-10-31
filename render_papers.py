#!/usr/bin/env python3
"""从只留本机的文献索引 literature.local.html 生成公开版文献列表 papers.html。

公开版只写论文本身的信息：题目、日期、为什么读、中文摘要、精读分析的链接。
作者分级、团队、引用数、注意事项、阅读状态和笔记都不写进去。

用法：python3 -I render_papers.py
"""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(ROOT, "literature.local.html")
TARGET = os.path.join(ROOT, "papers.html")

STYLE = """
  .topics { columns: 2 280px; column-gap: 24px; margin: 16px 0 0; padding: 0; list-style: none; }
  .topics li { break-inside: avoid; padding-block: 4px; }
  .papers { list-style: none; margin: 16px 0 0; padding: 0; }
  .paper { padding-block: 16px; border-top: 1px solid var(--line); }
  .paper .meta { color: var(--ink-3); margin-top: 4px; overflow-wrap: anywhere; }
  .paper .why { color: var(--ink-2); margin-top: 8px; }
  .paper .more { margin-top: 8px; }
  .paper details { margin-top: 8px; }
  .paper summary { cursor: pointer; color: var(--ink-2); }
  .paper summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 6px; }
  .paper details p { margin-top: 8px; color: var(--ink-2); }
"""


def esc(text):
    return html.escape(str(text), quote=True)


def load():
    with open(SOURCE, encoding="utf-8") as f:
        page = f.read()
    block = re.search(r'<script id="papers-data" type="application/json">\s*(.*?)\s*</script>', page, re.S)
    topics = [
        (href, re.sub(r"<[^>]+>|\s*→\s*$", "", label).strip())
        for href, label in re.findall(r'<a class="ana" href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    ]
    return json.loads(block.group(1)), topics


def paper_item(paper):
    meta = " · ".join(esc(x) for x in (paper["date"], paper.get("venue"), paper["title"]) if x)
    parts = [
        f'<li class="paper" id="{esc(paper["id"])}">',
        f'  <h3 class="title-3"><a href="https://arxiv.org/abs/{esc(paper["id"])}">{esc(paper["short"])}</a></h3>',
        f'  <p class="meta caption-2">{meta}</p>',
        f'  <p class="why body-6">{esc(paper["why"])}</p>',
    ]
    if paper.get("analysis"):
        parts.append(f'  <p class="more body-6"><a href="{esc(paper["analysis"])}">精读分析 →</a></p>')
    if paper.get("abstract_zh"):
        parts.append(
            f'  <details><summary class="body-6">中文摘要</summary><p class="body-6">{esc(paper["abstract_zh"])}</p></details>'
        )
    parts.append("</li>")
    return "\n".join(parts)


def render(data, topics):
    sections = []
    for group in data["groups"]:
        members = [p for p in data["papers"] if p["group"] == group["key"]]
        if not members:
            continue
        items = "\n".join(paper_item(p) for p in members)
        sections.append(
            f'<section class="block" id="group-{esc(group["key"])}">\n'
            f'  <h2 class="heading-5">{esc(group["key"])}. {esc(group["title"])}</h2>\n'
            f'  <ul class="papers">\n{items}\n  </ul>\n</section>'
        )
    topic_items = "\n".join(f'    <li class="body-6"><a href="{esc(h)}">{esc(t)}</a></li>' for h, t in topics)
    count = len(data["papers"])
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>文献索引 · 深度研究评测基准</title>
<meta name="description" content="深度研究评测相关的 {count} 篇论文，含中文摘要和精读分析。">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="site/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600&display=swap">
<link rel="stylesheet" href="site/pages.css">
<style>{STYLE}</style>
</head>
<body>
<a class="skip caption-1" href="#main">跳到正文</a>

<header class="top">
  <div class="wrap">
    <a class="back caption-1" href="site/index.html">← 回到资料站</a>
    <p class="eyebrow caption-1">深度研究评测基准</p>
    <h1 class="heading-3">文献索引</h1>
    <p class="body-3 lede">{count} 篇论文，2025 年 8 月到 2026 年 10 月。点题目打开 arXiv，全文的版权在原作者。{esc(data["order"])}。</p>
  </div>
</header>

<main id="main">
<div class="wrap">
<section class="block" id="topics">
  <h2 class="heading-5">专题分析和研究过程</h2>
  <ul class="topics">
{topic_items}
  </ul>
</section>
{chr(10).join(sections)}
</div>
</main>

<footer>
  <div class="wrap caption-2">
    <span>深度研究评测基准 · 资料站</span>
    <nav aria-label="页脚"><a href="site/index.html">资料站首页</a><a href="https://github.com/XiaoKuge/deep-research-benchmark">仓库</a></nav>
  </div>
</footer>
</body>
</html>
"""


def main():
    data, topics = load()
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(render(data, topics))
    print(f"写出 {os.path.relpath(TARGET, ROOT)}：{len(data['papers'])} 篇，{len(topics)} 个专题链接")


if __name__ == "__main__":
    main()
