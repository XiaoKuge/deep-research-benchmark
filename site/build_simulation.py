"""从模拟出题和模拟评审的输出目录生成资料站上的题库页和评审记录页。

用法：在仓库根目录运行
    python3 -I site/build_simulation.py [--questions 目录] [--reviews 目录] [--output 目录]
默认读 simulation/questions/ 和 simulation/reviews/，写到 site/simulation/。只读输出目录，不改它们。

写出的页面：
    questions.html                          题库页
    questions/<题目标识>/index.html          每道题的详情页
    questions/<题目标识>/calls/<序号>.html    出这道题时每一次模型调用的原文页
    reviews.html                            评审记录页
    reviews/<运行标识>/index.html            每次评审的详情页
    reviews/<运行标识>/calls/<序号>.html      这次评审每一次模型调用的原文页
    reviews/<运行标识>/results/              这次评审的名次页、复核页和要点池页（有结果文件时，由 build_results.py 生成）
序号是调用记录文件里的第几行，从 1 起。

公开的规则：练习题，或者元数据里写明 "已公开": true 的正式题，公开题目卡、两个交给智能体的版本、深度地图、
三项检查记录和每一次调用的原文。其余的题（正式题没有"已公开"字段，或者类别不明）只显示深度地图的校验值：
题目卡、深度地图、话题和调用原文都不显示，也不链接到这些文件。用这种题做的模拟评审，同样只显示调用次数和厂商，
不显示调用原文、报告和名次页。

页面里的链接按页面实际写到的目录来写。每次运行先在输出目录旁边、同一层的新目录里把全部页面写完，
再换下旧目录，所以删掉的题目和评审不会留下旧页面；中途出错时旧的页面原样留着，新目录删掉。
输出目录里如果有不是本程序写的东西（没有 questions.html），就拒绝运行。

替代记录只读一种格式（tools/substitutes.py 的五个字段：步骤、任务、原来的厂商、改用的厂商、原因）。
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_results as results  # noqa: E402
import models  # noqa: E402

DEFAULT_QUESTIONS = os.path.join(ROOT, "simulation", "questions")
DEFAULT_REVIEWS = os.path.join(ROOT, "simulation", "reviews")
DEFAULT_OUTPUT = os.path.join(HERE, "simulation")

esc = results.esc
href = results.href
model_name = results.model_name
task_text = results.task_text
join_cn = results.join_cn

FOLD_FILE = 6000    # 文件超过这么多字就折叠起来，点开看全文
FOLD_CALL = 2000    # 提示词和回答超过这么多字就折叠起来

QUESTION_FILES = [
    ("card", "题目卡.txt", "题目卡的三个版本", "评委版、提问版、裸题版，以及附在交给智能体的版本之后的交付要求和说明。"),
    ("asked", "提问版.txt", "提问版：交给智能体的全文", "智能体收到的就是这个文件，一字不差。"),
    ("bare", "裸题版.txt", "裸题版：交给智能体的全文", "智能体收到的就是这个文件，一字不差。"),
    ("map", "深度地图.txt", "深度地图", "浅答案、转折点、要点表，以及两人对照、泄露检查、闭卷对照三项记录的摘要。"),
    ("pair", "两人对照记录.md", "两人对照记录", "每一轮两位出题人各自的地图、配对和数鱼的计算。"),
    ("leak", "泄露检查记录.md", "泄露检查记录", "另一个模型只看交给智能体的两个版本，回答三个问题。"),
    ("closed", "闭卷对照记录.md", "闭卷对照记录", "换一家模型不联网作答，看它答到了哪几条核心要点。"),
]

NOTE_NAMES = {
    "evidence_not_found": "引文在报告里找不到的环节评级",
    "not_merged": "合并时漏收的条目",
    "unknown_sources": "来源编号不认识的条目",
    "map_points_added": "程序补进要点池的地图要点",
    "map_points_merged_together": "合在一起的地图要点",
    "unjudged_points": "没有评委判定的要点",
    "unverified_claims": "没有核验意见的结论",
    "ignored_map_changes": "没写理由、按登记值计的改动次数",
    "reach_added": "写到核对补记的条数",
}

EXTRA_STYLE = """
  /* 模拟出题和模拟评审页面另加的样式：原文块、字段表 */
  .raw { margin: 8px 0 0; padding: 12px 16px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface);
    white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; tab-size: 4;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 14px; line-height: 20px; }
  code { overflow-wrap: anywhere; }
  .fields { margin: 16px 0 0; max-width: 880px; border-top: 1px solid var(--line); }
  .fields > div { display: grid; grid-template-columns: 176px minmax(0, 1fr); gap: 16px; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .fields dt { color: var(--ink-3); }
  .fields dd { margin: 0; min-width: 0; }
  .fields dd p + p { margin-top: 4px; }
  @media (max-width: 639px) { .fields > div { grid-template-columns: minmax(0, 1fr); gap: 4px; } }
  .file + .file { margin-top: 32px; }
  .file-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; }
  .card .fields { margin-top: 8px; border-top: 0; }
  .card .fields > div { padding: 4px 0; border-bottom: 0; }
  .empty { margin-top: 16px; padding: 16px; border-radius: 12px; background: var(--surface); color: var(--ink-2); max-width: 760px; }
  .alert { margin-top: 32px; padding: 16px; border-radius: 12px; border: 1px solid var(--bad); background: var(--surface); max-width: 880px; }
  .alert strong { color: var(--bad); }
