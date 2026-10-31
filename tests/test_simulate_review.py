"""模拟评审（tools/simulate_review.py）的测试。

一律用回放方式（手写的回放材料）和只估算方式，不真的调用模型。
只通过命令行和程序写出的文件观察行为：运行元数据 run.json、调用记录 calls.jsonl、
数据目录、计分程序第 1.2 版写出的结果文件。

测试用的场景：一道题（深度地图两条要点，编号 1、2，评审时记作 M1、M2），三份报告 Alpha、Bravo、Charlie。
Alpha 没有网址；Bravo 引了一个有存档的网址；Charlie 引了一个没有存档的网址。
回放材料按评审细则设计成：Alpha 写到的要点包含 Bravo 写到的，Bravo 写到的包含 Charlie 写到的，
所以名次区间应当是 Alpha 第 1、Bravo 第 2、Charlie 第 3（手算见 StandardRunTest）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "simulate_review.py")
SCORER = os.path.join(ROOT, "research-plan", "stage5-pilot", "score.py")

BRAVO_URL = "https://example.org/bravo-source"
CHARLIE_URL = "https://example.org/charlie-source"
ARCHIVED_TEXT = "存档原文：布拉沃来源支持这条结论。"

# 题目目录的格式照模拟出题者（tools/simulate_setter.md「输出目录」）：评审要用的是题目卡.txt 和 深度地图.json。
QUESTION_CARD = """一、评委版（只给评委）
【提问者】一位想选用深度研究产品的普通用户。
【用途】帮助决定用哪一家。
【问题】哪家的深度研究功能最好？
【截止时间】只使用截至 2026-03-03 已经公开的信息。

二、提问版（交给智能体）
我想选一款深度研究产品，哪家的深度研究功能最好？只使用截至 2026-03-03 已经公开的信息。

