"""从第五阶段试评的数据生成名次页、六个复核页和要点池页；也能为一次模拟评审生成同样格式的一套页面。

用法：在仓库根目录运行 python3 -I site/build_results.py [--input 目录] [--output 目录]

不给 --input 时读第五阶段试评，默认写到 site/results/。只读 research-plan/stage5-pilot/ 下的文件，不改它们：
- 第 1.2 版计分结果文件（文件名见 RESULTS_NAME）：名次区间、净分、严重问题、环节档位、分开的对；
- mapping.json：匿名编号对应的产品；
- out/ 下的评委输出：断言核验、要点池、环节评级、两两比较、对题目的直接回答；
- judges/manifest.json：每个评委输出文件对应的提示词和模型。
试评页面里的链接按页面放在 site/results/ 下来写。

--input 给一次模拟评审的输出目录（simulation/reviews/<运行标识>/，格式见 tools/simulate_review.md）时，
读其中的 run.json、calls.jsonl、mapping.json、data/、judgments/extract.json 和第 1.2 版计分结果文件，
题目卡从 run.json 记下的题目目录读。这时 --output 必须给，页面里的链接按页面实际写到的目录来写。
资料站的模拟评审页面由 site/build_simulation.py 调用这里的 build()，并把每一次调用的原文页链接进来。
"""
import argparse
import html
import importlib.util
import json
import os
import re
import sys
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PILOT = os.path.join(ROOT, "research-plan", "stage5-pilot")
OUT = os.path.join(PILOT, "out")
DEFAULT_OUTPUT = os.path.join(HERE, "results")
# 从 site/results/ 下的页面到其他文件的相对路径
TO_PILOT = "../../research-plan/stage5-pilot/"
TO_SITE = "../"
TO_NOTES = "../../notes/"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return html.escape(str(s), quote=True)


STYLE = """
  /* 与资料站首页同一套规则：字号只用 Tailwind 档位，间距只用表内数值，动效用同一条减速曲线，深浅两套颜色 */
  :root {
    --bg: #ffffff; --surface: #f7f7f5; --raised: #ffffff; --line: #e6e6e3;
    --ink: #111111; --ink-2: #555555; --ink-3: #737373;
    --accent: #2f5bd3; --ok: #1e7f4f; --warn: #a15c00; --bad: #b42318;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
    --font: "Manrope", "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", "Microsoft YaHei", sans-serif;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #181818; --surface: #1f1f1f; --raised: #272727; --line: #313131;
      --ink: #f2f2f2; --ink-2: #b3b3b3; --ink-3: #8c8c8c;
      --accent: #8fb0ff; --ok: #6fd3a0; --warn: #f0b45a; --bad: #ff8a7a;
      color-scheme: dark;
    }
  }
  .heading-3 { font-size: 36px; line-height: 40px; font-weight: 600; }
  .heading-5 { font-size: 24px; line-height: 32px; font-weight: 600; }
  .heading-6 { font-size: 20px; line-height: 28px; font-weight: 600; }
  .title-3 { font-size: 16px; line-height: 24px; font-weight: 500; }
  .title-4 { font-size: 14px; line-height: 20px; font-weight: 500; }
  .body-3 { font-size: 16px; line-height: 24px; font-weight: 400; }
  .body-5 { font-size: 14px; line-height: 20px; font-weight: 500; }
  .body-6 { font-size: 14px; line-height: 20px; font-weight: 400; }
  .caption-1 { font-size: 14px; line-height: 20px; font-weight: 500; }
  .caption-2 { font-size: 14px; line-height: 20px; font-weight: 400; }
  .caption-3 { font-size: 12px; line-height: 16px; font-weight: 600; }
  .caption-5 { font-size: 12px; line-height: 16px; font-weight: 400; }

  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; scroll-padding-top: 24px; }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font); font-size: 16px; line-height: 24px;
    -webkit-font-smoothing: antialiased; overflow-wrap: anywhere; }
  h1, h2, h3, p { margin: 0; }
  h1, h2 { text-wrap: balance; }
  p, li, td, blockquote { text-wrap: pretty; }
  a { color: var(--accent); text-underline-offset: 4px; }
  a:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 6px; }
  .wrap { max-width: 1120px; margin: 0 auto; padding-inline: 16px; }
  @media (min-width: 768px) { .wrap { padding-inline: 32px; } }
  .skip { position: absolute; left: 16px; top: -64px; z-index: 50; background: var(--ink); color: var(--bg); padding: 8px 12px; border-radius: 8px; text-decoration: none; transition: top 300ms var(--ease); }
  .skip:focus { top: 16px; }
  .muted { color: var(--ink-2); }
  .faint { color: var(--ink-3); }

  header.top { padding-block: 32px 24px; }
  .back { display: inline-block; color: var(--ink-2); text-decoration: none; margin-bottom: 24px; }
  .back:hover { color: var(--ink); text-decoration: underline; }
  .eyebrow { color: var(--ink-3); margin-bottom: 8px; }
  .lede { max-width: 760px; margin-top: 16px; color: var(--ink-2); }

  /* 演示声明：每页都有，名次页上最醒目 */
  .demo { display: flex; gap: 12px; align-items: flex-start; max-width: 760px; margin-top: 24px; padding: 16px; border-radius: 12px;
    border: 1px solid var(--warn); background: var(--surface); }
  .demo svg { width: 20px; height: 20px; flex: none; fill: var(--warn); margin-top: 2px; }
  .demo strong { display: block; font-weight: 600; color: var(--ink); }
  .demo p + p { margin-top: 8px; color: var(--ink-2); }

  /* 页面之间的跳转 */
  .pages { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; padding: 0; list-style: none; }
  .pages a { display: inline-block; padding: 4px 12px; border-radius: 9999px; border: 1px solid var(--line); color: var(--ink); text-decoration: none;
    background: var(--raised); transition: background-color 300ms var(--ease); }
  .pages a:hover { background: var(--surface); }
  .pages a[aria-current="page"] { background: var(--ink); color: var(--bg); border-color: var(--ink); }

  main { padding-bottom: 96px; }
  .block { padding-block: 48px; border-top: 1px solid var(--line); }
  .block > h2 { margin-bottom: 8px; }
  .block > .sum { max-width: 760px; color: var(--ink-2); }
  .block > .sum + .sum { margin-top: 8px; }
  .sub { margin-top: 32px; }
  .sub > h3 { margin-bottom: 8px; }
  .prose { max-width: 760px; }
  .prose p + p { margin-top: 8px; }
  .prose ul, .prose ol { margin: 8px 0 0; padding-left: 24px; }
  .prose li + li { margin-top: 4px; }

  /* 名次区间横条 */
  .ranks { margin-top: 24px; display: grid; gap: 8px; padding: 0; list-style: none; max-width: 880px; }
  .rank-row { display: grid; grid-template-columns: 176px minmax(0, 1fr) 112px; gap: 16px; align-items: center; padding: 8px 0; }
  .rank-axis { color: var(--ink-3); padding: 0; }
  .rank-who a { color: var(--ink); text-decoration: none; }
  .rank-who a:hover { text-decoration: underline; }
  .rank-who .faint { display: block; }
  .track { position: relative; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); height: 24px; }
  .track .slot { border-left: 1px solid var(--line); }
  .track .slot:last-child { border-right: 1px solid var(--line); }
  .track .bar { position: absolute; top: 4px; height: 16px; border-radius: 4px; background: var(--accent); }
  .axis-labels { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .axis-labels span { text-align: center; }
  .rank-text { white-space: nowrap; }
  @media (max-width: 639px) {
    .rank-row { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "who text" "track track"; gap: 8px 12px; }
    .rank-who { grid-area: who; } .rank-text { grid-area: text; } .track, .axis-labels { grid-area: track; }
    .rank-axis .rank-who, .rank-axis .rank-text { display: none; }
    .rank-who .faint { display: inline; margin-left: 4px; }
  }

  /* 表格：窄屏时在自己的框里横向滚动，页面本身不溢出 */
  .scroll { overflow-x: auto; margin-top: 16px; -webkit-overflow-scrolling: touch; border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; line-height: 20px; background: var(--raised); }
  th, td { border: 1px solid var(--line); padding: 8px 12px; text-align: left; vertical-align: top; overflow-wrap: normal; }
  th { font-weight: 600; color: var(--ink-2); background: var(--surface); white-space: nowrap; }
  td.n, th.n { text-align: center; white-space: nowrap; font-variant-numeric: tabular-nums; }
  td a { white-space: nowrap; }
  .legend { margin-top: 8px; color: var(--ink-3); max-width: 760px; }

  /* 分开的对 */
  .pairs { margin-top: 16px; display: grid; gap: 8px; padding: 0; list-style: none; max-width: 880px; }
  .pairs li { padding: 12px 16px; border-radius: 12px; background: var(--surface); }
  .pairs .who { font-weight: 600; }
  .pairs p + p { margin-top: 4px; color: var(--ink-2); }

  /* 卡片：主要结论、评级、比较 */
  .cards { margin-top: 16px; display: grid; gap: 12px; padding: 0; list-style: none; }
  .card { min-width: 0; padding: 16px; border-radius: 12px; border: 1px solid var(--line); background: var(--raised); }
  .card-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
  .card-head .title-3 { margin-right: 4px; }
  .card h4 { margin: 12px 0 4px; color: var(--ink-3); font-size: 12px; line-height: 16px; font-weight: 600; }
  .card blockquote { margin: 0; padding-left: 12px; border-left: 2px solid var(--line); color: var(--ink-2); }
  .card p + p { margin-top: 4px; }
  .grid-2 { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
  @media (max-width: 479px) { .grid-2 { grid-template-columns: minmax(0, 1fr); } }

  /* 标签：文字用正文颜色，前面的小圆点表示状态 */
  .tag { display: inline-flex; align-items: center; gap: 4px; padding: 0 8px; border-radius: 9999px; border: 1px solid var(--line); color: var(--ink); white-space: nowrap; }
  .tag::before { content: ""; width: 8px; height: 8px; border-radius: 9999px; background: var(--ink-3); }
  .tag.ok::before { background: var(--ok); }
  .tag.warn::before { background: var(--warn); }
  .tag.bad::before { background: var(--bad); }
  .tag.plain::before { display: none; }

  /* 数字小格 */
  .stats { margin-top: 24px; display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
  .stat { padding: 16px; border-radius: 12px; border: 1px solid var(--line); }
  .stat .heading-6 { margin-top: 4px; font-variant-numeric: tabular-nums; }
  .stat p + p { margin-top: 4px; color: var(--ink-2); }

  /* 要点池的大表：宽屏是表格，窄屏每条要点一张卡片 */
  .pool-table { margin-top: 16px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .pool-table td:nth-child(n+3):nth-child(-n+6) { white-space: nowrap; }
  .pool-table td.content { min-width: 320px; }
  .pool-table td.content p + details { margin-top: 4px; }
  .pool-table td.who { min-width: 160px; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; }
  a.tag { text-decoration: none; transition: background-color 300ms var(--ease); }
  a.tag:hover { background: var(--surface); }
  .pool-table tr:target td { background: var(--surface); }
  @media (max-width: 767px) {
    .pool-table table, .pool-table tbody, .pool-table tr, .pool-table td { display: block; width: 100%; }
    .pool-table thead { display: none; }
    .pool-table tr { border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; margin-bottom: 12px; }
    .pool-table td { border: 0; padding: 4px 0; min-width: 0 !important; }
    .pool-table td:not(.pid):not(.content)::before { content: attr(data-label) "："; color: var(--ink-3); }
    .pool-table td:nth-child(3), .pool-table td:nth-child(4), .pool-table td:nth-child(5), .pool-table td:nth-child(6) { display: inline-block; width: auto; margin-right: 16px; }
  }

  details { margin-top: 8px; }
  summary { cursor: pointer; color: var(--ink-2); }
  details[open] summary { margin-bottom: 4px; }

  .links { display: grid; gap: 8px; margin-top: 16px; padding: 0; list-style: none; max-width: 760px; }
  .links li { padding-left: 16px; position: relative; }
  .links li::before { content: ""; position: absolute; left: 0; top: 10px; width: 4px; height: 4px; border-radius: 9999px; background: var(--ink-3); }

  footer { border-top: 1px solid var(--line); padding-block: 32px; color: var(--ink-3); }
  footer a { color: var(--ink-2); }
  code { font-size: 14px; }
  @media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } }
"""

