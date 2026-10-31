"""计分程序（research-plan/stage5-pilot/score.py）的验收测试。

只通过命令行和它写出的结果文件观察行为。期望值来自独立来源：
已提交的试评结果文件、第五阶段报告的验收表、"一道题走完全程"页面上手算并经程序复核过的示意名次。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.path.join(ROOT, "research-plan", "stage5-pilot")
SCORER = os.path.join(PILOT, "score.py")
PILOT_MAPPING = os.path.join(PILOT, "mapping.json")


def run_scorer(version, mapping=PILOT_MAPPING, data=None):
    """运行计分程序，结果写到临时文件，返回读出的结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        output = os.path.join(tmp, "result.json")
        cmd = [sys.executable, "-I", SCORER, mapping, version, "--output", output]
        if data:
            cmd += ["--data", data]
        subprocess.run(cmd, cwd=PILOT, check=True, capture_output=True)
        with open(output, encoding="utf-8") as f:
            return json.load(f)


def committed(version):
    with open(os.path.join(PILOT, f"results-v{version}.json"), encoding="utf-8") as f:
        return json.load(f)


def intervals(result):
    return {r: v["interval"] for r, v in result["main"].items()}


class PilotDataTest(unittest.TestCase):
    """第五阶段试评数据。"""

    @classmethod
    def setUpClass(cls):
        cls.results = {}

    def result(self, version):
        if version not in self.results:
            self.results[version] = run_scorer(version)
        return self.results[version]

    def test_version_1_1_reproduces_committed_rank_intervals(self):
        self.assertEqual(intervals(self.result("1.1")), intervals(committed("1.1")))

    def test_versions_1_0_and_1_1_reproduce_committed_result_files_in_full(self):
        for version in ("1.0", "1.1"):
            with self.subTest(version=version):
                self.assertEqual(self.result(version), committed(version))

    def test_acceptance_outcomes_match_stage_five_report(self):
        # 第五阶段报告第一节的表（第一版）：1、2、4、6 通过，3、5、7、8 没有通过
        expected = {"1": True, "2": True, "3": False, "4": True,
                    "5": False, "6": True, "7": False, "8": False}
        acc = self.result("1.0")["acceptance"]
        actual = {}
        for key, value in acc.items():
            number = key.split(" ")[0]
            if number in expected:
                actual[number] = value if isinstance(value, bool) else value["通过"]
        self.assertEqual(actual, expected)

    def test_version_1_2_gives_the_same_rank_intervals_as_version_1_1(self):
        # 试评数据没有有争议的标注；没有报告写到的要点（Q4、Q6，以及只有扰动版本写到的 Q122）不影响名次
        self.assertEqual(intervals(self.result("1.2")), intervals(committed("1.1")))

    def test_committed_version_1_2_result_file_matches_a_fresh_run(self):
        self.assertEqual(committed("1.2"), self.result("1.2"))


ELEMENTS = ["①", "③", "④", "⑤", "⑦"]


