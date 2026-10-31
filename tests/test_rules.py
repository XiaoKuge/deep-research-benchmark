"""规则手册：源文件 research-plan/rules.md 和生成的网页 notes/rules.html。

检查草案第 3 版的四条〔默认〕新规则、状态行、附录五《版本变更记录》，
以及网页已经重新生成。运行：python3 -I -m unittest discover -s tests -v
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_MD = os.path.join(ROOT, "research-plan", "rules.md")
RULES_HTML = os.path.join(ROOT, "notes", "rules.html")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def sections(text, level):
    """按某一级标题切开，返回 {标题: 该标题下直到同级或更高一级标题之前的文字}。"""
    marker = "#" * level + " "
    result, title, lines = {}, None, []
    for line in text.splitlines():
        m = re.match(r"(#+) ", line)
        if m and len(m.group(1)) <= level:
            if title is not None:
                result[title] = "\n".join(lines)
            title = line[len(marker):].strip() if line.startswith(marker) else None
            lines = []
        elif title is not None:
            lines.append(line)
    if title is not None:
        result[title] = "\n".join(lines)
    return result


def section_starting(text, level, prefix):
    for title, body in sections(text, level).items():
        if title.startswith(prefix):
            return body
    raise AssertionError(f"找不到以“{prefix}”开头的标题")


def rule_paragraph(body, label):
    """取以加粗标签开头的那一段，连同紧跟在它后面的列表。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body)]
    found = [i for i, p in enumerate(paras) if re.match(r"(- )?\*\*" + re.escape(label), p)]
    if len(found) != 1:
        raise AssertionError(f"“{label}”应当恰好出现一次，实际 {len(found)} 次")
    i = found[0]
    block = [paras[i]]
    for p in paras[i + 1:]:
        if not re.match(r"(- |\d+\. )", p):
            break
        block.append(p)
    return "\n\n".join(block)


class NewRules(unittest.TestCase):
    def setUp(self):
        self.text = read(RULES_MD)

    def test_mutual_review_in_appeals_section(self):
        body = section_starting(self.text, 2, "九、申诉与复核")
        para = rule_paragraph(body, "互查〔默认〕")
        for words in ["所有队伍的报告", "全部判定", "别家", "具体判定", "证据"]:
            self.assertIn(words, para)

    def test_random_rerun_in_run_section(self):
        body = section_starting(self.text, 2, "五、运行")
        line = [l for l in body.splitlines() if l.startswith("- **随机抽查〔默认〕。**")]
        self.assertEqual(len(line), 1)
        for words in ["随机抽一支队伍", "冻结申报的版本", "重跑一道题", "复核包", "第十节"]:
            self.assertIn(words, line[0])

    def test_random_rerun_mismatch_has_a_penalty(self):
        body = section_starting(self.text, 2, "十、违规与处理")
        rows = [l for l in body.splitlines() if l.startswith("| 随机抽查")]
        self.assertEqual(len(rows), 1)

    def test_one_rule_version_per_season_in_scope_section(self):
        body = section_starting(self.text, 2, "范围、状态与依据")
        line = [l for l in body.splitlines() if l.startswith("- **规则版本〔默认〕。**")]
        self.assertEqual(len(line), 1)
        for words in ["每届", "开始前", "届中不改", "名次注明", "附录五"]:
            self.assertIn(words, line[0])

    def test_closed_and_open_groups_in_entry_section(self):
        body = section_starting(self.text, 2, "二、参赛智能体：冻结与申报")
        para = rule_paragraph(body, "封闭组和开放组〔默认〕")
        for words in ["题目原文原样", "主名次只在封闭组内排", "看到题目后调整",
                      "单独公布", "不与封闭组比较", "申报", "调整内容", "公开"]:
            self.assertIn(words, para)

    def test_undeclared_open_group_adjustment_has_a_penalty(self):
        body = section_starting(self.text, 2, "十、违规与处理")
        rows = [l for l in body.splitlines() if l.startswith("| 开放组")]
        self.assertEqual(len(rows), 1)