"""


# ---------- 读文件 ----------

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def subdirs(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(name for name in os.listdir(folder)
                  if os.path.isdir(os.path.join(folder, name)) and not name.startswith("."))


def is_public(meta):
    """练习题公开；正式题只有元数据里写明 "已公开": true 才公开；类别不明的按未公开处理。"""
    return meta.get("类别") == "练习题" or meta.get("已公开") is True


class Question:
    def __init__(self, folder):
        self.folder = folder
        self.id = os.path.basename(folder)
        path = os.path.join(folder, "元数据.json")
        self.meta = load(path) if os.path.isfile(path) else {}
        self.public = is_public(self.meta)
        self.calls = results.read_jsonl(os.path.join(folder, "调用记录.jsonl"))
        card = read_text(os.path.join(folder, "题目卡.txt")) or ""
        m = re.search(r"【问题】(.+)", card)
        self.question = m.group(1).strip() if m else None
        self.checksum = read_checksum(folder, self.meta)
        self.reviews = []

    def date(self):
        return self.meta.get("写成日期") or (self.meta.get("生成时间") or "")[:10]


def read_checksum(folder, meta):
    text = read_text(os.path.join(folder, "深度地图校验值.txt"))
    if text and text.split():
        return text.split()[0]
    return (meta.get("深度地图校验值") or {}).get("值")


class Review:
    def __init__(self, folder, bank):
        self.folder = folder
        self.id = os.path.basename(folder)
        self.run = load(os.path.join(folder, "run.json"))
        self.calls = results.read_jsonl(os.path.join(folder, "calls.jsonl"))
        self.mapping = load(os.path.join(folder, "mapping.json")) if os.path.isfile(os.path.join(folder, "mapping.json")) else {}
        self.has_results = os.path.isfile(os.path.join(folder, "results-v1.2.json"))
        self.results = load(os.path.join(folder, "results-v1.2.json")) if self.has_results else None
        q = self.run.get("question") or {}
        qdir = q.get("dir")
        qid = os.path.basename(os.path.normpath(qdir)) if qdir else None
        self.question = bank.get(qid)
        if self.question is not None:
            meta = self.question.meta
        elif qdir and os.path.isfile(os.path.join(qdir, "元数据.json")):
            meta = load(os.path.join(qdir, "元数据.json"))
        else:
            meta = {"类别": q.get("kind")}
        self.kind = meta.get("类别")
        self.public = is_public(meta)
        self.question_id = qid

    def labels(self):
        return [r["label"] for r in self.run.get("reports", [])]


# ---------- 文字 ----------

def shown(ident):
    """题目标识和运行标识放进可见文字时，连字符换成空格；原样的写法另外放在代码样式里。"""
    return ident.replace("-", " ")


def day(text):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text or "")
    if not m:
        return text or "没有记下"
    y, mo, d = (int(x) for x in m.groups())
    return f"{y} 年 {mo} 月 {d} 日"


def zone_words(zone):
    """时区的白话写法，与 tools/archive_sources.py 一样称协调世界时：
    -07:00 写成"协调世界时减 7 小时"，+05:30 写成"协调世界时加 5 小时 30 分"，Z 写成"协调世界时"。"""
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", zone)
    if zone == "Z" or not m or m.group(2) == m.group(3) == "00":
        return "协调世界时"
    hours, minutes = int(m.group(2)), int(m.group(3))
    return f"协调世界时{'加' if m.group(1) == '+' else '减'} {hours} 小时" + (f" {minutes} 分" if minutes else "")


def when(text):
    """2026-10-30T20:03:45.125-07:00 写成 2026 年 10 月 30 日 20:03:45.125（协调世界时减 7 小时）。"""
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)(Z|[+-]\d{2}:\d{2})?", text or "")
    if not m:
        return text or "没有记下"
    zone = f"（{zone_words(m.group(3))}）" if m.group(3) else ""
    return f"{day(m.group(1))} {m.group(2)}{zone}"


def seconds(x):
    if x is None:
        return "没有记下"
    return f"{results.num(round(float(x), 3))} 秒"


def model_text(record):
    """一次调用用的模型：命令行报告的优先，其次是指定的，都没有就是命令行默认模型。"""
    m = record.get("reported_model") or record.get("model")
    return model_name(m) if m else "命令行默认模型"


def counts_text(by_vendor):
    return "、".join(f"{v} {n} 次" for v, n in by_vendor.items()) if by_vendor else "没有调用"


def vendor_summary(calls):
    """[(公司, 厂商, 次数, 成功次数, 模型)]，按第一次出现的先后。"""
    rows = {}
    for c in calls:
        key = (c.get("company") or c["vendor"], c["vendor"])
        row = rows.setdefault(key, {"n": 0, "ok": 0, "models": []})
        row["n"] += 1
        row["ok"] += c.get("status") == models.SUCCEEDED
        if c.get("status") == models.SUCCEEDED:
            m = model_text(c)
            if m not in row["models"]:
                row["models"].append(m)
    return [(k[0], k[1], v["n"], v["ok"], v["models"]) for k, v in rows.items()]


def vendors_text(calls):
    parts = []
    for company, vendor, n, ok, ms in vendor_summary(calls):
        parts.append(f"{company}（{vendor}，{join_cn(ms) if ms else '没有成功的调用'}）")
    return "、".join(parts) if parts else "没有调用"


def kv(d):
    return "；".join(f"{k}：{v}" for k, v in d.items())


def compact(value):
    return json.dumps(value, ensure_ascii=False)


# ---------- 页面骨架 ----------

def shell(to_site, title, description, body):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · 深度研究评测基准</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="{to_site}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600&display=swap">
<style>{results.STYLE}{EXTRA_STYLE}</style>
</head>
<body>
<a class="skip caption-1" href="#main">跳到正文</a>
{body}
</body>
</html>
"""