WARN_ICON = ('<svg viewBox="0 0 256 256" aria-hidden="true"><path d="M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm0,192a88,88,0,1,1,'
             '88-88A88.1,88.1,0,0,1,128,216Zm-8-80V80a8,8,0,0,1,16,0v56a8,8,0,0,1-16,0Zm20,36a12,12,0,1,1-12-12A12,12,0,0,1,140,172Z"/></svg>')


def style(n):
    """名次横条的格数等于报告数。"""
    return STYLE.replace("repeat(6, minmax(0, 1fr))", f"repeat({n}, minmax(0, 1fr))")


def shell(data, title, description, body):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · 深度研究评测基准</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="{data.to_site}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600&display=swap">
<style>{style(len(data.labels))}</style>
</head>
<body>
<a class="skip caption-1" href="#main">跳到正文</a>
{body}
</body>
</html>
"""


# ---------- 数据 ----------

def load_module(name, path):
    """按文件路径载入一个程序当模块用，不改 sys.path，也不写字节码缓存。"""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# 计分程序里的权重、单条要点的计分公式和环节名称：复核页上逐条列出的得分用它算，与名次用的是同一套。
SCORE = load_module("stage5_score", os.path.join(PILOT, "score.py"))
COMMON = load_module("tools_common", os.path.join(ROOT, "tools", "common.py"))
RESULTS_NAME = "results-v1.2.json"  # 计分程序第 1.2 版写出的结果文件
WEIGHTS = list(SCORE.LEVEL_W)  # 甲、乙、丙
LEVELS = ["现象", "全体", "内部联系", "本质"]
ELEMENTS = [(key, SCORE.ELEMENT_NAMES[key]) for key in SCORE.ELEMENTS]  # 五个环节：①③④⑤⑦
TIMELINESS = SCORE.ELEMENT_NAMES["②"]


def href(path, start):
    """从 start 目录到 path 的相对链接，路径里的非英文字符按网址的写法编码。"""
    return quote(os.path.relpath(path, start).replace(os.sep, "/"))


def read_jsonl(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class Data:
    """source 是第五阶段试评的目录（默认）或一次模拟评审的输出目录（有 run.json）。
    links 只用于模拟评审：{"review": 评审记录页, "calls": 调用原文页所在的目录, "question": 题库里这道题的页面}，
    都是文件系统路径；不给的就链接到原始文件。"""

    def __init__(self, source=PILOT, output=DEFAULT_OUTPUT, links=None):
        self.source = source
        self.sim = os.path.isfile(os.path.join(source, "run.json"))
        if self.sim:
            links = links or {}
            out = os.path.join(source, "data")
            self.to_src = href(source, output) + "/"
            self.to_site = href(HERE, output) + "/"
            self.to_notes = href(os.path.join(ROOT, "notes"), output) + "/"
            self.to_scorer = href(os.path.join(PILOT, "score.py"), output)
            self.to_guide = href(os.path.join(ROOT, "tools", "simulate_review.md"), output)
            self.review_page = href(links["review"], output) if links.get("review") else None
            self.calls_dir = href(links["calls"], output) + "/" if links.get("calls") else None
            self.question_page = href(links["question"], output) if links.get("question") else None
            self.run = load(os.path.join(source, "run.json"))
            self.calls = read_jsonl(os.path.join(source, "calls.jsonl"))
            self.manifest = None
            self.question = sim_question(self.run)
            extract = os.path.join(source, "judgments", "extract.json")
            self.extracted = {p["id"]: p for p in load(extract)["points"]} if os.path.isfile(extract) else {}
            self.copies = {r["label"]: r.get("copy") for r in self.run.get("reports", [])}
        else:
            out = OUT
            self.to_src, self.to_site, self.to_notes = TO_PILOT, TO_SITE, TO_NOTES
            self.manifest = load(os.path.join(PILOT, "judges", "manifest.json"))
            self.question = read_question_card(os.path.join(PILOT, "question-card.md"))
        self.results = load(os.path.join(source, RESULTS_NAME))
        self.mapping = load(os.path.join(source, "mapping.json"))
        self.reports = {r["label"]: r for r in self.results["reports"]}
        self.labels = [r["label"] for r in self.results["reports"]]
        self.order = sorted(self.labels, key=lambda r: (self.reports[r]["rank_best"], self.reports[r]["rank_worst"], r))
        self.above = {(p["higher"], p["lower"]): p for p in self.results["separated_pairs"]}
        self.vetoed = {(p["higher"], p["lower"]) for p in self.results["vetoed_pairs"]}
        self.pool = load(os.path.join(out, "pool.json"))["points"]
        # 主要结论：与计分程序相同，按文件名顺序读 verify-*.json 里带 reports 的文件
        self.claims, self.verify, self.verify_file = {}, {}, {}
        for name in sorted(os.listdir(out)):
            if name.startswith("verify-"):
                d = load(os.path.join(out, name))
                for r, v in d.get("reports", {}).items():
                    self.claims[r], self.verify[r], self.verify_file[r] = v["claims"], v, name
        recheck = os.path.join(out, "verify-sonnet-subset.json")
        self.recheck = {c["id"]: c for c in load(recheck)["claims"]} if os.path.exists(recheck) else {}
        names = sorted(os.listdir(out), key=natural)
        self.ratings = {n[len("rating-"):-len(".json")]: load(os.path.join(out, n))["reports"]
                        for n in names if n.startswith("rating-")}
        self.pairwise = [(n, load(os.path.join(out, n))) for n in names if n.startswith("pairwise-")]
        self.direct = load(os.path.join(out, "direct-answers.json"))
        self.runs = {os.path.basename(run["output"]): run for run in self.manifest["runs"]} if self.manifest else {}
        # 只在页面上用到的说法：试评和模拟评审的做法不同
        self.verifier_word = "评委组" if self.sim else "核验评委"
        self.timeliness_by = "时效取各次环节评级的中位数" if self.sim else "时效由核验评委评"

    def product(self, r):
        return self.mapping["reports"][r]

    def name(self, r):
        return f"报告 {r}"

    def grades(self, r):
        """五个环节的档位。深度净分分不开时，第 1.2 版计分程序比较的就是这五项（规则手册第八节第 3 条），时效不在其中。"""
        rep = self.reports[r]
        return [(name, rep["element_grades"][key]) for key, name in ELEMENTS]

    def models(self):
        return sorted({run["model"] for run in self.manifest["runs"]})

    def kind(self):
        """页面上称呼这次评审的说法。"""
        return "模拟评审" if self.sim else "试评"

    def report_href(self, r):
        if self.sim:
            return self.to_src + quote(self.copies.get(r) or f"reports/{r}.md")
        return f"{self.to_src}reports/{r}.md"

    # ---- 只用于模拟评审：从调用记录里读出谁做了哪一步 ----

    def task_calls(self, prefix, slot=None):
        """任务名以 prefix 开头、状态为成功的调用；slot 给出时只取这位评委的。"""
        found = []
        for i, c in enumerate(self.calls, 1):
            if c.get("status") == "成功" and c["task"].startswith(prefix):
                if slot is None or c["task"].endswith(f"评委 {slot}"):
                    found.append((i, c))
        return found

    def who(self, calls):
        """几次调用用到的厂商和模型，写成"claude、codex"或"claude，Claude Opus 5.5"。"""
        vendors = unique(c["vendor"] for _, c in calls)
        models = unique(model_name(m) for m in (c.get("reported_model") or c.get("model") for _, c in calls) if m)
        return "、".join(vendors) + ("，" + "、".join(models) if models else "")

    def vendors(self):
        """成功调用过的厂商：[(公司, 厂商)]，按第一次出现的先后。"""
        return unique((c.get("company") or c["vendor"], c["vendor"]) for c in self.calls if c.get("status") == "成功")


def natural(name):
    """文件名里的数字按大小排：rating-2.json 排在 rating-10.json 前面。"""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", name)]


def unique(items):
    out = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


def sim_question(run):
    """模拟评审的题目：问题取自题目卡的【问题】一栏，截止日期取 run.json 里实际用的。"""
    q = run.get("question") or {}
    card = os.path.join(q.get("dir") or "", "题目卡.txt")
    text = ""
    if q.get("dir") and os.path.isfile(card):
        with open(card, encoding="utf-8") as f:
            text = f.read()
    m = re.search(r"【问题】(.+)", text)
    cutoff = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", q.get("cutoff") or "")
    return {"question": m.group(1).strip() if m else "（题目卡里没有找到问题一栏）",
            "cutoff": "{} 年 {} 月 {} 日".format(*(int(x) for x in cutoff.groups())) if cutoff else "题目卡上写明的截止时间",
            "id": os.path.basename(os.path.normpath(q["dir"])) if q.get("dir") else None}


def read_question_card(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    q = re.search(r"\*\*问题\*\*：(.+)", text).group(1).strip()
    cutoff = re.search(r"\*\*截止时间\*\*：(\d{4})-(\d{2})-(\d{2})", text)
    y, m, d = (int(x) for x in cutoff.groups())
    return {"question": q, "cutoff": f"{y} 年 {m} 月 {d} 日"}


# ---------- 文字 ----------

def num(x):
    """数字：整数不带小数点，负号用减号，不用连字符。"""
    x = float(x)
    s = str(int(x)) if x == int(x) else f"{x:g}"
    return s.replace("-", "−")


def pct(x):
    return f"{x * 100:.1f}%"


def interval(rep):
    b, w = rep["rank_best"], rep["rank_worst"]
    return f"第 {b} 名" if b == w else f"第 {b} 至 {w} 名"


def model_name(model_id):
    """claude-opus-5-5 写成 Claude Opus 5.5，可见文字里不出现连字符。"""
    words, version = [], []
    for part in model_id.split("-"):
        (version if part.isdigit() else words).append(part)
    return " ".join(w.capitalize() for w in words) + (" " + ".".join(version) if version else "")


def join_cn(items):
    items = list(items)
    return "、".join(items)


def count_cn(n, unit="份"):
    """六份、两份、三次；十以上写数字。"""
    if n == 2:
        return "两" + unit
    return f"{ORDINALS[n - 1]}{unit}" if 1 <= n <= 10 else f"{n} {unit}"


def ordinal(i):
    """第几次：从 0 数起的序号写成一、二、三；十以上写数字。"""
    return ORDINALS[i] if i < len(ORDINALS) else f" {i + 1} "


def task_text(task):
    """调用记录里的任务名，可见文字里不出现连字符：出题-深度地图-甲-第1轮 写成 出题 · 深度地图 · 甲 · 第1轮。"""
    return task.replace("-", " · ")


def page_nav(data, current):
    items = [("index.html", "名次"), ("points.html", "要点池")] + [(f"report-{r}.html", f"报告 {r}") for r in data.labels]
    here = ' aria-current="page"'
    lis = "".join(f'<li><a class="caption-1" href="{href}"{here if href == current else ""}>{esc(text)}</a></li>'
                  for href, text in items)
    if data.sim and data.review_page:
        lis += f'<li><a class="caption-1" href="{data.review_page}">评审记录</a></li>'
    return f'<nav aria-label="{data.kind()}页面"><ul class="pages">{lis}</ul></nav>'


def sim_notice(data, detail):
    extra = ""
    if detail:
        vendors = data.vendors()
        found = "、".join(f"{company}（{vendor}）" for company, vendor in vendors)
        text = f"评委来自{count_cn(len(vendors), '家')}厂商：{found}。" if vendors else "这次评审没有成功的模型调用。"
        if len(vendors) < 3:
            text += "规则要求至少三家。"
        gone = [u["vendor"] for u in data.run.get("unavailable", [])]
        if gone:
            text += f"{join_cn(gone)} 在这次运行中不可用，它的评委位置由别家替代。"
        if data.run.get("mode") == "回放":
            text += "这次是回放：回答取自录好的调用记录，没有真的调用模型。"
        record = (f'<a href="{data.review_page}">这次评审的记录</a>' if data.review_page
                  else f'<a href="{data.to_src}calls.jsonl">调用记录文件</a>')
        extra = f'<p class="body-6">{esc(text)}用了哪些模型、每一次调用的提示词和回答原文，见{record}。</p>'
    return (f'<div class="demo" role="note">{WARN_ICON}<div><p class="body-3"><strong>这是模拟评审的演示，评委全部由大模型担任，'
            f'不是对产品的评价。</strong></p>{extra}</div></div>')


def demo_notice(data, detail=True):
    if data.sim:
        return sim_notice(data, detail)
    models = join_cn(model_name(m) for m in data.models())
    same = [r for r in data.labels if any(data.product(r).lower() in m for m in data.models())]
    extra = ""
    if detail:
        rel = f"其中{join_cn(data.name(r) for r in same)} 出自同一家公司的产品。" if same else ""
        extra = (f'<p class="body-6">评委用的是 Anthropic 公司的模型（{esc(models)}），只来自一家厂商，规则要求至少三家；{esc(rel)}'
                 '题目是根据报告还原的，深度地图也是读过其中一份报告之后才写的。产品名照论文和一页总结里已经公开的对应关系注明。'
                 f'这些局限见<a href="{TO_NOTES}plan-stage5-report.html">第五阶段报告</a>。</p>')
    return (f'<div class="demo" role="note">{WARN_ICON}<div><p class="body-3"><strong>这是第五阶段的试评演示，评委全部由大模型担任，'
            f'不是对产品的评价。</strong></p>{extra}</div></div>')


def back_link(data):
    if data.sim and data.review_page:
        return f'<a class="back caption-1" href="{data.review_page}">← 回到这次评审的记录</a>'
    return f'<a class="back caption-1" href="{data.to_site}index.html">← 回到资料站</a>'


def header(data, current, eyebrow, title, lede_html, detail_notice):
    return f"""<header class="top">
  <div class="wrap">
    {back_link(data)}
    <p class="eyebrow caption-1">{esc(eyebrow)}</p>
    <h1 class="heading-3">{esc(title)}</h1>
    <p class="body-3 lede">{lede_html}</p>
    {demo_notice(data, detail_notice)}
    {page_nav(data, current)}
  </div>