class VersionChangesAppendix(unittest.TestCase):
    # 日期取自各版的源文件：规则手册 rules.md，评法 stage4-design.md、stage4-rubric.md、stage5-report.md
    ENTRIES = [
        ("规则手册草案第 1 版", "2026 年 10 月 30 日"),
        ("规则手册草案第 2 版", "2026 年 10 月 30 日"),
        ("规则手册草案第 3 版", "2026 年 10 月 30 日"),
        ("评法第 1.0 版", "2026 年 10 月 29 日"),
        ("评法第 1.1 版", "2026 年 10 月 29 日"),
        ("评法第 1.2 版", "2026 年 10 月 30 日"),
    ]

    def setUp(self):
        appendix = section_starting(read(RULES_MD), 2, "附录")
        titles = [t for t in sections(appendix, 3) if t.startswith("附录五")]
        self.assertEqual(len(titles), 1)
        self.assertIn("版本变更记录", titles[0])
        self.body = sections(appendix, 3)[titles[0]]

    def test_each_version_says_what_changed_and_why(self):
        for label, date in self.ENTRIES:
            with self.subTest(label):
                entry = rule_paragraph(self.body, label)
                self.assertIn(date, entry.split("\n")[0])
                for part in ["改了什么。", "为什么。"]:
                    m = re.search(r"^- \*\*" + part + r"\*\*(.*)$", entry, re.M)
                    self.assertIsNotNone(m, f"{label} 缺少“{part}”")
                    self.assertGreater(len(m.group(1).strip()), 10)


class StatusLine(unittest.TestCase):
    def test_status_says_draft_three(self):
        scope = section_starting(read(RULES_MD), 2, "范围、状态与依据")
        status = [l for l in scope.splitlines() if l.startswith("- **状态。**")]
        self.assertEqual(len(status), 1)
        self.assertIn("草案第 3 版", status[0])


class GeneratedPage(unittest.TestCase):
    def setUp(self):
        self.html = read(RULES_HTML)

    def heading_ids(self):
        return {m.group(1): re.sub(r"<[^>]+>", "", m.group(2)).strip()
                for m in re.finditer(r'<h[1-6] id="([^"]+)">(.*?)</h[1-6]>', self.html)}

    def test_page_was_regenerated_from_draft_three(self):
        for words in ["草案第 3 版", "互查〔默认〕", "附录五"]:
            self.assertTrue(words in self.html, f"网页里没有“{words}”，请运行 render_plan.py")

    def test_table_of_contents_lists_the_version_changes_appendix(self):
        toc = re.search(r'<nav class="toc">(.*?)</nav>', self.html, re.S).group(1)
        links = re.findall(r'<a href="#([^"]+)">([^<]+)</a>', toc)
        found = [anchor for anchor, text in links if "版本变更记录" in text]
        self.assertEqual(len(found), 1)
        self.assertIn("版本变更记录", self.heading_ids()[found[0]])

    def test_anchors_used_by_other_pages_still_point_to_the_same_sections(self):
        # 资料站的架构图和"一道题走完全程"页面用这些锚点链接规则手册
        expected = {
            "_4": "二、参赛智能体：冻结与申报", "_5": "三、题目", "_6": "四、深度地图",
            "_7": "五、运行", "_9": "七、评审", "_10": "八、名次与公布", "_11": "九、申诉与复核",
        }
        ids = self.heading_ids()
        for anchor, title in expected.items():
            self.assertEqual(ids.get(anchor), title)

    def test_local_links_open(self):
        ids = self.heading_ids()
        notes = os.path.dirname(RULES_HTML)
        for href in re.findall(r'href="([^"]+)"', self.html):
            if re.match(r"(https?:|mailto:)", href):
                continue
            path, _, frag = href.partition("#")
            with self.subTest(href):
                if path:
                    target = os.path.normpath(os.path.join(notes, path))
                    self.assertTrue(os.path.isfile(target), target)
                    if frag:
                        self.assertIn(f'id="{frag}"', read(target))
                else:
                    self.assertIn(frag, ids)


if __name__ == "__main__":
    unittest.main()