class Site:
    """写页面：记下输出目录，算出每一页到资料站其他页面的相对链接。"""

    def __init__(self, output, questions_dir, reviews_dir):
        self.output = output
        self.questions_dir = questions_dir
        self.reviews_dir = reviews_dir
        self.pages = {}

    def path(self, *parts):
        return os.path.join(self.output, *parts)

    def link(self, target, page):
        """从 page（输出目录里的一页）到 target（文件系统里的路径）的相对链接。"""
        return href(target, os.path.dirname(page))

    def to_site(self, page):
        return self.link(HERE, page) + "/"

    def add(self, page, text):
        self.pages[page] = text

    def write(self, folder):
        """把全部页面写进 folder；folder 与输出目录同一层，页面在里面的位置与在输出目录里相同。"""
        for page, text in self.pages.items():
            path = os.path.join(folder, os.path.relpath(page, self.output))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def header(self, page, back, back_text, eyebrow, title_html, lede_html, current=None):
        nav = [(self.path("questions.html"), "题库"), (self.path("reviews.html"), "评审记录")]
        here = ' aria-current="page"'
        lis = "".join(f'<li><a class="caption-1" href="{self.link(p, page)}"{here if p == current else ""}>{t}</a></li>'
                      for p, t in nav)
        return f"""<header class="top">
  <div class="wrap">
    <a class="back caption-1" href="{back}">← {esc(back_text)}</a>
    <p class="eyebrow caption-1">{eyebrow}</p>
    <h1 class="heading-3">{title_html}</h1>
    <p class="body-3 lede">{lede_html}</p>
    <nav aria-label="模拟出题和模拟评审"><ul class="pages">{lis}</ul></nav>
  </div>
</header>"""

    def footer(self, page):
        return (f'<footer><div class="wrap caption-2"><p>本页由 <code>site/build_simulation.py</code> 从模拟出题和模拟评审的输出目录生成，'
                f'不手工修改。<a href="{self.to_site(page)}index.html">回到资料站</a></p></div></footer>')

    def page(self, page, title, description, head, sections):
        body = "\n".join([head, '<main id="main"><div class="wrap">', *sections, "</div></main>", self.footer(page)])
        self.add(page, shell(self.to_site(page), title, description, body))


def section(sid, title, intro, content):
    intro_html = "".join(f'<p class="body-3 sum">{p}</p>' for p in ([intro] if isinstance(intro, str) else intro) if p)
    return f"""<section class="block" id="{sid}" aria-labelledby="{sid}-h">
  <h2 class="heading-5" id="{sid}-h">{title}</h2>
  {intro_html}
  {content}
</section>"""


def fields(rows):
    """rows 是 [(名称, 已转义的值)]。"""
    items = "".join(f'<div><dt class="caption-1">{name}</dt><dd class="body-6">{value}</dd></div>' for name, value in rows)
    return f'<dl class="fields">{items}</dl>'


def raw_block(text, pre_id, fold_at, what):
    """原文放在 pre 里，一字不改；超过 fold_at 字就放进可折叠的 details，点开看全文。"""
    pre = f'<pre class="raw" id="{pre_id}">\n{esc(text)}</pre>'
    if len(text) > fold_at:
        return (f'<details><summary class="caption-2">{what}共 {len(text)} 字，点开看全文</summary>{pre}</details>')
    return pre


# ---------- 调用原文页 ----------

def call_page(site, page, record, n, total, owner, back, back_text, raw_file):
    """一次模型调用的原文页。owner 是"模拟评审 xxx"或"模拟出题 xxx"。"""
    def call_link(i):
        return site.link(os.path.join(os.path.dirname(page), f"{i}.html"), page)
    pager = []
    if n > 1:
        pager.append(f'<li><a class="caption-1" href="{call_link(n - 1)}">上一次调用</a></li>')
    if n < total:
        pager.append(f'<li><a class="caption-1" href="{call_link(n + 1)}">下一次调用</a></li>')
    pager.append(f'<li><a class="caption-1" href="{back}#calls">全部调用</a></li>')
    status = record.get("status") or "没有记下"
    tone = {models.SUCCEEDED: "ok", models.FAILED: "bad", models.TIMED_OUT: "bad"}.get(status, "")
    rows = [
        ("任务名", f'<code>{esc(record.get("task", ""))}</code>'),
        ("厂商", esc(f'{record.get("company") or ""}（{record.get("vendor", "")}）')),
        ("指定的模型", esc(model_name(record["model"])) + f'（<code>{esc(record["model"])}</code>）' if record.get("model")
         else "没有指定，用命令行的默认模型"),
        ("命令行报告的模型", esc(model_name(record["reported_model"])) + f'（<code>{esc(record["reported_model"])}</code>）'
         if record.get("reported_model") else "没有报告"),
        ("命令行报告的可用工具", f'<code>{esc(compact(record["reported_tools"]))}</code>' if record.get("reported_tools") is not None
         else "没有报告"),
        ("工具限定", esc(record.get("tools") or "没有记下")),
        ("方式", esc(record.get("mode") or "没有记下")),
        ("状态", results.tag(status, tone)),
    ]
    if record.get("error"):
        rows.append(("失败的原因", f'<code>{esc(record["error"])}</code>'))
    rows += [
        ("开始时间", esc(when(record.get("started_at")))),
        ("结束时间", esc(when(record.get("ended_at")))),
        ("耗时", esc(seconds(record.get("duration_seconds")))),
        ("提示词校验值", f'<code>{esc(record.get("prompt_sha256") or "")}</code>'),
        ("回答校验值", f'<code>{esc(record.get("answer_sha256") or "")}</code>'),
    ]
    if record.get("command"):
        rows.append(("命令行参数", f'<code>{esc(" ".join(str(x) for x in record["command"]))}</code>'))
    if record.get("exit_code") is not None:
        rows.append(("退出状态", esc(str(record["exit_code"]))))
    if record.get("replayed_from"):
        rows.append(("回放出处", f'<code>{esc(compact(record["replayed_from"]))}</code>'))
    rows.append(("调用记录", f'<a href="{site.link(raw_file, page)}">调用记录文件</a>的第 {n} 行'
                 + (f'，记录里的序号是 {esc(str(record["call_index"]))}' if record.get("call_index") is not None else "")))

    prompt = record.get("prompt") or ""
    answer = record.get("answer") or ""
    parts = [section("info", "这次调用", f"{esc(owner)}的第 {n} 次调用，共 {total} 次。字段的含义见"
                     f'<a href="{site.link(os.path.join(ROOT, "tools", "models.md"), page)}">模型调用层使用说明</a>的调用记录一节。',
                     fields(rows) + f'<nav aria-label="前后的调用"><ul class="pages">{"".join(pager)}</ul></nav>'),
             section("prompt-text", "提示词全文", f"共 {len(prompt)} 字，从标准输入交给命令行，一字不改。",
                     raw_block(prompt, "prompt", FOLD_CALL, "提示词"))]
    if answer:
        parts.append(section("answer-text", "回答全文", f"共 {len(answer)} 字，一字不改。", raw_block(answer, "answer", FOLD_CALL, "回答")))
    else:
        parts.append(section("answer-text", "回答全文", f"这次调用没有回答（状态：{esc(status)}）。", ""))
    if record.get("config_files"):
        blocks = "".join(f'<div class="file"><h3 class="title-3"><code>{esc(name)}</code></h3>{raw_block(text, f"config-{i}", FOLD_FILE, "")}</div>'
                         for i, (name, text) in enumerate(sorted(record["config_files"].items()), 1))
        parts.append(section("config", "调用前写进临时目录的设置文件", "", blocks))
    if record.get("raw_output") or record.get("stderr"):
        blocks = ""
        if record.get("raw_output"):
            blocks += f'<details><summary class="caption-2">标准输出原文，共 {len(record["raw_output"])} 字</summary>' \
                      f'<pre class="raw" id="raw-output">\n{esc(record["raw_output"])}</pre></details>'
        if record.get("stderr"):
            blocks += f'<details><summary class="caption-2">标准错误，共 {len(record["stderr"])} 字</summary>' \
                      f'<pre class="raw" id="stderr">\n{esc(record["stderr"])}</pre></details>'
        parts.append(section("output", "命令行的原始输出", "各家命令行的事件流原样保存，供复核。", blocks))
    head = site.header(page, back, back_text, f"{esc(owner)} · 第 {n} 次调用", esc(task_text(record.get("task", ""))),
                       f"{esc(record.get('company') or '')}（{esc(record.get('vendor', ''))}），{esc(model_text(record))}，"
                       f"{esc(record.get('tools') or '')}，{esc(status)}。")
    site.page(page, f"{owner} 第 {n} 次调用", f"{owner}第 {n} 次模型调用的提示词和回答原文。", head, parts)


