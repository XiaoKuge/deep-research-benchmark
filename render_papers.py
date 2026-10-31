#!/usr/bin/env python3
"""从只留本机的文献索引 literature.local.html 生成公开版文献列表 papers.html。

公开版只写论文本身的信息：首页截图、题目、日期、为什么读、中文摘要、精读分析的链接。
作者分级、团队、引用数、注意事项、阅读状态和笔记都不写进去。
首页截图在 site/assets/papers/<arXiv 编号>.webp，取自 arXiv 的 PDF 第一页；点截图或题目打开 arXiv。

用法：python3 -I render_papers.py
"""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(ROOT, "literature.local.html")
TARGET = os.path.join(ROOT, "papers.html")
THUMBS = "site/assets/papers"  # 相对 ROOT，也是 papers.html 里的相对路径

STYLE = """
  .topics { columns: 2 280px; column-gap: 24px; margin: 16px 0 0; padding: 0; list-style: none; }
  .topics li { break-inside: avoid; padding-block: 4px; }
  /* 每篇论文一张卡片：上面是 arXiv PDF 第一页的截图，点截图或题目打开 arXiv */
  .papers { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 24px; }
  .paper { display: flex; flex-direction: column; padding: 12px 12px 24px; border-radius: 16px; background: var(--glass); border: 1px solid var(--glass-line); box-shadow: var(--shadow); }
  .paper .thumb { display: block; aspect-ratio: 560 / 725; overflow: hidden; border-radius: 8px; background: #fff; box-shadow: 0 1px 2px rgba(50, 28, 39, .12);
    transition: transform 300ms var(--ease), box-shadow 300ms var(--ease); }
  .paper .thumb img { display: block; width: 100%; height: 100%; object-fit: cover; object-position: top; }
  .paper .thumb:hover { transform: translateY(-4px); box-shadow: 0 12px 32px rgba(50, 28, 39, .16); }
  .paper h3, .paper p, .paper details { padding-inline: 12px; }
  .paper h3 { margin-top: 16px; }
  .paper h3 a { color: var(--ink); text-decoration: none; }
  .paper h3 a:hover { color: var(--accent); }
  .paper .meta { color: var(--ink-3); margin-top: 4px; overflow-wrap: anywhere; }
  .paper .why { color: var(--ink-2); margin-top: 8px; }
  .paper .more { margin-top: 8px; }
  .paper details { margin-top: 8px; }
  .paper summary { cursor: pointer; color: var(--ink-2); }
  .paper summary:focus-visible { outline: 2px solid var(--rose); outline-offset: 2px; border-radius: 6px; }
  .paper details p { margin-top: 8px; padding: 0; color: var(--ink-2); }
  @media (prefers-reduced-motion: reduce) { .paper .thumb:hover { transform: none; } }
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
    url = f'https://arxiv.org/abs/{esc(paper["id"])}'
    parts = [f'<li class="paper" id="{esc(paper["id"])}">']
    thumb = f'{THUMBS}/{paper["id"]}.webp'
    if os.path.isfile(os.path.join(ROOT, thumb)):
        parts.append(f'  <a class="thumb" href="{url}" aria-label="在 arXiv 打开 {esc(paper["short"])}">'
                     f'<img src="{esc(thumb)}" alt="{esc(paper["short"])} 论文第一页" width="560" height="725" loading="lazy"></a>')
    parts += [
        f'  <h3 class="title-3"><a href="{url}">{esc(paper["short"])}</a></h3>',
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
            f'  <h2 class="heading-3">{esc(group["key"])}. {esc(group["title"])}</h2>\n'
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap">
<link rel="stylesheet" href="site/pages.css">
<style>{STYLE}</style>
</head>
<body>
<a class="skip caption-1" href="#main">跳到正文</a>

<header class="top">
  <div class="wrap">
    <a class="back caption-1" href="site/index.html">← 回到资料站</a>
    <p class="eyebrow caption-1">深度研究评测基准</p>
    <h1 class="heading-1">文献索引</h1>
    <p class="body-3 lede">{count} 篇论文，2025 年 8 月到 2026 年 10 月。每张卡片上是论文 PDF 的第一页，点它或题目打开 arXiv；全文的版权在原作者。{esc(data["order"])}。</p>
  </div>
</header>

<main id="main">
<div class="wrap">
<section class="block" id="topics">
  <h2 class="heading-3">专题分析和研究过程</h2>
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
    tmp = TARGET + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(render(data, topics))
    os.replace(tmp, TARGET)
    print(f"写出 {os.path.relpath(TARGET, ROOT)}：{len(data['papers'])} 篇，{len(topics)} 个专题链接")


if __name__ == "__main__":
    main()
