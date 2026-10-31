"""新手包 site/starter-kit/ 的测试。

只从对外接口检查：新手包里的文件、统一运行程序读取申报表模板和示例运行计划的结果、
示例智能体交出的报告、检查报告的小程序在命令行上的结论。
期望值取自独立来源：规则手册附录一、附录二，出题手册第四节实例一。
运行：python3 -I -m unittest discover -s tests -v
"""

import csv
import datetime
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "site" / "starter-kit"
RULES = ROOT / "research-plan" / "rules.md"
HANDBOOK = ROOT / "research-plan" / "question-handbook.src.html"
RUNNER = ROOT / "tools" / "run_agents.py"
CHECKER = KIT / "check_report.py"

# 测试里把时长上限设成 6 秒：示例智能体立即交付，万一卡住也很快停下。
SHORT_LIMIT_MINUTES = 0.1


def appendix_one():
    """规则手册附录一：统一交付要求和说明的原文。"""
    lines = RULES.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("### 附录一"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("#"))
    return "\n".join(lines[start + 1:end]).strip()


def five_parts():
    """附录一列出的五个必备部分的名称，按原文的先后。"""
    names = re.findall(r"^\d\. ([^：。]+)", appendix_one(), re.M)
    assert len(names) == 5, names
    return names


def appendix_two_reply():
    """规则手册附录二：统一答复原文。"""
    lines = RULES.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("### 附录二"))
    body = next(line for line in lines[start + 1:] if "一律回复：" in line)
    return body.split("一律回复：", 1)[1].strip()


def handbook_lake_versions():
    """出题手册第四节实例一（淡水湖）交给智能体的两个版本的原文。"""
    source = HANDBOOK.read_text(encoding="utf-8")
    section = source.split('id="example-lake"', 1)[1].split("<h2", 1)[0]
    versions = {}
    for version in ("提问版", "裸题版"):
        card = section.split(f"<span>第一题　{version}</span>", 1)[1]
        text = re.search(r"<dd>(.*?)</dd>", card, re.S).group(1)
        assert "<" not in text, "原文里不应当有标记"
        versions[version] = html.unescape(text)
    return versions

# 新手包应有的文件（相对 site/starter-kit/）
KIT_FILES = [
    "README.md",
    "申报表模板.json",
    "系统提示词.md",
    "agent.py",
    "运行计划.json",
    "练习题/淡水湖/提问版.txt",
    "练习题/淡水湖/裸题版.txt",
    "交付要求.txt",
    "check_report.py",
    "check_report.md",
]
KIT_GUIDES = ["README.md", "check_report.md"]
DEFAULT_MARK = "〔默认〕，以主办方确认为准"


def markdown_link_targets(path):
    text = path.read_text(encoding="utf-8")
    return [target for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text) if "://" not in target]


