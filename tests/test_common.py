"""tools/common.py 的测试：校验值、当前时间、整份替换的写文件。"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import common  # noqa: E402


class ChecksumTest(unittest.TestCase):
    def test_text_checksum_uses_utf8(self):
        self.assertEqual(common.sha256_text("你好"),
                         "670d9743542cae3ea7ebe36af56bd53648b0a1126162e78d81a32934a711302e")
        self.assertEqual(common.sha256_bytes("你好".encode("utf-8")), common.sha256_text("你好"))


class NowTest(unittest.TestCase):
    def test_time_has_a_timezone_and_the_requested_precision(self):
        self.assertRegex(common.now_iso(), r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertRegex(common.now_iso("milliseconds"),
                         r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d$")


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_writes_text_and_creates_missing_folders(self):
        path = os.path.join(self.tmp, "甲", "乙", "页.html")
        common.write_text_atomic(path, "第一行\n第二行")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "第一行\n第二行")
        self.assertEqual(os.listdir(os.path.dirname(path)), ["页.html"])

    def test_a_failed_write_keeps_the_old_file_and_leaves_no_temporary_file(self):
        path = os.path.join(self.tmp, "结果.json")
        common.write_json_atomic(path, {"名次": 1})
        with mock.patch.object(common.os, "replace", side_effect=OSError("磁盘满了")):
            with self.assertRaises(OSError):
                common.write_json_atomic(path, {"名次": 2})
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"名次": 1})
        self.assertEqual(os.listdir(self.tmp), ["结果.json"])

    def test_json_keeps_chinese_ends_with_a_newline_and_uses_the_given_indent(self):
        path = os.path.join(self.tmp, "run.json")
        common.write_json_atomic(path, {"状态": "完成", "列表": [1]}, indent=1)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("完成", text)
        self.assertTrue(text.endswith("}\n"))
        self.assertTrue(re.search(r'^ "列表"', text, re.M))


if __name__ == "__main__":
    unittest.main()
