"""资料站的四个说明页面：赛事说明、上手、公告、常见问题。

检查四页都存在、沿用资料站的视觉规则、顶部能回到资料站、彼此能跳转、
必备章节齐全、本地链接都能打开。运行：python3 -I -m unittest discover -s tests -v
"""
import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
PAGES = ["brief.html", "start.html", "news.html", "faq.html"]
# 还没有建好、允许暂时打不开的页面（相对 site/）
PENDING = set()

# 资料站的视觉规则，见 site/index.html 的样式和共用说明
SPACING = {0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96}
FONT_SIZES = {12, 14, 16, 18, 20, 24, 30, 36, 48, 60}
LINE_HEIGHTS = {16, 20, 24, 28, 32, 36, 40, 48, 60}
RADII = {2, 4, 6, 8, 12, 16, 24, 9999}
EASE = "cubic-bezier(0.22, 1, 0.36, 1)"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Page(HTMLParser):
    """把一个页面读成：全部 id、全部链接、可见文字、样式表，以及各个块的文字和链接。"""

    BLOCKS = {"section", "article", "details", "summary", "tr", "a",
              "h1", "h2", "h3", "h4"}
    HIDDEN = {"style", "script", "svg", "title"}

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.ids, self.links, self.blocks = set(), [], []
        self.visible, self.css = [], []
        self.open, self.hidden = [], []
        self.feed(read(path))
        self.close()
        self.text = "".join(self.visible)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if a.get("id"):
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if key in a:
                self.links.append(a[key])
                for b in self.open:
                    b["links"].append(a[key])
        # 链接的本地样式文件按出现的先后并入样式表，与页面里的样式一起检查
        if tag == "link" and "stylesheet" in a.get("rel", "") and not re.match(r"https?:", a.get("href", "")):
            self.css.append(read(os.path.join(os.path.dirname(self.path), a["href"])))
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        if tag in self.BLOCKS:
            inside = [b["id"] for b in self.open if b["id"]]
            self.open.append({"tag": tag, "id": a.get("id", ""), "attrs": a,
                              "text": [], "links": [], "inside": inside})

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        if tag in self.BLOCKS:
            for i in range(len(self.open) - 1, -1, -1):
                if self.open[i]["tag"] == tag:
                    b = self.open.pop(i)
                    b["text"] = "".join(b["text"])
                    self.blocks.append(b)
                    break

    def handle_data(self, data):
        if self.hidden:
            if self.hidden[-1] == "style":
                self.css.append(data)
            return
        self.visible.append(data)
        for b in self.open:
            b["text"].append(data)

    # 查询
    def block(self, block_id):
        found = [b for b in self.blocks if b["id"] == block_id]
        if len(found) != 1:
            raise AssertionError(f"{os.path.basename(self.path)} 里 id 为“{block_id}”的块应当恰好一个，实际 {len(found)} 个")
        return found[0]

    def of(self, tag, inside=None):
        return [b for b in self.blocks if b["tag"] == tag and (inside is None or inside in b["inside"])]

    def heading(self, block_id):
        heads = [b for b in self.blocks if b["tag"] in ("h1", "h2", "h3") and block_id in b["inside"]]
        if not heads:
            raise AssertionError(f"“{block_id}”里没有标题")
        return heads[0]["text"].strip()


def local_link_problems(page):
    """返回打不开的本地链接；PENDING 里的页面除外。"""
    problems = []
    here = os.path.dirname(page.path)
    for href in page.links:
        if re.match(r"(https?:|mailto:|data:)", href):
            continue
        path, _, frag = href.partition("#")
        path = path.partition("?")[0]
        if path:
            target = os.path.normpath(os.path.join(here, path))
            if os.path.relpath(target, SITE) in PENDING:
                continue
            exists = os.path.isdir(target) if path.endswith("/") else os.path.isfile(target)
            if not exists:
                problems.append(f"{href}：文件不存在")
            elif frag and target.endswith(".html") and f'id="{frag}"' not in read(target):
                problems.append(f"{href}：目标页没有这个锚点")
        elif frag and frag not in page.ids:
            problems.append(f"{href}：本页没有这个锚点")
    return problems