</header>"""


def footer(data):
    if data.sim:
        return (f'<footer><div class="wrap caption-2"><p>本页由 <code>site/build_results.py</code> 从模拟评审 <code>{esc(data.run["run_id"])}</code> '
                f'的数据目录和第 1.2 版计分结果生成，不手工修改。<a href="{data.to_site}index.html">回到资料站</a></p></div></footer>')
    return (f'<footer><div class="wrap caption-2"><p>本页由 <code>site/build_results.py</code> 从第五阶段试评的评委输出和第 1.2 版计分结果生成，'
            f'不手工修改。<a href="{TO_SITE}index.html">回到资料站</a></p></div></footer>')


def table(head, rows, numeric=()):
    """head 是列名，rows 是已转义的单元格。numeric 是居中显示的数字列的序号。"""
    centre = ' class="n"'
    th = "".join(f'<th{centre if i in numeric else ""} scope="col">{h}</th>' for i, h in enumerate(head))
    body = "".join("<tr>" + "".join(f'<td{centre if i in numeric else ""}>{c}</td>' for i, c in enumerate(row)) + "</tr>"
                   for row in rows)
    return f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def problems_text(data, r):
    probs = data.reports[r]["severe_problems"]
    return join_cn(probs) if probs else "无"


def nets_text(data, x, y):
    nx, ny = data.reports[x]["net_scores"], data.reports[y]["net_scores"]
    return "，".join(f"{w}种权重 {num(nx[w])} 比 {num(ny[w])}" for w in WEIGHTS)


def separated_story(data, x, y):
    """一对已经分开的报告：为什么 x 排在 y 之前。"""
    p = data.above[(x, y)]
    if p["basis"] == "硬伤分档":
        return f"{x} 没有严重问题，{y} 有（{problems_text(data, y)}）。按严重问题分档，{x} 排在前面。"
    if p["basis"] == "深度净分":
        shares = "、".join(pct(p["bootstrap_share"][w]) for w in WEIGHTS)
        s = (f"三种权重下 {x} 的深度净分都高于 {y}（{nets_text(data, x, y)}）；重抽一千遍要点，{x} 领先的比例依次是 {shares}，"
             f"都不低于九成。")
        if p["disputed_labels"]:
            used = "；".join(f"{pid} 在{w}种权重下按{v['level']}、{v['importance']}计"
                            for pid, by_w in sorted(p["disputed_labels"].items()) for w, v in by_w.items())
            s += f"有争议的要点按对 {x} 最不利的标注计分：{used}。"
        return s
    gx, gy = dict(data.grades(x)), dict(data.grades(y))
    better = [k for k, _ in data.grades(x) if gx[k] > gy[k]]
    return (f"深度净分分不开，于是比较五个环节的评级：{x} 在五个环节上都不低于 {y}，并在{join_cn(better)}上更高。"
            f"（{x}：{grades_inline(data, x)}；{y}：{grades_inline(data, y)}。）")


def grades_inline(data, r):
    return "，".join(f"{k} {num(v)}" for k, v in data.grades(r))


def tied_story(data, a, b):
    """一对分不开的报告：为什么分不开。"""
    if (a, b) in data.vetoed or (b, a) in data.vetoed:
        x, y = (a, b) if (a, b) in data.vetoed else (b, a)
        votes = pairwise_votes(data).get(frozenset((x, y)), [])
        against = sum(w == y for w in votes)
        return (f"按前面的步骤 {x} 本应排在 {y} 之前，但两两比较 {len(votes)} 次中有 {against} 次判 {y} 更好，"
                f"至少占四分之三，这一对改为并列。")
    ha, hb = bool(data.reports[a]["severe_problems"]), bool(data.reports[b]["severe_problems"])
    parts = ["两份都有严重问题，在同一档里比较。" if ha and hb else "两份都没有严重问题，在同一档里比较。"]
    na, nb = data.reports[a]["net_scores"], data.reports[b]["net_scores"]
    lead = a if all(na[w] > nb[w] for w in WEIGHTS) else b if all(nb[w] > na[w] for w in WEIGHTS) else None
    disputed = data.results["resampling"]["disputed_points"]
    if lead is None:
        parts.append(f"深度净分不是三种权重下都由同一方领先（{nets_text(data, a, b)}）。")
    elif not disputed:
        other = b if lead == a else a
        parts.append(f"{lead} 在三种权重下深度净分都高于 {other}（{nets_text(data, lead, other)}），但重抽一千遍要点，"
                     f"至少有一种权重下 {lead} 领先的比例不到九成，领先不够稳。")
    else:
        other = b if lead == a else a
        parts.append(f"{lead} 在三种权重下深度净分都高于 {other}（{nets_text(data, lead, other)}），但有争议的要点按对 {lead} "
                     f"最不利的标注计分后，或者重抽一千遍要点后，领先站不住。")
    ga, gb = dict(data.grades(a)), dict(data.grades(b))
    up_a = [k for k, _ in data.grades(a) if ga[k] > gb[k]]
    up_b = [k for k, _ in data.grades(a) if gb[k] > ga[k]]
    if not up_a and not up_b:
        parts.append("比较五个环节的评级，完全相同。")
    else:
        parts.append(f"比较五个环节的评级，互有高低：{a} 在{join_cn(up_a)}上更高，{b} 在{join_cn(up_b)}上更高，谁也不是样样不低于对方。")
    return "".join(parts)


def pairwise_votes(data):
    """每个无序对的各次两两比较判定的胜者（"tie" 表示相当），与计分程序 pairwise_winners 的算法相同。"""
    votes = {}
    for _, d in data.pairwise:
        for it in d["pairs"]:
            a, b, v = it["first"], it["second"], it["verdict"]
            votes.setdefault(frozenset((a, b)), []).append(a if v == "first" else b if v == "second" else "tie")
    return votes


def veto_rule_text(data):
    """两两比较怎样否决（规则手册第八节第 4 条），以及这次每对实际比了几次、要几次相反。
    比较 n 次时至少要 n 的四分之三次相反，向上取整，与计分程序 vetoes 的算法相同。"""
    counts = sorted({len(v) for v in pairwise_votes(data).values()})
    s = ("两两比较只用来核对前面排出的先后：规则要求两位评委各按两种先后比一次，四次中至少三次与前面的结果相反，"
         "这一对才改为并列；比较次数不是四次时，相反的次数至少要占四分之三。")
    if len(counts) == 1:
        s += f"这次每对比了 {counts[0]} 次，至少 {-(-3 * counts[0] // 4)} 次相反才改为并列。"
    elif counts:
        s += f"这次各对比较的次数在 {counts[0]} 到 {counts[-1]} 次之间，每对按自己比较的次数算。"
    else:
        s += "这次没有做两两比较。"
    return s


def all_pairs(data):
    order = data.order
    return [(order[i], order[j]) for i in range(len(order)) for j in range(i + 1, len(order))]


# ---------- 名次页 ----------

BASIS_TITLES = {"硬伤分档": "按严重问题分档分开", "深度净分": "按深度净分分开", "环节评级": "深度净分分不开，比较五个环节的评级分开"}


def rank_page(data):
    n = len(data.labels)
    q = data.question
    if data.sim:
        lede = (f"模拟评审 <code>{esc(data.run['run_id'])}</code> 让大模型按评审细则评审一道题的{count_cn(n)}报告：“{esc(q['question'])}”"
                f"报告编为{esc(join_cn(data.labels))}。判断对错和时效，以截至 {esc(q['cutoff'])} 已经存在的信息为准。"
                f"名次按区间公布，分不开的报告并列。")
        head = header(data, "index.html", "模拟评审 · 评法第 1.2 版", "模拟评审名次", lede, True)
    else:
        lede = (f"试评用一道题检验这套评法：“{esc(q['question'])}”六个产品各交一份报告，匿名编为 A 至 F。判断对错和时效，"
                f"以截至 {esc(q['cutoff'])}（报告的生成日期）已经存在的信息为准。名次按区间公布，分不开的报告并列。")
        head = header(data, "index.html", "第五阶段试评 · 评法第 1.2 版", "试评名次", lede, True)

    axis = "".join(f'<span>{i}</span>' for i in range(1, n + 1))
    rows = [f'<li class="rank-row rank-axis caption-5" aria-hidden="true"><span class="rank-who">报告</span>'
            f'<span class="axis-labels">{axis}</span><span class="rank-text">名次区间</span></li>']
    for r in data.order:
        rep = data.reports[r]
        left = (rep["rank_best"] - 1) * 100 / n
        width = (rep["rank_worst"] - rep["rank_best"] + 1) * 100 / n
        slots = '<span class="slot"></span>' * n
        rows.append(
            f'<li class="rank-row" id="rank-{r}"><span class="rank-who title-3"><a href="report-{r}.html">{esc(data.name(r))}</a>'
            f'<span class="faint caption-2">{esc(data.product(r))}</span></span>'
            f'<span class="track" aria-hidden="true">{slots}<span class="bar" style="left: calc({left:.4f}% + 2px); '
            f'width: calc({width:.4f}% - 4px);" title="{esc(data.name(r))}：{esc(interval(rep))}"></span></span>'
            f'<span class="rank-text body-5">{esc(interval(rep))}</span></li>')
    chart = f'<ol class="ranks" aria-label="{count_cn(n)}报告的名次区间">{"".join(rows)}</ol>'
    ranks = f"""<section class="block" id="ranks" aria-labelledby="ranks-h">
  <h2 class="heading-5" id="ranks-h">名次区间</h2>
  <p class="body-3 sum">横条盖住的是这份报告可能的名次范围。最好名次等于 1 加上确定排在它前面的报告数；最差名次等于报告总数 {n} 减去确定排在它后面的报告数。横条越短，名次越确定；两条横条重叠，说明这两份报告分不开。点报告名可以看它的复核页。</p>
  {chart}