def calls_table(site, page, calls, calls_dir, linked):
    """全部调用的表：linked 为假时只列信息，不链接原文页。"""
    rows = []
    for i, c in enumerate(calls, 1):
        name = esc(task_text(c.get("task", "")))
        no = f'<a href="{site.link(os.path.join(calls_dir, f"{i}.html"), page)}">{i}</a>' if linked else str(i)
        rows.append([no, name, esc(c.get("vendor", "")), esc(model_text(c)), esc(c.get("tools") or ""),
                     esc(c.get("status") or ""), esc(seconds(c.get("duration_seconds")))])
    return results.table(["序号", "任务", "厂商", "模型", "工具限定", "状态", "耗时"], rows, numeric=(0,))


# ---------- 题库 ----------

def question_page(site, q):
    page = site.path("questions", q.id, "index.html")
    bank = site.path("questions.html")
    meta = q.meta
    kind = meta.get("类别") or "类别不明"
    lede = (f"{esc(kind)}。" + ("公开题目卡的三个版本、深度地图、三项检查记录和每一次模型调用的原文。" if q.public else
                                "这道题在公开之前只显示深度地图的校验值，题目卡、深度地图和调用原文都不显示。"))
    head = site.header(page, site.link(bank, page), "回到题库", f"模拟出题 · {esc(kind)}", esc(shown(q.id)), lede)
    checksum = f'<code>{esc(q.checksum)}</code>' if q.checksum else "没有深度地图"
    verify = ("在题目目录里运行 <code>shasum -a 256 -c 深度地图校验值.txt</code>（Linux 上用 <code>sha256sum -c</code>），"
              "可以核对深度地图在写成之后没有改过。")
    reviews = "、".join(f'<a href="{site.link(site.path("reviews", r.id, "index.html"), page)}">{esc(shown(r.id))}</a>'
                       for r in q.reviews) or "还没有"
    if not q.public:
        rows = [("题目标识", f"<code>{esc(q.id)}</code>"), ("类别", esc(kind)), ("是否公开", "未公开"),
                ("状态", esc(meta.get("状态") or "没有记下")), ("写成日期", esc(day(q.date()))),
                ("调用次数", f"{len(q.calls)} 次"), ("深度地图校验值", checksum),
                ("用这道题的模拟评审", reviews)]
        sections = [section("summary", "这道题", [
            "正式题赛前只公开深度地图的校验值。比赛结束、主办方在这道题的元数据里写明 <code>\"已公开\": true</code> 之后，"
            "重新运行生成器，这一页就会显示题目卡、深度地图和每一次调用的原文。", verify], fields(rows)),
            section("calls", "调用记录", "出这道题时的每一次模型调用。题目公开之前，只列出调用的步骤和厂商，提示词和回答的原文不显示。",
                    calls_table(site, page, q.calls, "", False) if q.calls else '<p class="empty body-6">没有调用记录。</p>')]
        site.page(page, f"题目 {shown(q.id)}", f"{kind}{shown(q.id)}：公开之前只显示深度地图的校验值。", head, sections)
        return

    rows = [("题目标识", f"<code>{esc(q.id)}</code>"), ("类别", esc(kind)),
            ("是否公开", "公开" + ("（元数据里写明已公开）" if meta.get("已公开") is True else "（练习题）")),
            ("状态", esc(meta.get("状态") or "没有记下"))]
    if meta.get("停止的原因"):
        rows.append(("停止的原因", esc(meta["停止的原因"])))
    for key in ("话题", "题型"):
        if meta.get(key):
            rows.append((key, esc(meta[key])))
    if q.question:
        rows.append(("问题", esc(q.question)))
    rows += [("写成日期", esc(day(q.date())))]
    if meta.get("生成时间"):
        rows.append(("生成时间", esc(when(meta["生成时间"]))))
    if meta.get("方式"):
        rows.append(("方式", esc(meta["方式"])))
    calls_n = (meta.get("调用次数") or {}).get("按厂商")
    rows += [("调用次数", f"{len(q.calls)} 次" + (f"：{esc(counts_text(calls_n))}" if calls_n else "")),
             ("深度地图校验值", checksum),
             ("题目目录", f'<a href="{site.link(q.folder, page)}/元数据.json">元数据.json</a>，目录 <code>{esc(results.repo_path(q.folder))}</code>'),
             ("用这道题的模拟评审", reviews)]
    notes = meta.get("说明") or []
    intro = [verify] + ([f"说明：{esc(n)}" for n in notes] if notes else [])
    sections = [section("summary", "这道题", intro, fields(rows))]

    checks = meta.get("检查结果")
    if checks:
        standard = checks.get("写完标准") or {}
        items = [f'<li class="card"><div class="card-head"><span class="title-3">{esc(k)}</span>'
                 f'{results.tag("满足", "ok") if v else results.tag("没有满足", "bad")}</div></li>' for k, v in standard.items()]
        crows = [("四层里没有要点的层", esc(join_cn(checks.get("四层里没有要点的层") or []) or "没有")),
                 ("泄露检查", esc(str(checks.get("泄露检查", "没有记下")))),
                 ("闭卷对照", esc(str(checks.get("闭卷对照", "没有记下")))),
                 ("全部通过", "是" if checks.get("全部通过") else "否")]
        sections.append(section("checks", "检查结果", "程序能机械判断的部分：写完标准五条、泄露检查和闭卷对照。要点的对错、核心判得准不准，还要靠领域专家审阅。",
                                f'<ul class="cards grid-2">{"".join(items)}</ul>' + fields(crows)))
    roles = meta.get("角色")
    if roles:
        trows = []
        for role, info in roles.items():
            subs = "；".join(f"{task_text(s['任务'])}：{s['原来的厂商']} 改用 {s['改用的厂商']}（{s['原因']}）"
                            for s in info.get("替代", []))
            models = info.get("命令行报告的模型") or [m for m in (info.get("指定的模型") or {}).values() if m]
            trows.append([esc(role), esc(info.get("配置的厂商") or ""), esc(join_cn(info.get("用到的厂商") or [])),
                          esc(join_cn(model_name(m) for m in models) or "命令行默认模型"), esc(join_cn(info.get("工具限定") or [])),
                          esc(subs or "没有")])
        outages = meta.get("厂商不可用") or []
        gone = "".join(f'<li><code>{esc(kv(o))}</code></li>' for o in outages)
        sections.append(section("roles", "角色和厂商", "每个角色配置的是哪家、实际用了哪家；某一家不可用时换了哪家。",
                                results.table(["角色", "配置的厂商", "用到的厂商", "模型", "工具限定", "替代"], trows)
                                + (f'<div class="sub"><h3 class="heading-6">不可用的厂商</h3><ul class="links body-6">{gone}</ul></div>' if gone else "")))
    files = []
    for fid, name, title, note in QUESTION_FILES:
        text = read_text(os.path.join(q.folder, name))
        if text is None:
            files.append(f'<div class="file" id="file-{fid}"><h3 class="heading-6">{esc(title)}</h3>'
                         f'<p class="body-6 muted">这道题没有这个文件{"，原因见上面的说明" if notes else ""}。</p></div>')
            continue
        files.append(f'<div class="file" id="file-{fid}"><div class="file-head"><h3 class="heading-6">{esc(title)}</h3>'
                     f'<a class="caption-2" href="{site.link(os.path.join(q.folder, name), page)}">原文件</a></div>'
                     f'<p class="body-6 muted">{esc(note)}</p>{raw_block(text, fid, FOLD_FILE, "")}</div>')
    sections.append(section("files", "题目卡、深度地图和检查记录", "下面是题目目录里的文件原文，一字不改。", "".join(files)))
    if q.calls:
        sections.append(section("calls", "调用记录", f"出这道题时的 {len(q.calls)} 次模型调用，点序号看提示词和回答的原文。",
                                calls_table(site, page, q.calls, site.path("questions", q.id, "calls"), True)))
        raw = os.path.join(q.folder, "调用记录.jsonl")
        for i, record in enumerate(q.calls, 1):
            call_page(site, site.path("questions", q.id, "calls", f"{i}.html"), record, i, len(q.calls),
                      f"模拟出题 {shown(q.id)}", site.link(page, site.path("questions", q.id, "calls", "x.html")), "回到这道题", raw)
    else:
        sections.append(section("calls", "调用记录", esc(meta.get("方式") or "这道题没有调用记录。"), ""))
    site.page(page, f"题目 {shown(q.id)}", f"{kind}{shown(q.id)}的题目卡、深度地图、检查记录和调用原文。", head, sections)


