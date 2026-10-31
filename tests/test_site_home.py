"""资料站首页 site/index.html 接入全部新页面的测试。

检查导航（宽屏导航和手机菜单）、资料库都有全部新页面的入口；页脚有行为准则、联系方式
和数据使用许可，未定的标〔待定〕；首页本地链接都能打开；不再出现过时的规则版本；
首页问答与常见问题页 site/faq.html 的补充说法一致。
运行：python3 -I -m unittest discover -s tests -v
"""
import os
import re
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
HOME = os.path.join(SITE, "index.html")
FAQ = os.path.join(SITE, "faq.html")

# 新页面（相对 site/）和入口文字里必须有的名字
NEW_PAGES = {
    "brief.html": "赛事说明",
    "start.html": "上手",
    "news.html": "公告",
    "faq.html": "常见问题",
    "teams.html": "技术文档",
    "starter-kit/README.md": "新手包",
    "results/index.html": "名次",
    "simulation/questions.html": "题库",
    "simulation/reviews.html": "评审记录",
}

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
HIDDEN = {"style", "script", "svg", "title"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Node:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children = []

    def walk(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.walk()

    def text(self):
        if self.tag in HIDDEN:
            return ""
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def find_all(self, tag):
        return [n for n in self.walk() if n.tag == tag]

    def by_id(self, node_id):
        found = [n for n in self.walk() if n.attrs.get("id") == node_id]
        if len(found) != 1:
            raise AssertionError(f"id 为“{node_id}”的元素应当恰好一个，实际 {len(found)} 个")
        return found[0]

    def anchors(self):
        return [n for n in self.find_all("a") if "href" in n.attrs]

    def links(self):
        out = []
        for n in [self] + list(self.walk()):
            for key in ("href", "src", "srcset"):
                if key in n.attrs and n.tag != "use":
                    out.append(n.attrs[key])
        return out


class Tree(HTMLParser):
    """把页面读成一棵元素树。"""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.root = Node("#root", {}, None)
        self.cur = self.root
        self.feed(read(path))
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def path_of(href):
    return href.partition("#")[0].partition("?")[0]


class HomeEntries(unittest.TestCase):
    """导航和资料库里的新页面入口。"""

    @classmethod
    def setUpClass(cls):
        cls.home = Tree(HOME).root

    def assert_has_entries(self, container, where):
        anchors = container.anchors()
        for page, name in NEW_PAGES.items():
            with self.subTest(where=where, page=page):
                hits = [a for a in anchors if path_of(a.attrs["href"]) == page and name in a.text()]
                self.assertTrue(hits, f"{where}里没有写着“{name}”、指向 {page} 的入口")

    def test_wide_screen_nav_links_to_every_new_page(self):
        self.assert_has_entries(self.home.by_id("nav"), "宽屏导航")

    def test_phone_menu_links_to_every_new_page(self):
        self.assert_has_entries(self.home.by_id("menu-panel"), "手机菜单")

    def test_library_has_a_competition_group_with_every_new_page(self):
        library = self.home.by_id("library")
        groups = [g for g in library.walk() if "data-group" in g.attrs]
        titled = [g for g in groups if any(h.text().strip() == "比赛" for h in g.find_all("h3"))]
        self.assertEqual(len(titled), 1, "资料库要有且只有一组叫“比赛”")
        self.assert_has_entries(titled[0], "资料库的“比赛”组")

    def test_library_intro_counts_the_groups(self):
        library = self.home.by_id("library")
        groups = [g for g in library.walk() if "data-group" in g.attrs]
        numerals = "零一二三四五六七八九十"
        intro = next(p.text() for p in library.find_all("p") if "按用途" in p.text())
        self.assertIn(f"分成{numerals[len(groups)]}组", intro)


class HomeFooter(unittest.TestCase):
    """页脚：行为准则、联系方式、数据使用许可。都还没有定，各自标〔待定〕。"""

    ITEMS = ["行为准则", "联系方式", "数据使用许可"]

    @classmethod
    def setUpClass(cls):
        footers = Tree(HOME).root.find_all("footer")
        if len(footers) != 1:
            raise AssertionError(f"首页应当恰好一个页脚，实际 {len(footers)} 个")
        cls.footer = footers[0]

    def test_footer_lists_conduct_contact_and_data_license_marked_undecided(self):
        items = self.footer.find_all("li")
        for name in self.ITEMS:
            with self.subTest(name):
                hits = [li for li in items if name in li.text()]
                self.assertEqual(len(hits), 1, f"页脚要有一项“{name}”")
                self.assertIn("〔待定〕", hits[0].text())

    def test_footer_invents_no_email_address(self):
        self.assertNotIn("@", self.footer.text())
        self.assertFalse([h for h in self.footer.links() if h.startswith("mailto:")])



class HomeLinks(unittest.TestCase):
    """首页的每个本地链接都能打开：文件或文件夹存在，锚点在目标页上。"""

    def test_every_local_link_opens(self):
        tree = Tree(HOME)
        ids = {n.attrs["id"] for n in tree.root.walk() if n.attrs.get("id")}
        problems = []
        for href in tree.root.links():
            if re.match(r"(https?:|mailto:|data:)", href):
                continue
            path, _, frag = href.partition("#")
            path = path.partition("?")[0]
            if not path:
                if frag and frag not in ids:
                    problems.append(f"{href}：本页没有这个锚点")
                continue
            target = os.path.normpath(os.path.join(SITE, path))
            exists = os.path.isdir(target) if path.endswith("/") else os.path.isfile(target)
            if not exists:
                problems.append(f"{href}：文件不存在")
            elif frag and target.endswith(".html") and f'id="{frag}"' not in read(target):
                problems.append(f"{href}：目标页没有这个锚点")
        self.assertEqual(problems, [])


class HomeIsCurrent(unittest.TestCase):
    """首页上的说法与现行规则一致。"""

    @classmethod
    def setUpClass(cls):
        cls.home = Tree(HOME).root
        cls.faq = Tree(FAQ).root

    def test_no_outdated_rules_draft(self):
        for old in ["草案第 2 版", "草案第 3 版"]:
            self.assertFalse(old in self.home.text(), f"首页还写着规则手册“{old}”")

    def test_rules_card_names_draft_four(self):
        cards = [a for a in self.home.by_id("library").anchors() if path_of(a.attrs["href"]) == "../notes/rules.html"]
        self.assertTrue(cards)
        self.assertIn("草案第 4 版", cards[0].text())

    def answers(self, root):
        """问题文字 → 答案元素。"""
        out = {}
        for d in root.find_all("details"):
            summary = d.find_all("summary")[0].text().strip()
            out[summary] = d
        return out

    def test_home_questions_carry_the_faq_page_supplements(self):
        """常见问题页给首页原有的问答加了“补充”（开放组、模拟评委），首页同一问也要有同样的补充。"""
        home = self.answers(self.home.by_id("faq"))
        faq = self.answers(self.faq)
        checked = 0
        for question, answer in faq.items():
            notes = [p.text().strip() for p in answer.find_all("p") if p.text().strip().startswith("补充")]
            if not notes or question not in home:
                continue
            for note in notes:
                checked += 1
                with self.subTest(question):
                    self.assertIn(note, [p.text().strip() for p in home[question].find_all("p")])
        self.assertGreaterEqual(checked, 2, "常见问题页里至少有开放组和模拟评委两条补充")

    def test_appeal_period_is_marked_as_a_default_term(self):
        # 规则手册第九节：临时名次公布后有〔7 天，默认〕申诉期
        text = self.home.text()
        self.assertIn("〔7 天，默认〕申诉期", text)
        self.assertNotIn("7 天申诉期", text)

    def test_says_language_models_not_ai(self):
        # 只查单独的“AI”，公司名 OpenAI 不算
        self.assertNotRegex(self.home.text(), r"(?<![A-Za-z])AI(?![A-Za-z])")

    def test_home_faq_points_to_the_full_faq_page(self):
        self.assertIn("faq.html", [path_of(h) for h in self.home.by_id("faq").links()])



class HomeStyle(unittest.TestCase):
    """新加的导航、资料库和页脚沿用资料站的视觉规则（见共用说明）。"""

    SPACING = {0, 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96}
    FONT_SIZES = {12, 14, 16, 18, 20, 24, 30, 36, 48, 60}
    LINE_HEIGHTS = {16, 20, 24, 28, 32, 36, 40, 48, 60}
    RADII = {2, 4, 6, 8, 12, 16, 24, 9999}
    # 首页原有的专名，连字符是名字的一部分
    NAMES = ["BrowseComp-Plus", "landing-page-design"]

    @classmethod
    def setUpClass(cls):
        tree = Tree(HOME).root
        cls.css = "".join(c for n in tree.find_all("style") for c in n.children if isinstance(c, str))
        cls.text = tree.text()

    def test_sizes_come_from_the_fixed_scales(self):
        checks = [
            (r"(?:margin|padding)[\w-]*|gap|row-gap|column-gap", self.SPACING, "间距"),
            (r"font-size", self.FONT_SIZES, "字号"),
            (r"line-height", self.LINE_HEIGHTS, "行高"),
            (r"border-radius", self.RADII, "圆角"),
        ]
        for prop, allowed, label in checks:
            for value in re.findall(r"(?<![\w-])(?:" + prop + r")\s*:\s*([^;}]+)", self.css):
                for n in re.findall(r"(\d+(?:\.\d+)?)px", value):
                    with self.subTest(label=label, value=value.strip()):
                        self.assertIn(float(n), allowed)

    def test_motion_uses_the_site_curve(self):
        self.assertIn("cubic-bezier(0.22, 1, 0.36, 1)", self.css)
        self.assertNotRegex(self.css, r"\bease-(?:in|out|in-out)\b")

    def test_visible_text_has_no_hyphen_outside_proper_names(self):
        text = self.text
        for name in self.NAMES:
            text = text.replace(name, "")
        for ch in "-‐–":
            self.assertNotIn(ch, text, f"可见文字里有连字符“{ch}”")


if __name__ == "__main__":
    unittest.main()
