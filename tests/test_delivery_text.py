"""交付要求和说明的原文（规则手册附录一，"一字不改"）在引用它的各处逐字相同。

期望值只从规则手册附录一取。检查的是引原文的地方：出题手册第八节的题目卡模板（源文件和生成的网页）、
新手包的交付要求文件和练习题的两个版本、参赛队伍技术文档的交付要求一节。只提到交付要求、不引原文的地方不查。
"""
import html
import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, "research-plan", "rules.md")
HANDBOOK_SOURCE = os.path.join(ROOT, "research-plan", "question-handbook.src.html")
HANDBOOK_PAGE = os.path.join(ROOT, "notes", "question-handbook.html")
KIT = os.path.join(ROOT, "site", "starter-kit")
TEAMS = os.path.join(ROOT, "site", "teams.html")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def appendix_one():
    """规则手册附录一的原文：标题之后、附录二之前的全部文字。"""
    return re.search(r"^### 附录一[^\n]*\n(.*?)(?=^### )", read(RULES), re.S | re.M).group(1).strip("\n")


def card_template(path):
    """出题手册第八节的题目卡模板原文。"""
    return html.unescape(re.search(r'<pre id="tpl-card">(.*?)</pre>', read(path), re.S).group(1))


class Paragraphs(HTMLParser):
    """读出 id 为 block_id 的元素里每个段落的文字。"""

    def __init__(self, path, block_id):
        super().__init__(convert_charrefs=True)
        self.block_id, self.depth, self.inside, self.paragraphs = block_id, 0, False, []
        self.feed(read(path))

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("id") == self.block_id:
            self.inside, self.depth = True, 0
        if self.inside:
            self.depth += 1
            if tag == "p":
                self.paragraphs.append("")

    def handle_endtag(self, tag):
        if self.inside:
            self.depth -= 1
            if self.depth == 0:
                self.inside = False

    def handle_data(self, data):
        if self.inside and self.paragraphs:
            self.paragraphs[-1] += data


class DeliveryTextTest(unittest.TestCase):

    def test_appendix_one_is_found(self):
        text = appendix_one()
        self.assertTrue(text.startswith("交付要求：请交付一份书面报告。"))
        self.assertIn("\n\n说明：本题已包含全部信息", text)

    def test_handbook_card_template_appends_appendix_one_word_for_word(self):
        for path in (HANDBOOK_SOURCE, HANDBOOK_PAGE):
            with self.subTest(os.path.relpath(path, ROOT)):
                card = card_template(path)
                part_four = card[card.index("四、"):]
                attached = part_four[part_four.index("\n"):].strip("\n")
                self.assertEqual(attached, appendix_one())

    def test_handbook_says_the_original_is_appendix_one_wherever_it_says_unchanged(self):
        # 手册里说交付要求和说明"一字不改"或"不要改"的每一处，都写明原文以规则手册附录一为准
        text = re.sub(r"<[^>]+>", "", read(HANDBOOK_SOURCE))
        places = [line for line in text.splitlines()
                  if ("交付要求" in line or "四、附在" in line) and ("一字不改" in line or "不要改" in line)]
        self.assertGreaterEqual(len(places), 3)
        for line in places:
            with self.subTest(line.strip()[:40]):
                self.assertIn("以规则手册附录一为准", line)

    def test_starter_kit_files_append_appendix_one_word_for_word(self):
        self.assertEqual(read(os.path.join(KIT, "交付要求.txt")).strip("\n"), appendix_one())
        for version in ("提问版", "裸题版"):
            with self.subTest(version):
                text = read(os.path.join(KIT, "练习题", "淡水湖", f"{version}.txt"))
                self.assertTrue(text.rstrip("\n").endswith("\n\n" + appendix_one()))

    def test_teams_page_quotes_appendix_one_word_for_word(self):
        quoted = [p.strip() for p in Paragraphs(TEAMS, "delivery-text").paragraphs]
        self.assertEqual(quoted, [line for line in appendix_one().splitlines() if line.strip()])


if __name__ == "__main__":
    unittest.main()