def bank_page(site, questions):
    page = site.path("questions.html")
    head = site.header(page, f"{site.to_site(page)}index.html", "回到资料站", "模拟出题 · 题库", "题库",
                       "主办方用大模型按出题手册模拟出的题目，以及由第五阶段试评转来的题目。练习题公开题目卡的三个版本和深度地图；"
                       "正式题在公开之前只显示深度地图的校验值，题目卡和深度地图的内容都不显示。", page)
    cards = []
    for q in questions:
        link = site.link(site.path("questions", q.id, "index.html"), page)
        kind = q.meta.get("类别") or "类别不明"
        tags = [results.tag(kind, "plain"), results.tag("公开", "ok") if q.public else results.tag("未公开", "warn"),
                results.tag(q.meta.get("状态") or "状态不明", "plain")]
        rows = []
        if q.public:
            if q.meta.get("话题"):
                rows.append(("话题", esc(q.meta["话题"])))
            rows.append(("问题", esc(q.question or "题目卡里没有找到问题一栏")))
        else:
            rows.append(("问题", "正式题，公开之前不显示"))
        rows += [("写成日期", esc(day(q.date()))),
                 ("深度地图校验值", f'<code>{esc(q.checksum)}</code>' if q.checksum else "没有深度地图")]
        if q.reviews:
            rows.append(("模拟评审", "、".join(f'<a href="{site.link(site.path("reviews", r.id, "index.html"), page)}">{esc(shown(r.id))}</a>'
                                           for r in q.reviews)))
        cards.append(f'<li class="card" id="question-{esc(q.id)}"><div class="card-head"><a class="title-3" href="{link}">{esc(shown(q.id))}</a>'
                     f'{"".join(tags)}</div>{fields(rows)}</li>')
    listing = f'<ul class="cards">{"".join(cards)}</ul>' if cards else '<p class="empty body-6">还没有题目。</p>'
    practice = sum(1 for q in questions if q.meta.get("类别") == "练习题")
    sections = [
        section("all", "全部题目", f"共 {len(questions)} 道，其中练习题 {practice} 道。点题目看详情。", listing),
        section("checksum", "校验值怎样用", [
            "深度地图写成之后、任何报告出现之前，先公开它的校验值。比赛结束公开地图全文时，任何人都能算一遍校验值，"
            "核对地图在看到报告之后没有改过。",
            "核对的办法：在题目目录里运行 <code>shasum -a 256 -c 深度地图校验值.txt</code>（Linux 上用 <code>sha256sum -c</code>）。"
            f'题目目录的格式见<a href="{site.link(os.path.join(ROOT, "tools", "simulate_setter.md"), page)}">模拟出题者使用说明</a>。'], ""),
    ]
    site.page(page, "题库", "模拟出题的题库：练习题公开全文，正式题赛前只公开深度地图的校验值。", head, sections)