class KitContentsTest(unittest.TestCase):
    def test_every_file_is_there(self):
        for name in KIT_FILES:
            with self.subTest(name):
                self.assertTrue((KIT / name).is_file())

    def test_readme_lists_every_file(self):
        text = (KIT / "README.md").read_text(encoding="utf-8")
        for name in KIT_FILES[1:]:
            with self.subTest(name):
                self.assertIn(name, text)

    def test_local_links_in_the_kit_guides_open(self):
        for guide in KIT_GUIDES:
            targets = markdown_link_targets(KIT / guide)
            self.assertTrue(targets, guide)
            for target in targets:
                with self.subTest(guide=guide, target=target):
                    self.assertTrue((KIT / guide).parent.joinpath(target).exists())

    def test_readme_gives_the_commands_to_run_the_example_and_check_the_reports(self):
        text = (KIT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 tools/run_agents.py site/starter-kit/运行计划.json", text)
        self.assertIn("python3 site/starter-kit/check_report.py", text)

    def test_readme_marks_the_default_time_limit(self):
        text = (KIT / "README.md").read_text(encoding="utf-8")
        self.assertIn("120 分钟" + DEFAULT_MARK, text)

    def test_checker_guide_names_the_five_parts_and_the_exit_statuses(self):
        text = (KIT / "check_report.md").read_text(encoding="utf-8")
        self.assertIn("python3 check_report.py", text)
        for name in five_parts():
            with self.subTest(name):
                self.assertIn(name, text)
        for status in ("0", "1", "2"):
            with self.subTest(status=status):
                self.assertRegex(text, rf"\|\s*{status}\s*\|")


class PracticeQuestionTest(unittest.TestCase):
    def test_practice_files_are_the_handbook_text_unchanged_followed_by_appendix_one(self):
        for version, original in handbook_lake_versions().items():
            with self.subTest(version):
                text = (KIT / "练习题" / "淡水湖" / f"{version}.txt").read_text(encoding="utf-8")
                self.assertTrue(text.startswith(original + "\n"), "开头应当是出题手册的原文，一字不改")
                self.assertEqual(text[len(original):].strip(), appendix_one())

    def test_delivery_requirement_file_is_appendix_one_word_for_word(self):
        text = (KIT / "交付要求.txt").read_text(encoding="utf-8")
        self.assertEqual(text.strip(), appendix_one())


class ExampleRun:
    """把新手包复制到临时目录，时长上限改短，用统一运行程序跑一遍示例运行计划。"""

    def __init__(self, folder):
        self.kit = Path(folder) / "starter-kit"
        shutil.copytree(KIT, self.kit, ignore=shutil.ignore_patterns("运行结果", "__pycache__"))
        self.plan_path = self.kit / "运行计划.json"
        self.plan = json.loads(self.plan_path.read_text(encoding="utf-8"))
        self.plan["时长上限分钟"] = SHORT_LIMIT_MINUTES
        self.plan_path.write_text(json.dumps(self.plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self.result = subprocess.run(
            [sys.executable, "-I", str(RUNNER), str(self.plan_path)],
            capture_output=True, text=True, timeout=60,
        )
        self.day = self.kit / self.plan.get("输出目录", "运行结果") / datetime.date.today().isoformat()

    def records(self):
        with open(self.day / "运行记录.csv", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def reports(self):
        return [self.day / row["文件名"] for row in self.records() if row["文件名"] != "未交付"]

    def logs(self):
        return [json.loads(path.read_text(encoding="utf-8")) for path in self.day.rglob("运行日志.json")]


class ExampleRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.example = ExampleRun(cls.folder.name)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_runner_accepts_the_declaration_template_and_the_example_plan(self):
        self.assertEqual(self.example.result.returncode, 0, self.example.result.stdout + self.example.result.stderr)

    def test_both_versions_of_the_practice_question_are_delivered(self):
        rows = self.example.records()
        self.assertEqual(sorted((row["题目"], row["版本"]) for row in rows),
                         [("淡水湖", "提问版"), ("淡水湖", "裸题版")])
        for row in rows:
            with self.subTest(row["版本"]):
                self.assertNotEqual(row["文件名"], "未交付")
                self.assertEqual(row["输入校验值是否一致"], "一致")

    def test_example_plan_gives_the_checksums_of_the_practice_files(self):
        logs = self.example.logs()
        self.assertEqual(len(logs), 2)
        for log in logs:
            with self.subTest(log["版本"]):
                self.assertEqual(log["题目文本校验值来源"], "运行计划")
                self.assertEqual(log["输入校验值是否一致"], "一致")

    def test_example_agent_asks_back_once_and_gets_the_unified_reply(self):
        for row in self.example.records():
            with self.subTest(row["版本"]):
                self.assertTrue(row["智能体是否提问，问了什么"].startswith("是："))
                self.assertNotIn("；", row["智能体是否提问，问了什么"], "示例只反问一次")
        for path in self.example.reports():
            with self.subTest(path.parent.name):
                self.assertIn(appendix_two_reply(), path.read_text(encoding="utf-8"))

    def test_example_report_says_it_is_an_example_and_calls_no_model(self):
        for path in self.example.reports():
            with self.subTest(path.parent.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("示例", text.splitlines()[0])
                self.assertIn("没有调用任何模型", text)


    def test_example_reports_pass_the_report_checker(self):
        reports = self.example.reports()
        self.assertEqual(len(reports), 2)
        result = run_checker(*reports)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def run_checker(*paths):
    return subprocess.run([sys.executable, "-I", str(CHECKER), *map(str, paths)],
                          capture_output=True, text=True, timeout=30)


PART_TEXT = {
    "主要结论": "中国最大的淡水湖是鄱阳湖，按丰水期的面积算。",
    "论证与解释": "按枯水期算，排名会变，所以要写明口径。",
    "出处": "江西省水利厅，https://example.org/poyang ，取用日期 2026 年 10 月 30 日。",
    "把握程度": "按面积算是鄱阳湖，把握高；枯水期的排名，把握中等。",
    "查找与来源说明": "查了水利部门的公报和湖泊调查报告；缺少最近一年的遥感数据。",
}


def markdown_report(parts, link=True):
    lines = ["# 中国最大的淡水湖"]
    for name in parts:
        text = PART_TEXT[name] if link else PART_TEXT[name].replace("https://example.org/poyang ，", "")
        lines += ["", f"## {name}", "", text]
    return "\n".join(lines) + "\n"


def html_report(parts):
    sections = "".join(f"<h2>{name}</h2><p>{PART_TEXT[name]}</p>" for name in parts)
    return f"<!doctype html><html><head><title>报告</title></head><body><h1>中国最大的淡水湖</h1>{sections}</body></html>"


def verdict(result):
    """检查小程序输出里的结论那一行。"""
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("结论：")]
    assert len(lines) == 1, result.stdout + result.stderr
    return lines[0]


class CheckReportTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def check(self, content, name="报告.md"):
        path = Path(self.folder.name) / name
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return run_checker(path)

    def test_report_with_all_five_parts_passes(self):
        result = self.check(markdown_report(five_parts()))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(verdict(result), "结论：合格")

    def test_report_missing_a_part_fails_and_names_the_missing_part(self):
        for missing in five_parts():
            with self.subTest(missing):
                result = self.check(markdown_report([p for p in five_parts() if p != missing]))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertTrue(verdict(result).startswith("结论：不合格"))
                self.assertIn(missing, verdict(result))

    def test_main_conclusions_not_at_the_start_fails(self):
        parts = five_parts()
        result = self.check(markdown_report(parts[1:2] + parts[:1] + parts[2:]))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("主要结论", verdict(result))
        self.assertIn("开头", verdict(result))

    def test_part_names_only_mentioned_in_sentences_do_not_count(self):
        text = "# 中国最大的淡水湖\n\n" + "".join(f"{name}写在这句话里，没有单独成为一个部分。\n" for name in five_parts())
        result = self.check(text)
        self.assertEqual(result.returncode, 1, result.stdout)
        for name in five_parts():
            self.assertIn(name, verdict(result))

    def test_parts_written_as_bold_labels_count(self):
        text = "\n\n".join(f"**{name}**：{PART_TEXT[name]}" for name in five_parts()) + "\n"
        result = self.check(text)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_numbered_part_titles_count(self):
        text = "\n\n".join(f"## {i}. {name}\n\n{PART_TEXT[name]}" for i, name in enumerate(five_parts(), 1))
        result = self.check(text)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_web_page_report_is_checked_the_same_way(self):
        self.assertEqual(self.check(html_report(five_parts()), "报告.html").returncode, 0)
        result = self.check(html_report(five_parts()[:-1]), "报告.html")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(five_parts()[-1], verdict(result))

    def test_pdf_report_cannot_be_checked(self):
        result = self.check(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "报告.pdf")
        self.assertEqual(result.returncode, 2)
        self.assertIn("PDF", result.stdout + result.stderr)

    def test_report_without_any_link_passes_with_a_reminder(self):
        result = self.check(markdown_report(five_parts(), link=False))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("提醒", result.stdout)
        self.assertIn("网址", result.stdout)

    def test_report_with_a_link_has_no_reminder(self):
        result = self.check(markdown_report(five_parts()))
        self.assertNotIn("提醒", result.stdout)

    def test_several_reports_fail_together_if_one_fails(self):
        folder = Path(self.folder.name)
        (folder / "好.md").write_text(markdown_report(five_parts()), encoding="utf-8")
        (folder / "缺.md").write_text(markdown_report(five_parts()[:3]), encoding="utf-8")
        result = run_checker(folder / "好.md", folder / "缺.md")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("好.md", result.stdout)
        self.assertIn("缺.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