class CommonChecks:
    """每个页面都要满足的检查。子类设定 NAME。"""

    NAME = ""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(SITE, cls.NAME)
        if not os.path.isfile(path):
            raise AssertionError(f"缺少页面 site/{cls.NAME}")
        cls.page = Page(path)

    def test_top_links_back_to_site_home(self):
        backs = [a for a in self.page.of("a") if a["attrs"].get("href") == "index.html" and "回到资料站" in a["text"]]
        self.assertTrue(backs, "要有“回到资料站”的链接")
        raw = read(self.page.path)
        self.assertLess(raw.index("回到资料站"), raw.index("<main"), "“回到资料站”要在正文之前")

    def test_links_to_the_other_three_pages(self):
        for other in PAGES:
            if other != self.NAME:
                with self.subTest(other):
                    self.assertTrue(any(l.partition("#")[0] == other for l in self.page.links), f"没有链接到 {other}")

    def test_local_links_open(self):
        self.assertEqual(local_link_problems(self.page), [])

    def test_follows_site_visual_rules(self):
        css = "".join(self.page.css)
        raw = read(self.page.path)
        self.assertIn('name="viewport"', raw)
        self.assertIn(EASE, css)
        self.assertIn("prefers-color-scheme: dark", css)
        self.assertNotIn("gradient(", css, "不用背景渐变")
        checks = [
            (r"(?:margin|padding)[\w-]*|gap|row-gap|column-gap", SPACING, "间距"),
            (r"font-size", FONT_SIZES, "字号"),
            (r"line-height", LINE_HEIGHTS, "行高"),
            (r"border-radius", RADII, "圆角"),
        ]
        for prop, allowed, label in checks:
            for value in re.findall(r"(?<![\w-])(?:" + prop + r")\s*:\s*([^;}]+)", css):
                for n in re.findall(r"(\d+(?:\.\d+)?)px", value):
                    with self.subTest(label=label, value=value.strip()):
                        self.assertIn(float(n), allowed)

    def test_headings_use_named_text_styles(self):
        for h in [b for b in self.page.blocks if b["tag"] in ("h1", "h2", "h3", "h4")]:
            with self.subTest(h["text"].strip()):
                self.assertRegex(h["attrs"].get("class", ""), r"\b(heading|title)-\d\b")

    def test_visible_text_has_no_hyphen(self):
        for ch in "-‐–":
            self.assertNotIn(ch, self.page.text, f"可见文字里有连字符“{ch}”")


class BriefPage(CommonChecks, unittest.TestCase):
    NAME = "brief.html"

    SECTIONS = {
        "what": "比什么",
        "stages": "练习阶段和正式阶段",
        "schedule": "日程、奖项与报名",
        "run": "运行",
        "review": "评审",
        "ranking": "名次与公布",
        "appeals": "申诉",
        "groups": "封闭组和开放组",
        "spot-check": "随机抽查",
    }

    def test_required_sections(self):
        for sid, title in self.SECTIONS.items():
            with self.subTest(sid):
                self.assertIn(title, self.page.heading(sid))

    def test_each_rule_section_points_to_the_rules_handbook(self):
        for sid in ["what", "run", "review", "ranking", "appeals", "groups", "spot-check"]:
            with self.subTest(sid):
                links = self.page.block(sid)["links"]
                self.assertTrue(any(l.startswith("../notes/rules.html") for l in links))

    def test_practice_stage_is_public_and_formal_questions_are_secret(self):
        body = self.page.block("stages")
        for words in ["练习阶段", "淡水湖", "正式阶段", "两道", "赛前保密", "赛后", "公开"]:
            self.assertIn(words, body["text"])
        self.assertIn("../notes/question-handbook.html#example-lake", body["links"])
        self.assertIn("walkthrough.html", body["links"])

    def test_dates_prizes_and_registration_are_marked_undecided(self):
        rows = self.page.of("tr", inside="schedule")
        for item in ["运行日", "冻结截止", "临时名次", "最终名次", "奖项", "报名方式"]:
            with self.subTest(item):
                hits = [r for r in rows if item in r["text"]]
                self.assertTrue(hits, f"日程表里没有“{item}”")
                self.assertIn("〔待定〕", hits[0]["text"])

    def test_default_terms_are_marked(self):
        for sid in ["run", "groups", "spot-check", "appeals"]:
            with self.subTest(sid):
                self.assertIn("〔默认〕", self.page.block(sid)["text"])


