"""检查一份报告是否包含交付要求的五个部分。

用法：

    python3 check_report.py 报告.md [更多报告]

五个部分取自规则手册附录一：主要结论（放在报告开头）、论证与解释、出处、把握程度、
查找与来源说明。说明见同目录的 check_report.md。只用 Python 自带的标准库。

退出状态：0 表示全部合格；1 表示至少一份不合格；2 表示至少一份读不了（例如 PDF）。
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# 规则手册附录一的五个部分，按原文的先后。
PARTS = ["主要结论", "论证与解释", "出处", "把握程度", "查找与来源说明"]
FIRST_PART = "主要结论"

# 名称后面跟着这些符号之一（或者什么也不跟），这一行才算这个部分的标题。
AFTER_NAME = ("：", ":", "（", "(", "　", " ", "—", "，")

# 标题前面的编号，例如“1.”“1、”“一、”“（一）”“第一部分”。
NUMBERING = re.compile(
    r"^(?:\d+\s*[.、．)）]|[一二三四五六七八九十]+\s*[、.．]|[（(][一二三四五六七八九十\d]+[)）]"
    r"|第[一二三四五六七八九十\d]+部分\s*[：:]?)\s*"
)

LINK = re.compile(r"https?://", re.I)


class Unreadable(Exception):
    """这份报告读不了，不做检查。"""


class WebPageLines(HTMLParser):
    """把网页报告拆成一行一行的文字，记下哪些行是标题（h1 至 h6）。"""

    BLOCKS = {"address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt",
              "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
              "li", "main", "nav", "ol", "p", "pre", "section", "summary", "table", "td", "th", "tr", "ul"}
    HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    HIDDEN = {"script", "style", "title", "template", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.current = []
        self.heading_depth = 0
        self.hidden_depth = 0

    def flush(self):
        text = "".join(self.current).strip()
        if text:
            self.lines.append((text, self.heading_depth > 0))
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden_depth += 1
        if tag in self.BLOCKS:
            self.flush()
        if tag in self.HEADINGS:
            self.heading_depth += 1

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.hidden_depth:
            self.hidden_depth -= 1
        if tag in self.BLOCKS:
            self.flush()
        if tag in self.HEADINGS and self.heading_depth:
            self.heading_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.current.append(data.replace("\n", " "))


def markdown_lines(text):
    """把 Markdown 报告拆成行，记下哪些行是标题（# 开头）；代码块里的行不算。"""
    lines = []
    in_code = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        lines.append((stripped, stripped.startswith("#")))
    return lines


def read_report(path):
    """读报告，返回（全文，各行）。格式按开头判断，与统一运行程序判断报告文件类型的办法相同。"""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise Unreadable(f"打不开文件（{error.strerror}）")
    if data.startswith(b"%PDF"):
        raise Unreadable("这是 PDF 文件，本程序读不了 PDF。请检查生成 PDF 之前的 Markdown 或网页原稿")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Unreadable("不是 UTF-8 编码的文字")
    head = text.lstrip()[:64].lower()
    if head.startswith("<!doctype html") or head.startswith("<html"):
        parser = WebPageLines()
        parser.feed(text)
        parser.close()
        parser.flush()
        return text, parser.lines
    return text, markdown_lines(text)


def plain(line):
    """去掉行首的 Markdown 记号、加粗记号和编号，只留文字。"""
    text = line.lstrip("#>*_-+ \t　")
    text = NUMBERING.sub("", text, count=1)
    return text.lstrip("*_ \t　")


def part_of(line, is_heading):
    """这一行若是某个部分的标题，返回部分名称，否则返回 None。"""
    text = plain(line)
    for name in sorted(PARTS, key=len, reverse=True):
        if not text.startswith(name):
            continue
        rest = text[len(name):].lstrip("*_")
        if is_heading or not rest or rest.startswith(AFTER_NAME):
            return name
    return None


def check(lines, text):
    """返回（是否合格，结论，提醒）。"""
    found = {}
    for index, (line, is_heading) in enumerate(lines):
        name = part_of(line, is_heading)
        if name and name not in found:
            found[name] = index
    missing = [name for name in PARTS if name not in found]
    problems = []
    if missing:
        problems.append("缺少：" + "、".join(missing))
    if FIRST_PART in found:
        before = [name for name in PARTS if name in found and found[name] < found[FIRST_PART]]
        if before:
            problems.append(f"{FIRST_PART}不在开头，前面已经有：" + "、".join(before))
    reminders = []
    if not LINK.search(text):
        reminders.append("报告里没有找到可以点开的网址（http:// 或 https:// 开头）。"
                         "出处要给每个关键结论标明网址和取用日期。")
    status = {name: name in found for name in PARTS}
    return status, problems, reminders


def main(argv=None):
    paths = sys.argv[1:] if argv is None else argv
    if not paths or paths[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if paths else 2
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    worst = 0
    for number, path in enumerate(paths):
        if number:
            print()
        print(path)
        try:
            text, lines = read_report(path)
        except Unreadable as reason:
            print(f"  读不了：{reason}。")
            worst = max(worst, 2)
            continue
        status, problems, reminders = check(lines, text)
        for name in PARTS:
            note = "（放在开头）" if name == FIRST_PART else ""
            print(f"  {'有' if status[name] else '缺'}　{name}{note}")
        for reminder in reminders:
            print(f"  提醒：{reminder}")
        if problems:
            print("  结论：不合格。" + "；".join(problems) + "。")
            worst = max(worst, 1)
        else:
            print("  结论：合格")
    return worst


if __name__ == "__main__":
    sys.exit(main())
