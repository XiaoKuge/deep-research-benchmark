"""把 research-plan/ 下的 Markdown 渲染成 notes/ 下与精读页同样式的网页，并生成本地出题手册。

用法：python3 render_plan.py
修改 .md 之后重新运行一次即可；.md 是源文件，网页由它生成。
"""
import os
import re

import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))

PAGES = [
    # (源文件, 输出文件, 页面标题, 副标题[, 目录列到第几级标题，默认 2])
    ("research-plan/v3.md", "notes/plan-v3.html",
     "研究计划第三稿", "《智能体深度研究评测基准研究计划》当前稿"),
    ("research-plan/stage1-concepts.md", "notes/plan-stage1-concepts.html",
     "第一阶段概念说明", "调研、好的调研、深、交付形式、范围的定义与讨论经过"),
    ("research-plan/collection-protocol.md", "notes/plan-collection-protocol.html",
     "对照报告收集规程", "按基础级规则收集真实报告的规程和题目草稿"),
    ("research-plan/stage2-framework.md", "notes/plan-stage2-framework.html",
     "第二阶段审视框架", "论证式效度与 Bean 等人检查清单相结合的审视框架和记录模板"),
    ("research-plan/stage2-summary.md", "notes/plan-stage2-summary.html",
     "第二阶段汇总", "18 个评测工具的总表、覆盖表、共同问题、统计、五点观察复核与勘误"),
    ("research-plan/stage3-problems.md", "notes/plan-stage3-problems.html",
     "第三阶段：关键问题", "从第二阶段的问题归纳出的 8 个关键问题、子问题与优先级"),
    ("research-plan/stage4-design.md", "notes/plan-stage4-design.html",
     "第四阶段：改进方案", "每个关键问题的候选办法、选择与理由，以及验收标准"),
    ("research-plan/stage4-rubric.md", "notes/plan-stage4-rubric.html",
     "评审细则", "交给评委使用的操作版本"),
    ("research-plan/stage5-report.md", "notes/plan-stage5-report.html",
     "第五阶段：小规模检验与修订", "用三月那批六份真实报告试跑的结果、发现的问题和第 1.1 版修订"),
    ("research-plan/summary.md", "notes/plan-summary.html",
     "一页总结", "研究计划五个阶段的结论"),
    ("research-plan/paper.md", "notes/paper.html",
     "什么是智能体的深度研究", "论文工作稿：摘要、引言、相关工作、方法、实验、结论、参考文献"),
    ("research-plan/site-mapping.md", "notes/plan-site-mapping.html",
     "资料与程序对照巡天网站结构", "现有资料和程序按巡天黑客松网站的结构逐项对照：已有、部分、缺，以及待办"),
    ("research-plan/rules.md", "notes/rules.html",
     "深度研究比赛规则手册", "出题、冻结与申报、运行、交付、评审、名次、申诉和违规处理的规则", "3"),
]

# 样式在 site/doc.css，资料站所有长文档页面共用

TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap">
<link rel="stylesheet" href="../site/doc.css">
</head>
<body>
<div class="wrap">
<nav class="docnav"><a class="back" href="../papers.html">← 文献索引</a><a href="../site/index.html">资料站首页</a></nav>
{heading}<div class="meta">{dek}。本页由 <code>{src}</code> 生成，修改请改源文件后运行 <code>render_plan.py</code>。</div>
<nav class="toc">{toc}</nav>
{body}
<footer>源文件：<code>{src}</code></footer>
</div>
</body>
</html>
"""


def render(src, out, title, dek, toc_depth="2"):
    with open(os.path.join(ROOT, src), encoding="utf-8") as f:
        text = f.read()
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
                           extension_configs={"toc": {"toc_depth": toc_depth}})
    body = md.convert(text)
    # 文档开头的一级标题放到最前面，后面才是出处说明和目录
    heading = ""
    m = re.match(r"\s*(<h1[^>]*>.*?</h1>)", body, re.S)
    if m:
        heading, body = m.group(1) + "\n", body[m.end():]
    body = re.sub(r"<table>", '<div class="tbl"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)
    html = TEMPLATE.format(title=title, heading=heading, dek=dek, src=src, toc=md.toc, body=body)
    path = os.path.join(ROOT, out)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, path)
    print("wrote", out)


def render_records():
    """第二阶段审视记录：每份渲染成 notes/record-*.html，再生成一页目录。"""
    src_dir = os.path.join(ROOT, "research-plan", "stage2-records")
    if not os.path.isdir(src_dir):
        return
    lines = ["# 第二阶段审视记录", "",
             "每个评测工具一份，按《第二阶段审视框架》第三节的模板写成；"
             "另有一份三篇测量研究的标尺要点。", ""]
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith(".md"):
            continue
        src = f"research-plan/stage2-records/{name}"
        out = f"notes/record-{name[:-3]}.html"
        with open(os.path.join(ROOT, src), encoding="utf-8") as f:
            first = f.readline().lstrip("# ").strip()
        render(src, out, first, "第二阶段审视记录")
        lines.append(f"- [{first}]({os.path.basename(out)})")
    index_md = os.path.join(ROOT, "research-plan", "stage2-records-index.md")
    with open(index_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    render("research-plan/stage2-records-index.md", "notes/plan-stage2-records.html",
           "第二阶段审视记录", "18 个评测工具的审视记录和标尺要点")


HANDBOOK_HEAD = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
"""


def render_handbook():
    """出题手册：源文件是页面内容，前面加上网页的头，生成 notes/question-handbook.html。"""
    with open(os.path.join(ROOT, "research-plan", "question-handbook.src.html"), encoding="utf-8") as f:
        body = f.read()
    path = os.path.join(ROOT, "notes", "question-handbook.html")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(HANDBOOK_HEAD + body.rstrip("\n") + "\n\n</html>\n")
    os.replace(tmp, path)
    print("wrote notes/question-handbook.html")


if __name__ == "__main__":
    for page in PAGES:
        render(*page)
    render_records()
    render_handbook()