</section>"""

    t1 = table(["报告", "产品", "名次", "严重问题"] + [f"{w}种权重" for w in WEIGHTS],
               [[f'<a href="report-{r}.html">{esc(data.name(r))}</a>', esc(data.product(r)), esc(interval(data.reports[r])),
                 esc(problems_text(data, r))] + [num(data.reports[r]["net_scores"][w]) for w in WEIGHTS] for r in data.order],
               numeric=(4, 5, 6))
    tw = table(["层级权重"] + LEVELS, [[f"{w}种"] + [num(SCORE.LEVEL_W[w][lv]) for lv in LEVELS] for w in WEIGHTS],
               numeric=(1, 2, 3, 4))
    t2 = table(["报告"] + [name for _, name in ELEMENTS] + [f"{TIMELINESS}（不进入名次）", "写作（不进入名次）"],
               [[f'<a href="report-{r}.html">{esc(data.name(r))}</a>'] + [num(v) for _, v in data.grades(r)]
                + [num(data.reports[r]["timeliness"]), num(data.reports[r]["writing"])] for r in data.order],
               numeric=(1, 2, 3, 4, 5, 6, 7))
    basis = f"""<section class="block" id="basis" aria-labelledby="basis-h">
  <h2 class="heading-5" id="basis-h">名次从哪里来</h2>
  <p class="body-3 sum">排法按<a href="{data.to_notes}rules.html#_10">规则手册第八节</a>，一步一步来：先按有没有严重问题分档；同一档里比深度净分；深度净分分不开，再比较五个环节的评级；两两比较只用来否决，四次中至少三次相反才改为并列。</p>
  <div class="sub">
    <h3 class="heading-6">严重问题和深度净分</h3>
    <div class="prose body-3 muted"><p>严重问题即规则手册所说的“硬伤”，有四种：确认编造来源；对题目的直接回答被可靠证据明确否定（计分结果里写作“主要结论与证据相反”）；答非所问；全篇没有可追溯的出处。有严重问题的报告排在所有没有严重问题的报告之后。</p>
    <p>深度净分等于写对的、切题的要点的分数之和，减去写错的扣分。一条要点的分数是层级权重乘以重要性（核心 2，一般 1）；核心内容写错扣 2，一般内容写错扣 1，所引来源不支持主要结论的每处扣 {num(SCORE.UNSUPPORTED_W)}。层级权重事先声明了三种，见下面第二张表。</p></div>
    {t1}
    {tw}
  </div>
  <div class="sub">
    <h3 class="heading-6">环节评级</h3>
    <div class="prose body-3 muted"><p>五个环节各评 0、1、2 三档，{count_cn(len(data.ratings), "次")}评级取中位数。环节评级不加总，只在深度净分分不开时比较：一份报告五个环节都不低于另一份、并且至少一个环节更高，才排在前面。{data.timeliness_by}，也是 0 至 2 档，列在表里，不进入名次；写作也只记录，不进入名次。</p>
    <p>第 1.0、1.1 版的计分程序把时效也算进比较；第 1.2 版按规则手册第八节第 3 条，只比五个环节。</p></div>
    {t2}
  </div>
</section>"""

    groups = []
    for key, title in BASIS_TITLES.items():
        items = [(x, y) for (x, y), p in sorted(data.above.items(), key=lambda kv: (data.order.index(kv[0][0]), data.order.index(kv[0][1])))
                 if p["basis"] == key]
        if not items:
            continue
        lis = "".join(f'<li id="pair-{x}-{y}"><p class="who body-3">{x} 排在 {y} 之前</p><p class="body-6">{esc(separated_story(data, x, y))}</p></li>'
                      for x, y in items)
        groups.append(f'<div class="sub"><h3 class="heading-6">{esc(title)}（{len(items)} 对）</h3><ul class="pairs">{lis}</ul></div>')
    tied = [(a, b) for a, b in all_pairs(data) if (a, b) not in data.above and (b, a) not in data.above]
    tied_lis = "".join(f'<li id="pair-{a}-{b}"><p class="who body-3">{a} 和 {b} 分不开</p><p class="body-6">{esc(tied_story(data, a, b))}</p></li>'
                       for a, b in tied)
    groups.append(f'<div class="sub"><h3 class="heading-6">分不开的对（{len(tied)} 对）</h3><ul class="pairs">{tied_lis}</ul></div>')
    veto = ("两两比较没有否决任何一对。" if not data.vetoed else
            f"两两比较否决了 {len(data.vetoed)} 对：" + "、".join(f"{x} 和 {y}" for x, y in sorted(data.vetoed)) + "，改为并列。")
    total = len(all_pairs(data))
    pairs = f"""<section class="block" id="pairs" aria-labelledby="pairs-h">
  <h2 class="heading-5" id="pairs-h">哪些报告分开了</h2>
  <p class="body-3 sum">{count_cn(n)}报告两两成对，共 {total} 对。分开的有 {len(data.above)} 对，分不开的有 {len(tied)} 对；分不开的两份名次区间重叠。</p>
  <p class="body-3 sum">{esc(veto_rule_text(data))}严重问题分档不能被否决。{esc(veto)}</p>
  {"".join(groups)}