def write_question(folder, points, grades, timeliness=None, pairwise=()):
    """把一道示意题写成计分程序读的文件：映射表、要点池、环节评级、断言核验、直接回答、两两比较。

    points：要点列表，每条有 pid、level、importance、reach（报告 → 符合或相反）。
    grades：报告 → 五个环节（①③④⑤⑦）的档位。没有硬伤，没有来源不支持的结论。
    timeliness：报告 → 时效的档位，不给的都记为 1。
    pairwise：两两比较的各次判定，每次一项 (排在前面的报告, 排在后面的报告, 判定)，判定是 first、second 或 tie。
    返回 (映射表路径, 数据目录)。
    """
    data = os.path.join(folder, "data")
    os.makedirs(data)
    reports = list(grades)

    def dump(path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    mapping = os.path.join(folder, "mapping.json")
    dump(mapping, {"reports": {r: f"示意{r}" for r in reports}})
    dump(os.path.join(data, "pool.json"), {"points": [
        dict(correct="正确", relevant=True, content=p["pid"], **p) for p in points]})
    dump(os.path.join(data, "rating-example.json"), {"reports": {r: {
        "ratings": {**{e: {"score": g} for e, g in zip(ELEMENTS, grades[r])}, "写作": {"score": 1}},
        "off_topic": {"value": False}} for r in reports}})
    dump(os.path.join(data, "verify-example.json"), {"reports": {r: {
        "claims": [{"id": f"{r}-c1", "core": True, "source_label": "支持", "correct": "正确"}],
        "timeliness": {"score": (timeliness or {}).get(r, 1)}, "traceable_sources": True} for r in reports}})
    dump(os.path.join(data, "direct-answers.json"), {r: {"ids": [f"{r}-c1"]} for r in reports})
    if pairwise:
        dump(os.path.join(data, "pairwise-example.json"), {"pairs": [
            {"first": a, "second": b, "verdict": v} for a, b, v in pairwise]})
    return mapping, data


class ContestedLabelTest(unittest.TestCase):
    """有争议的标注按对领先一方最不利的方式计分，只能让一对报告并列，不能把它们拉开。"""

    # 两份报告都写到 L1；一号另外写到 L4、L5、L6。环节评级互有长短，所以分不开时环节评级也排不出先后。
    GRADES = {"一号": (2, 0, 1, 1, 2), "二号": (2, 2, 1, 2, 1)}

    def points(self, l4, l5, l6):
        return [
            {"pid": "L1", "level": "现象", "importance": "核心", "reach": {"一号": "符合", "二号": "符合"}},
            {"pid": "L4", "level": l4, "importance": "核心", "reach": {"一号": "符合"}},
            {"pid": "L5", "level": l5, "importance": "一般", "reach": {"一号": "符合"}},
            {"pid": "L6", "level": l6, "importance": "核心", "reach": {"一号": "符合"}},
        ]

    def score(self, points):
        with tempfile.TemporaryDirectory() as tmp:
            mapping, data = write_question(tmp, points, self.GRADES)
            return intervals(run_scorer("1.2", mapping, data))

    def test_disputed_levels_turn_a_separated_pair_into_a_tie(self):
        registered = self.score(self.points("本质", "内部联系", "本质"))
        self.assertEqual(registered, {"一号": [1, 1], "二号": [2, 2]})
        # 三条要点的层级评委组意见不一：登记的层级，还是现象。按对一号最不利的方式都算现象，
        # 在第一种权重下一号与二号的净分都是 0，不再领先，两份并列。
        disputed = self.score(self.points(["本质", "现象"], ["内部联系", "现象"], ["本质", "现象"]))
        self.assertEqual(disputed, {"一号": [1, 2], "二号": [1, 2]})


class PairwiseVetoTest(unittest.TestCase):
    """规则第八节第 4 条：两两比较只用来否决。四次中至少三次与前面的结果相反，这一对才改为并列；
    比较次数不是四次时，相反的次数至少占四分之三，向上取整（两次就要两次都相反）。"""

    # 一号比二号多写到三条深的核心要点，深度净分分开：一号第 1 名，二号第 2 名
    GRADES = {"一号": (2, 0, 1, 1, 2), "二号": (2, 2, 1, 2, 1)}
    POINTS = [
        {"pid": "L1", "level": "现象", "importance": "核心", "reach": {"一号": "符合", "二号": "符合"}},
        {"pid": "L4", "level": "本质", "importance": "核心", "reach": {"一号": "符合"}},
        {"pid": "L5", "level": "内部联系", "importance": "一般", "reach": {"一号": "符合"}},
        {"pid": "L6", "level": "本质", "importance": "核心", "reach": {"一号": "符合"}},
    ]
    SEPARATED = {"一号": [1, 1], "二号": [2, 2]}
    TIED = {"一号": [1, 2], "二号": [1, 2]}

    def score(self, pairwise, version="1.2"):
        with tempfile.TemporaryDirectory() as tmp:
            mapping, data = write_question(tmp, self.POINTS, self.GRADES, pairwise=pairwise)
            return intervals(run_scorer(version, mapping, data))

    # 每次判定写成 (排在前面的报告, 排在后面的报告, 判定)；"二号更好"就是与前面的结果相反
    FOUR_WITH_THREE_AGAINST = [("一号", "二号", "second"), ("二号", "一号", "first"),
                               ("一号", "二号", "second"), ("二号", "一号", "second")]
    FOUR_WITH_TWO_AGAINST = [("一号", "二号", "second"), ("二号", "一号", "first"),
                             ("一号", "二号", "first"), ("二号", "一号", "second")]

    def test_three_of_four_against_turns_the_pair_into_a_tie(self):
        self.assertEqual(self.score(self.FOUR_WITH_THREE_AGAINST), self.TIED)

    def test_two_of_four_against_keeps_the_pair_apart(self):
        self.assertEqual(self.score(self.FOUR_WITH_TWO_AGAINST), self.SEPARATED)

    def test_with_two_comparisons_both_must_be_against(self):
        both = [("一号", "二号", "second"), ("二号", "一号", "first")]
        self.assertEqual(self.score(both), self.TIED)
        one_and_a_draw = [("一号", "二号", "second"), ("二号", "一号", "tie")]
        self.assertEqual(self.score(one_and_a_draw), self.SEPARATED)

    def test_versions_1_0_and_1_1_still_need_every_comparison_against(self):
        for version in ("1.0", "1.1"):
            with self.subTest(version=version):
                self.assertEqual(self.score(self.FOUR_WITH_THREE_AGAINST, version), self.SEPARATED)


WALK = os.path.join(ROOT, "tests", "fixtures", "scorer-walkthrough")
WALK_MAPPING = os.path.join(WALK, "mapping.json")
WALK_DATA = os.path.join(WALK, "data")


class WalkthroughTest(unittest.TestCase):
    """"一道题走完全程"的五份示意报告。

    夹具 tests/fixtures/scorer-walkthrough/ 是把 site/walkthrough_example.py 里的数据（要点池、谁写到哪条、
    来源不支持的结论、编造来源、环节评级）原样转成计分程序读的格式；时效和写作在示意里没有评，都记为 1。
    测试不调用 walkthrough_example.py 的计算。
    """

    @classmethod
    def setUpClass(cls):
        cls.result = run_scorer("1.2", WALK_MAPPING, WALK_DATA)

    def test_version_1_2_gives_the_walkthrough_rank_intervals(self):
        self.assertEqual(intervals(self.result), {
            "一号": [4, 4], "二号": [2, 3], "三号": [1, 1], "四号": [2, 3], "五号": [5, 5]})

    def test_export_lists_each_report_with_interval_net_scores_severe_problems_and_grades(self):
        # 期望值取自"一道题走完全程"第 8 至 10 站的表；时效和写作在示意里没有评，夹具里都记为 1
        def entry(label, best, worst, nets, problems, grades):
            return {"label": label, "product": f"示意报告{label}（虚构）", "rank_best": best, "rank_worst": worst,
                    "net_scores": dict(zip("甲乙丙", nets)), "severe_problems": problems,
                    "element_grades": dict(zip(ELEMENTS, grades)), "timeliness": 1, "writing": 1}
        self.assertEqual(self.result["reports"], [
            entry("一号", 4, 4, (-2, -2, -1), [], (1, 0, 0, 0, 1)),
            entry("二号", 2, 3, (4.5, 6.5, 7.5), [], (2, 2, 1, 2, 1)),
            entry("三号", 1, 1, (9, 15, 15.5), [], (2, 2, 2, 2, 2)),
            entry("四号", 2, 3, (4, 5, 6), [], (2, 0, 1, 1, 2)),
            entry("五号", 5, 5, (0, 0, 1), ["编造来源"], (1, 1, 0, 1, 1)),
        ])

    def test_export_lists_separated_pairs_with_their_basis(self):
        pairs = {(p["higher"], p["lower"]): p["basis"] for p in self.result["separated_pairs"]}
        self.assertEqual(pairs, {
            ("一号", "五号"): "硬伤分档", ("二号", "五号"): "硬伤分档",
            ("三号", "五号"): "硬伤分档", ("四号", "五号"): "硬伤分档",
            ("三号", "一号"): "深度净分", ("三号", "二号"): "深度净分", ("三号", "四号"): "深度净分",
            ("二号", "一号"): "深度净分", ("四号", "一号"): "深度净分",
        })

    def test_points_no_report_wrote_do_not_change_the_ranking(self):
        # 深度地图上多登记五条核心要点，五份报告都没有写到。名次区间、分开的对、
        # 以及每对在重抽样中领先的比例都应完全不变。
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "data")
            shutil.copytree(WALK_DATA, data)
            pool_file = os.path.join(data, "pool.json")
            with open(pool_file, encoding="utf-8") as f:
                points = json.load(f)["points"]
            for k in range(5):
                extra = {"pid": f"M{k + 1}", "content": f"地图上没有报告写到的要点 {k + 1}", "correct": "正确",
                         "relevant": True, "level": "本质", "importance": "核心", "reach": {}}
                points.insert(2 * k, extra)
            with open(pool_file, "w", encoding="utf-8") as f:
                json.dump({"points": points}, f, ensure_ascii=False)
            padded = run_scorer("1.2", WALK_MAPPING, data)
        for key in ("reports", "separated_pairs"):
            with self.subTest(key=key):
                self.assertEqual(padded[key], self.result[key])

    def test_export_gives_resampling_share_under_each_weight_for_net_score_pairs(self):
        # 页面第 9 站：三号领先二号、一号都是 100%，领先四号 98%；二号、四号领先一号 97.2%、97.4%
        expected = {("三号", "一号"): 1.0, ("三号", "二号"): 1.0, ("三号", "四号"): 0.98,
                    ("二号", "一号"): 0.972, ("四号", "一号"): 0.974}
        for p in self.result["separated_pairs"]:
            if p["basis"] == "深度净分":
                with self.subTest(pair=(p["higher"], p["lower"])):
                    self.assertEqual(set(p["bootstrap_share"]), set("甲乙丙"))
                    for share in p["bootstrap_share"].values():
                        self.assertAlmostEqual(share, expected[(p["higher"], p["lower"])], delta=0.02)


if __name__ == "__main__":
    unittest.main()