# ---------- 评审记录 ----------

def results_links(site, review, page):
    folder = site.path("reviews", review.id, "results")
    rank = site.link(os.path.join(folder, "index.html"), page)
    points = site.link(os.path.join(folder, "points.html"), page)
    reports = "、".join(f'<a href="{site.link(os.path.join(folder, f"report-{r}.html"), page)}">报告 {esc(r)}</a>' for r in review.labels())
    return f'<a href="{rank}">名次页</a>、<a href="{points}">要点池</a>；复核页：{reports}'


def result_state(review):
    """这次评审的结果在哪里：返回 (有没有名次页, 说明)。"""
    if not review.public:
        return False, "这道题是还没有公开的正式题：名次页、复核页和调用原文等题目公开后再显示。"
    if review.has_results:
        return True, ""
    if review.run.get("mode") == models.ESTIMATE:
        return False, "只估算，没有调用模型，也没有结果。"
    if review.run.get("status") != "完成":
        return False, f"评审中止，没有结果。原因：<code>{esc(review.run.get('error') or '没有记下')}</code>"
    return False, "没有结果文件。"


def review_rows(site, review, page):
    run = review.run
    calls = run.get("calls") or {}
    q = review.question
    if q is not None:
        qtext = f'<a href="{site.link(site.path("questions", q.id, "index.html"), page)}">{esc(shown(q.id))}</a>（{esc(review.kind or "类别不明")}）'
    else:
        qtext = (f"<code>{esc(review.question_id)}</code>" if review.question_id else "没有记下") + f"（{esc(review.kind or '类别不明')}，不在题库里）"
    names = review.mapping.get("reports", {})
    reports = "、".join(f"{esc(r)}（{esc(names.get(r, r))}）" for r in review.labels())
    rows = [("题目", qtext), ("报告", f"{len(review.labels())} 份：{reports}"),
            ("时间", f"{esc(when(run.get('started_at')))} 至 {esc(when(run.get('finished_at')))}"),
            ("调用次数", f"共 {calls.get('calls', len(review.calls))} 次：{esc(counts_text(calls.get('by_vendor') or {}))}")]
    if run.get("mode") == models.ESTIMATE:
        rows[-1] = ("将要发起的调用次数", rows[-1][1] + "。只估算，没有真的调用")
        rows.append(("配置的厂商", esc("、".join(f"{c}（{v}）" for c, v, *_ in vendor_summary(review.calls)) or "没有")))
    else:
        rows.append(("厂商和模型", esc(vendors_text(review.calls))))
    if run.get("estimate"):
        rows.append(("开始前估算的调用次数", f"{run['estimate'].get('calls')} 次"))
    gone = run.get("unavailable") or []
    if gone:
        rows.append(("不可用的厂商", esc(join_cn(f"{u.get('vendor')}（{u.get('company')}）" for u in gone))))
    if run.get("substitutions"):
        rows.append(("替代", f"{len(run['substitutions'])} 次"))
    ok, why = result_state(review)
    rows.append(("结果", results_links(site, review, page) if ok else why))
    return rows


def rule_warning(run):
    """计划用三家以上、替代之后不足三家的步骤（run.json 的 too_few_vendors）：放在评审页最前面的醒目的一句话。"""
    found = run.get("too_few_vendors") or []
    if not found:
        return ""
    steps = "；".join(f"{item['step']}计划用 {'、'.join(item['planned_vendors'])}，实际只用了 {'、'.join(item['used_vendors'])}"
                     for item in found)
    return (f'<div class="alert" id="rule-warning" role="note"><p class="body-3"><strong>这次评审有 {len(found)} 步不合'
            f'{esc(found[0]["rule"])}：{esc(steps)}。</strong>评审照样做完了，结果只能当演示看。</p></div>')


def reviews_page(site, reviews):
    page = site.path("reviews.html")
    head = site.header(page, f"{site.to_site(page)}index.html", "回到资料站", "模拟评审 · 评审记录", "评审记录",
                       "每一次模拟评审用了哪些厂商和模型、调用了几次、结果怎样。结果链接到这次评审的名次页和复核页；"
                       "每一次模型调用都能点开看提示词和回答的原文。", site.path("reviews.html"))
    cards = []
    for r in reviews:
        link = site.link(site.path("reviews", r.id, "index.html"), page)
        tags = [results.tag(r.run.get("mode") or "方式不明", "plain"),
                results.tag(r.run.get("status") or "状态不明", "ok" if r.run.get("status") == "完成" else "bad")]
        cards.append(f'<li class="card" id="review-{esc(r.id)}"><div class="card-head"><a class="title-3" href="{link}">{esc(shown(r.id))}</a>'
                     f'{"".join(tags)}</div>{fields(review_rows(site, r, page))}</li>')
    listing = f'<ul class="cards">{"".join(cards)}</ul>' if cards else '<p class="empty body-6">还没有模拟评审的记录。</p>'
    pilot = os.path.join(HERE, "results", "index.html")
    sections = [section("all", "全部评审", f"共 {len(reviews)} 次。点运行标识看这次评审的详情和全部调用。", listing)]
    if os.path.isfile(pilot):
        sections.append(section("pilot", "第五阶段试评", f'第五阶段试评不是由模拟评审程序完成的：评委运行的提示词另外存了档。它的名次见'
                                f'<a href="{site.link(pilot, page)}">试评名次</a>。', ""))
    site.page(page, "评审记录", "每一次模拟评审用了哪些厂商和模型、调用了几次，以及名次页、复核页和每一次调用的原文。", head, sections)