</section>"""

    rs = data.results["resampling"]
    disputed = ("没有标为有争议的要点。" if not rs["disputed_points"] else
                f"有争议的要点有 {len(rs['disputed_points'])} 条（{join_cn(rs['disputed_points'])}），比较一对报告时按对领先一方最不利的标注计分。")
    checks = f"""<section class="block" id="checks" aria-labelledby="checks-h">
  <h2 class="heading-5" id="checks-h">分开要过两道检查</h2>
  <div class="prose body-3">
    <p>两份报告的深度净分要算“分开”，必须同时过两道检查。</p>
    <p><strong>换一种算分口径。</strong>三种权重各算一遍，都领先才行。</p>
    <p><strong>换一批要点。</strong>从要点池里随机抽出同样多条要点，每次抽完放回去，所以同一条可能被抽到两三次，也可能一次都没抽到。用抽出的这一批要点给两份报告重新算分，看谁高。这样重复一千次，数一数领先的一方在多少次里仍然领先，至少九成才算稳。一千只是重复的次数，不是一千种方案；次数多，算出的比例才准。</p>
    <p>为什么要换一批要点：要点池本身带有偶然，换一位出题人、换一组评委，列出的要点会有出入。只靠一两条要点撑着的领先，换一批要点就站不住；靠很多条要点积累起来的领先，怎么换都还在。</p>
    <p class="muted">这次的要点池共 {rs['pool_points']} 条，其中 {rs['resampled_points']} 条至少有一份报告写到。按第 1.2 版的规定，重抽样只在这 {rs['resampled_points']} 条里进行：没有报告写到的要点对每份报告都是 0 分，不该影响先后。重抽 {rs['rounds']} 遍，随机种子固定为 {rs['seed']}，任何人重跑都得到同样的比例；领先的比例至少要达到 {rs['separation_share'] * 100:g}% 才算分开。{esc(disputed)}</p>
    <p class="muted">完整的例子见<a href="{data.to_site}walkthrough.html#step-scorer">一道题走完全程</a>的第 9、10 站。</p>
  </div>
</section>"""

    materials = sim_materials(data) if data.sim else f"""<section class="block" id="materials" aria-labelledby="materials-h">
  <h2 class="heading-5" id="materials-h">复核材料</h2>
  <p class="body-3 sum">每一个数都能追到评委的输出和计分程序。有异议，先看对应报告的复核页。</p>
  <ul class="links body-3">
    <li>六份报告的复核页：{"、".join(f'<a href="report-{r}.html">{esc(data.name(r))}</a>' for r in data.labels)}</li>
    <li><a href="points.html">要点池</a>：全部 {len(data.pool)} 条要点，以及每条有哪几份报告写到</li>
    <li><a href="{TO_PILOT}question-card.md">题目卡</a>和<a href="{TO_PILOT}depth-map.md">出题人的深度地图</a></li>
    <li><a href="{TO_PILOT}judges/README.md">评委收到的提示词</a>：每次评委运行的提示词原文和清单</li>
    <li><a href="{TO_PILOT}score.py">计分程序</a>和它写出的<a href="{TO_PILOT}{RESULTS_NAME}">第 1.2 版结果文件</a>。在计分程序所在的目录运行 <code>python3 -I score.py mapping.json 1.2</code> 可以重算</li>
    <li><a href="{TO_NOTES}rules.html#_10">规则手册第八节：名次与公布</a>；<a href="{TO_NOTES}plan-stage5-report.html">第五阶段报告</a></li>
  </ul>
</section>"""

    body = "\n".join([head, '<main id="main"><div class="wrap">', ranks, basis, pairs, checks, materials, "</div></main>", footer(data)])
    if data.sim:
        return shell(data, "模拟评审名次", f"模拟评审{count_cn(n)}报告的名次区间、深度净分、严重问题、环节档位和分开的对。演示，不是对产品的评价。", body)
    return shell(data, "试评名次", "第五阶段试评六份报告的名次区间、深度净分、严重问题、环节档位和分开的对。试评演示，不是对产品的评价。", body)


def repo_path(path):
    """仓库里的路径写成相对仓库根目录的样子，仓库外的照原样。"""
    path = os.path.abspath(path)
    return os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path


def sim_materials(data):
    labels = data.labels
    src = repo_path(data.source)
    question = (f'<li>题目：<a href="{data.question_page}">题库里的这道题</a>，有题目卡和深度地图</li>' if data.question_page else "")
    record = (f'<li><a href="{data.review_page}">这次评审的记录</a>：用了哪些厂商和模型、调用了几次，以及每一次调用的提示词和回答原文</li>'
              if data.review_page else f'<li><a href="{data.to_src}calls.jsonl">调用记录文件</a>：每一次调用的提示词和回答原文</li>')
    return f"""<section class="block" id="materials" aria-labelledby="materials-h">
  <h2 class="heading-5" id="materials-h">复核材料</h2>
  <p class="body-3 sum">每一个数都能追到评委的回答和计分程序。有异议，先看对应报告的复核页。</p>
  <ul class="links body-3">
    <li>{count_cn(len(labels))}报告的复核页：{"、".join(f'<a href="report-{r}.html">{esc(data.name(r))}</a>' for r in labels)}</li>
    <li><a href="points.html">要点池</a>：全部 {len(data.pool)} 条要点，以及每条有哪几份报告写到</li>
    {question}
    {record}
    <li><a href="{data.to_scorer}">计分程序</a>和它写出的<a href="{data.to_src}{RESULTS_NAME}">第 1.2 版结果文件</a>。在仓库根目录运行 <code>python3 -I research-plan/stage5-pilot/score.py {esc(src)}/mapping.json 1.2 --data {esc(src)}/data</code> 可以重算</li>
    <li><a href="{data.to_notes}rules.html#_10">规则手册第八节：名次与公布</a>；<a href="{data.to_guide}">模拟评审使用说明</a></li>
  </ul>
</section>"""


# ---------- 复核页 ----------

SOURCE_TONE = {"支持": "ok", "部分支持": "warn", "失效但有存档": "warn", "不支持": "bad", "找不到（疑似编造）": "bad", "找不到": "bad"}
CORRECT_TONE = {"正确": "ok", "无法判断": "warn", "有误": "bad"}
REACH_TEXT = {"符合": "说法一致", "相反": "说法相反"}
ORDINALS = "一二三四五六七八九十"


def tag(text, tone=""):
    return f'<span class="tag caption-3 {tone}">{esc(text)}</span>'


def plain_tag(text):
    return tag(text, "plain")


def claim_no(cid):
    """A-c3 写成"结论 3"，可见文字里不出现连字符。"""
    return "结论 " + cid.rsplit("-c", 1)[1]


def labels_text(p, key, default=None):
    cands = SCORE.candidates(p, key, default)
    return cands[0] if len(cands) == 1 else "有争议：" + " 或 ".join(cands)


def point_scores(p, r):
    """一条要点在三种权重下给这份报告的分数，按登记的标注计，用计分程序的公式。"""
    return {w: SCORE.point_score(p, r, SCORE.LEVEL_W[w], *SCORE.labelings(p)[0]) for w in WEIGHTS}


def rating_judges(data):
    """三次环节评级：名字写成"第一次评级（Claude Opus 5.5）"。模拟评审写成"评委 1（claude）"。"""
    if data.sim:
        return [(key, f"评委 {key}（{data.who(data.task_calls('评审-环节评级：', key)) or '没有成功的调用'}）", None)
                for key in data.ratings]
    out = []
    for i, key in enumerate(data.ratings):
        run = data.runs[f"rating-{key}.json"]
        out.append((key, f"第{ORDINALS[i]}次评级（{model_name(run['model'])}）", run))
    return out


def run_link(data, file_name):
    run = data.runs[file_name]
    return (f'<li><a href="{TO_PILOT}{esc(run["prompt"])}">{esc(run["task"])}</a>'
            f'<span class="faint">（{esc(model_name(run["model"]))}，{esc(run["date"].replace("-", " 年 ", 1).replace("-", " 月 ", 1))} 日；'
            f'<a href="{TO_PILOT}{esc(run["output"])}">评委的输出文件</a>）</span></li>')


def point_quote(data, p, r):
    """这份报告写到这条要点的原文：取合并进这条要点的第一个出自这份报告的条目。"""
    if data.sim:
        for s in p["sources"]:
            item = data.extracted.get(s)
            if item and item.get("report") == r and item.get("quote"):
                return item["quote"], f"评委 {item['slot']}（{item['vendor']}）抽取要点时从这份报告摘出的原文"
            m = re.fullmatch(r"(.+)-c(\d+)", s)
            if m and m.group(1) == r:
                for c in data.claims.get(r, []):
                    if c["id"] == s:
                        return c["quote"], f"这份报告的主要结论（{claim_no(s)}）"
        return None, None
    for s in p["sources"]:
        m = re.fullmatch(r"([a-z]+-\d+):([A-Z]+)-(\d+)", s)
        if m and m.group(2) == r and m.group(1) in data.ratings:
            for item in data.ratings[m.group(1)][r]["points"]:
                if item["id"] == f"{r}-{m.group(3)}":
                    i = list(data.ratings).index(m.group(1))
                    return item["quote"], f"第{ORDINALS[i]}次评级时从这份报告抽出的要点"
        m = re.fullmatch(r"([A-Z]+)-c(\d+)", s)
        if m and m.group(1) == r:
            for c in data.claims.get(r, []):
                if c["id"] == s:
                    return c["quote"], f"这份报告的主要结论（{claim_no(s)}）"
    return None, None


def relation_items(data, r):
    items = []
    for o in data.order:
        if o == r:
            continue
        if (r, o) in data.above:
            head, story, anchor = f"排在 {o} 之前", separated_story(data, r, o), f"pair-{r}-{o}"
        elif (o, r) in data.above:
            head, story, anchor = f"排在 {o} 之后", separated_story(data, o, r), f"pair-{o}-{r}"
        else:
            a, b = sorted((r, o), key=data.order.index)
            head, story, anchor = f"与 {o} 分不开", tied_story(data, a, b), f"pair-{a}-{b}"
        items.append(f'<li><p class="who body-3"><a href="report-{o}.html">{esc(head)}</a></p><p class="body-6">{esc(story)}'
                     f' <a href="index.html#{anchor}">在名次页上看</a></p></li>')
    return f'<ul class="pairs">{"".join(items)}</ul>'


def problems_section(data, r):
    claims = data.claims[r]
    probs = data.reports[r]["severe_problems"]
    fake = [c for c in claims if c["source_label"].startswith("找不到")]
    direct = data.direct[r]
    direct_claims = [c for c in claims if c["id"] in direct["ids"]]
    wrong = [c for c in direct_claims if c["correct"] == "有误"]
    off = [(name, data.ratings[key][r]["off_topic"]) for key, name, _ in rating_judges(data)]
    off_yes = sum(bool(v["value"]) for _, v in off)
    traceable = data.verify[r]["traceable_sources"]

    def item(title, hit, text):
        mark = tag("是严重问题", "bad") if hit else tag("不构成严重问题", "ok")
        return f'<li class="card"><div class="card-head"><span class="title-3">{esc(title)}</span>{mark}</div>{text}</li>'

    fake_text = ("<p class=\"body-6\">核验中没有来源被判为找不到。</p>" if not fake else
                 "<p class=\"body-6\">" + esc(join_cn(claim_no(c["id"]) for c in fake)) + " 的来源被判为找不到，详见下面的主要结论。</p>")
    direct_text = (f'<p class="body-6">标注评委选出的直接回答：{esc(join_cn(claim_no(c["id"]) for c in direct_claims))}。'
                   f'理由：{esc(direct["reason"])}</p>'
                   + "".join(f'<p class="body-6">{esc(claim_no(c["id"]))}：{esc(c["claim"])} 对错标签：{esc(c["correct"])}。</p>'
                             for c in direct_claims))
    off_text = "".join(f'<p class="body-6">{esc(name)}：{"判为答非所问" if v["value"] else "不算答非所问"}。{esc(v["reason"])}</p>'
                       for name, v in off)
    trace_text = (f'<p class="body-6">{data.verifier_word}判定：{"有可追溯的出处" if traceable else "全篇没有可追溯的出处"}。'
                  f'判定的理由写在{data.verifier_word}的备注里，见下一节开头。</p>')
    items = [
        item("确认编造来源", "编造来源" in probs, fake_text),
        item("对题目的直接回答被可靠证据否定", "主要结论与证据相反" in probs, direct_text
             + ("" if not wrong else f'<p class="body-6">其中{esc(join_cn(claim_no(c["id"]) for c in wrong))} 被判有误，'
                                     f'计分结果记为“主要结论与证据相反”。</p>')),
        item("答非所问", "答非所问" in probs, off_text + f'<p class="body-6 faint">{count_cn(len(off), "次")}评级中 {off_yes} 次判为答非所问，过半才算。</p>'),
        item("全篇没有可追溯的出处", "全篇没有可追溯的出处" in probs, trace_text),
    ]
    summary = " 没有严重问题。" if not probs else f" 有严重问题：{join_cn(probs)}。有严重问题的报告排在所有没有严重问题的报告之后。"
    return f"""<section class="block" id="problems" aria-labelledby="problems-h">
  <h2 class="heading-5" id="problems-h">有没有严重问题</h2>
  <p class="body-3 sum">{esc(data.name(r))}{esc(summary)}规则手册第八节列了四种严重问题（手册里叫“硬伤”），下面逐一列出判定和依据。从第 1.1 版起，第二种只看对题目的直接回答有没有被否定，其他结论写错在深度净分里扣分。</p>
  <ul class="cards grid-2">{"".join(items)}</ul>
