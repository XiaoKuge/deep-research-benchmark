"""名次页、复核页和要点池页的生成器（site/build_results.py）的测试。

只通过命令行和它写出的页面观察行为。期望值来自独立来源：已提交的第 1.2 版结果文件里的名次区间（写成字面值）、
映射表、评委输出文件（主要结论、要点池）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
PAGES = os.path.join(SITE, "results")
GENERATOR = os.path.join(SITE, "build_results.py")
PILOT = os.path.join(ROOT, "research-plan", "stage5-pilot")
LABELS = ["A", "B", "C", "D", "E", "F"]
PAGE_NAMES = ["index.html", "points.html"] + [f"report-{r}.html" for r in LABELS]


def generate(output):
    subprocess.run([sys.executable, "-I", GENERATOR, "--output", output], cwd=ROOT, check=True,
                   capture_output=True)


def load_json(*parts):
    with open(os.path.join(PILOT, *parts), encoding="utf-8") as f:
        return json.load(f)


class Page(HTMLParser):
    """读出页面的可见文字、每个带 id 的元素里的文字，以及全部链接。"""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.parts, self.by_id, self.links, self.stack, self.skip = [], {}, [], [], 0
        with open(path, encoding="utf-8") as f:
            self.feed(f.read())
        self.text = squash("".join(self.parts))
        self.by_id = {k: squash("".join(v)) for k, v in self.by_id.items()}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("href", "src"):
            if a.get(key) is not None:
                self.links.append(a[key])
        if tag in self.VOID:
            if a.get("id"):
                self.by_id.setdefault(a["id"], [])
            return
        if tag in ("script", "style"):
            self.skip += 1
        self.stack.append((tag, a.get("id")))
        if a.get("id"):
            self.by_id.setdefault(a["id"], [])

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        while self.stack:
            t, _ = self.stack.pop()
            if t in ("script", "style"):
                self.skip -= 1
            if t == tag:
                break

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(data)
        for _, i in self.stack:
            if i:
                self.by_id[i].append(data)


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


def committed_page(name):
    """已提交的页面，即读者打开的页面。它与生成器当前的输出一致，由下面的测试保证。"""
    return Page(os.path.join(PAGES, name))


class GeneratorTest(unittest.TestCase):

    def test_one_command_writes_rank_page_six_review_pages_and_point_pool_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate(tmp)
            for name in PAGE_NAMES:
                with self.subTest(page=name):
                    self.assertTrue(os.path.isfile(os.path.join(tmp, name)))

    def test_committed_pages_are_exactly_what_the_generator_writes_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            generate(tmp)
            self.assertEqual(sorted(os.listdir(PAGES)), sorted(os.listdir(tmp)))
            for name in os.listdir(tmp):
                with self.subTest(page=name):
                    with open(os.path.join(tmp, name), "rb") as fresh, open(os.path.join(PAGES, name), "rb") as kept:
                        self.assertTrue(fresh.read() == kept.read(), f"site/results/{name} 不是最新的，请重新运行生成器")


class RankPageTest(unittest.TestCase):
    """名次页。名次区间的期望值抄自已提交的第 1.2 版结果文件。"""
    INTERVALS = {"A": "第 3 至 4 名", "B": "第 5 至 6 名", "C": "第 5 至 6 名",
                 "D": "第 1 至 2 名", "E": "第 3 至 4 名", "F": "第 1 至 2 名"}

    @classmethod
    def setUpClass(cls):
        cls.page = committed_page("index.html")

    def test_states_that_this_is_a_demo_judged_by_language_models_not_a_product_review(self):
        self.assertIn("这是第五阶段的试评演示，评委全部由大模型担任，不是对产品的评价", self.page.text)

    def test_each_of_the_six_reports_shows_its_product_and_rank_interval(self):
        products = load_json("mapping.json")["reports"]
        for r in LABELS:
            with self.subTest(report=r):
                row = self.page.by_id[f"rank-{r}"]
                self.assertIn(f"报告 {r}", row)
                self.assertIn(products[r], row)
                self.assertIn(self.INTERVALS[r], row)
                self.assertIn(f"report-{r}.html", self.page.links)

    def test_names_the_five_elements_and_timeliness_in_full(self):
        for name in ["切题与真实需要", "查找过程的交代", "甄别来源与处理矛盾", "分析", "结论与把握", "时效"]:
            with self.subTest(name=name):
                self.assertIn(name, self.page.text)

    def test_says_the_tie_break_compares_element_grades_and_timeliness(self):
        self.assertIn("比较环节评级和时效", self.page.text)


class ReviewPageTest(unittest.TestCase):
    """每份报告的复核页。期望内容直接取自评委输出文件。"""

    @classmethod
    def setUpClass(cls):
        cls.pages = {r: committed_page(f"report-{r}.html") for r in LABELS}
        cls.claims = {}
        for name in ("verify-opus-ABCF.json", "verify-opus-DE.json"):
            for r, v in load_json("out", name)["reports"].items():
                cls.claims[r] = v["claims"]
        cls.pool = load_json("out", "pool.json")["points"]

    def test_shows_every_main_claim_with_its_source_label_verdict_and_basis(self):
        self.assertEqual(sum(len(self.claims[r]) for r in LABELS), 58)
        for r in LABELS:
            for c in self.claims[r]:
                with self.subTest(report=r, claim=c["id"]):
                    box = self.pages[r].by_id[f"claim-{c['id']}"]
                    self.assertIn(squash(c["claim"]), box)
                    self.assertIn(c["source_label"], box)
                    self.assertIn(c["correct"], box)
                    self.assertIn(squash(c["correct_basis"]), box)

    def test_shows_every_pool_point_the_report_wrote_with_its_level_and_importance(self):
        for r in LABELS:
            for p in self.pool:
                if r not in p["reach"]:
                    continue
                with self.subTest(report=r, point=p["pid"]):
                    box = self.pages[r].by_id[f"point-{p['pid']}"]
                    self.assertIn(squash(p["content"]), box)
                    self.assertIn(p["level"], box)
                    self.assertIn(p["importance"], box)

    def test_quotes_the_report_text_that_each_element_grade_rests_on(self):
        for judge in ("opus-1", "opus-2", "sonnet-1"):
            reports = load_json("out", f"rating-{judge}.json")["reports"]
            for r in LABELS:
                for element, rating in reports[r]["ratings"].items():
                    with self.subTest(judge=judge, report=r, element=element):
                        self.assertIn(squash(rating["evidence"]), self.pages[r].text)


class PointPoolPageTest(unittest.TestCase):
    """要点池页：每条要点一行，行的 id 就是要点编号，复核页从这里链接过来。"""

    @classmethod
    def setUpClass(cls):
        cls.page = committed_page("points.html")
        cls.pool = load_json("out", "pool.json")["points"]

    def test_lists_every_point_in_the_pilot_pool_once(self):
        rows = [i for i in self.page.by_id if re.fullmatch(r"Q\d+", i)]
        self.assertEqual(len(rows), 122)
        self.assertEqual(sorted(rows), sorted(p["pid"] for p in self.pool))

    def test_each_row_shows_the_point_and_which_reports_wrote_it(self):
        for p in self.pool:
            with self.subTest(point=p["pid"]):
                row = self.page.by_id[p["pid"]]
                self.assertIn(squash(p["content"]), row)
                for r in LABELS:
                    if r in p["reach"]:
                        self.assertIn(f"{r} {'说法一致' if p['reach'][r] == '符合' else '说法相反'}", row)


class LocalLinksTest(unittest.TestCase):
    """页面上的本地链接（文件和页内位置）都能打开。外部网址不检查。"""

    def test_every_local_link_points_to_an_existing_file_and_anchor(self):
        pages = {}
        for name in PAGE_NAMES:
            for link in committed_page(name).links:
                if re.match(r"^(https?:|mailto:|data:|//)", link):
                    continue
                path, _, anchor = link.partition("#")
                target = os.path.normpath(os.path.join(PAGES, path)) if path else os.path.join(PAGES, name)
                with self.subTest(page=name, link=link):
                    self.assertTrue(os.path.exists(target), f"{name} 链接到不存在的 {link}")
                    if anchor and target.endswith(".html"):
                        if target not in pages:
                            pages[target] = Page(target)
                        self.assertTrue(anchor in pages[target].by_id, f"{name} 链接到 {link}，但那一页没有这个位置")


if __name__ == "__main__":
    unittest.main()