def review_page(site, review):
    page = site.path("reviews", review.id, "index.html")
    folder = review.folder
    run = review.run
    head = site.header(page, site.link(site.path("reviews.html"), page), "回到评审记录", "模拟评审",
                       f"模拟评审 {esc(shown(review.id))}",
                       f"方式：{esc(run.get('mode') or '没有记下')}；状态：{esc(run.get('status') or '没有记下')}。"
                       "这次评审用了哪些厂商和模型、每一步调用了几次、结果，以及每一次调用的原文。")
    q = run.get("question") or {}
    rows = [("运行标识", f"<code>{esc(run.get('run_id') or review.id)}</code>")] + review_rows(site, review, page)
    if run.get("error"):
        rows.append(("中止的原因", f"<code>{esc(run['error'])}</code>"))
    rows += [("截止日期", esc(day(q.get("cutoff")) if q.get("cutoff") else "没有给出，提示词里写的是以题目卡为准")),
             ("题目卡校验值", f'<code>{esc(q.get("card_sha256") or "")}</code>'),
             ("深度地图校验值", (f'<code>{esc(q["depth_map_sha256"])}</code>，' + ("和校验值文件一致" if q.get("checksum_matches") else "和校验值文件不一致")
                           if q.get("depth_map_sha256") else "题目目录里没有深度地图.txt，没有核对"))]
    archive = run.get("archive") or {}
    if archive.get("dir"):
        rows.append(("网页存档", f"可用的存档 {archive.get('usable_urls', 0)} 条，清单 {len(archive.get('manifests') or [])} 份"))
    if review.public:
        rows.append(("输出目录", f'<a href="{site.link(os.path.join(folder, "run.json"), page)}">run.json</a>、'
                                f'<a href="{site.link(os.path.join(folder, "calls.jsonl"), page)}">calls.jsonl</a>，'
                                f'目录 <code>{esc(results.repo_path(folder))}</code>'))
    sections = [rule_warning(run), section("summary", "这次评审", "", fields(rows))]

    ok, why = result_state(review)
    if ok:
        rank_rows = []
        res = {r["label"]: r for r in review.results["reports"]}
        for label in review.labels():
            r = res.get(label)
            if r:
                rank_rows.append([f'<a href="{site.link(site.path("reviews", review.id, "results", f"report-{label}.html"), page)}">报告 {esc(label)}</a>',
                                  esc(r.get("product") or ""), esc(results.interval(r)),
                                  esc(join_cn(r.get("severe_problems") or []) or "无")])
        sections.append(section("results", "结果", [results_links(site, review, page),
                                                  "名次区间由计分程序第 1.2 版算出，排法见名次页。"],
                                results.table(["报告", "名称", "名次区间", "严重问题"], rank_rows)))
    else:
        sections.append(section("results", "结果", why, ""))

    if review.public:
        names = review.mapping.get("reports", {})
        rrows = [[f'<a href="{site.link(os.path.join(folder, r["copy"]), page)}">报告 {esc(r["label"])}</a>' if r.get("copy") else f'报告 {esc(r["label"])}',
                  esc(names.get(r["label"], r.get("name") or "")), esc(str(r.get("characters", ""))), esc(str(r.get("urls", ""))),
                  f'<code>{esc(r.get("sha256") or "")}</code>'] for r in run.get("reports", [])]
        sections.append(section("reports", "报告", "评委看不到报告的原名；点编号看交给评委的报告副本。",
                                results.table(["编号", "名称", "字数", "网址个数", "校验值"], rrows, numeric=(2, 3))))

    vrows = [[esc(company), esc(vendor), str(n), str(ok_n), esc(join_cn(ms) or "没有成功的调用")]
             for company, vendor, n, ok_n, ms in vendor_summary(review.calls)]
    extra = ""
    gone = run.get("unavailable") or []
    if gone:
        extra += (f'<div class="sub"><h3 class="heading-6">不可用的厂商</h3>'
                  + results.table(["厂商", "公司", "第一次失败的任务", "原因", "发现的时间"],
                                  [[esc(u.get("vendor", "")), esc(u.get("company", "")), esc(task_text(u.get("first_failed_task", ""))),
                                    f'<code>{esc(u.get("error") or "")}</code>', esc(when(u.get("noticed_at")))] for u in gone]) + "</div>")
    subs = run.get("substitutions") or []
    if subs:
        extra += (f'<div class="sub"><h3 class="heading-6">替代</h3>'
                  + results.table(["步骤", "任务", "原来的厂商", "改用的厂商", "原因"],
                                  [[esc(s["步骤"]), esc(task_text(s["任务"])), esc(s["原来的厂商"]), esc(s["改用的厂商"]),
                                    esc(s["原因"])] for s in subs]) + "</div>")
    sections.append(section("vendors", "厂商和模型", "按调用记录统计：每一家调用了几次、成功几次、用的是什么模型（命令行报告的模型优先，其次是指定的模型）。",
                            results.table(["公司", "厂商", "调用次数", "成功", "模型"], vrows, numeric=(2, 3)) + extra))

    steps = run.get("steps") or {}
    srows = []
    for name, st in steps.items():
        planned = "、".join(f"评委 {p.get('slot')} {p.get('vendor')}" for p in st.get("planned", []))
        ms = "；".join(f"{v}：{join_cn(model_name(m) if m != '命令行默认模型' else m for m in lst)}" for v, lst in (st.get("models") or {}).items())
        srows.append([esc(name), esc(planned), str(st.get("calls", 0)), esc(counts_text(st.get("by_vendor") or {})), esc(ms)])
    calls = run.get("calls") or {}
    est = run.get("estimate")
    intro = [f"实际调用 {calls.get('calls', len(review.calls))} 次"
             + (f"，开始前估算 {est.get('calls')} 次" if est else "")
             + (f"，上限 {calls.get('max_calls')} 次" if calls.get("max_calls") else "") + "。"]
    if run.get("mode") == models.ESTIMATE:
        intro.append("这次只估算：下面是将要发起的调用次数，调用记录里每一条的状态都是未调用。")
    sections.append(section("steps", "每一步的调用", intro,
                            results.table(["步骤", "配置的评委", "调用次数", "按厂商", "模型"], srows, numeric=(2,)) if srows else ""))

    if review.public:
        notes = []
        for key, label in (("disputed_points", "有争议的要点"), ("audit_points", "列入人工审计的要点")):
            if run.get(key):
                notes.append((label, esc(join_cn(run[key]))))
        if run.get("invalid_answers"):
            notes.append(("不合格、没有计入的回答", "".join(f'<p><code>{esc(compact(x))}</code></p>' for x in run["invalid_answers"])))
        for key, value in (run.get("notes") or {}).items():
            label = NOTE_NAMES.get(key, key)
            if isinstance(value, list):
                notes.append((esc(label), f"{len(value)} 条" + "".join(f'<p><code>{esc(compact(x))}</code></p>' for x in value)))
            else:
                notes.append((esc(label), esc(str(value))))
        if notes:
            sections.append(section("notes", "要人核对的事", "程序如实记下、没有自动处理的地方，含义见模拟评审使用说明的运行元数据一节。", fields(notes)))
        scorer = run.get("scorer")
        if scorer:
            sections.append(section("scorer", "计分程序", "",
                                    fields([("程序", f"<code>{esc(scorer.get('program', ''))}</code>，第 {esc(str(scorer.get('version', '')))} 版"),
                                            ("命令", f"<code>{esc(' '.join(str(x) for x in scorer.get('command') or []))}</code>"),
                                            ("退出状态", esc(str(scorer.get("exit_code"))))])))

    calls_dir = site.path("reviews", review.id, "calls")
    if review.public:
        intro = f"这次评审的 {len(review.calls)} 次模型调用，点序号看提示词和回答的原文。"
    else:
        intro = "这道题是还没有公开的正式题，提示词里有题目卡全文和深度地图的要点，所以只列出调用的步骤和厂商，原文等题目公开后再显示。"
    sections.append(section("calls", "全部调用", intro,
                            calls_table(site, page, review.calls, calls_dir, review.public) if review.calls
                            else '<p class="empty body-6">没有调用记录。</p>'))
    site.page(page, f"模拟评审 {shown(review.id)}", f"模拟评审{shown(review.id)}用到的厂商和模型、调用次数、结果和全部调用。", head, sections)

    if review.public:
        raw = os.path.join(folder, "calls.jsonl")
        for i, record in enumerate(review.calls, 1):
            call_page(site, os.path.join(calls_dir, f"{i}.html"), record, i, len(review.calls), f"模拟评审 {shown(review.id)}",
                      site.link(page, os.path.join(calls_dir, "x.html")), "回到这次评审", raw)


