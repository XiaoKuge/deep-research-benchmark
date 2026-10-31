"""资料站上的模拟出题页和模拟评审页的生成器（site/build_simulation.py）的测试。

只通过命令行和它写出的页面观察行为。夹具用模拟出题者和模拟评审自己的测试里的回放材料现场生成
（tests/test_simulate_setter.py、tests/test_simulate_review.py），不真的调用模型：
- 题库：练习题「萤火虫」；正式题「保密题」（没有「已公开」字段，赛前不公开）；正式题「已公开题」（元数据写明已公开）；
  模拟评审用的练习题 test-question。正式题的题目卡和深度地图里每一处文字都带着记号「机密」，
  所以生成的任何文件里出现「机密」，就是泄露了。
  练习题「替代题」把乙配置成 google：写深度地图要读网页，google 不能用于只读网页一档，换成了 codex。
- 评审记录：test-run（回放，三份报告，有结果文件）；estimate-run（只估算，没有结果）；
  secret-run（对正式题「保密题」只估算，提示词里有题目卡全文和深度地图的要点）；
  few-run（回放，kimi 和 google 都不可用，kimi 的评委位置换成 claude，断言核验和要点判定只剩两家）。
期望值来自独立来源：调用记录文件、题目目录里的文件、模拟评审测试里手算的名次区间。
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
GENERATOR = os.path.join(SITE, "build_simulation.py")
COMMITTED = os.path.join(SITE, "simulation")
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_simulate_review as review_material  # noqa: E402
import test_simulate_setter as setter_material  # noqa: E402

SECRET = "机密"
PUBLISHED = "解密"
# 正式题回放材料里要带上记号的栏：题目卡和深度地图里的文字
SECRET_KEYS = {"话题", "选题理由", "浅答案", "怎样改变", "提问者", "用途", "问题", "提问版", "裸题版", "转折点", "要点"}

# 资料站的视觉规则，见 site/index.html 的样式和共用说明
SPACING = {0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96}
FONT_SIZES = {12, 14, 16, 18, 20, 24, 30, 36, 48, 60, 72, 96}  # Tailwind text-xs 至 text-8xl
LINE_HEIGHTS = {16, 20, 24, 28, 32, 36, 40, 48, 60}
RADII = {2, 4, 6, 8, 12, 16, 24, 9999}
EASE = "cubic-bezier(0.22, 1, 0.36, 1)"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    return json.loads(read(path))


def read_records(path):
    return [json.loads(line) for line in read(path).splitlines() if line.strip()]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def marked(value, mark):
    """回放材料的回答里，题目卡和深度地图的每一栏文字前面加上记号。"""
    if isinstance(value, dict):
        return {k: (mark + v if k in SECRET_KEYS and isinstance(v, str) else marked(v, mark)) for k, v in value.items()}
    if isinstance(value, list):
        return [marked(v, mark) for v in value]
    return value


def formal_material(mark):
    lines = []
    for line in setter_material.material():
        try:
            answer = json.loads(line["answer"])
        except ValueError:
            answer = None
        if isinstance(answer, dict):
            text = json.dumps(marked(answer, mark), ensure_ascii=False)
        else:
            text = mark + line["answer"]  # 闭卷对照的回答是一段文字
        lines.append(dict(line, answer=text))
    return lines


def run_setter(base, questions, qid, kind, lines, topic, *extra):
    material = os.path.join(base, qid + "-回放材料.jsonl")
    write(material, "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))
    argv = ["--topic", topic, "--asker", "小区物业的绿化主管", "--kind", kind, "--id", qid, "--out", questions,
            "--replay", material, *extra]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
        code = setter_material.simulate_setter.main(argv)
    if code != 0:
        raise RuntimeError(printed.getvalue())


def run_review(inputs, out, *extra):
    result = review_material.run_tool(inputs, out, *extra)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def generate(questions, reviews, output):
    return subprocess.run([sys.executable, "-I", GENERATOR, "--questions", questions, "--reviews", reviews,
                           "--output", output], capture_output=True, text=True, encoding="utf-8")


class Fixture:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self.base = self._tmp.name
        self.questions = os.path.join(base, "questions")
        self.reviews = os.path.join(base, "reviews")
        self.out = os.path.join(base, "site", "simulation")
        run_setter(base, self.questions, "萤火虫", "练习题", setter_material.material(), "城市里的萤火虫")
        run_setter(base, self.questions, "保密题", "正式题", formal_material(SECRET), SECRET + "话题")
        run_setter(base, self.questions, "已公开题", "正式题", formal_material(PUBLISHED), PUBLISHED + "话题")
        substituted = setter_material.material(overrides={
            "出题-闭卷对照-作答": ("kimi", "闭卷的回答：萤火虫少了是因为农药。")})
        run_setter(base, self.questions, "替代题", "练习题", substituted, "城市里的萤火虫",
                   "--map-b", "google", "--closed-book", "kimi")
        meta_path = os.path.join(self.questions, "已公开题", "元数据.json")
        write(meta_path, json.dumps(dict(read_json(meta_path), 已公开=True), ensure_ascii=False, indent=2))
        # 模拟评审的输入：题目目录 questions/test-question，三份报告、名称表、网页存档、配置
        self.inputs = review_material.build_inputs(base)
        write(os.path.join(self.inputs["question"], "元数据.json"),
              json.dumps({"题目标识": "test-question", "类别": "练习题", "状态": "完成"}, ensure_ascii=False))
        replay = review_material.write_replay(os.path.join(base, "review-replay.jsonl"), review_material.standard_replay())
        run_review(self.inputs, os.path.join(self.reviews, "test-run"), "--replay", replay)
        run_review(self.inputs, os.path.join(self.reviews, "estimate-run"), "--estimate", "--run-id", "estimate-run")
        secret = dict(self.inputs, question=os.path.join(self.questions, "保密题"))
        run_review(secret, os.path.join(self.reviews, "secret-run"), "--estimate", "--run-id", "secret-run")
        few = review_material.write_replay(os.path.join(base, "few-replay.jsonl"), review_material.unavailable_replay())
        run_review(self.inputs, os.path.join(self.reviews, "few-run"), "--replay", few, "--run-id", "few-run")
        self.result = generate(self.questions, self.reviews, self.out)

    def cleanup(self):
        self._tmp.cleanup()

    def page(self, *parts):
        return Page(os.path.join(self.out, *parts))

    def calls(self, kind, name):
        if kind == "reviews":
            return read_records(os.path.join(self.reviews, name, "calls.jsonl"))
        return read_records(os.path.join(self.questions, name, "调用记录.jsonl"))

    def generated_files(self):
        for folder, _, names in os.walk(self.out):
            for name in names:
                yield os.path.join(folder, name)


FX = None


def setUpModule():
    global FX
    FX = Fixture()


def tearDownModule():
    FX.cleanup()


class Page(HTMLParser):
    """读出页面的可见文字（另存一份不含代码的）、带 id 的元素里的文字、全部链接、样式表和标题，
    以及每个 pre 元素的原文和它是否在一个可折叠的 details 里面。"""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    HIDDEN = {"style", "script", "svg", "title"}
    CODE = {"pre", "code"}

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.parts, self.prose, self.css, self.links, self.headings = [], [], [], [], []
        self.by_id, self.pres = {}, {}
        self.stack, self.hidden, self.code, self.pre = [], 0, 0, None
        self.feed(read(path))
        self.close()
        self.text = squash("".join(self.parts))
        self.prose_text = "".join(self.prose)
        self.by_id = {k: squash("".join(v)) for k, v in self.by_id.items()}

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for key in ("href", "src"):
            if key in a:
                self.links.append(a[key])
        if a.get("id"):
            self.by_id.setdefault(a["id"], [])
        if tag in self.VOID:
            return
        if tag in self.HIDDEN:
            self.hidden += 1
        if tag in self.CODE:
            self.code += 1
        if tag == "pre":
            folded = any(t == "details" for t, _ in self.stack)
            self.pre = {"id": a.get("id", ""), "text": [], "folded": folded}
        if tag in ("h1", "h2", "h3", "h4"):
            self.headings.append(a.get("class", ""))
        self.stack.append((tag, a.get("id")))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        while self.stack:
            t, _ = self.stack.pop()
            if t in self.HIDDEN:
                self.hidden -= 1
            if t in self.CODE:
                self.code -= 1
            if t == "pre" and self.pre is not None:
                text = "".join(self.pre["text"])
                # 按网页的规定，紧跟在 <pre> 后面的一个换行不算内容
                self.pres[self.pre["id"] or len(self.pres)] = {"text": text[1:] if text.startswith("\n") else text,
                                                               "folded": self.pre["folded"]}
                self.pre = None
            if t == tag:
                break

    def handle_data(self, data):
        if self.hidden:
            if self.stack and self.stack[-1][0] == "style":
                self.css.append(data)
            return
        self.parts.append(data)
        if not self.code:
            self.prose.append(data)
        if self.pre is not None:
            self.pre["text"].append(data)
        for _, i in self.stack:
            if i:
                self.by_id[i].append(data)


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


class GeneratorTest(unittest.TestCase):

    def test_one_command_writes_the_question_bank_the_review_records_and_every_detail_page(self):
        self.assertEqual(FX.result.returncode, 0, FX.result.stdout + FX.result.stderr)
        expected = ["questions.html", "reviews.html"]
        expected += [f"questions/{q}/index.html" for q in ("萤火虫", "保密题", "已公开题", "test-question")]
        expected += [f"reviews/{r}/index.html" for r in ("test-run", "estimate-run", "secret-run")]
        expected += [f"reviews/test-run/results/{name}" for name in
                     ("index.html", "points.html", "report-Alpha.html", "report-Bravo.html", "report-Charlie.html")]
        for name in expected:
            with self.subTest(page=name):
                self.assertTrue(os.path.isfile(os.path.join(FX.out, name)))


def local_targets(page):
    """页面上每个本地链接：(链接原文, 指向的文件, 页内位置)。外部网址不算。"""
    for link in page.links:
        if re.match(r"^(https?:|mailto:|data:|//)", link):
            continue
        path, _, anchor = link.partition("#")
        target = os.path.normpath(os.path.join(os.path.dirname(page.path), unquote(path))) if path else page.path
        yield link, target, anchor


class QuestionBankTest(unittest.TestCase):

    def test_the_bank_lists_every_question_with_its_kind(self):
        bank = FX.page("questions.html")
        for qid, kind in (("萤火虫", "练习题"), ("保密题", "正式题"), ("已公开题", "正式题"), ("test-question", "练习题")):
            with self.subTest(question=qid):
                self.assertIn(kind, bank.by_id[f"question-{qid}"])
                self.assertIn(f"questions/{qid}/index.html", [unquote(x) for x in bank.links])

    def test_a_practice_question_shows_its_three_versions_and_depth_map_in_full(self):
        page = FX.page("questions", "萤火虫", "index.html")
        shown = [p["text"] for p in page.pres.values()]
        for name in ("题目卡.txt", "提问版.txt", "裸题版.txt", "深度地图.txt", "两人对照记录.md", "泄露检查记录.md", "闭卷对照记录.md"):
            with self.subTest(file=name):
                self.assertIn(read(os.path.join(FX.questions, "萤火虫", name)), shown)

    def test_a_formal_question_before_publication_shows_only_the_depth_map_checksum(self):
        checksum = read(os.path.join(FX.questions, "保密题", "深度地图校验值.txt")).split()[0]
        page = FX.page("questions", "保密题", "index.html")
        self.assertIn(checksum, page.text)
        self.assertIn(checksum, FX.page("questions.html").by_id["question-保密题"])
        self.assertEqual(page.pres, {}, "公开之前不应当显示任何原文")
        self.assertFalse(os.path.exists(os.path.join(FX.out, "questions", "保密题", "calls")))

    def test_nothing_generated_contains_any_text_of_an_unpublished_formal_question(self):
        # 正式题「保密题」的题目卡和深度地图里每一处文字都带着记号；用它做的模拟评审，提示词里也有。
        self.assertIn(SECRET, read(os.path.join(FX.questions, "保密题", "深度地图.txt")))
        self.assertIn(SECRET, read(os.path.join(FX.reviews, "secret-run", "calls.jsonl")))
        for path in FX.generated_files():
            with self.subTest(file=os.path.relpath(path, FX.out)):
                self.assertNotIn(SECRET, read(path))

    def test_nothing_links_to_the_files_of_an_unpublished_formal_question_or_its_review(self):
        hidden = [os.path.join(FX.questions, "保密题"), os.path.join(FX.reviews, "secret-run")]
        for path in FX.generated_files():
            if not path.endswith(".html"):
                continue
            for link, target, _ in local_targets(Page(path)):
                with self.subTest(page=os.path.relpath(path, FX.out), link=link):
                    self.assertFalse(any(target == h or target.startswith(h + os.sep) for h in hidden))
        self.assertFalse(os.path.exists(os.path.join(FX.out, "reviews", "secret-run", "calls")))
        self.assertFalse(os.path.exists(os.path.join(FX.out, "reviews", "secret-run", "results")))

    def test_a_formal_question_marked_as_published_shows_its_full_text(self):
        page = FX.page("questions", "已公开题", "index.html")
        shown = [p["text"] for p in page.pres.values()]
        self.assertIn(read(os.path.join(FX.questions, "已公开题", "深度地图.txt")), shown)
        self.assertIn(read(os.path.join(FX.questions, "已公开题", "题目卡.txt")), shown)


def shown_time(iso):
    """调用记录里的时间在页面上的写法，例如 2026 年 10 月 30 日 20:03:45.125；只估算的记录没有时间。"""
    if iso is None:
        return "没有记下"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)", iso)
    return f"{int(m.group(1))} 年 {int(m.group(2))} 月 {int(m.group(3))} 日 {m.group(4)}"


class CallPagesTest(unittest.TestCase):
    """每一次模型调用都有原文页：调用记录文件的第 n 行对应 calls/n.html。"""
    PUBLIC = [("reviews", "test-run"), ("reviews", "estimate-run"), ("questions", "萤火虫"), ("questions", "已公开题")]

    def test_every_call_has_a_page_with_the_prompt_and_answer_in_full(self):
        for kind, name in self.PUBLIC:
            records = FX.calls(kind, name)
            self.assertTrue(records)
            for n, record in enumerate(records, 1):
                with self.subTest(owner=name, call=n):
                    page = FX.page(kind, name, "calls", f"{n}.html")
                    self.assertEqual(page.pres["prompt"]["text"], record["prompt"])
                    if record["answer"]:
                        self.assertEqual(page.pres["answer"]["text"], record["answer"])
                    else:
                        self.assertNotIn("answer", page.pres)

    def test_every_call_page_names_the_vendor_model_tool_limit_times_and_status(self):
        for kind, name in self.PUBLIC:
            for n, record in enumerate(FX.calls(kind, name), 1):
                with self.subTest(owner=name, call=n):
                    text = FX.page(kind, name, "calls", f"{n}.html").by_id["info"]
                    for value in (record["vendor"], record["company"], record["tools"], record["status"],
                                  shown_time(record["started_at"]), shown_time(record["ended_at"])):
                        self.assertIn(value, text)
                    self.assertIn("命令行的默认模型" if record["model"] is None else record["model"], text)

    def test_long_prompts_fold_but_stay_whole(self):
        records = FX.calls("reviews", "test-run")
        long_one = max(range(len(records)), key=lambda i: len(records[i]["prompt"]))
        self.assertGreater(len(records[long_one]["prompt"]), 5000)
        page = FX.page("reviews", "test-run", "calls", f"{long_one + 1}.html")
        self.assertTrue(page.pres["prompt"]["folded"])
        self.assertEqual(page.pres["prompt"]["text"], records[long_one]["prompt"])

    def test_the_review_and_question_pages_link_every_call_page(self):
        for kind, name in self.PUBLIC:
            page = FX.page(kind, name, "index.html")
            links = {unquote(x) for x in page.links}
            for n in range(1, len(FX.calls(kind, name)) + 1):
                with self.subTest(owner=name, call=n):
                    self.assertIn(f"calls/{n}.html", links)


class ReviewRecordsTest(unittest.TestCase):
    """评审记录页：每次评审用了哪些厂商和模型、调用次数，结果链接到名次页和复核页。
    test-run 的调用次数按模拟评审测试里的手算：共 46 次，claude 27、codex 14、kimi 5。"""

    @classmethod
    def setUpClass(cls):
        cls.page = FX.page("reviews.html")
        cls.row = cls.page.by_id["review-test-run"]

    def test_lists_every_review(self):
        for run in ("test-run", "estimate-run", "secret-run"):
            with self.subTest(run=run):
                self.assertIn(f"review-{run}", self.page.by_id)
                self.assertIn(f"reviews/{run}/index.html", [unquote(x) for x in self.page.links])

    def test_names_the_vendors_models_and_call_counts(self):
        for text in ("共 46 次", "claude 27 次", "codex 14 次", "kimi 5 次", "Anthropic", "OpenAI", "月之暗面", "命令行默认模型"):
            with self.subTest(text=text):
                self.assertIn(text, self.row)

    def test_results_link_to_the_rank_page_and_every_review_page(self):
        links = [unquote(x) for x in self.page.links]
        for name in ("index.html", "points.html", "report-Alpha.html", "report-Bravo.html", "report-Charlie.html"):
            with self.subTest(page=name):
                self.assertIn(f"reviews/test-run/results/{name}", links)

    def test_a_review_without_results_says_why(self):
        self.assertIn("只估算", self.page.by_id["review-estimate-run"])
        self.assertIn("还没有公开的正式题", self.page.by_id["review-secret-run"])

    def test_the_review_page_shows_calls_by_step_and_the_rank_intervals(self):
        page = FX.page("reviews", "test-run", "index.html")
        for step in ("结论清单", "断言核验", "要点池合并", "要点判定", "环节评级", "两两比较", "直接回答"):
            self.assertIn(step, page.by_id["steps"])
        self.assertIn("第 1 名", page.by_id["results"])
        self.assertIn("results/report-Alpha.html", [unquote(x) for x in page.links])


def zone_text(iso):
    """时间里的时区在页面上的白话写法，与 tools/archive_sources.py 一样称协调世界时：
    -07:00 写成「协调世界时减 7 小时」，+05:30 写成「协调世界时加 5 小时 30 分」，Z 写成「协调世界时」。"""
    m = re.search(r"(Z|([+-])(\d{2}):(\d{2}))$", iso)
    if m.group(1) == "Z":
        return "（协调世界时）"
    hours, minutes = int(m.group(3)), int(m.group(4))
    if hours == minutes == 0:
        return "（协调世界时）"
    return "（协调世界时%s %d 小时%s）" % ("加" if m.group(2) == "+" else "减", hours,
                                         " %d 分" % minutes if minutes else "")


class PlainWordsTest(unittest.TestCase):
    """页面上的可见文字用白话：时区写成"协调世界时减 7 小时"，校验值不写算法名"SHA-256"。"""

    def test_times_name_the_time_zone_in_plain_words(self):
        record = FX.calls("reviews", "test-run")[0]
        text = FX.page("reviews", "test-run", "calls", "1.html").by_id["info"]
        self.assertIn(shown_time(record["started_at"]) + zone_text(record["started_at"]), text)
        for parts in (("reviews", "test-run", "calls", "1.html"), ("reviews", "test-run", "index.html"),
                      ("questions", "萤火虫", "index.html")):
            with self.subTest(page="/".join(parts)):
                self.assertNotIn("UTC", FX.page(*parts).text)

    def test_checksums_are_called_checksums_without_the_algorithm_name(self):
        for parts in (("questions.html",), ("reviews", "test-run", "calls", "1.html"), ("questions", "萤火虫", "index.html"),
                      ("questions", "保密题", "index.html"), ("questions", "萤火虫", "calls", "1.html")):
            with self.subTest(page="/".join(parts)):
                self.assertNotIn("SHA-256", FX.page(*parts).text)

    def test_the_generator_compares_with_the_model_layer_constants(self):
        source = read(GENERATOR)
        for status in ("成功", "失败", "超时", "只估算"):  # 与 models 里的常量比较，不写字面的状态
            self.assertNotRegex(source, r'(==|!=)\s*"%s"|"%s"\s*(:|==)' % (status, status))
        self.assertNotIn("def tag(", source)


class SubstitutionPagesTest(unittest.TestCase):
    """替代记录只有一种格式（步骤、任务、原来的厂商、改用的厂商、原因），出题页和评审页都照它显示。"""

    def test_the_review_page_lists_each_substitution_with_its_reason(self):
        meta = read_json(os.path.join(FX.reviews, "few-run", "run.json"))
        self.assertTrue(meta["substitutions"])
        text = FX.page("reviews", "few-run", "index.html").by_id["vendors"]
        for item in meta["substitutions"]:
            with self.subTest(task=item["任务"]):
                self.assertIn(squash(item["原因"]), text)
        self.assertIn("原来的厂商", text)
        self.assertIn("改用的厂商", text)

    def test_the_question_page_shows_the_substitution_of_a_role(self):
        meta = read_json(os.path.join(FX.questions, "替代题", "元数据.json"))
        item = meta["角色"]["乙"]["替代"][0]
        self.assertEqual((item["原来的厂商"], item["改用的厂商"]), ("google", "codex"))
        text = FX.page("questions", "替代题", "index.html").by_id["roles"]
        self.assertIn("google 改用 codex", text)
        self.assertIn("不能用于只读网页一档", text)


class ThreeVendorRuleTest(unittest.TestCase):
    """规则手册第七节"评委组"第 1 条：至少三家厂商。替代之后不足三家的步骤，评审页上用醒目的一句话写明。"""

    def test_the_review_page_warns_about_steps_with_fewer_than_three_vendors(self):
        page = FX.page("reviews", "few-run", "index.html")
        warning = page.by_id["rule-warning"]
        for text in ("至少三家厂商的模型担任评委", "断言核验", "要点判定", "claude、codex"):
            self.assertIn(text, warning)
        self.assertNotIn("环节评级", warning)
        raw = read(page.path)
        self.assertLess(raw.index('id="rule-warning"'), raw.index('id="summary"'))

    def test_a_review_that_kept_three_vendors_has_no_warning(self):
        self.assertNotIn("rule-warning", FX.page("reviews", "test-run", "index.html").by_id)


class OutputSwapTest(unittest.TestCase):
    """输出目录先在旁边的新目录里写完，再换下旧目录：中途出错时旧的页面原样留着，旁边不留下写了一半的目录。"""

    def test_a_failure_while_writing_keeps_the_old_pages(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            reviews = os.path.join(tmp, "reviews")
            shutil.copytree(os.path.join(FX.reviews, "test-run"), os.path.join(reviews, "test-run"))
            out = os.path.join(tmp, "site", "simulation")
            first = generate(FX.questions, reviews, out)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            before = {os.path.relpath(os.path.join(d, n), out): read(os.path.join(d, n))
                      for d, _, names in os.walk(out) for n in names}
            broken = os.path.join(reviews, "broken-run")
            shutil.copytree(os.path.join(FX.reviews, "test-run"), broken)
            os.remove(os.path.join(broken, "data", "pool.json"))  # 名次页要读它，写到一半会出错
            second = generate(FX.questions, reviews, out)
            self.assertNotEqual(second.returncode, 0)
            after = {os.path.relpath(os.path.join(d, n), out): read(os.path.join(d, n))
                     for d, _, names in os.walk(out) for n in names}
            self.assertEqual(after, before)
            self.assertEqual(os.listdir(os.path.join(tmp, "site")), ["simulation"])


class SimulatedResultsTest(unittest.TestCase):
    """模拟评审的名次页和复核页：与试评的格式相同，由 site/build_results.py 生成。
    名次区间的期望值抄自模拟评审测试的手算：Alpha 第 1、Bravo 第 2、Charlie 第 3。"""
    INTERVALS = {"Alpha": "第 1 名", "Bravo": "第 2 名", "Charlie": "第 3 名"}
    NAMES = {"Alpha": "产品甲", "Bravo": "产品乙", "Charlie": "产品丙"}

    @classmethod
    def setUpClass(cls):
        cls.rank = FX.page("reviews", "test-run", "results", "index.html")
        data = os.path.join(FX.reviews, "test-run", "data")
        cls.claims = {r: v["claims"] for r, v in read_json(os.path.join(data, "verify-majority.json"))["reports"].items()}
        cls.pool = read_json(os.path.join(data, "pool.json"))["points"]

    def test_rank_page_says_this_is_a_simulated_review_not_a_product_review(self):
        self.assertIn("这是模拟评审的演示，评委全部由大模型担任，不是对产品的评价", self.rank.text)

    def test_rank_page_shows_each_report_with_its_name_and_interval(self):
        for r, interval in self.INTERVALS.items():
            with self.subTest(report=r):
                row = self.rank.by_id[f"rank-{r}"]
                self.assertIn(interval, row)
                self.assertIn(self.NAMES[r], row)

    def test_review_pages_show_every_main_claim_and_every_point_the_report_wrote(self):
        for r in self.INTERVALS:
            page = FX.page("reviews", "test-run", "results", f"report-{r}.html")
            for c in self.claims[r]:
                with self.subTest(report=r, claim=c["id"]):
                    box = page.by_id[f"claim-{c['id']}"]
                    self.assertIn(squash(c["claim"]), box)
                    self.assertIn(c["source_label"], box)
            for p in self.pool:
                if r in p["reach"]:
                    with self.subTest(report=r, point=p["pid"]):
                        self.assertIn(squash(p["content"]), page.by_id[f"point-{p['pid']}"])

    def test_review_pages_link_the_calls_that_concern_the_report(self):
        records = FX.calls("reviews", "test-run")
        page = FX.page("reviews", "test-run", "results", "report-Charlie.html")
        links = {unquote(x) for x in page.links}
        for n, record in enumerate(records, 1):
            concerns = "Charlie" in record["task"] or record["task"].startswith(("评审-要点池合并", "评审-要点判定"))
            with self.subTest(call=n, task=record["task"]):
                self.assertEqual(f"../calls/{n}.html" in links, concerns)


class LocalLinksTest(unittest.TestCase):
    """生成的每一页上的本地链接（文件和页内位置）都能打开。外部网址不检查。"""

    def test_every_local_link_points_to_an_existing_file_and_anchor(self):
        pages = {}
        checked = 0
        for path in FX.generated_files():
            if not path.endswith(".html"):
                continue
            for link, target, anchor in local_targets(Page(path)):
                checked += 1
                with self.subTest(page=os.path.relpath(path, FX.out), link=link):
                    self.assertTrue(os.path.exists(target), f"链接到不存在的 {target}")
                    if anchor and target.endswith(".html"):
                        if target not in pages:
                            pages[target] = Page(target)
                        self.assertIn(anchor, pages[target].by_id, "那一页没有这个位置")
        self.assertGreater(checked, 1000)


class CommittedPagesTest(unittest.TestCase):
    """已提交的 site/simulation/ 就是生成器用仓库里的 simulation/ 现在写出的页面。
    生成到 site/ 下与 site/simulation/ 同一层的临时目录，这样相对链接一样。"""

    def test_committed_pages_are_exactly_what_the_generator_writes_now(self):
        with tempfile.TemporaryDirectory(dir=SITE, prefix=".simulation-check-") as tmp:
            result = generate(os.path.join(ROOT, "simulation", "questions"), os.path.join(ROOT, "simulation", "reviews"), tmp)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            fresh = sorted(os.path.relpath(os.path.join(d, n), tmp) for d, _, ns in os.walk(tmp) for n in ns)
            kept = sorted(os.path.relpath(os.path.join(d, n), COMMITTED) for d, _, ns in os.walk(COMMITTED) for n in ns)
            self.assertEqual(fresh, kept, "site/simulation/ 不是最新的，请重新运行 python3 -I site/build_simulation.py")
            for name in fresh:
                with self.subTest(page=name):
                    with open(os.path.join(tmp, name), "rb") as a, open(os.path.join(COMMITTED, name), "rb") as b:
                        self.assertTrue(a.read() == b.read(), f"site/simulation/{name} 不是最新的，请重新运行生成器")

    def test_the_committed_review_records_link_the_demo_note(self):
        page = Page(os.path.join(COMMITTED, "reviews.html"))
        self.assertIn("../../simulation/演示运行说明.md", [unquote(x) for x in page.links])

    def test_the_pilot_question_is_in_the_committed_bank_with_its_full_text(self):
        page = Page(os.path.join(COMMITTED, "questions", "第五阶段试评题", "index.html"))
        shown = [p["text"] for p in page.pres.values()]
        folder = os.path.join(ROOT, "simulation", "questions", "第五阶段试评题")
        self.assertIn(read(os.path.join(folder, "题目卡.txt")), shown)
        self.assertIn(read(os.path.join(folder, "深度地图.txt")), shown)


class VisualRulesTest(unittest.TestCase):
    """沿用资料站的视觉规则：命名文字样式、固定的间距和字号档位、减速动效曲线、只用浅色一套颜色、不用背景渐变、
    代码以外的可见文字里不用连字符。"""
    PAGES = [("questions.html",), ("reviews.html",), ("questions", "萤火虫", "index.html"), ("questions", "保密题", "index.html"),
             ("reviews", "test-run", "index.html"), ("reviews", "secret-run", "index.html"),
             ("reviews", "test-run", "calls", "1.html"), ("questions", "萤火虫", "calls", "3.html")]

    def test_follows_site_visual_rules(self):
        for parts in self.PAGES:
            page = FX.page(*parts)
            css = "".join(page.css)
            with self.subTest(page="/".join(parts)):
                self.assertIn('name="viewport"', read(page.path))
                self.assertIn(EASE, css)
                self.assertIn("color-scheme: light", css, "样式乙只用浅色一套，要写明 color-scheme")
                self.assertNotIn("gradient(", css)
            checks = [(r"(?:margin|padding)[\w-]*|gap|row-gap|column-gap", SPACING, "间距"), (r"font-size", FONT_SIZES, "字号"),
                      (r"line-height", LINE_HEIGHTS, "行高"), (r"border-radius", RADII, "圆角")]
            for prop, allowed, label in checks:
                for value in re.findall(r"(?<![\w-])(?:" + prop + r")\s*:\s*([^;}]+)", css):
                    for n in re.findall(r"(\d+(?:\.\d+)?)px", value):
                        with self.subTest(page="/".join(parts), label=label, value=value.strip()):
                            self.assertIn(float(n), allowed)

    def test_headings_use_named_text_styles(self):
        for parts in self.PAGES:
            for cls in FX.page(*parts).headings:
                with self.subTest(page="/".join(parts), cls=cls):
                    self.assertRegex(cls, r"\b(heading|title)-\d\b")

    def test_visible_text_outside_code_has_no_hyphen(self):
        for parts in self.PAGES:
            text = FX.page(*parts).prose_text
            for ch in "-‐–":
                with self.subTest(page="/".join(parts), ch=ch):
                    self.assertNotIn(ch, text)


if __name__ == "__main__":
    unittest.main()
