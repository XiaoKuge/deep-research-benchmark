"""模拟出题者（tools/simulate_setter.py）的测试。

一律用回放方式：回答是手写的回放材料（调用记录文件，每行只写任务名、厂商和回答），
不真的调用模型。只看对外行为：命令行的输入输出、生成的题目目录和调用记录。
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import simulate_setter  # noqa: E402

HANDBOOK = os.path.join(ROOT, "research-plan", "question-handbook.src.html")
RULES = os.path.join(ROOT, "research-plan", "rules.md")

# 默认的角色分工：出题人 claude，甲 claude，乙 codex，泄露检查 google，闭卷对照 google。
# 写深度地图要读网页，google 不能用于只读网页一档，所以两位出题人是 claude 和 codex。
CARD = {
    "话题": "城市里的萤火虫", "题型": "看似简单型", "选题理由": "人人见过，挖深要靠理解",
    "浅答案": "城市里萤火虫少了，是因为污染。", "挖深会改变结论": True,
    "怎样改变": "主因是光污染和水岸硬化，建议随之改变",
    "提问者": "一位小区物业的绿化主管，想在小区里恢复萤火虫",
    "用途": "决定明年绿化预算花在哪里",
    "问题": "为什么城市里的萤火虫越来越少？",
}
VERSIONS = {
    "提问版": "我是一个小区物业的绿化主管，想在小区里恢复萤火虫，明年的绿化预算要决定花在哪里。"
             "为什么城市里的萤火虫越来越少？只使用截至〔运行当日〕已经公开的信息。",
    "裸题版": "为什么城市里的萤火虫越来越少？",
}


def handbook_template(template_id):
    """出题手册第八节的模板原文。"""
    import html
    with open(HANDBOOK, encoding="utf-8") as f:
        source = f.read()
    return html.unescape(re.search(r'<pre id="%s">(.*?)</pre>' % template_id, source, re.S).group(1))


def rules_appendix_one():
    """规则手册附录一：附在提问版和裸题版之后、一字不改的统一交付要求和说明（新手包的练习题也是这样附的）。"""
    with open(RULES, encoding="utf-8") as f:
        rules = f.read()
    return re.search(r"^### 附录一[^\n]*\n(.*?)(?=^### )", rules, re.S | re.M).group(1).strip("\n")


def template_labels(template):
    """模板每一行要原样保留的开头：去掉行尾括号里的填写提示；整行是提示的跳过（带冒号的整行括号是要填的栏）；
    带冒号的行只保留到第一个冒号；示例行「1 ｜ ｜ ｜ ｜ ｜」另外检查。"""
    labels = []
    for line in template.splitlines():
        line = line.strip()
        if not line or re.match(r"^\d+ ｜", line):
            continue
        if line.startswith("（") and line.endswith("）"):
            if "：" not in line:
                continue
            labels.append(line[:line.index("：") + 1])
            continue
        line = re.sub(r"（[^（）]*）$", "", line).rstrip()
        if "：" in line:
            line = line[:line.index("：") + 1]
        labels.append(line)
    return labels


def point(text, level="全体", importance="核心", url="https://example.org/a", confidence="高"):
    return {"要点": text, "层级": level, "重要性": importance, "依据": [url], "把握": confidence}


def depth_map(who, core_count, general=()):
    """一位出题人的深度地图回答：core_count 条核心要点（文字带上出题人的记号），外加一般要点。"""
    levels = ["现象", "全体", "内部联系", "本质"]
    points = [point("%s的核心要点%d号" % (who, i + 1), level=levels[i % 4]) for i in range(core_count)]
    points += [point(text, importance="一般") for text in general]
    for number, row in enumerate(points, 1):
        row["编号"] = number
    return {"浅答案": "%s写的浅答案" % who, "转折点": "%s写的转折点" % who,
            "转折点用到的要点": [3, 4], "要点": points, "找不到要点的层": ""}


def merged(pairs, rows):
    """两人对照的回答：pairs 是 [["甲1", "乙1"], ……]，rows 是合并后的要点表。"""
    for number, row in enumerate(rows, 1):
        row["编号"] = number
    return {"都列到的": pairs, "浅答案": "合并后的浅答案", "转折点": "合并后的转折点：口径一变，建议就变",
            "转折点用到的要点": [2, 3], "要点": rows, "找不到要点的层": ""}


def merged_rows(count):
    levels = ["现象", "内部联系", "本质", "全体"]
    return [point("合并后的核心要点%d号" % (i + 1), level=levels[i % 4]) for i in range(count)]


LEAK_OK = {"暗示往哪里挖": {"有没有": "没有", "说明": "只问原因"},
           "给出中间答案": {"有没有": "没有", "说明": "没有"},
           "点名来源或方法": {"有没有": "没有", "说明": "没有"}}


def material(rounds=None, overrides=None, extra=()):
    """手写的回放材料：默认一轮就写全（甲 4 条、乙 4 条、都列到 4 条）。

    rounds：每一轮的 (甲的地图, 乙的地图, 两人对照)；overrides：{任务名: (厂商, 回答)}。
    """
    if rounds is None:
        pairs = [["甲%d" % i, "乙%d" % i] for i in range(1, 5)]
        rounds = [(depth_map("甲", 4), depth_map("乙", 4), merged(pairs, merged_rows(4)))]
    entries = [
        ("出题-评委版", "claude", CARD),
        ("出题-提问版和裸题版", "claude", VERSIONS),
    ]
    for number, (map_a, map_b, comparison) in enumerate(rounds, 1):
        entries += [
            ("出题-深度地图-甲-第%d轮" % number, "claude", map_a),
            ("出题-深度地图-乙-第%d轮" % number, "codex", map_b),
            ("出题-两人对照-第%d轮" % number, "claude", comparison),
        ]
    entries += [
        ("出题-泄露检查", "google", LEAK_OK),
        ("出题-闭卷对照-作答", "google", "闭卷的回答：萤火虫少了是因为农药。"),
        ("出题-闭卷对照-比对", "claude", {"答到的核心要点": [{"编号": 1, "理由": "提到了"}],
                                     "建议": "改题", "说明": "只答到一条"}),
    ]
    overrides = overrides or {}
    lines = []
    for task, vendor, answer in entries:
        if task in overrides:
            vendor, answer = overrides[task]
        if not isinstance(answer, str):
            answer = json.dumps(answer, ensure_ascii=False)
        lines.append({"task": task, "vendor": vendor, "answer": answer})
    lines.extend(extra)
    return lines


class SetterCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.out = os.path.join(self.tmp, "questions")

    def tearDown(self):
        self._tmp.cleanup()

    def write_material(self, lines, name="回放材料.jsonl"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return path

    def run_setter(self, *args, lines=None):
        """在本进程里运行命令行，返回 (退出状态, 打印的文字)。"""
        argv = ["--topic", "城市里的萤火虫", "--asker", "小区物业的绿化主管", "--kind", "练习题",
                "--id", "萤火虫", "--out", self.out]
        if lines is not False:
            argv += ["--replay", self.write_material(material() if lines is None else lines)]
        argv += list(args)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            try:
                code = simulate_setter.main(argv)
            except SystemExit as stop:
                code = stop.code
        return code, printed.getvalue()

    def folder(self, name="萤火虫"):
        return os.path.join(self.out, name)

    def read(self, name, folder=None):
        with open(os.path.join(folder or self.folder(), name), encoding="utf-8") as f:
            return f.read()

    def metadata(self):
        return json.loads(self.read("元数据.json"))

    def calls(self):
        with open(os.path.join(self.folder(), "调用记录.jsonl"), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def call(self, task):
        found = [record for record in self.calls() if record["task"] == task]
        self.assertEqual(len(found), 1, "任务「%s」应当正好调用一次" % task)
        return found[0]


class QuestionFolderTest(SetterCase):
    def test_a_topic_where_digging_does_not_change_the_conclusion_stops_at_step_two(self):
        flat = dict(CARD, 挖深会改变结论=False, 怎样改变="怎么查答案都一样")
        code, printed = self.run_setter(lines=material(overrides={"出题-评委版": ("claude", flat)}))
        self.assertEqual(code, 1)
        self.assertIn("第 2 步不通过", printed)
        meta = self.metadata()
        self.assertEqual(meta["状态"], "中途停止")
        self.assertIn("换题", meta["停止的原因"])
        self.assertFalse(os.path.exists(os.path.join(self.folder(), "深度地图.txt")))
        self.assertEqual([r["task"] for r in self.calls()], ["出题-评委版"])

    def test_one_command_writes_the_complete_question_folder(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        for name in ("题目卡.txt", "提问版.txt", "裸题版.txt", "深度地图.txt", "深度地图.json",
                     "深度地图校验值.txt", "两人对照记录.md", "泄露检查记录.md", "闭卷对照记录.md",
                     "元数据.json", "调用记录.jsonl"):
            self.assertTrue(os.path.isfile(os.path.join(self.folder(), name)), name)
        meta = self.metadata()
        self.assertEqual(meta["题目标识"], "萤火虫")
        self.assertEqual(meta["类别"], "练习题")
        self.assertRegex(meta["生成时间"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
        self.assertEqual(meta["方式"], "回放")
        used = {role: info["用到的厂商"] for role, info in meta["角色"].items()}
        self.assertEqual(used, {"出题人": ["claude"], "甲": ["claude"], "乙": ["codex"],
                                "泄露检查人": ["google"], "闭卷对照": ["google"]})
        self.assertEqual({role: info["配置的厂商"] for role, info in meta["角色"].items()},
                         {"出题人": "claude", "甲": "claude", "乙": "codex", "泄露检查人": "google",
                          "闭卷对照": "google"})
        records = self.calls()
        self.assertEqual(len(records), 8)
        self.assertTrue(all(record["mode"] == "回放" for record in records))


class TemplateFormatTest(SetterCase):
    def assertFollowsTemplate(self, text, template_id):
        lines = [line.strip() for line in text.splitlines()]
        position = 0
        for label in template_labels(handbook_template(template_id)):
            while position < len(lines) and not lines[position].startswith(label):
                position += 1
            self.assertLess(position, len(lines), "缺少模板里的这一行，或者顺序不对：%s" % label)
            position += 1

    def test_card_has_the_three_versions_in_template_order_with_the_fixed_text_unchanged(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        card = self.read("题目卡.txt")
        self.assertFollowsTemplate(card, "tpl-card")
        self.assertIn("【提问者】" + CARD["提问者"], card)
        self.assertIn(VERSIONS["提问版"], card)
        fixed = handbook_template("tpl-card")
        fixed = fixed[fixed.index("【交付要求】"):]
        self.assertTrue(card.rstrip("\n").endswith(fixed.rstrip("\n")))
        # 交给智能体的两个文件：版本的文字，空一行，再接规则手册附录一的交付要求和说明，一字不改
        appendix = rules_appendix_one()
        self.assertEqual(self.read("提问版.txt"), VERSIONS["提问版"] + "\n\n" + appendix + "\n")
        self.assertEqual(self.read("裸题版.txt"), VERSIONS["裸题版"] + "\n\n" + appendix + "\n")

    def test_depth_map_has_the_six_template_sections_and_a_matching_checksum(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        text = self.read("深度地图.txt")
        self.assertFollowsTemplate(text, "tpl-map")
        rows = [line for line in text.splitlines() if re.match(r"^\d+ ｜", line)]
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row.count("｜"), 5, row)
        self.assertIn("1 ｜ 合并后的核心要点1号 ｜ 现象 ｜ 核心 ｜ https://example.org/a ｜ 高", rows)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(self.read("深度地图校验值.txt"), "%s  深度地图.txt\n" % digest)
        self.assertEqual(self.metadata()["深度地图校验值"]["值"], digest)


class FishEstimateTest(SetterCase):
    """期望值取自出题手册第三节第 4 步「数鱼的办法」的表：4、5、4 写全了；4、4、2 估计 8 条、合并后 6 条，继续查。"""

    def fish_lines(self):
        text = self.read("深度地图.txt")
        section = text[text.index("四、两人对照记录"):text.index("五、泄露检查记录")]
        return [line.strip() for line in section.splitlines() if line.strip()]

    def test_four_five_four_is_complete_in_one_round(self):
        pairs = [["甲%d" % i, "乙%d" % i] for i in range(1, 5)]
        rounds = [(depth_map("甲", 4), depth_map("乙", 5), merged(pairs, merged_rows(5)))]
        code, printed = self.run_setter(lines=material(rounds=rounds))
        self.assertEqual(code, 0, printed)
        lines = self.fish_lines()
        self.assertIn("两人都列到的：4 条", lines)
        self.assertIn("估计总数 = 甲的条数 × 乙的条数 ÷ 都列到的条数 = 4 × 5 ÷ 4 = 5", lines)
        self.assertIn("合并后的条数 = 甲 + 乙 − 都列到的 = 4 + 5 − 4 = 5", lines)
        self.assertIn("结论：写全了", lines)
        self.assertTrue(any(line.startswith("甲：") and line.endswith("列出核心要点 4 条") for line in lines))
        self.assertTrue(any(line.startswith("乙：") and line.endswith("列出核心要点 5 条") for line in lines))
        self.assertTrue(self.metadata()["检查结果"]["写完标准"]["核心要点写全"])
        self.assertFalse([r for r in self.calls() if r["task"].endswith("第2轮")])

    def test_four_four_two_searches_again_on_the_one_sided_points(self):
        first = (depth_map("甲", 4), depth_map("乙", 4),
                 merged([["甲1", "乙1"], ["甲2", "乙2"]], merged_rows(6)))
        second = (depth_map("甲", 4), depth_map("乙", 4),
                  merged([["甲%d" % i, "乙%d" % i] for i in range(1, 5)], merged_rows(4)))
        code, printed = self.run_setter(lines=material(rounds=[first, second]))
        self.assertEqual(code, 0, printed)
        pair_record = self.read("两人对照记录.md")
        self.assertIn("估计总数 = 甲的条数 × 乙的条数 ÷ 都列到的条数 = 4 × 4 ÷ 2 = 8", pair_record)
        self.assertIn("合并后的条数 = 甲 + 乙 − 都列到的 = 4 + 4 − 2 = 6", pair_record)
        self.assertIn("还差约 2 条", pair_record)
        self.assertIn("结论：写全了", self.fish_lines())
        # 第二轮：每人都拿到只有一人列到的方向（甲3、甲4、乙3、乙4）
        for who in ("甲", "乙"):
            prompt = self.call("出题-深度地图-%s-第2轮" % who)["prompt"]
            for text in ("甲的核心要点3号", "甲的核心要点4号", "乙的核心要点3号", "乙的核心要点4号"):
                self.assertIn(text, prompt)

    def test_no_overlap_cannot_be_estimated_and_stops_at_the_round_limit(self):
        rounds = [(depth_map("甲", 3), depth_map("乙", 3),
                   merged([["甲1", "乙9"], ["甲2", "甲3"]], merged_rows(6)))]
        code, printed = self.run_setter("--max-extra-rounds", "0", lines=material(rounds=rounds))
        self.assertEqual(code, 0, printed)
        lines = self.fish_lines()
        self.assertIn("两人都列到的：0 条", lines)
        self.assertTrue(any("3 × 3 ÷ 0，无法估计" in line for line in lines), lines)
        self.assertIn("合并后的条数 = 甲 + 乙 − 都列到的 = 3 + 3 − 0 = 6", lines)
        self.assertTrue(any(line.startswith("结论：继续查") for line in lines))
        self.assertFalse(self.metadata()["检查结果"]["写完标准"]["核心要点写全"])
        self.assertIn("乙9 不是乙的核心要点", self.read("两人对照记录.md"))


class CompletionStandardTest(SetterCase):
    """深度地图写完标准里的两条按事实记：四层都查过，要看要点表里每一层有没有要点，没有的层是否写明
    查过、没有（不只是提到层的名字）；两人对过，要看每一轮两张地图是否真的都写出了要点、并做了对照。"""

    def standard(self, rows, note, map_b=None, *options):
        pairs = [["甲%d" % i, "乙%d" % i] for i in range(1, 5)]
        comparison = merged(pairs, rows)
        comparison["找不到要点的层"] = note
        rounds = [(depth_map("甲", 4), map_b if map_b is not None else depth_map("乙", 4), comparison)]
        code, printed = self.run_setter(*options, lines=material(rounds=rounds))
        self.assertEqual(code, 0, printed)
        return self.metadata()["检查结果"]

    def three_levels(self):
        return [point("合并后的核心要点%d号" % n, level=level) for n, level in
                enumerate(("现象", "内部联系", "本质", "现象"), 1)]

    def test_naming_every_level_without_saying_it_was_checked_is_not_enough(self):
        checks = self.standard(self.three_levels(), "现象、全体、内部联系、本质四层都查过")
        self.assertEqual(checks["四层里没有要点的层"], ["全体"])
        self.assertFalse(checks["写完标准"]["四层都查过"])

    def test_a_level_without_points_counts_when_the_note_says_it_was_checked_and_nothing_found(self):
        checks = self.standard(self.three_levels(), "全体层查了市政绿化年报和两篇综述，没有找到要点。")
        self.assertTrue(checks["写完标准"]["四层都查过"])

    def test_four_levels_with_points_need_no_note(self):
        self.assertTrue(self.standard(merged_rows(4), "")["写完标准"]["四层都查过"])

    def test_two_maps_with_points_that_were_compared_count_as_compared(self):
        self.assertTrue(self.standard(merged_rows(4), "")["写完标准"]["两人对过"])

    def test_a_map_without_points_does_not_count_as_compared(self):
        empty = {"浅答案": "乙写的浅答案", "转折点": "", "转折点用到的要点": [], "要点": [], "找不到要点的层": ""}
        checks = self.standard(merged_rows(4), "", empty, "--max-extra-rounds", "0")
        self.assertFalse(checks["写完标准"]["两人对过"])
        self.assertFalse(checks["全部通过"])


# 深度地图和出题人调研笔记里的文字：交给泄露检查人的提示词里一个也不能有
MAP_MARKERS = ("甲的核心要点", "乙的核心要点", "甲写的浅答案", "乙写的浅答案", "甲写的转折点", "乙写的转折点",
               "合并后的核心要点", "合并后的浅答案", "合并后的转折点", "https://example.org/a",
               CARD["浅答案"], CARD["怎样改变"])


class IndependenceTest(SetterCase):
    def test_leak_check_prompt_has_the_two_versions_and_nothing_from_the_depth_map(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        record = self.call("出题-泄露检查")
        self.assertEqual(record["tools"], "只给材料")
        self.assertNotEqual(record["vendor"], self.call("出题-评委版")["vendor"])
        self.assertIn(self.read("提问版.txt"), record["prompt"])
        self.assertIn(self.read("裸题版.txt"), record["prompt"])
        for marker in MAP_MARKERS:
            self.assertNotIn(marker, record["prompt"])
        self.assertIn("没有发现泄露", self.read("深度地图.txt"))

    def test_the_two_setters_write_their_first_maps_without_seeing_each_other(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        first_a = self.call("出题-深度地图-甲-第1轮")
        first_b = self.call("出题-深度地图-乙-第1轮")
        self.assertEqual((first_a["tools"], first_b["tools"]), ("只读网页", "只读网页"))
        self.assertNotEqual(first_a["vendor"], first_b["vendor"])
        for marker in ("乙的核心要点", "乙写的浅答案", "乙写的转折点"):
            self.assertNotIn(marker, first_a["prompt"])
        for marker in ("甲的核心要点", "甲写的浅答案", "甲写的转折点"):
            self.assertNotIn(marker, first_b["prompt"])


class ClosedBookTest(SetterCase):
    def test_closed_book_uses_a_vendor_that_wrote_no_map_and_gets_only_the_question(self):
        code, printed = self.run_setter()
        self.assertEqual(code, 0, printed)
        record = self.call("出题-闭卷对照-作答")
        map_vendors = {r["vendor"] for r in self.calls() if r["task"].startswith("出题-深度地图-")}
        self.assertEqual(map_vendors, {"claude", "codex"})
        self.assertNotIn(record["vendor"], map_vendors)
        self.assertEqual(record["tools"], "只给材料")
        self.assertEqual(record["prompt"], self.read("提问版.txt"))
        closed = self.read("闭卷对照记录.md")
        self.assertIn("闭卷的回答：萤火虫少了是因为农药。", closed)
        self.assertIn("共 4 条核心要点，答到 1 条", self.read("深度地图.txt"))
        self.assertEqual(self.metadata()["检查结果"]["闭卷对照"], "保留")

    def test_answering_most_core_points_without_the_web_means_the_question_is_not_kept(self):
        reached = {"答到的核心要点": [{"编号": n, "理由": "答到了"} for n in (1, 2, 3)],
                   "建议": "换题", "说明": "不联网就答到了三条"}
        code, printed = self.run_setter(lines=material(overrides={"出题-闭卷对照-比对": ("claude", reached)}))
        self.assertEqual(code, 0, printed)
        self.assertIn("结论：换题", self.read("深度地图.txt"))
        self.assertEqual(self.metadata()["检查结果"]["闭卷对照"], "换题")
        self.assertFalse(self.metadata()["检查结果"]["全部通过"])

    def test_configuring_the_closed_book_with_a_map_writer_vendor_is_refused(self):
        code, printed = self.run_setter("--closed-book", "codex")
        self.assertEqual(code, 2)
        self.assertIn("闭卷对照要换一家与写深度地图不同的厂商", printed)
        self.assertFalse(os.path.exists(self.folder()))


KIMI_401 = "退出状态 1；标准输出最后几行：Error code: 401 - The API Key appears to be invalid or may have expired"
AGY_LOGIN = "退出状态 1；标准错误最后几行：agy 还没有登录"
CODEX_LIMIT = "退出状态 1；标准错误最后几行：额度用完，请稍后再试"


def failed(task, vendor, error=KIMI_401):
    """回放材料里录下的一次失败调用：回放时当作这一家在这一步不可用。"""
    return {"task": task, "vendor": vendor, "status": "失败", "error": error, "answer": ""}


class UnavailableVendorTest(SetterCase):
    def test_an_unavailable_map_writer_is_replaced_and_the_replacement_is_recorded(self):
        # 乙配置成 kimi（登录过期），替代顺序里的 codex 也失败；google 不能用于只读网页一档，排在最后，
        # 闭卷对照的 google 也要留着，于是换成 claude，和甲同一家
        lines = material(overrides={"出题-深度地图-乙-第1轮": ("claude", depth_map("乙", 4))},
                         extra=[failed("出题-深度地图-乙-第1轮", "kimi"),
                                failed("出题-深度地图-乙-第1轮", "codex", CODEX_LIMIT)])
        code, printed = self.run_setter("--map-b", "kimi", lines=lines)
        self.assertEqual(code, 0, printed)
        meta = self.metadata()
        b = meta["角色"]["乙"]
        self.assertEqual(b["配置的厂商"], "kimi")
        self.assertEqual(b["用到的厂商"], ["claude"])
        self.assertEqual(len(b["替代"]), 1)
        self.assertEqual(list(b["替代"][0]), ["步骤", "任务", "原来的厂商", "改用的厂商", "原因"])
        self.assertEqual(b["替代"][0]["改用的厂商"], "claude")
        self.assertEqual(b["替代"][0]["原来的厂商"], "kimi")
        self.assertEqual(b["替代"][0]["任务"], "出题-深度地图-乙-第1轮")
        self.assertEqual(b["替代"][0]["步骤"], "深度地图")
        self.assertIn("401", b["替代"][0]["原因"])
        self.assertIn("额度用完", b["替代"][0]["原因"])
        self.assertEqual([item["厂商"] for item in meta["厂商不可用"]], ["kimi", "codex"])
        self.assertTrue(any("两位出题人用了同一家" in note for note in meta["说明"]))
        self.assertEqual(meta["角色"]["闭卷对照"]["用到的厂商"], ["google"])
        self.assertFalse([r for r in self.calls() if r["vendor"] in ("kimi", "codex")])
        self.assertIn("乙：claude（Anthropic）（配置的是 kimi", self.read("深度地图.txt"))
        self.assertIn("改用 claude", printed)

    def test_closed_book_is_recorded_as_not_done_when_only_map_writers_are_left(self):
        lines = material(overrides={"出题-深度地图-乙-第1轮": ("codex", depth_map("乙", 4)),
                                    "出题-闭卷对照-作答": ("codex", "写过地图的厂商不会被问到")},
                         extra=[failed("出题-闭卷对照-作答", "kimi"),
                                failed("出题-闭卷对照-作答", "google", AGY_LOGIN)])
        code, printed = self.run_setter("--map-b", "codex", "--closed-book", "kimi", lines=lines)
        self.assertEqual(code, 0, printed)
        self.assertFalse([r for r in self.calls() if r["task"].startswith("出题-闭卷对照")])
        meta = self.metadata()
        self.assertEqual(meta["检查结果"]["闭卷对照"], "未做")
        self.assertFalse(meta["检查结果"]["全部通过"])
        self.assertEqual(meta["角色"]["闭卷对照"]["用到的厂商"], [])
        closed = self.read("闭卷对照记录.md")
        self.assertIn("结论：未做", closed)
        self.assertIn("401", closed)
        self.assertIn("agy 还没有登录", closed)
        self.assertIn("写过本题的深度地图", closed)
        self.assertIn("结论：未做", self.read("深度地图.txt"))


class WebTierTest(SetterCase):
    """google 不能用于只读网页一档：写深度地图要读网页，配置给 google 的乙直接换一家，记一条替代，
    原因写明不能用于只读网页一档；不发调用，google 也不算不可用，只给材料的步骤照常用它。"""

    def test_a_map_writer_configured_as_google_is_replaced_without_a_call(self):
        lines = material(overrides={"出题-深度地图-乙-第1轮": ("codex", depth_map("乙", 4)),
                                    "出题-泄露检查": ("google", LEAK_OK),
                                    "出题-闭卷对照-作答": ("kimi", "闭卷的回答：萤火虫少了是因为农药。")})
        code, printed = self.run_setter("--map-b", "google", "--leak-checker", "google",
                                        "--closed-book", "kimi", lines=lines)
        self.assertEqual(code, 0, printed)
        meta = self.metadata()
        b = meta["角色"]["乙"]
        self.assertEqual(b["用到的厂商"], ["codex"])  # 不换成 claude：甲已经是 claude；也不占闭卷对照的 kimi
        self.assertEqual(len(b["替代"]), 1)
        item = b["替代"][0]
        self.assertEqual((item["步骤"], item["任务"], item["原来的厂商"], item["改用的厂商"]),
                         ("深度地图", "出题-深度地图-乙-第1轮", "google", "codex"))
        self.assertIn("google：Google（agy）不能用于只读网页一档", item["原因"])
        self.assertEqual(meta["厂商不可用"], [])
        self.assertEqual(meta["角色"]["泄露检查人"]["用到的厂商"], ["google"])
        self.assertFalse([r for r in self.calls() if r["vendor"] == "google" and r["tools"] == "只读网页"])

    def test_the_estimate_picks_the_same_substitute(self):
        code, printed = self.run_setter("--map-b", "google", "--leak-checker", "google",
                                        "--closed-book", "kimi", "--estimate", lines=False)
        self.assertEqual(code, 0, printed)
        # 乙的三轮地图都换成 codex；google 只做泄露检查；kimi 做闭卷作答
        for count in ("claude 9 次", "codex 3 次", "google 1 次", "kimi 1 次"):
            self.assertIn(count, printed)


class EstimateTest(SetterCase):
    def test_estimate_reports_the_call_count_without_calling_or_writing_anything(self):
        # 评委版 1 + 两个版本 1 + 三轮（甲、乙、对照）×3 + 泄露检查 1 + 闭卷作答 1 + 闭卷比对 1 = 14
        code, printed = self.run_setter("--estimate", "--max-calls", "10", lines=False)
        self.assertEqual(code, 0, printed)
        self.assertIn("最多 14 次", printed)
        self.assertIn("第一轮就写全时 8 次", printed)
        for count in ("claude 9 次", "codex 3 次", "google 2 次"):
            self.assertIn(count, printed)
        self.assertIn("会超过上限", printed)
        self.assertFalse(os.path.exists(self.out))

    def test_a_live_run_without_a_call_limit_is_refused_before_anything_starts(self):
        code, printed = self.run_setter(lines=False)
        self.assertEqual(code, 2)
        self.assertIn("--max-calls", printed)
        self.assertFalse(os.path.exists(self.out))


class GuideTest(unittest.TestCase):
    """使用说明 tools/simulate_setter.md：必备章节齐全，每个选项和输出文件都有解释，本地链接都能打开。"""

    PATH = os.path.join(ROOT, "tools", "simulate_setter.md")

    def setUp(self):
        with open(self.PATH, encoding="utf-8") as f:
            self.text = f.read()

    def test_required_sections_exist(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        for heading in ("一条命令", "出题七步怎样变成调用", "数鱼的办法怎样算", "角色和厂商", "输出目录",
                        "只估算", "回放", "测试"):
            self.assertIn(heading, headings)

    def test_every_option_and_output_file_is_explained(self):
        for option in ("--topic", "--asker", "--domain", "--question-type", "--kind", "--id", "--out",
                       "--setter", "--map-a", "--map-b", "--leak-checker", "--closed-book", "--model",
                       "--max-extra-rounds", "--estimate", "--replay", "--max-calls", "--timeout-seconds"):
            self.assertIn("`%s" % option, self.text)
        for name in ("题目卡.txt", "提问版.txt", "裸题版.txt", "深度地图.txt", "深度地图校验值.txt",
                     "深度地图.json", "两人对照记录.md", "泄露检查记录.md", "闭卷对照记录.md",
                     "元数据.json", "调用记录.jsonl"):
            self.assertIn(name, self.text)

    def test_local_links_open(self):
        prose = re.sub(r"```.*?```", "", self.text, flags=re.S)
        prose = re.sub(r"`[^`]*`", "", prose)
        targets = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", prose)
        self.assertTrue(targets)
        for target in targets:
            if not re.match(r"https?://", target):
                path = os.path.normpath(os.path.join(os.path.dirname(self.PATH), target))
                self.assertTrue(os.path.exists(path), target)


if __name__ == "__main__":
    unittest.main()
