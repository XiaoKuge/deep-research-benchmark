"""第五阶段小规模检验：匿名化六份报告，生成扰动版本。"""
import json, os, random, re, sys
SRC = os.path.expanduser("~/github/mofa-research/docs/deep-research-of-deep-research")
DST = os.path.expanduser("~/github/mofa-research/docs/deep-research-benchmarks-2026/research-plan/stage5-pilot")
SECRET = sys.argv[1]  # 映射表存放处（评委看不到）
files = {
    "ChatGPT": "deep-research-report-chatgpt.md",
    "Gemini": "Gemini-Deep-Research.md",
    "Kimi": "Deep-Research-Report-kimi.md",
    "Perplexity": "Perplexity_Deep_Research_Report.md",
    "DeepSeek": "DeepSeek_Deep_Research_Report.md",
    "Claude": "research-report-claude.md",
}
labels = ["A", "B", "C", "D", "E", "F"]
names = list(files)
random.Random(20261029).shuffle(names)
mapping = dict(zip(labels, names))
os.makedirs(f"{DST}/reports", exist_ok=True)
os.makedirs(f"{DST}/perturb", exist_ok=True)
os.makedirs(f"{DST}/out", exist_ok=True)

def anonymize(text, label):
    lines = text.split("\n")
    # 第一行标题替换为统一标题，去掉 "ChatGPT's" 之类的产品名
    assert lines[0].startswith("#")
    lines[0] = f"# 报告{label}"
    return "\n".join(lines)

for lab, name in mapping.items():
    t = open(f"{SRC}/{files[name]}", encoding="utf-8").read()
    open(f"{DST}/reports/{lab}.md", "w", encoding="utf-8").write(anonymize(t, lab))

# 扰动：以 Perplexity 报告为底
base = open(f"{SRC}/{files['Perplexity']}", encoding="utf-8").read()
def must(s, a, b):
    assert s.count(a) == 1, a
    return s.replace(a, b)

err = base
err = must(err, "在 Humanity’s Last Exam 上达到 21.1% 准确率", "在 Humanity’s Last Exam 上达到 41.1% 准确率")
err = must(err, "在 SimpleQA factuality 基准上达到 93.9%", "在 SimpleQA factuality 基准上达到 73.9%")
err = must(err, "同时保持在几分钟内完成任务。", "但通常需要两到三个小时才能完成一次任务。")

PAD = open(os.path.join(os.path.dirname(__file__), "padding.md"), encoding="utf-8").read()
pad = must(base, "\n------\n\n## 主流 Deep Research 能力对比", "\n" + PAD + "\n------\n\n## 主流 Deep Research 能力对比")

fab = must(base, "[[creatoreconomy](https://creatoreconomy.so/p/an-opinionated-guide-on-which-ai-model-2025)]",
           "[[deepresearch-index](https://www.deepresearch-index.org/reports/2026-q1-head-to-head-evaluation.pdf)]")

versions = {"original": base, "errors": err, "padding": pad, "fabricated": fab}
plabels = ["P1", "P2", "P3", "P4"]
order = list(versions)
random.Random(7).shuffle(order)
pmap = dict(zip(plabels, order))
for lab, v in pmap.items():
    open(f"{DST}/perturb/{lab}.md", "w", encoding="utf-8").write(anonymize(versions[v], lab))
json.dump({"reports": mapping, "perturb": pmap}, open(SECRET, "w"), ensure_ascii=False, indent=1)
for lab in labels:
    print(lab, len(open(f"{DST}/reports/{lab}.md", encoding="utf-8").read()), "chars")
for lab in plabels:
    print(lab, len(open(f"{DST}/perturb/{lab}.md", encoding="utf-8").read()), "chars")