三、裸题版（交给智能体）
哪家的深度研究功能最好？
"""

DEPTH_MAP = {
    "题目标识": "测试题", "类别": "练习题", "写成日期": "2026-03-01",
    "浅答案": "某一家最好。", "转折点": "\"最好\"要先说清对谁、做什么用。", "转折点用到的要点": [1],
    "要点": [
        {"编号": 1, "要点": "没有脱离用途的\"最好\"，要先确定用途再比较", "层级": "本质", "重要性": "核心",
         "依据": ["测试"], "把握": "高"},
        {"编号": 2, "要点": "各家先后推出深度研究功能，评价很快过时", "层级": "全体", "重要性": "一般",
         "依据": ["测试"], "把握": "中"},
    ],
    "找不到要点的层": "",
}

REPORTS = {
    "Alpha": "# 报告\n\n结论：没有绝对最好，要按用途选。\n\n各家优化的目标不同，所以先定用途。\n",
    "Bravo": "# 报告\n\n结论：引用准确的那家更可靠。\n\n见[来源](%s)。\n" % BRAVO_URL,
    "Charlie": "# 报告\n\n结论：选最快的那家。\n\n见 %s 。另外，速度最重要。\n" % CHARLIE_URL,
}
LABELS = ["Alpha", "Bravo", "Charlie"]
NAMES = {"Alpha": "产品甲", "Bravo": "产品乙", "Charlie": "产品丙"}

# 小配置：每一步用哪几家、每家几次。
CONFIG = {
    "steps": {
        "claims_list": {"vendors": ["claude"], "times": 1},
        "verify": {"vendors": ["claude", "codex", "kimi"], "times": 1},
        "extract": {"vendors": ["claude"], "times": 1},
        "merge": {"vendors": ["claude"], "times": 1},
        "reach": {"vendors": ["claude"], "times": 1},
        "judge": {"vendors": ["claude", "codex", "kimi"], "times": 1},
        "rating": {"vendors": ["claude", "codex"], "times": 1},
        "pairwise": {"vendors": ["claude", "codex"], "times": 1},
        "direct": {"vendors": ["claude"], "times": 1},
    }
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_inputs(tmp):
    """在 tmp 下写出题目目录、三份报告、名称表、网页存档和配置，返回命令行参数里要用的路径。"""
    question = os.path.join(tmp, "questions", "test-question")
    write(os.path.join(question, "题目卡.txt"), QUESTION_CARD)
    write(os.path.join(question, "深度地图.json"), json.dumps(DEPTH_MAP, ensure_ascii=False, indent=2))
    reports = []
    for label in LABELS:
        path = os.path.join(tmp, "reports", label + ".md")
        write(path, REPORTS[label])
        reports.append(path)
    names = os.path.join(tmp, "names.json")
    write(names, json.dumps(NAMES, ensure_ascii=False))
    archive = os.path.join(tmp, "archive", "Bravo")
    write(os.path.join(archive, "content", "bravo.html"),
          "<html><body><script>var hidden = 1;</script><p>%s</p></body></html>" % ARCHIVED_TEXT)
    write(os.path.join(archive, "manifest.json"), json.dumps({
        "report": "Bravo.md", "entries": [{
            "url": BRAVO_URL, "final_url": BRAVO_URL, "status": 200,
            "content_type": "text/html; charset=utf-8", "bytes": 100, "sha256": "0" * 64,
            "file": "content/bravo.html", "fetched_at": "2026-03-03T10:00:00Z", "error": None}]}))
    config = os.path.join(tmp, "config.json")
    write(config, json.dumps(CONFIG, ensure_ascii=False))
    return {"question": question, "reports": reports, "names": names,
            "archive": os.path.join(tmp, "archive"), "config": config}


def run_tool(inputs, out, *extra, keep_labels=True):
    cmd = [sys.executable, "-I", TOOL, "--question", inputs["question"],
           "--reports", *inputs["reports"], "--names", inputs["names"],
           "--archive", inputs["archive"], "--config", inputs["config"],
           "--out", out, "--run-id", "test-run"]
    if keep_labels:
        cmd.append("--keep-labels")
    return subprocess.run(cmd + list(extra), capture_output=True, text=True, encoding="utf-8")


# ---- 手写的回放材料 ------------------------------------------------------------
# 任务名的写法见 tools/simulate_review.md「回放材料」一节；评委按配置编号：
# 断言核验和要点判定 1 claude、2 codex、3 kimi；环节评级和两两比较 1 claude、2 codex；其余只有评委 1（claude）。

THREE = [(1, "claude"), (2, "codex"), (3, "kimi")]
TWO = [(1, "claude"), (2, "codex")]

CLAIMS = {
    "Alpha": [{"claim": "没有绝对最好，要按用途选", "quote": "结论：没有绝对最好，要按用途选。",
               "cited": "无", "urls": [], "core": True}],
    "Bravo": [{"claim": "引用准确的那家更可靠", "quote": "结论：引用准确的那家更可靠。",
               "cited": BRAVO_URL, "urls": [BRAVO_URL], "core": True}],
    "Charlie": [{"claim": "选最快的那家", "quote": "结论：选最快的那家。", "cited": CHARLIE_URL,
                 "urls": [CHARLIE_URL], "core": True},
                {"claim": "速度最重要", "quote": "另外，速度最重要。", "cited": "无", "urls": [],
                 "core": False}],
}
VERIFY = {
    ("Alpha", "只给材料"): [{"id": "c1", "correct": "正确", "correct_basis": "测试"}],
    ("Bravo", "只给材料"): [{"id": "c1", "source_label": "支持", "source_note": "存档写明",
                            "second_check": "", "correct": "正确", "correct_basis": "测试"}],
    ("Charlie", "只给材料"): [{"id": "c2", "correct": "正确", "correct_basis": "测试"}],
    ("Charlie", "只读网页"): [{"id": "c1", "source_label": "支持", "source_note": "网页写明",
                              "second_check": "", "correct": "正确", "correct_basis": "测试"}],
}
EXTRACTED = {"Alpha": 6, "Bravo": 3, "Charlie": 1}  # 每份报告抽出几条要点
# 合并后的要点池：Q1 由地图 M1 和 Alpha 的第 1 条合成，Q11 只有地图 M2。
MERGED = [
    ["M1", "claude-1:Alpha-1"], ["claude-1:Alpha-2", "Alpha-c1"], ["claude-1:Alpha-3"],
    ["claude-1:Alpha-4"], ["claude-1:Alpha-5"], ["claude-1:Alpha-6"],
    ["claude-1:Bravo-1", "Bravo-c1"], ["claude-1:Bravo-2"], ["claude-1:Bravo-3"],
    ["claude-1:Charlie-1", "Charlie-c1", "Charlie-c2"], ["M2"],
]
POINT_TEXT = ["用途决定比较的标准", "评测各有偏向", "厂商自己发布评测", "定义各家不同", "速度与深度的取舍",
              "中文与英文覆盖不同", "引用多不等于引用准", "运行越久越完整", "更新很快要注明时间",
              "速度是一个维度", "各家先后推出"]
WRITTEN = {"Alpha": ["Q7", "Q8", "Q9", "Q10"], "Bravo": ["Q10"], "Charlie": []}
# 要点判定：每条要点三位评委的（层级, 重要性, 改动理由）；None 表示这位评委漏了这一条。
R = "依据细则第三节的定义"
JUDGED = {
    "Q1": [("全体", "核心", R), ("全体", "核心", R), ("本质", "核心", "")],   # 三分之二改动地图登记
    "Q2": [("本质", "核心", "")] * 3,
    "Q3": [("本质", "核心", ""), ("本质", "核心", ""), ("全体", "核心", "")],  # 恰好三分之二
    "Q4": [("本质", "一般", ""), ("全体", "一般", ""), ("内部联系", "一般", "")],  # 三种意见各一
    "Q5": [("内部联系", "核心", ""), ("内部联系", "一般", ""), ("内部联系", "一般", "")],
    "Q6": [("全体", "核心", ""), ("全体", "核心", ""), ("全体", "一般", "")],
    "Q7": [("全体", "一般", "")] * 3,
    "Q8": [("内部联系", "一般", "")] * 3,
    "Q9": [("内部联系", "核心", ""), ("内部联系", "一般", ""), None],         # 两票各一
    "Q10": [("全体", "一般", "")] * 3,
    "Q11": [("全体", "一般", ""), ("全体", "一般", ""), ("本质", "一般", "")],  # 改动没写理由
}
BETTER = {"Alpha": 3, "Bravo": 2, "Charlie": 1}


def entry(task, vendor, answer):
    return {"task": task, "vendor": vendor, "answer": json.dumps(answer, ensure_ascii=False)}


def rating_answer(label):
    quote = REPORTS[label].splitlines()[2]
    item = {"score": 1, "evidence": quote, "reason": "测试"}
    return {"ratings": {e: dict(item) for e in ("①", "③", "④", "⑤", "⑦", "写作")},
            "timeliness": {"score": 1, "reason": "测试"},
            "off_topic": {"value": False, "reason": "测试"},
            "traceable_sources": {"value": True, "reason": "测试"}}


def standard_replay():
    """标准场景下全部 46 次调用的回答。"""
    entries = []
    for label in LABELS:
        entries.append(entry("评审-结论清单：报告 %s，评委 1" % label, "claude", {"claims": CLAIMS[label]}))
    for (label, tools), claims in VERIFY.items():
        for slot, vendor in THREE:
            entries.append(entry("评审-断言核验：报告 %s，%s，评委 %d" % (label, tools, slot), vendor,
                                 {"claims": claims}))
    for label, n in EXTRACTED.items():
        points = [{"content": "%s 的第 %d 条认识" % (label, i), "level": "全体", "quote": "测试"}
                  for i in range(1, n + 1)]
        entries.append(entry("评审-要点抽取：报告 %s，评委 1" % label, "claude", {"points": points}))
    entries.append(entry("评审-要点池合并：评委 1", "claude", {"points": [
        {"content": text, "sources": sources, "opposite": []} for text, sources in zip(POINT_TEXT, MERGED)]}))
    for label in LABELS:
        entries.append(entry("评审-写到核对：报告 %s，评委 1" % label, "claude", {
            "written": [{"pid": pid, "reach": "符合", "quote": "测试"} for pid in WRITTEN[label]]}))
    for i, (slot, vendor) in enumerate(THREE):
        points = []
        for pid, votes in JUDGED.items():
            if votes[i] is None:
                continue
            level, importance, reason = votes[i]
            points.append({"pid": pid, "correct": "正确", "basis": "测试", "relevant": True,
                           "level": level, "importance": importance, "change_reason": reason})
        entries.append(entry("评审-要点判定：评委 %d" % slot, vendor, {"points": points}))
    for label in LABELS:
        for slot, vendor in TWO:
            entries.append(entry("评审-环节评级：报告 %s，评委 %d" % (label, slot), vendor, rating_answer(label)))
    for first in LABELS:
        for second in LABELS:
            if first == second:
                continue
            for slot, vendor in TWO:
                verdict = ("first" if BETTER[first] > BETTER[second] else "second") if vendor == "claude" else "tie"
                entries.append(entry("评审-两两比较：%s 在前，%s 在后，评委 %d" % (first, second, slot), vendor,
                                     {"verdict": verdict, "reason": "测试"}))
    for label in LABELS:
        entries.append(entry("评审-直接回答：报告 %s，评委 1" % label, "claude", {"ids": ["c1"], "reason": "测试"}))
    return entries


def write_replay(path, entries):
    write(path, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))
    return path


class StandardRunTest(unittest.TestCase):
    """标准场景用回放跑一遍：从报告一直到计分程序第 1.2 版的结果文件。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = cls._tmp.name
        cls.inputs = build_inputs(tmp)
        replay = write_replay(os.path.join(tmp, "replay.jsonl"), standard_replay())
        cls.out = os.path.join(tmp, "review")
        cls.result = run_tool(cls.inputs, cls.out, "--replay", replay)
        cls.meta = read_json(os.path.join(cls.out, "run.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def results(self):
        return {r["label"]: r for r in read_json(os.path.join(self.out, "results-v1.2.json"))["reports"]}

    def test_one_command_goes_from_reports_to_rank_intervals(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertEqual(self.meta["status"], "完成")
        results = self.results()
        self.assertEqual({label: (r["rank_best"], r["rank_worst"]) for label, r in results.items()},
                         {"Alpha": (1, 1), "Bravo": (2, 2), "Charlie": (3, 3)})
        self.assertEqual({label: r["product"] for label, r in results.items()}, NAMES)

    def test_net_scores_follow_the_registered_labels(self):
        # 手算（层级权重 × 重要性权重，有争议的按登记值即候选列表第一项）：
        # Alpha 写到 Q1–Q10：甲 2+2+2+1+1+2+1+1+1+1=14，乙 4+4+4+1+2+2+1+2+2+1=23，丙 4+4+4+1+1.5+2+1+1.5+1.5+1=21.5
        # Bravo 写到 Q7–Q10：甲 4，乙 6，丙 5；Charlie 写到 Q10：甲、乙、丙都是 1。
        self.assertEqual({label: r["net_scores"] for label, r in self.results().items()}, {
            "Alpha": {"甲": 14, "乙": 23, "丙": 21.5},
            "Bravo": {"甲": 4, "乙": 6, "丙": 5},
            "Charlie": {"甲": 1, "乙": 1, "丙": 1}})

    def test_data_directory_is_read_by_scorer_version_1_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "again.json")
            subprocess.run([sys.executable, "-I", SCORER, os.path.join(self.out, "mapping.json"), "1.2",
                            "--data", os.path.join(self.out, "data"), "--output", output],
                           check=True, capture_output=True)
            again = read_json(output)
        self.assertEqual({r["label"]: [r["rank_best"], r["rank_worst"]] for r in again["reports"]},
                         {"Alpha": [1, 1], "Bravo": [2, 2], "Charlie": [3, 3]})
        self.assertEqual(again["version"], "1.2")

    # 三分之二规则（评审细则第四节末尾）：期望值按规则条文逐条手推。
    def pool(self):
        return {p["pid"]: p for p in read_json(os.path.join(self.out, "data", "pool.json"))["points"]}

    def test_two_of_three_agreeing_is_not_disputed(self):
        pool = self.pool()
        self.assertEqual(pool["Q3"]["level"], "本质")         # 本质、本质、全体
        self.assertEqual(pool["Q5"]["importance"], "一般")    # 核心、一般、一般
        self.assertEqual(pool["Q6"]["importance"], "核心")    # 核心、核心、一般
        self.assertEqual(pool["Q2"]["level"], "本质")

    def test_no_opinion_reaching_two_thirds_becomes_a_candidate_list(self):
        pool = self.pool()
        # 三种意见各一：登记值取票数最多里最浅的"全体"，其余按由浅到深排在后面。
        self.assertEqual(pool["Q4"]["level"], ["全体", "内部联系", "本质"])
        # 一位评委漏判，剩下两票各一：登记值取"一般"。
        self.assertEqual(pool["Q9"]["importance"], ["一般", "核心"])

    def test_changing_a_map_label_is_disputed_with_the_map_label_first(self):
        # 地图登记 M1 为本质；两位评委写明理由改为全体，达到三分之二，算评委组改动过的地图标注。
        self.assertEqual(self.pool()["Q1"]["level"], ["本质", "全体"])

    def test_a_map_change_without_a_reason_counts_as_the_map_label(self):
        # 地图登记 M2 为全体；一位评委改成本质却没写理由，按默认值计，三票都是全体。
        self.assertEqual(self.pool()["Q11"]["level"], "全体")

    def test_disputed_points_are_listed_in_the_run_record(self):
        self.assertEqual(self.meta["disputed_points"], ["Q1", "Q4", "Q9"])
        results = read_json(os.path.join(self.out, "results-v1.2.json"))
        self.assertEqual(results["resampling"]["disputed_points"], ["Q1", "Q4", "Q9"])

    # 要点判定时隐去出处和报告编号
    def records(self, task_prefix=""):
        return [r for r in read_records(os.path.join(self.out, "calls.jsonl"))
                if r["task"].startswith(task_prefix)]

    def test_point_judging_prompts_name_no_report_and_no_source(self):
        judging = self.records("评审-要点判定")
        self.assertEqual(len(judging), 3)
        sources = {s for group in MERGED for s in group if s not in ("M1", "M2")}
        for record in judging:
            for label in LABELS:
                self.assertNotIn(label, record["prompt"])
            for source in sources:
                self.assertNotIn(source, record["prompt"])
            for text in POINT_TEXT:
                self.assertIn(text, record["prompt"])

    # 工具限定：评审各步只给材料；只有引了网址却没有存档的结论，核验时只读网页
    def test_every_step_is_materials_only_except_checking_unarchived_links(self):
        web = [r for r in self.records() if r["tools"] == "只读网页"]
        self.assertEqual(sorted(r["task"] for r in web),
                         ["评审-断言核验：报告 Charlie，只读网页，评委 %d" % n for n in (1, 2, 3)])
        for record in web:
            self.assertIn(CHARLIE_URL, record["prompt"])
        others = [r for r in self.records() if r["tools"] != "只读网页"]
        self.assertEqual(len(others), 43)
        self.assertTrue(all(r["tools"] == "只给材料" for r in others))

    def test_archived_page_text_is_given_to_the_verifier(self):
        for record in self.records("评审-断言核验：报告 Bravo"):
            self.assertEqual(record["tools"], "只给材料")
            self.assertIn(ARCHIVED_TEXT, record["prompt"])


KIMI_ERROR = ("退出状态 1；标准输出最后几行：Error code: 401 - "
              "The API Key appears to be invalid or may have expired")


GOOGLE_ERROR = "退出状态 1；标准错误最后几行：还没有登录"


class UnavailableVendorTest(unittest.TestCase):
    """厂商不可用：回放材料里录下了 kimi 和 google 各一次失败（kimi 登录过期、agy 没有登录）。
    kimi 的评委位置先换这一步没用到的 google，google 也不可用，再按替代顺序换成 claude。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = cls._tmp.name
        cls.inputs = build_inputs(tmp)
        entries = standard_replay()
        for e in entries:
            if e["vendor"] == "kimi":
                e["vendor"] = "claude"
        entries.insert(0, {"task": "评审-要点判定：评委 3", "vendor": "kimi", "status": "失败",
                           "error": KIMI_ERROR})
        entries.insert(1, {"task": "评审-要点判定：评委 3", "vendor": "google", "status": "失败",
                           "error": GOOGLE_ERROR})
        replay = write_replay(os.path.join(tmp, "replay.jsonl"), entries)
        cls.out = os.path.join(tmp, "review")
        cls.result = run_tool(cls.inputs, cls.out, "--replay", replay)
        cls.meta = read_json(os.path.join(cls.out, "run.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_unavailable_vendors_and_their_reasons_are_recorded(self):
        found = {u["vendor"]: u for u in self.meta["unavailable"]}
        self.assertEqual(sorted(found), ["google", "kimi"])
        self.assertEqual(found["kimi"]["company"], "月之暗面")
        self.assertIn("401", found["kimi"]["error"])
        self.assertIn("还没有登录", found["google"]["error"])

    def test_every_substitution_is_listed(self):
        expected = {("断言核验", "评审-断言核验：报告 %s，评委 3" % unit) for unit in
                    ("Alpha，只给材料", "Bravo，只给材料", "Charlie，只给材料", "Charlie，只读网页")}
        expected.add(("要点判定", "评审-要点判定：评委 3"))
        substitutions = self.meta["substitutions"]
        self.assertEqual({(s["步骤"], s["任务"]) for s in substitutions}, expected)
        self.assertTrue(all(list(s) == ["步骤", "任务", "原来的厂商", "改用的厂商", "原因"] for s in substitutions))
        self.assertTrue(all(s["原来的厂商"] == "kimi" and s["改用的厂商"] == "claude" for s in substitutions))
        for s in substitutions:
            self.assertIn("kimi：", s["原因"])
            if "只读网页" in s["任务"]:  # google 不能用于只读网页一档，没有试它
                self.assertIn("google：Google（agy）不能用于只读网页一档", s["原因"])
            else:
                self.assertIn("google：", s["原因"])

    def test_no_result_is_attributed_to_the_unavailable_vendor(self):
        vendors = {r["vendor"] for r in read_records(os.path.join(self.out, "calls.jsonl"))}
        self.assertEqual(vendors, {"claude", "codex"})
        self.assertEqual(self.meta["steps"]["要点判定"]["by_vendor"], {"claude": 2, "codex": 1})

    def test_the_review_still_finishes_with_the_substitute(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        results = read_json(os.path.join(self.out, "results-v1.2.json"))
        self.assertEqual({r["label"]: (r["rank_best"], r["rank_worst"]) for r in results["reports"]},
                         {"Alpha": (1, 1), "Bravo": (2, 2), "Charlie": (3, 3)})
        self.assertIn("kimi", self.result.stdout)


class WebTierTest(unittest.TestCase):
    """google 不能用于只读网页一档：断言核验里所引网址没有存档的那一组（Charlie），计划给 google 的评委位置
    直接按替代顺序换一家（先挑这一步没配的 kimi），记一条替代，不发调用，google 也不算不可用。
    只估算时同样这样挑，估算的各家次数才与真实运行一致。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.inputs = build_inputs(cls._tmp.name)
        steps = dict(CONFIG["steps"], verify={"vendors": ["claude", "codex", "google"], "times": 1})
        write(cls.inputs["config"], json.dumps(dict(CONFIG, steps=steps), ensure_ascii=False))
        cls.out = os.path.join(cls._tmp.name, "review")
        cls.result = run_tool(cls.inputs, cls.out, "--estimate")
        cls.meta = read_json(os.path.join(cls.out, "run.json"))
        cls.records = read_records(os.path.join(cls.out, "calls.jsonl"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_google_is_never_given_a_web_task(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        web = [r for r in self.records if r["tools"] == "只读网页"]
        self.assertEqual(sorted(r["vendor"] for r in web), ["claude", "codex", "kimi"])
        google = [r for r in self.records if r["vendor"] == "google"]
        self.assertEqual(len(google), 3)
        self.assertTrue(all(r["tools"] == "只给材料" for r in google))

    def test_the_substitution_names_the_tier_and_google_stays_available(self):
        reason = "google：" + "Google（agy）不能用于只读网页一档"
        self.assertEqual(len(self.meta["substitutions"]), 1)
        item = self.meta["substitutions"][0]
        self.assertEqual({k: item[k] for k in ("步骤", "任务", "原来的厂商", "改用的厂商")},
                         {"步骤": "断言核验", "任务": "评审-断言核验：报告 Charlie，只读网页，评委 3",
                          "原来的厂商": "google", "改用的厂商": "kimi"})
        self.assertTrue(item["原因"].startswith(reason), item["原因"])
        self.assertEqual(self.meta["unavailable"], [])

    def test_the_estimate_counts_the_substitute(self):
        self.assertEqual(self.meta["steps"]["断言核验"]["by_vendor"],
                         {"claude": 4, "codex": 4, "google": 3, "kimi": 1})


class EstimateTest(unittest.TestCase):
    """只估算：不调用任何模型，先报出将要发起的调用次数。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.inputs = build_inputs(cls._tmp.name)
        cls.out = os.path.join(cls._tmp.name, "review")
        cls.result = run_tool(cls.inputs, cls.out, "--estimate")
        cls.meta = read_json(os.path.join(cls.out, "run.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_estimate_counts_every_planned_call(self):
        # 手算：结论清单 3；断言核验 Alpha 1 组、Bravo 1 组（网址有存档）、Charlie 2 组（网址没有存档），
        # 共 4 组 × 3 家 = 12；要点抽取 3；合并 1；写到核对 3；要点判定 3；环节评级 3 × 2 = 6；
        # 两两比较 3 对 × 两种先后 × 2 家 = 12；直接回答 3。合计 46。
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        calls = self.meta["calls"]
        self.assertEqual(calls["calls"], 46)
        self.assertEqual(calls["by_vendor"], {"claude": 27, "codex": 14, "kimi": 5})
        self.assertEqual(calls["by_step"], {
            "结论清单": 3, "断言核验": 12, "要点抽取": 3, "要点池合并": 1, "写到核对": 3,
            "要点判定": 3, "环节评级": 6, "两两比较": 12, "直接回答": 3})
        self.assertIn("46", self.result.stdout)

    def test_estimate_writes_no_results(self):
        self.assertEqual(self.meta["mode"], "只估算")
        self.assertFalse(os.path.exists(os.path.join(self.out, "data")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "results-v1.2.json")))
        for record in read_records(os.path.join(self.out, "calls.jsonl")):
            self.assertEqual(record["status"], "未调用")


class RealCallGuardTest(unittest.TestCase):
    """真实调用之前的两道关：必须给调用次数上限；估算超过上限就不开始。两种情况都不启动任何命令行。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.inputs = build_inputs(self._tmp.name)
        self.out = os.path.join(self._tmp.name, "review")

    def tearDown(self):
        self._tmp.cleanup()

    def test_real_calls_need_a_call_limit(self):
        result = run_tool(self.inputs, self.out)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--max-calls", result.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_a_limit_below_the_estimate_refuses_to_start(self):
        result = run_tool(self.inputs, self.out, "--max-calls", "10")
        self.assertEqual(result.returncode, 2)
        self.assertIn("46", result.stderr)
        self.assertFalse(os.path.exists(self.out))


class AnonymizationTest(unittest.TestCase):
    """不加 --keep-labels 时，报告按随机种子编为 A、B、C；原名只出现在 mapping.json 里。"""

    def test_report_names_never_reach_a_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = build_inputs(tmp)
            out = os.path.join(tmp, "review")
            result = run_tool(inputs, out, "--estimate", keep_labels=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            mapping = read_json(os.path.join(out, "mapping.json"))["reports"]
            self.assertEqual(sorted(mapping), ["A", "B", "C"])
            self.assertEqual(sorted(mapping.values()), sorted(NAMES.values()))
            for record in read_records(os.path.join(out, "calls.jsonl")):
                for name in list(NAMES) + list(NAMES.values()):
                    self.assertNotIn(name, record["prompt"])
                    self.assertNotIn(name, record["task"])
            self.assertEqual(sorted(os.listdir(os.path.join(out, "reports"))), ["A.md", "B.md", "C.md"])


class PilotQuestionTest(unittest.TestCase):
    """第五阶段的题目转成的题目目录，和试评的六份报告，能直接交给本程序（只估算，不调用模型）。"""

    def test_pilot_question_and_six_reports_are_estimated_with_the_default_plan(self):
        pilot = os.path.join(ROOT, "research-plan", "stage5-pilot")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "review")
            result = subprocess.run(
                [sys.executable, "-I", TOOL, "--question",
                 os.path.join(ROOT, "simulation", "questions", "第五阶段试评题"),
                 "--reports", *[os.path.join(pilot, "reports", "%s.md" % x) for x in "ABCDEF"],
                 "--keep-labels", "--names", os.path.join(pilot, "mapping.json"),
                 "--estimate", "--out", out],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            meta = read_json(os.path.join(out, "run.json"))
            mapping = read_json(os.path.join(out, "mapping.json"))["reports"]
        self.assertEqual(meta["question"]["map_points"], ["M%d" % n for n in range(1, 9)])
        self.assertEqual(meta["question"]["cutoff"], "2026-03-03")
        self.assertTrue(meta["question"]["checksum_matches"])
        self.assertEqual(mapping["A"], "ChatGPT")
        # 手算，默认配置：结论清单 6；断言核验只有 E 有网址（没给存档）分两组，共 7 组 × 6 位核验员 = 42；
        # 要点抽取 6 × 3 = 18；合并 1；写到核对 6；要点判定 6；环节评级 6 × 6 = 36；
        # 两两比较 15 对 × 两种先后 × 2 位 = 60；直接回答 6。合计 181。
        self.assertEqual(meta["calls"]["calls"], 181)


class GuideTest(unittest.TestCase):
    """使用说明 tools/simulate_review.md：必备章节齐全，每个提示词模板都列出了改写处，本地链接都能打开。"""

    def setUp(self):
        self.path = os.path.join(ROOT, "tools", "simulate_review.md")
        with open(self.path, encoding="utf-8") as f:
            self.guide = f.read()

    def test_required_sections_exist(self):
        for heading in ("## 一条命令", "## 输入", "## 评审各步怎样变成调用", "## 判定怎样合并",
                        "## 配置", "## 厂商不可用时", "## 输出目录", "## 只估算和调用次数上限",
                        "## 回放材料", "## 评委提示词改写了哪些地方", "## 已知的局限", "## 测试"):
            self.assertIn(heading, self.guide)

    def test_every_prompt_template_is_linked_with_its_pilot_starting_point(self):
        import re
        prompts = os.path.join(ROOT, "tools", "review_prompts")
        section = self.guide.split("## 评委提示词改写了哪些地方", 1)[1].split("\n## ", 1)[0]
        for name in sorted(os.listdir(prompts)):
            self.assertIn("(review_prompts/%s)" % name, section, name)
        starting_points = re.findall(r"\]\((\.\./research-plan/stage5-pilot/judges/prompts/[^)]+)\)", section)
        self.assertGreaterEqual(len(set(starting_points)), 5)

    def test_every_local_link_opens(self):
        import re
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", self.guide):
            if target.startswith(("http://", "https://")):
                continue
            self.assertTrue(os.path.exists(os.path.join(os.path.dirname(self.path), target)), target)


if __name__ == "__main__":
    unittest.main()