</section>"""


def sim_claims_sum(data, r, claims, count_text):
    lister = data.who(data.task_calls(f"评审-结论清单：报告 {r}，")) or "没有成功的调用"
    checks = data.task_calls(f"评审-断言核验：报告 {r}，")
    slots = unique(re.search(r"评委 (\d+)$", c["task"]).group(1) for _, c in checks if re.search(r"评委 (\d+)$", c["task"]))
    return (f"清单员（{lister}）从这份报告列出 {len(claims)} 条主要结论，{len(slots)} 位核验员（{data.who(checks) or '没有成功的调用'}）"
            f"逐条判定来源标签和对错标签，各取多数（{count_text}）。对错以截至 {data.question['cutoff']} 已经存在的信息为准。")


def votes_text(votes):
    return "，".join(f"{k} {v} 票" for k, v in votes.items())


def claims_section(data, r):
    claims = data.claims[r]
    verifier = None if data.sim else model_name(data.runs[data.verify_file[r]]["model"])
    direct = set(data.direct[r]["ids"])
    tl = data.verify[r]["timeliness"]
    cards = []
    for c in claims:
        tags = [plain_tag("核心结论" if c.get("core") else "非核心结论")]
        if c["id"] in direct:
            tags.append(plain_tag("对题目的直接回答"))
        tags += [tag(c["source_label"], SOURCE_TONE.get(c["source_label"], "")), tag(c["correct"], CORRECT_TONE.get(c["correct"], ""))]
        parts = [f'<div class="card-head"><span class="title-3">{esc(claim_no(c["id"]))}</span>{"".join(tags)}</div>',
                 f'<p class="body-3">{esc(c["claim"])}</p>',
                 f'<h4>报告原文</h4><blockquote class="body-6">{esc(c["quote"])}</blockquote>',
                 f'<h4>所引来源</h4><p class="body-6">{esc(c["cited"])}</p>',
                 f'<h4>来源标签：{esc(c["source_label"])}</h4><p class="body-6">{esc(c["source_note"])}</p>']
        if c.get("second_check"):
            parts.append(f'<h4>第二次核查</h4><p class="body-6">{esc(c["second_check"])}</p>')
        parts.append(f'<h4>对错标签：{esc(c["correct"])}</h4><p class="body-6">{esc(c["correct_basis"])}</p>')
        if c.get("votes") is not None:
            v = c["votes"]
            source = votes_text(v.get("source_label") or {}) or "没有投票：报告里这条结论没有网址，程序直接定为没有出处"
            parts.append(f'<h4>核验员的票数</h4><p class="body-6">来源标签：{esc(source)}。对错标签：{esc(votes_text(v.get("correct") or {}) or "没有投票")}。'
                         f'核验时的工具限定：{esc(join_cn(c.get("tools") or []))}。</p>')
        re_c = data.recheck.get(c["id"])
        if re_c:
            who = model_name(data.runs["verify-sonnet-subset.json"]["model"])
            same = re_c["source_label"] == c["source_label"] and re_c["correct"] == c["correct"]
            parts.append(f'<h4>独立重核（{esc(who)}）：{"两个标签都与上面相同" if same else "与上面不同"}</h4>'
                         f'<p class="body-6">来源标签：{esc(re_c["source_label"])}。{esc(re_c["source_note"])}</p>'
                         f'<p class="body-6">对错标签：{esc(re_c["correct"])}。{esc(re_c["correct_basis"])}</p>')
        cards.append(f'<li class="card" id="claim-{esc(c["id"])}">{"".join(parts)}</li>')
    counts = {}
    for c in claims:
        counts[c["correct"]] = counts.get(c["correct"], 0) + 1
    count_text = "，".join(f"{k} {v} 条" for k, v in counts.items())
    return f"""<section class="block" id="claims" aria-labelledby="claims-h">
  <h2 class="heading-5" id="claims-h">主要结论的核验</h2>
  <p class="body-3 sum">{esc(sim_claims_sum(data, r, claims, count_text)) if data.sim else f"核验评委（{esc(verifier)}）从这份报告抽出 {len(claims)} 条主要结论，逐条打开所引来源核对，记下来源标签和对错标签（{esc(count_text)}）。对错以截至 {esc(data.question['cutoff'])} 已经存在的信息为准。"}</p>
  <p class="body-3 sum">来源标签有六种：支持、部分支持、不支持、失效但有存档、找不到、没有出处。“找不到”经第二次核查确认才算编造。所引来源不支持主要结论的，每处在深度净分里扣 {num(SCORE.UNSUPPORTED_W)}。对错标签有三种：正确、有误、无法判断。</p>
  <div class="sub"><h3 class="heading-6">{data.verifier_word}的备注</h3><p class="body-6 prose">{esc(data.verify[r]["notes"])}</p></div>
  <div class="sub"><h3 class="heading-6">时效：{num(tl["score"])} 档</h3><p class="body-6 prose">{esc(tl["reason"])}</p></div>
  <ol class="cards">{"".join(cards)}</ol>
</section>"""


def no_quote_text(data, p, r):
    if not data.sim:
        return "没有单独抽出的原文：这一处是要点池评委核对报告原文时补记的。"
    if p.get("reach_from", {}).get(r) == "写到核对":
        return "没有单独抽出的原文：这一处是写到核对一步补记的。"
    return "没有单独抽出的原文。"


def points_section(data, r):
    reached = [p for p in data.pool if r in p.get("reach", {})]
    groups = {"得分的要点": [], "扣分的要点": [], "不计分的要点": []}
    totals = {w: 0.0 for w in WEIGHTS}
    for p in reached:
        sc = point_scores(p, r)
        for w in WEIGHTS:
            totals[w] += sc[w]
        key = "扣分的要点" if any(v < 0 for v in sc.values()) else "得分的要点" if any(v > 0 for v in sc.values()) else "不计分的要点"
        groups[key].append((p, sc))
    unsupported = sum(1 for c in data.claims[r] if c["source_label"] == "不支持")
    penalty = SCORE.UNSUPPORTED_W * unsupported
    nets = data.reports[r]["net_scores"]
    for w in WEIGHTS:
        if round(totals[w] - penalty, 2) != nets[w]:
            raise SystemExit(f"报告 {r} 在{w}种权重下逐条相加得 {totals[w] - penalty}，与结果文件的净分 {nets[w]} 不一致")

    def card(p, sc):
        reach = p["reach"][r]
        tags = [plain_tag(labels_text(p, "level")), plain_tag(labels_text(p, "importance", "一般")),
                tag(p["correct"], CORRECT_TONE.get(p["correct"], "")),
                plain_tag("切题" if p.get("relevant", True) else "不切题"),
                tag(REACH_TEXT.get(reach, reach), "ok" if reach == "符合" else "bad")]
        quote, where = point_quote(data, p, r)
        q = (f'<details><summary class="caption-2">报告原文（{esc(where)}）</summary><blockquote class="body-6">{esc(quote)}</blockquote></details>'
             if quote else f'<p class="caption-2 faint">{no_quote_text(data, p, r)}</p>')
        scores = "，".join(f"{w}种 {num(sc[w])}" for w in WEIGHTS)
        return (f'<li class="card" id="point-{esc(p["pid"])}"><div class="card-head"><a class="title-3" href="points.html#{esc(p["pid"])}">'
                f'{esc(p["pid"])}</a>{"".join(tags)}</div><p class="body-3">{esc(p["content"])}</p>'
                f'<p class="caption-2 muted">得分：{esc(scores)}</p>{q}</li>')

    subs = []
    notes = {"得分的要点": "写对的、切题的要点，按层级权重乘以重要性加分。现象一层在甲、乙两种权重下是 0 分，在丙种权重下是 0.5。",
             "扣分的要点": "说法与正确的要点相反，或写了被判为有误的内容：核心内容扣 2，一般内容扣 1。",
             "不计分的要点": "对错无法判断、不切题，或者写的是一条有误要点的反面，这些都不加分也不扣分。"}
    for key, items in groups.items():
        if items:
            subs.append(f'<div class="sub"><h3 class="heading-6">{key}（{len(items)} 条）</h3><p class="body-6 muted prose">{notes[key]}</p>'
                        f'<ul class="cards">{"".join(card(p, sc) for p, sc in items)}</ul></div>')
    agree = sum(1 for p in reached if p["reach"][r] == "符合")
    tot = table(["", *[f"{w}种权重" for w in WEIGHTS]],
                [["要点得分合计"] + [num(round(totals[w], 2)) for w in WEIGHTS],
                 [f"来源不支持的扣分（{unsupported} 处，每处 {num(SCORE.UNSUPPORTED_W)}）"] + [num(-penalty) if penalty else "0" for _ in WEIGHTS],
                 ["深度净分"] + [f"<strong>{num(nets[w])}</strong>" for w in WEIGHTS]],
                numeric=(1, 2, 3))
    return f"""<section class="block" id="points" aria-labelledby="points-h">
  <h2 class="heading-5" id="points-h">写到的要点</h2>
  <p class="body-3 sum">要点池共 {len(data.pool)} 条要点，这份报告写到其中 {len(reached)} 条：说法一致的 {agree} 条，说法相反的 {len(reached) - agree} 条。每条标出深到哪一层（现象、全体、内部联系、本质）、是核心还是一般、对不对、切不切题，以及在三种权重下给这份报告的分数。逐条相加，再减去来源不支持的扣分，就是名次页上的深度净分。</p>
  {tot}
  {"".join(subs)}
