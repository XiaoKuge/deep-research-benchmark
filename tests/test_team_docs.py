"""参赛队伍技术文档 site/teams.html 的测试。

检查必备章节、本地链接、资料站的视觉规则，以及文档写的调用约定与统一运行程序的
使用说明 tools/run_agents.md 一致：约定的原文两边都有，文档里的申报表示例就是新手包的
申报表模板，反问的写法就是使用说明里的写法。期望值取自规则手册和使用说明。
运行：python3 -I -m unittest discover -s tests -v
"""

import json
import os
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGE = SITE / "teams.html"
KIT = SITE / "starter-kit"
GUIDE = ROOT / "tools" / "run_agents.md"
RULES = ROOT / "research-plan" / "rules.md"

DEFAULT_MARK = "〔默认〕，以主办方确认为准"

# 资料站的视觉规则，见 site/index.html 的样式和共用说明
SPACING = {0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96}
FONT_SIZES = {12, 14, 16, 18, 20, 24, 30, 36, 48, 60}
LINE_HEIGHTS = {16, 20, 24, 28, 32, 36, 40, 48, 60}
RADII = {2, 4, 6, 8, 12, 16, 24, 9999}
EASE = "cubic-bezier(0.22, 1, 0.36, 1)"

# 新手包的文件（相对 site/starter-kit/），文档里每一个都要能点开
KIT_FILES = [
    "README.md", "申报表模板.json", "系统提示词.md", "agent.py", "运行计划.json",
    "练习题/淡水湖/提问版.txt", "练习题/淡水湖/裸题版.txt", "交付要求.txt",
    "check_report.py", "check_report.md",
]


def rules_lines():
    return RULES.read_text(encoding="utf-8").splitlines()


def appendix_block(prefix):
    lines = rules_lines()
    start = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("#"))
    return lines[start + 1:end]


def appendix_one():
    return "\n".join(appendix_block("### 附录一")).strip()


def appendix_two_reply():
    body = next(line for line in appendix_block("### 附录二") if "一律回复：" in line)
    return body.split("一律回复：", 1)[1].strip()


def appendix_three_items():
    rows = [line for line in appendix_block("### 附录三") if line.startswith("|")][2:]
    return [row.strip("|").split("|")[0].strip() for row in rows]


def guide_block(heading, language):
    """取使用说明里某个二级标题下面第一个指定语言的代码块。"""
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return section.split(f"```{language}\n", 1)[1].split("\n```", 1)[0]


def squeeze(text):
    return re.sub(r"\s+", "", text)


class Page(HTMLParser):
    """把页面读成：全部 id、全部链接、样式表、标题、可见文字（另存一份不含代码的），以及带 id 的块。"""

    HIDDEN = {"style", "script", "svg", "title"}
    CODE = {"pre", "code"}
    BLOCKS = {"section", "pre", "a", "div", "blockquote", "h1", "h2", "h3", "h4"}

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.ids, self.links, self.css = set(), [], []
        self.visible, self.prose = [], []
        self.blocks, self.anchors, self.headings = {}, [], []
        self.stack, self.hidden, self.code = [], [], 0
        self.feed(path.read_text(encoding="utf-8"))
        self.close()
        self.text = "".join(self.visible)
        self.prose_text = "".join(self.prose)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if a.get("id"):
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if key in a:
                self.links.append(a[key])
                for item in self.stack:
                    item["links"].append(a[key])
        # 链接的本地样式文件按出现的先后并入样式表，与页面里的样式一起检查
        if tag == "link" and "stylesheet" in a.get("rel", "") and not re.match(r"https?:", a.get("href", "")):
            self.css.append((self.path.parent / a["href"]).read_text(encoding="utf-8"))
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        if tag in self.CODE:
            self.code += 1
        if tag in self.BLOCKS:
            self.stack.append({"tag": tag, "id": a.get("id", ""), "attrs": a, "text": [], "links": []})

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        if tag in self.CODE and self.code:
            self.code -= 1
        if tag in self.BLOCKS:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i]["tag"] == tag:
                    item = self.stack.pop(i)
                    item["text"] = "".join(item["text"])
                    if item["id"]:
                        self.blocks[item["id"]] = item
                    if tag == "a":
                        self.anchors.append(item)
                    if tag in ("h1", "h2", "h3", "h4"):
                        self.headings.append(item)
                    break

    def handle_data(self, data):
        if self.hidden:
            if self.hidden[-1] == "style":
                self.css.append(data)
            return
        self.visible.append(data)
        if not self.code:
            self.prose.append(data)
        for item in self.stack:
            item["text"].append(data)

    def block(self, block_id):
        if block_id not in self.blocks:
            raise AssertionError(f"teams.html 里没有 id 为“{block_id}”的块")
        return self.blocks[block_id]

    def section_title(self, section_id):
        """这一节的第一个二级标题。"""
        raw = self.path.read_text(encoding="utf-8")
        match = re.search(rf'<section[^>]*id="{re.escape(section_id)}"[^>]*>\s*<h2[^>]*>(.*?)</h2>', raw, re.S)
        if not match:
            raise AssertionError(f"“{section_id}”一节要以二级标题开头")
        return re.sub(r"<[^>]+>", "", match.group(1)).strip()