# ---------- 生成 ----------

def build(questions_dir, reviews_dir, output):
    bank = {name: Question(os.path.join(questions_dir, name)) for name in subdirs(questions_dir)}
    reviews = [Review(os.path.join(reviews_dir, name), bank) for name in subdirs(reviews_dir)
               if os.path.isfile(os.path.join(reviews_dir, name, "run.json"))]
    reviews.sort(key=lambda r: (r.run.get("started_at") or "", r.id), reverse=True)
    for r in reviews:
        if r.question is not None:
            r.question.reviews.append(r)
    questions = sorted(bank.values(), key=lambda q: (q.date(), q.id), reverse=True)

    site = Site(output, questions_dir, reviews_dir)
    bank_page(site, questions)
    for q in questions:
        question_page(site, q)
    reviews_page(site, reviews)
    for r in reviews:
        review_page(site, r)

    if os.path.isdir(output) and os.listdir(output) and not os.path.isfile(os.path.join(output, "questions.html")):
        raise SystemExit(f"输出目录里有不是本程序写的东西，不覆盖：{output}")
    # 先在旁边同一层的新目录里写完（相对链接因此与写在输出目录里完全相同），再换下旧目录。
    parent, name = os.path.split(output)
    os.makedirs(parent, exist_ok=True)
    fresh = tempfile.mkdtemp(dir=parent, prefix=f".{name}-new-")
    try:
        site.write(fresh)
        for r in reviews:
            ok, _ = result_state(r)
            if ok:
                q = r.question
                in_fresh = lambda *parts: os.path.join(fresh, "reviews", r.id, *parts)  # noqa: E731
                results.build(in_fresh("results"), r.folder, links={
                    "review": in_fresh("index.html"), "calls": in_fresh("calls"),
                    "question": os.path.join(fresh, "questions", q.id, "index.html") if q is not None else None})
        old = None
        if os.path.exists(output):
            old = tempfile.mkdtemp(dir=parent, prefix=f".{name}-old-")
            os.rmdir(old)
            os.rename(output, old)
        os.rename(fresh, output)
    except BaseException:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    if old:
        shutil.rmtree(old)
    return site


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成资料站上的题库页、评审记录页、每道题和每次评审的详情页，以及每一次模型调用的原文页。")
    ap.add_argument("--questions", default=DEFAULT_QUESTIONS, help="题目目录放在哪里，默认 simulation/questions/")
    ap.add_argument("--reviews", default=DEFAULT_REVIEWS, help="模拟评审的输出目录放在哪里，默认 simulation/reviews/")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="页面写到哪里，默认 site/simulation/")
    args = ap.parse_args(argv)
    site = build(os.path.abspath(args.questions), os.path.abspath(args.reviews), os.path.abspath(args.output))
    print(f"写了 {len(site.pages)} 个页面（不算名次页和复核页）：{site.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