</section>"""


def not_found_note(rating):
    if rating.get("evidence_in_report") is False:
        return '<p class="caption-2 faint">程序在报告里没有找到这段引文，档位没有改动，留给人工核对。</p>'
    return ""


def grades_section(data, r):
    judges = rating_judges(data)
    rep = data.reports[r]
    keys = [(k, name) for k, name in ELEMENTS] + [("写作", "写作（不进入名次）")]
    rows = []
    for k, name in keys:
        final = rep["writing"] if k == "写作" else rep["element_grades"][k]
        rows.append([esc(name), f"<strong>{num(final)}</strong>"] + [num(data.ratings[key][r]["ratings"][k]["score"]) for key, _, _ in judges])
    tl = data.verify[r]["timeliness"]
    summary = table(["", "用于名次的档位"] + [esc(n) for _, n, _ in judges], rows, numeric=tuple(range(1, 2 + len(judges))))
    summary += (f'<p class="legend caption-2">时效不在这张表里：它{"取各次环节评级的中位数" if data.sim else "由核验评委评"}，档位是 {num(rep["timeliness"])}，'
                f'不进入名次，理由见本节末尾。</p>')
    blocks = []
    for k, name in keys:
        cards = "".join(
            f'<li class="card"><div class="card-head"><span class="title-4">{esc(jn)}</span>{plain_tag(num(data.ratings[key][r]["ratings"][k]["score"]) + " 档")}</div>'
            f'<h4>引用的原文</h4><blockquote class="body-6">{esc(data.ratings[key][r]["ratings"][k]["evidence"])}</blockquote>'
            f'<h4>理由</h4><p class="body-6">{esc(data.ratings[key][r]["ratings"][k]["reason"])}</p>'
            f'{not_found_note(data.ratings[key][r]["ratings"][k])}</li>'
            for key, jn, _ in judges)
        final = rep["writing"] if k == "写作" else rep["element_grades"][k]
        blocks.append(f'<div class="sub" id="grade-{len(blocks) + 1}"><h3 class="heading-6">{esc(name)}：{num(final)} 档</h3>'
                      f'<ul class="cards grid-2">{cards}</ul></div>')
    blocks.append(f'<div class="sub"><h3 class="heading-6">时效：{num(rep["timeliness"])} 档</h3><p class="body-6 prose">{"" if data.sim else "核验评委评。"}{esc(tl["reason"])}</p></div>')
    return f"""<section class="block" id="grades" aria-labelledby="grades-h">
  <h2 class="heading-5" id="grades-h">环节评级</h2>
  <p class="body-3 sum">五个环节由{count_cn(len(judges), "次")}独立的评级各评 0、1、2 三档，每一档都引报告原文为证；用于名次的是{count_cn(len(judges), "次")}的中位数。{data.timeliness_by}，不进入名次。只有深度净分分不开时，才比较五个环节的评级。写作只记录，不进入名次。</p>
  {summary}
  {"".join(blocks)}
</section>"""


def pairwise_section(data, r):
    rows = []
    for o in data.order:
        if o == r:
            continue
        lines = []
        for i, (name, d) in enumerate(data.pairwise):
            for it in d["pairs"]:
                if {it["first"], it["second"]} != {r, o}:
                    continue
                v = it["verdict"]
                verdict = (f"判 {it['first']} 更好" if v == "first" else f"判 {it['second']} 更好" if v == "second" else "判两份相当")
                who = f"{d.get('judge', '')}（{it.get('vendor', '')}）" if data.sim else f"第{ordinal(i)}次比较"
                lines.append(f'<p class="body-6"><strong>{esc(who)}</strong>（先读 {it["first"]}，后读 {it["second"]}）：'
                             f'{esc(verdict)}。{esc(it["reason"])}</p>')
        if lines:
            rows.append(f'<li><p class="who body-3">与<a href="report-{o}.html">{esc(data.name(o))}</a> 比较</p>{"".join(lines)}</li>')
    return f"""<section class="block" id="pairwise" aria-labelledby="pairwise-h">
  <h2 class="heading-5" id="pairwise-h">两两比较</h2>
  <p class="body-3 sum">{esc(veto_rule_text(data))}</p>
  <ul class="pairs">{"".join(rows)}</ul>
</section>"""


def concerns(task, r):
    """这次调用是否涉及报告 r：只涉及一份报告的步骤写"报告 r，"，两两比较写"r 在前"或"r 在后"，合并和判定涉及全部报告。"""
    return (f"报告 {r}，" in task or f"：{r} 在前，" in task or f"，{r} 在后，" in task
            or task.startswith(("评审-要点池合并", "评审-要点判定")))


def sim_prompts_section(data, r):
    items = []
    for i, c in enumerate(data.calls, 1):
        if not concerns(c["task"], r):
            continue
        name = esc(task_text(c["task"]))
        link = f'<a href="{data.calls_dir}{i}.html">{name}</a>' if data.calls_dir else name
        items.append(f'<li>{link}<span class="faint">（{esc(c["vendor"])}，{esc(c.get("tools") or "")}，{esc(c.get("status") or "")}）</span></li>')
    where = (f'<a href="{data.review_page}#calls">这次评审的记录</a>' if data.review_page
             else f'<a href="{data.to_src}calls.jsonl">调用记录文件</a>')
    return f"""<section class="block" id="prompts" aria-labelledby="prompts-h">
  <h2 class="heading-5" id="prompts-h">评委收到的提示词</h2>
  <p class="body-3 sum">这一页用到的每一次模型调用，提示词和回答的原文都可以点开看：下面是涉及这份报告的 {len(items)} 次调用。全部调用见{where}。</p>
  <ul class="links body-6">{"".join(items)}</ul>
</section>"""


def prompts_section(data, r):
    if data.sim:
        return sim_prompts_section(data, r)
    files = [data.verify_file[r]] + [f"rating-{k}.json" for k in data.ratings] + ["pool.json", "direct-answers.json"]
    files += [name for name, _ in data.pairwise]
    if any(c["id"] in data.recheck for c in data.claims[r]):
        files.append("verify-sonnet-subset.json")
    links = "".join(run_link(data, f) for f in files if f in data.runs)
    return f"""<section class="block" id="prompts" aria-labelledby="prompts-h">
  <h2 class="heading-5" id="prompts-h">评委收到的提示词</h2>
  <p class="body-3 sum">这一页用到的每一次评委运行，评委收到的提示词原文都存了档。全部清单和存档说明见<a href="{data.to_src}judges/README.md">评委提示词存档</a>。</p>
  <ul class="links body-6">{links}</ul>
</section>"""


def review_page(data, r):
    rep = data.reports[r]
    lede = (f"这一页列出{esc(data.name(r))}的全部评审材料：名次从哪里来、有没有严重问题、每条主要结论的核验、写到了要点池里的哪几条、"
            f"环节评级引用的原文、两两比较的理由，以及评委收到的提示词。对哪一条判定有异议，可以照着依据和<a href=\"{data.report_href(r)}\">报告原文</a>核对。")
    eyebrow = "模拟评审 · 复核页" if data.sim else "第五阶段试评 · 复核页"
    head = header(data, f"report-{r}.html", eyebrow, f"{data.name(r)}（{data.product(r)}）", lede, False)
    nets = "，".join(f"{w}种 {num(rep['net_scores'][w])}" for w in WEIGHTS)
    stats = f"""<div class="stats">
    <div class="stat"><p class="caption-1 faint">名次区间</p><p class="heading-6">{esc(interval(rep))}</p></div>
    <div class="stat"><p class="caption-1 faint">严重问题</p><p class="heading-6">{esc(problems_text(data, r))}</p></div>
    <div class="stat"><p class="caption-1 faint">深度净分</p><p class="heading-6">{esc(nets)}</p></div>
    <div class="stat"><p class="caption-1 faint">环节评级</p><p class="body-6">{esc(grades_inline(data, r))}</p></div>
  </div>"""
    jump = "".join(f'<li><a class="caption-1" href="#{i}">{t}</a></li>' for i, t in
                   [("problems", "严重问题"), ("claims", "主要结论"), ("points", "写到的要点"), ("grades", "环节评级"),
                    ("pairwise", "两两比较"), ("prompts", "提示词")])
    summary = f"""<section class="block" id="summary" aria-labelledby="summary-h">
  <h2 class="heading-5" id="summary-h">名次从哪里来</h2>
  <p class="body-3 sum">与另外{count_cn(len(data.labels) - 1)}报告逐一相比，下面写明先后是按哪一步定的。</p>
  {stats}
  <nav aria-label="本页各节"><ul class="pages">{jump}</ul></nav>
  <div class="sub"><h3 class="heading-6">与其他报告的先后</h3>{relation_items(data, r)}</div>
