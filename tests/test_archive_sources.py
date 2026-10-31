"""网页存档程序 tools/archive_sources.py 的测试。

只通过命令行测试：--list 只列出提取到的网址；--out 取回并写出存档目录。
取回的测试只用本机测试服务器（在线程中运行），不连外网。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "archive_sources.py")
PILOT_REPORTS = os.path.join(ROOT, "research-plan", "stage5-pilot", "reports")


def run_tool(*args):
    return subprocess.run(
        [sys.executable, "-I", TOOL, *args],
        capture_output=True, text=True, timeout=60,
    )


def write_report(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def listed_urls(report_path):
    result = run_tool(report_path, "--list")
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return [line for line in result.stdout.splitlines() if line]


class ExtractFromMarkdown(unittest.TestCase):
    def test_links_bare_urls_and_autolinks_are_listed_once_in_order(self):
        text = (
            "# 报告\n\n"
            "结论一见 [欧盟公报](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)。\n"
            "结论二见 https://example.org/report.pdf，另见 <https://example.com/a?x=1&y=2>.\n"
            "嵌套方括号的链接 [[来源](https://example.net/path_(note))] 也算。\n"
            "同一页面带不同锚点只算一次：https://example.org/report.pdf#page=3 。\n"
            "图片不算被引网页：![图标](https://icons.example/favicon.ico)\n"
            "[1]: https://reference.example/def \"参考\"\n"
        )
        with tempfile.TemporaryDirectory() as d:
            urls = listed_urls(write_report(d, "report.md", text))
        self.assertEqual(urls, [
            "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
            "https://example.org/report.pdf",
            "https://example.com/a?x=1&y=2",
            "https://example.net/path_(note)",
            "https://reference.example/def",
        ])


class ExtractFromHtml(unittest.TestCase):
    def test_anchor_hrefs_and_bare_urls_in_text_are_listed_once_in_order(self):
        text = (
            "<!doctype html><html><head>"
            '<link rel="stylesheet" href="https://cdn.example/style.css">'
            "<script>var u = 'https://tracker.example/x';</script>"
            "</head><body>"
            '<p>结论一见 <a href="https://example.org/a?x=1&amp;y=2">来源</a>。</p>'
            '<p><img src="https://icons.example/logo.png"> 另见 https://example.net/b，'
            '<a href="#top">回到顶部</a> <a href="mailto:x@example.org">来信</a> '
            '<a href="notes.html">本地页</a></p>'
            '<p><a href="https://example.org/a?x=1&y=2#sec">同一页</a>'
            '<a href="http://plain.example/c">c</a></p>'
            "</body></html>"
        )
        with tempfile.TemporaryDirectory() as d:
            urls = listed_urls(write_report(d, "report.html", text))
        self.assertEqual(urls, [
            "https://example.org/a?x=1&y=2",
            "https://example.net/b",
            "http://plain.example/c",
        ])


class ExtractFromPilotReports(unittest.TestCase):
    """第五阶段试评的真实报告，只做离线提取，不取回。"""

    def test_report_E_lists_its_six_cited_pages(self):
        urls = listed_urls(os.path.join(PILOT_REPORTS, "E.md"))
        self.assertEqual(sorted(urls), sorted([
            "https://creatoreconomy.so/p/an-opinionated-guide-on-which-ai-model-2025",
            "https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/",
            "https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research",
            "https://www.lib.szu.edu.cn/sites/szulib/files/2025-03/"
            "清华大学第四弹：DeepSeek+DeepResearch：让科研像聊天一样简单-.pdf",
            "https://m.zhiding.cn/article/3169361.htm",
            "https://www.laksn.com/top-generative-ai-models-comparison-chatgpt-deepseek-claude-and-more",
        ]))

    def test_report_D_source_icons_are_not_cited_pages(self):
        self.assertEqual(listed_urls(os.path.join(PILOT_REPORTS, "D.md")), [])


PAGE_BODY = b"<html><body>archived page</body></html>\n"
PAGE_SHA256 = "7d8c7a1a19b3c58130832fcc2be71fd59a1cb99dcae0bf64311f0b27f513bc2c"
ENTRY_FIELDS = {
    "url", "final_url", "status", "content_type", "bytes",
    "sha256", "file", "fetched_at", "error",
}
UTC_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/page":
            self._reply(200, "text/html; charset=utf-8", PAGE_BODY)
        elif self.path == "/old":
            self.send_response(302)
            self.send_header("Location", "/page")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/missing":
            self._reply(404, "text/plain", b"not found\n")
        elif self.path == "/slow":
            time.sleep(2)
            self._reply(200, "text/plain", b"too late\n")
        else:
            self._reply(500, "text/plain", b"unexpected path\n")

    def _reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # 客户端超时放弃后，慢页面写回时连接已断开，不必打印


class ArchiveWithLocalServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _QuietServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = self._dir.name
        self.out = os.path.join(self.dir, "archive")

    def tearDown(self):
        self._dir.cleanup()

    def archive(self, report_text, *extra):
        report = write_report(self.dir, "report.md", report_text)
        result = run_tool(report, "--out", self.out, *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.out, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_successful_fetch_is_saved_under_its_checksum(self):
        manifest = self.archive(f"见 [来源]({self.base}/page)。\n")
        [entry] = manifest["entries"]
        self.assertEqual(set(entry), ENTRY_FIELDS)
        self.assertEqual(entry["url"], f"{self.base}/page")
        self.assertEqual(entry["final_url"], f"{self.base}/page")
        self.assertEqual(entry["status"], 200)
        self.assertEqual(entry["content_type"], "text/html; charset=utf-8")
        self.assertEqual(entry["bytes"], len(PAGE_BODY))
        self.assertEqual(entry["sha256"], PAGE_SHA256)
        self.assertRegex(entry["fetched_at"], UTC_TIME)
        self.assertIsNone(entry["error"])
        self.assertEqual(entry["file"], f"content/{PAGE_SHA256}.html")
        with open(os.path.join(self.out, entry["file"]), "rb") as f:
            self.assertEqual(f.read(), PAGE_BODY)

    def test_redirect_is_followed_and_final_url_recorded(self):
        manifest = self.archive(f"见 {self.base}/old 。\n")
        [entry] = manifest["entries"]
        self.assertEqual(
            (entry["url"], entry["final_url"], entry["status"], entry["sha256"], entry["error"]),
            (f"{self.base}/old", f"{self.base}/page", 200, PAGE_SHA256, None),
        )

    def test_not_found_records_status_and_reason_and_keeps_the_error_page(self):
        manifest = self.archive(f"见 {self.base}/missing 。\n")
        [entry] = manifest["entries"]
        self.assertEqual(set(entry), ENTRY_FIELDS)
        self.assertEqual(entry["status"], 404)
        self.assertIn("404", entry["error"])
        self.assertEqual(entry["sha256"],
                         "709009e02c8e364113b28205aadde30cce270d709073f28153c85fdc5036c96d")
        self.assertTrue(os.path.exists(os.path.join(self.out, entry["file"])))

    def test_timeout_records_reason_and_the_next_url_is_still_fetched(self):
        manifest = self.archive(
            f"先见 {self.base}/slow ，再见 {self.base}/page 。\n", "--timeout", "0.5")
        slow, page = manifest["entries"]
        self.assertEqual(set(slow), ENTRY_FIELDS)
        self.assertIn("超时", slow["error"])
        self.assertEqual((slow["status"], slow["sha256"], slow["file"]), (None, None, None))
        self.assertRegex(slow["fetched_at"], UTC_TIME)
        self.assertEqual((page["status"], page["sha256"]), (200, PAGE_SHA256))

    def test_content_over_the_size_limit_is_not_saved(self):
        manifest = self.archive(f"见 {self.base}/page 。\n", "--max-bytes", "10")
        [entry] = manifest["entries"]
        self.assertIn("大小上限", entry["error"])
        self.assertEqual((entry["sha256"], entry["file"]), (None, None))
        self.assertEqual(os.listdir(os.path.join(self.out, "content")), [])

    def test_an_earlier_archive_is_never_overwritten(self):
        first = self.archive(f"见 {self.base}/page 。\n")
        report = write_report(self.dir, "report.md", f"见 {self.base}/missing 。\n")
        again = run_tool(report, "--out", self.out)
        self.assertNotEqual(again.returncode, 0)
        with open(os.path.join(self.out, "manifest.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), first)


class UsageDocument(unittest.TestCase):
    PATH = os.path.join(ROOT, "tools", "archive_sources.md")

    def setUp(self):
        with open(self.PATH, encoding="utf-8") as f:
            self.text = f.read()

    def test_has_the_required_sections(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        for heading in ["用法", "网址怎样提取", "存档目录和清单", "失败怎样记录", "不做的事"]:
            self.assertIn(heading, headings)

    def test_explains_every_option_and_manifest_field(self):
        names = ["--list", "--out", "--timeout", "--max-bytes", *sorted(ENTRY_FIELDS)]
        for name in names:
            self.assertIn(f"`{name}`", self.text)

    def test_local_links_open(self):
        prose = re.sub(r"```.*?```", "", self.text, flags=re.S)
        prose = re.sub(r"`[^`]*`", "", prose)  # 代码里的链接写法只是示例
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", prose):
            if not re.match(r"https?://", target):
                path = os.path.normpath(os.path.join(os.path.dirname(self.PATH), target))
                self.assertTrue(os.path.exists(path), target)


if __name__ == "__main__":
    unittest.main()