class StartPage(CommonChecks, unittest.TestCase):
    NAME = "start.html"

    # 每类人的第一步必须指向的材料（相对 site/）
    ROLES = {
        "setters": ("出题同学", ["../notes/question-handbook.html#steps",
                                "../notes/question-handbook.html#templates",
                                "../notes/question-handbook.html#checklist"]),
        "teams": ("参赛队伍", ["../notes/rules.html", "teams.html",
                              "../notes/question-handbook.html#example-lake"]),
        "judges": ("评委", ["../notes/plan-stage4-rubric.html", "walkthrough.html"]),
    }

    def test_each_role_has_a_first_step_and_at_least_two_links(self):
        for sid, (title, needed) in self.ROLES.items():
            with self.subTest(sid):
                body = self.page.block(sid)
                self.assertIn(title, self.page.heading(sid))
                self.assertIn("第一步", body["text"])
                local = {l for l in body["links"] if not l.startswith("#")}
                self.assertGreaterEqual(len(local), 2)
                for link in needed:
                    self.assertIn(link, body["links"])

    def test_says_setters_and_judges_are_simulated_by_large_models(self):
        body = self.page.block("simulation")["text"]
        for words in ["出题者和评委", "大模型", "模拟", "Claude", "Codex", "Kimi", "三家"]:
            self.assertIn(words, body)

    def test_gives_the_commands_for_simulated_setting_and_review(self):
        body = self.page.block("simulation")["text"]
        for command in ["python3 tools/simulate_setter.py", "python3 tools/simulate_review.py"]:
            self.assertIn(command, body)
        self.assertIn("命令以程序的使用说明为准", body)

    def test_keeps_the_first_step_for_real_setters_and_judges(self):
        self.assertIn("真人出题", self.page.block("setters")["text"])
        self.assertIn("真人评审", self.page.block("judges")["text"])
        for sid in ["setters", "judges"]:
            with self.subTest(sid):
                self.assertIn("#simulation", self.page.block(sid)["links"])


class NewsPage(CommonChecks, unittest.TestCase):
    NAME = "news.html"
    DATE = re.compile(r"\d{4} 年 \d{1,2} 月 \d{1,2} 日")

    def announcements(self):
        items = self.page.of("article")
        self.assertTrue(items, "公告页没有公告")
        return items

    def test_every_announcement_is_dated(self):
        for item in self.announcements():
            with self.subTest(item["id"]):
                self.assertRegex(item["text"], self.DATE)

    def test_rules_draft_three_announcement_links_to_version_changes(self):
        hits = [a for a in self.announcements() if "草案第 3 版" in self.page.heading(a["id"])]
        self.assertEqual(len(hits), 1)
        self.assertIn("../notes/rules.html#version-changes", hits[0]["links"])

    def test_schedule_announcement_marks_dates_undecided(self):
        hits = [a for a in self.announcements() if "日程" in self.page.heading(a["id"])]
        self.assertTrue(hits)
        self.assertIn("〔待定〕", hits[0]["text"])

    def test_page_points_to_the_version_changes_appendix(self):
        intro = read(self.page.path).split("<main", 1)[0]
        self.assertIn("../notes/rules.html#version-changes", intro)