</section>"""
    body = "\n".join([head, '<main id="main"><div class="wrap">', summary, problems_section(data, r), claims_section(data, r),
                      points_section(data, r), grades_section(data, r), pairwise_section(data, r), prompts_section(data, r),
                      "</div></main>", footer(data)])
    if data.sim:
        return shell(data, f"{data.name(r)}复核页", f"模拟评审{data.name(r)}的主要结论核验、写到的要点、环节评级和两两比较。演示，不是对产品的评价。", body)
    return shell(data, f"{data.name(r)}复核页", f"第五阶段试评{data.name(r)}的主要结论核验、写到的要点、环节评级和两两比较。试评演示，不是对产品的评价。", body)


# ---------- 要点池页 ----------

LEVEL_NOTES = {"现象": "事情本身的事实和表面特征。",
               "全体": "事情的历史，即怎样演变而来；或者全部现状，特别是容易被忽略的方面、例外和反例。",
               "内部联系": "这件事与其他事情之间的因果、制约、依赖关系。",
               "本质": "事情的性质，即为什么是这样、根本的特征是什么，包括概念的名与实。"}


def sim_sources_text(data, p):
    depth, extracted, claims = [], {}, []
    for s in p["sources"]:
        m = re.fullmatch(r"(.+)-c(\d+)", s)
        if re.fullmatch(r"M\d+", s):
            depth.append(s)
        elif s in data.extracted:
            r = data.extracted[s].get("report")
            extracted[r] = extracted.get(r, 0) + 1
        elif m and m.group(1) in data.labels:
            claims.append(f"报告 {m.group(1)} 的结论 {m.group(2)}")
        else:
            claims.append(s)
    parts = [f"深度地图 {s}" for s in depth]
    parts += [f"抽取要点时从报告 {r} 抽出的要点 {extracted[r]} 条" for r in data.labels if r in extracted]
    return "；".join(parts + claims)


def sources_text(data, p):
    """一条要点由哪些条目合并而来，写成白话。"""
    if data.sim:
        return sim_sources_text(data, p)
    depth, extracted, claims, perturbed = [], {}, [], 0
    for s in p["sources"]:
        if re.fullmatch(r"M\d+", s):
            depth.append(s)
        elif re.fullmatch(r"P\d+-c?\d+", s):
            perturbed += 1
        elif m := re.fullmatch(r"[a-z]+-\d+:([A-Z]+)-\d+", s):
            extracted[m.group(1)] = extracted.get(m.group(1), 0) + 1
        elif m := re.fullmatch(r"([A-Z]+)-c(\d+)", s):
            claims.append(f"报告 {m.group(1)} 的结论 {m.group(2)}")
        else:
            claims.append(s)
    parts = [f"深度地图 {s}" for s in depth]
    parts += [f"评级时从报告 {r} 抽出的要点 {k} 条" for r, k in sorted(extracted.items())]
    parts += claims
    if perturbed:
        parts.append(f"扰动版本的条目 {perturbed} 条")
    return "；".join(parts)


def points_page(data):
    pool = data.pool
    n = count_cn(len(data.labels))
    span = f"{data.labels[0]} 至 {data.labels[-1]}"
    head = header(data, "points.html", f"{'模拟评审' if data.sim else '第五阶段试评'} · 要点池", f"{data.kind()}要点池",
                  f"要点池合并了出题人的深度地图和评委从{n}报告里抽出的要点、主要结论，意思相同的合成一条，再逐条判定对不对、切不切题、"
                  f"深到哪一层、是核心还是一般。共 {len(pool)} 条。每一行写明 {esc(span)} 哪几份报告写到、说法一致还是相反；点报告名可以跳到那份报告复核页上的同一条。", False)

    by = {(lv, imp): 0 for lv in LEVELS for imp in ("核心", "一般")}
    for p in pool:  # 有争议的要点按登记的标注计数
        key = (SCORE.candidates(p, "level")[0], SCORE.candidates(p, "importance", "一般")[0])
        by[key] += 1
    t_levels = table(["层级", "定义", "核心", "一般", "合计"],
                     [[lv, esc(LEVEL_NOTES[lv]), num(by[(lv, "核心")]), num(by[(lv, "一般")]), num(by[(lv, "核心")] + by[(lv, "一般")])]
                      for lv in LEVELS], numeric=(2, 3, 4))
    correct = {}
    for p in pool:
        correct[p["correct"]] = correct.get(p["correct"], 0) + 1
    irrelevant = sum(1 for p in pool if not p.get("relevant", True))
    nobody = [p["pid"] for p in pool if not any(r in p.get("reach", {}) for r in data.labels)]
    per = []
    for r in data.labels:
        reached = [p for p in pool if r in p.get("reach", {})]
        agree = sum(1 for p in reached if p["reach"][r] == "符合")
        core = sum(1 for p in reached if p["reach"][r] == "符合" and p["correct"] == "正确" and labels_text(p, "importance", "一般") == "核心")
        per.append([f'<a href="report-{r}.html#points">{esc(data.name(r))}</a>', esc(data.product(r)), num(len(reached)), num(agree),
                    num(len(reached) - agree), num(core)])
    t_reports = table(["报告", "产品", "写到", "说法一致", "说法相反", "其中写对的核心要点"], per, numeric=(2, 3, 4, 5))
    summary = f"""<section class="block" id="summary" aria-labelledby="summary-h">
  <h2 class="heading-5" id="summary-h">要点池一览</h2>
  <p class="body-3 sum">层级的定义取自<a href="{data.to_notes}plan-stage4-rubric.html#_1">评审细则</a>第一节。抽象的套话不算本质；一条要点只有说出了具体的性质或联系，才能定为内部联系或本质。</p>
  {t_levels}
  <p class="body-3 sum" style="margin-top: 16px;">对错：{esc("，".join(f"{k} {v} 条" for k, v in correct.items()))}；不切题的 {irrelevant} 条。只有正确、切题的要点写对了才加分。</p>
  <div class="sub"><h3 class="heading-6">每份报告写到多少</h3>{t_reports}
  <p class="legend caption-2">“说法相反”指报告写了与这条要点相反的说法。{n}报告都没有写到的有 {len(nobody)} 条（{esc(join_cn(nobody))}），它们不参与重抽样。{"" if data.sim else "试评还用了四份为检验评法故意改动过的扰动版本，它们不进名次，这里不列出。"}</p></div>
</section>"""

    rows = []
    for p in pool:
        chips = []
        for r in data.labels:
            reach = p.get("reach", {}).get(r)
            if reach:
                chips.append(f'<a class="tag caption-3 {"ok" if reach == "符合" else "bad"}" href="report-{r}.html#point-{esc(p["pid"])}">'
                             f'{r} {REACH_TEXT.get(reach, reach)}</a>')
        who = "".join(chips) if chips else f'<span class="faint">{n}报告都没有写到</span>'
        rows.append(
            f'<tr id="{esc(p["pid"])}"><td data-label="编号" class="pid"><strong>{esc(p["pid"])}</strong></td>'
            f'<td data-label="要点" class="content"><p>{esc(p["content"])}</p><details><summary class="caption-2">依据和出处</summary>'
            f'<p class="body-6">依据：{esc(p["basis"])}</p><p class="body-6 faint">合并自：{esc(sources_text(data, p))}</p></details></td>'
            f'<td data-label="层级">{esc(labels_text(p, "level"))}</td><td data-label="重要性">{esc(labels_text(p, "importance", "一般"))}</td>'
            f'<td data-label="对错">{esc(p["correct"])}</td><td data-label="切题">{"是" if p.get("relevant", True) else "否"}</td>'
            f'<td data-label="写到的报告" class="who"><span class="chips">{who}</span></td></tr>')
    listing = f"""<section class="block" id="all" aria-labelledby="all-h">
  <h2 class="heading-5" id="all-h">全部要点</h2>
  <p class="body-3 sum">按要点池的编号排列。点开“依据和出处”可以看判定对错的依据，以及这条要点由哪些条目合并而来。</p>
  <div class="pool-table"><table>
    <thead><tr><th scope="col">编号</th><th scope="col">要点</th><th scope="col">层级</th><th scope="col">重要性</th><th scope="col">对错</th><th scope="col">切题</th><th scope="col">写到的报告</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
</section>"""
    body = "\n".join([head, '<main id="main"><div class="wrap">', summary, listing, "</div></main>", footer(data)])
    if data.sim:
        return shell(data, "模拟评审要点池", f"模拟评审要点池的全部 {len(pool)} 条要点，以及每条有哪几份报告写到。演示，不是对产品的评价。", body)
    return shell(data, "试评要点池", f"第五阶段试评要点池的全部 {len(pool)} 条要点，以及每条有哪几份报告写到。试评演示，不是对产品的评价。", body)


# ---------- 生成 ----------

def build(output, source=PILOT, links=None):
    """生成名次页、每份报告的复核页和要点池页，返回写出的文件名。"""
    data = Data(source, output, links)
    pages = {"index.html": rank_page(data), "points.html": points_page(data)}
    for r in data.labels:
        pages[f"report-{r}.html"] = review_page(data, r)
    for name, text in pages.items():
        COMMON.write_text_atomic(os.path.join(output, name), text)
    return sorted(pages)


def main():
    ap = argparse.ArgumentParser(description="生成第五阶段试评（或一次模拟评审）的名次页、复核页和要点池页。")
    ap.add_argument("--input", default=PILOT, help="读哪里：默认第五阶段试评；也可以给一次模拟评审的输出目录 simulation/reviews/<运行标识>/")
    ap.add_argument("--output", default=None, help="页面写到哪个目录：试评默认 site/results/；模拟评审必须给")
    args = ap.parse_args()
    simulated = os.path.isfile(os.path.join(args.input, "run.json"))
    if simulated and not args.output:
        ap.error("模拟评审要用 --output 给出页面写到哪个目录")
    if simulated and not os.path.isfile(os.path.join(args.input, RESULTS_NAME)):
        ap.error(f"这次模拟评审没有结果文件 {RESULTS_NAME}（中止了，或者只估算），没有名次可写")
    build(args.output or DEFAULT_OUTPUT, os.path.abspath(args.input))


if __name__ == "__main__":
    main()