def local_link_problems(page):
    problems = []
    here = page.path.parent
    for href in page.links:
        if re.match(r"(https?:|mailto:|data:)", href):
            continue
        path, _, frag = href.partition("#")
        path = path.partition("?")[0]
        if path:
            target = Path(os.path.normpath(here / path))
            exists = target.is_dir() if path.endswith("/") else target.is_file()
            if not exists:
                problems.append(f"{href}：文件不存在")
            elif frag and target.suffix == ".html" and f'id="{frag}"' not in target.read_text(encoding="utf-8"):
                problems.append(f"{href}：目标页没有这个锚点")
        elif frag and frag not in page.ids:
            problems.append(f"{href}：本页没有这个锚点")
    return problems


class TeamDocsTest(unittest.TestCase):
    SECTIONS = {
        "flow": "一次运行的经过",
        "declare": "申报智能体",
        "call": "主办方怎样调用你的智能体",
        "ask": "反问和统一答复",
        "environment": "运行环境",
        "time-limit": "时长上限",
        "delivery": "交付要求",
        "groups": "封闭组和开放组",
        "spot-check": "随机抽查",
        "starter-kit": "新手包",
        "self-check": "用练习题自查",
    }

    @classmethod
    def setUpClass(cls):
        if not PAGE.is_file():
            raise AssertionError("缺少页面 site/teams.html")
        cls.page = Page(PAGE)

    # 章节和链接

    def test_required_sections(self):
        for section_id, title in self.SECTIONS.items():
            with self.subTest(section_id):
                self.assertIn(title, self.page.section_title(section_id))

    def test_top_links_back_to_site_home(self):
        backs = [a for a in self.page.anchors if a["attrs"].get("href") == "index.html" and "回到资料站" in a["text"]]
        self.assertTrue(backs, "要有“回到资料站”的链接")
        raw = PAGE.read_text(encoding="utf-8")
        self.assertLess(raw.index("回到资料站"), raw.index("<main"), "“回到资料站”要在正文之前")

    def test_local_links_open(self):
        self.assertEqual(local_link_problems(self.page), [])

    def test_links_to_every_starter_kit_file(self):
        links = self.page.block("starter-kit")["links"]
        for name in KIT_FILES:
            with self.subTest(name):
                self.assertIn("starter-kit/" + name, links)

    def test_points_to_the_runner_its_guide_and_the_rules(self):
        for link in ["../tools/run_agents.py", "../tools/run_agents.md", "../notes/rules.html#_4",
                     "../notes/rules.html#_7", "../notes/rules.html#_8"]:
            with self.subTest(link):
                self.assertIn(link, self.page.links)

    # 与统一运行程序一致

    def test_calling_conventions_are_word_for_word_those_of_the_runner_guide(self):
        guide = GUIDE.read_text(encoding="utf-8")
        phrases = [
            "python3 tools/run_agents.py 运行计划.json",
            "标准输入", "标准输出", "标准错误", "工作目录", "退出状态",
            "[[反问]]", "REPLY_PIPE", "命名管道",
            "POST", "application/json", "application/pdf",
            '{"题目": "题目原文", "往来": []}',
            '{"报告": "报告全文"}',
            '{"反问": "问题"}',
            '{"题目": "题目原文", "往来": [{"反问": "你的问题", "答复": "' + appendix_two_reply() + '"}]}',
            "%PDF", "<!doctype html", "<html", "报告.pdf", "报告.html", "报告.md",
            "20 次", "未交付", "SHA-256",
        ]
        for phrase in phrases:
            with self.subTest(phrase):
                self.assertIn(phrase, guide, "使用说明里应当有这一条约定")
                self.assertIn(phrase, self.page.text, "技术文档应当照使用说明写")

    def test_names_the_checksum_algorithm_once_where_teams_compute_it_themselves(self):
        # 其余地方只说“校验值”；队伍要自己算的那一处点一次算法名，并给出算的命令
        self.assertEqual(self.page.text.count("SHA-256"), 1)
        block = self.page.block("own-checksum")["text"]
        self.assertIn("SHA-256", block)
        self.assertIn("shasum -a 256", block)
        self.assertIn("sha256sum", block)

    def test_declaration_example_is_the_starter_kit_template(self):
        shown = json.loads(self.page.block("declaration-example")["text"])
        template = json.loads((KIT / "申报表模板.json").read_text(encoding="utf-8"))
        self.assertEqual(shown, template)

    def test_ask_back_example_is_the_runner_guides_example(self):
        self.assertEqual(self.page.block("ask-example")["text"].strip(), guide_block("反问约定", "python").strip())

    def test_declaration_covers_every_item_of_appendix_three(self):
        text = self.page.block("declare")["text"]
        template = json.loads((KIT / "申报表模板.json").read_text(encoding="utf-8"))
        for item in appendix_three_items() + list(template):
            with self.subTest(item):
                self.assertIn(item, text)

    def test_ask_section_gives_the_unified_reply(self):
        self.assertIn(appendix_two_reply(), self.page.block("ask")["text"])

    def test_delivery_section_quotes_appendix_one_word_for_word(self):
        self.assertIn(squeeze(appendix_one()), squeeze(self.page.block("delivery-text")["text"]))

    # 〔默认〕条款

    # 依赖规则手册〔默认〕条款的地方，每一处都紧跟着注明（节，条款的写法）
    DEFAULT_TERMS = [
        ("declare", "运行日前 7 天"),
        ("environment", "全部运行由主办方统一进行"),
        ("environment", "故障重跑"),
        ("time-limit", "120 分钟"),
        ("delivery", "链接必须保留"),
        ("groups", "参赛分两组"),
        ("spot-check", "每届随机抽一支队伍"),
    ]

    def test_every_default_term_is_marked_where_it_is_used(self):
        for section_id, term in self.DEFAULT_TERMS:
            with self.subTest(section=section_id, term=term):
                self.assertIn(term + DEFAULT_MARK, self.page.block(section_id)["text"])

    # 视觉规则

    def test_follows_site_visual_rules(self):
        css = "".join(self.page.css)
        raw = PAGE.read_text(encoding="utf-8")
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
        self.assertTrue(self.page.headings)
        for heading in self.page.headings:
            with self.subTest(heading["text"].strip()[:20]):
                self.assertRegex(heading["attrs"].get("class", ""), r"\b(heading|title)-\d\b")

    def test_visible_text_outside_code_has_no_hyphen(self):
        for ch in "-‐–":
            self.assertNotIn(ch, self.page.prose_text, f"可见文字里有连字符“{ch}”")


if __name__ == "__main__":
    unittest.main()