class FaqPage(CommonChecks, unittest.TestCase):
    NAME = "faq.html"
    GROUPS = {"setting": "出题", "competing": "参赛", "reviewing": "评审"}

    # 资料站首页 2026 年 10 月 30 日的九问，各取答案里的一句原话，用来核对答案保持原意；
    # 第二问的标题原为“评委是 AI”，按不用缩写的要求改成了白话
    SITE_QUESTIONS = {
        "为什么不直接用现有的评测工具？": "我们逐一审视了 18 个，没有一个能直接用",
        "评委是大模型，怎样保证判得对？": "评委至少来自三家厂商，每个评委评两次",
        "为什么公布名次区间，不直接排第几名？": "重复一千次，至少九成仍然领先",
        "深度地图是什么？它会不会让评分不客观？": "它是必需的，但不是标准答案",
        "参赛队伍能不能看了题目再改提示词？": "智能体在题目公布前冻结并申报",
        "真实用户很少写明自己是谁，题目为什么要写？": "评委要有参照，才能判断切不切题",
        "篇幅长、引用多，会加分吗？": "篇幅、格式、引用条数、文笔都不进入名次",
        "这套评法检验过了吗？": "8 条验收标准通过 4 条",
        "怎样在本机打开这些材料？": "全部材料都在本机，不需要联网，也不需要登录",
    }
    # 出题手册第九节“常见问题”的十问
    HANDBOOK_QUESTIONS = {
        "智能体的开发者能不能根据题目里的提问者和用途，去改写提示词？": "不能针对题目改",
        "真实使用时，用户很少写明自己是谁、要做什么。题目这样写，符合真实场景吗？": '基础级测不到"从一句话里推断真实需要"',
        "深度地图是不是可有可无？它写多写少有弹性，会不会让评分不客观、不权威？": "地图写多写少，对名次的影响严格为零",
        "凭什么相信能写出好的深度地图？": "不能事先保证，只能把要求写清楚、把关设够",
        "题目越难越好吗？": "深是调研的深，不是题目的难",
        "深度地图要写得很全吗？": "核心要点要全，一般要点不求全",
        "为什么截止时间定在运行当天？": "所有智能体在同一天运行",
        "智能体反问我，或者要我确认研究计划，怎么办？": "题目已包含全部信息，请按你的理解直接进行",
        "可以出带图片、要多轮对话的题吗？": "只用文字，一次给全，不交互",
        "深度地图写错了怎么办？": "对错一律看来源",
    }

    def test_three_groups(self):
        for sid, title in self.GROUPS.items():
            with self.subTest(sid):
                self.assertIn(title, self.page.heading(sid))

    def check_questions(self, questions):
        details = self.page.of("details")
        for question, phrase in questions.items():
            with self.subTest(question):
                hits = [d for d in details if question in d["text"]]
                self.assertEqual(len(hits), 1, "每一问恰好出现一次")
                groups = [g for g in self.GROUPS if g in hits[0]["inside"]]
                self.assertEqual(len(groups), 1, "每一问归入三组中的一组")
                self.assertIn(phrase, hits[0]["text"], "答案保持原意")

    def test_includes_the_nine_site_questions(self):
        self.check_questions(self.SITE_QUESTIONS)

    def test_includes_the_handbook_questions(self):
        self.check_questions(self.HANDBOOK_QUESTIONS)

    def test_question_titles_use_no_abbreviation_for_language_models(self):
        for summary in self.page.of("summary"):
            with self.subTest(summary["text"].strip()):
                self.assertNotRegex(summary["text"], r"(?<![A-Za-z])AI(?![A-Za-z])")


class SharedStylesTest(unittest.TestCase):
    """五个说明页面（赛事说明、上手、公告、常见问题、参赛队伍技术文档）共用的样式只写在 site/pages.css 一处。"""
    NAMES = PAGES + ["teams.html"]

    @staticmethod
    def rules(css):
        """样式表里的每一条规则（选择器连同声明），去掉注释和多余的空白。"""
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        return {re.sub(r"\s+", " ", r).strip() for r in re.findall(r"[^{}]+\{[^{}]*\}", css)}

    def test_every_page_links_the_shared_stylesheet(self):
        for name in self.NAMES:
            with self.subTest(name):
                self.assertIn('<link rel="stylesheet" href="pages.css">', read(os.path.join(SITE, name)))

    def test_no_page_repeats_a_shared_rule(self):
        shared = self.rules(read(os.path.join(SITE, "pages.css")))
        self.assertGreater(len(shared), 50)
        for name in self.NAMES:
            inline = "".join(re.findall(r"<style>(.*?)</style>", read(os.path.join(SITE, name)), re.S))
            with self.subTest(name):
                self.assertEqual(self.rules(inline) & shared, set())


class RulesWordingTest(unittest.TestCase):
    """说明页面转述规则的地方与规则手册草案第 3 版一致。"""

    def test_unseen_map_points_hide_which_and_how_many_reports_they_came_from(self):
        # 规则手册第七节第 3 条：地图上没有的要点，判定时不告诉评委它出自哪份报告、出自几份报告
        for name in ["brief.html", "news.html", "start.html", "walkthrough.html"]:
            with self.subTest(name):
                self.assertIn("出自哪份报告、出自几份报告", Page(os.path.join(SITE, name)).text)


if __name__ == "__main__":
    unittest.main()
