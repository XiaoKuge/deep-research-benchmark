"""统一运行程序 tools/run_agents.py 的测试。

只从对外接口检查：用一份运行计划启动程序，看它写出的报告、日志和运行记录。
假智能体有四种：回显程序、会反问的程序、超时的程序、本地网络接口。
"""

import csv
import datetime
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "run_agents.py"
GUIDE = ROOT / "tools" / "run_agents.md"
RULES = ROOT / "research-plan" / "rules.md"

QUESTION = "我是一名中学地理老师，想给学生讲清楚：中国最大的淡水湖是哪一个？\n交付要求：请交付一份书面报告。\n"

# 测试里把时长上限设成 1.2 秒。
SHORT_LIMIT_MINUTES = 0.02

ECHO_AGENT = """
import sys
sys.stdout.write(sys.stdin.read())
"""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def appendix_four_columns():
    """从规则手册附录四的表头取运行记录的列。"""
    lines = RULES.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("### 附录四"))
    header = next(line for line in lines[start:] if line.startswith("|"))
    return [cell.strip() for cell in header.strip("|").split("|")]


def appendix_two_reply():
    """从规则手册附录二取统一答复原文。"""
    lines = RULES.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("### 附录二"))
    body = next(line for line in lines[start + 1:] if "一律回复：" in line)
    return body.split("一律回复：", 1)[1].strip()


ASKING_AGENT = """
import os, sys
question = sys.stdin.read()
print("[[反问]] 你说的最大是按面积算还是按蓄水量算？", flush=True)
reply = open(os.environ["REPLY_PIPE"], encoding="utf-8").read()
print("收到答复：" + reply.strip())
"""


class Workspace:
    """在临时目录里搭一套运行计划、申报文件、题目文件和假智能体。"""

    def __init__(self, root):
        self.root = Path(root)
        self.agents = []
        self.questions = []

    def command_agent(self, team, script):
        folder = self.root / "申报" / team
        folder.mkdir(parents=True)
        (folder / "agent.py").write_text(textwrap.dedent(script), encoding="utf-8")
        return self._declare(team, folder, {
            "方式": "命令行",
            "命令": [sys.executable, "agent.py"],
        })

    def network_agent(self, team, address):
        folder = self.root / "申报" / team
        folder.mkdir(parents=True)
        return self._declare(team, folder, {"方式": "网络接口", "地址": address})

    def _declare(self, team, folder, call):
        (folder / "系统提示词.md").write_text("你是一个调研助手。", encoding="utf-8")
        declaration = {
            "队伍名称": team,
            "版本号或代码提交号": "1.0.0",
            "系统提示词文件": "系统提示词.md",
            "所用模型及其版本": "测试模型 1",
            "工具和外部服务清单": ["无"],
            "格式转换方式": "题目原文原样交给智能体，不增删任何内容",
            "调用方式": call,
            "运行环境说明": "Python 3",
            "申报日期": "2026-10-23",
            "申报人": "测试人",
        }
        path = folder / "申报.json"
        path.write_text(json.dumps(declaration, ensure_ascii=False, indent=2), encoding="utf-8")
        self.agents.append(str(path.relative_to(self.root)))
        return path

    def question(self, name, version, text=QUESTION, checksum=None):
        folder = self.root / "题目"
        folder.mkdir(exist_ok=True)
        path = folder / f"{name}-{version}.txt"
        path.write_bytes(text.encode("utf-8"))
        entry = {"题目": name, "版本": version, "文件": str(path.relative_to(self.root))}
        if checksum is not None:
            entry["校验值"] = checksum
        self.questions.append(entry)

    def run(self, *options, minutes=1):
        plan = {
            "时长上限分钟": minutes,
            "输出目录": "运行结果",
            "智能体": self.agents,
            "题目": self.questions,
        }
        plan_path = self.root / "运行计划.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-I", str(RUNNER), str(plan_path), *options],
            capture_output=True, text=True, timeout=60,
        )

    @property
    def day_folder(self):
        return self.root / "运行结果" / datetime.date.today().isoformat()

    def run_folder(self, team, name, version):
        return self.day_folder / team / name / version

    def records(self):
        with open(self.day_folder / "运行记录.csv", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))


class FakeNetworkAgent:
    """本地网络接口：起在线程里，按测试给的函数回应每个请求，并记下收到的请求。"""

    def __init__(self, respond):
        self.requests = []
        self.release = threading.Event()
        agent = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                request = json.loads(body.decode("utf-8"))
                agent.requests.append(request)
                status, content_type, payload = respond(request, agent.release)
                if isinstance(payload, (dict, list)):
                    payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.address = f"http://127.0.0.1:{self.server.server_port}/run"

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


JSON_TYPE = "application/json; charset=utf-8"


class RunnerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.space = Workspace(self._tmp.name)

    def network(self, respond):
        agent = FakeNetworkAgent(respond)
        self.addCleanup(agent.close)
        return agent

    def run_ok(self, *options, minutes=1):
        result = self.space.run(*options, minutes=minutes)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class CommandLineAgentTest(RunnerTestCase):
    def test_report_is_what_the_agent_printed_for_the_question_text(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        report = self.space.run_folder("回声队", "淡水湖", "提问版") / "报告.md"
        self.assertEqual(report.read_text(encoding="utf-8"), QUESTION)


class NetworkAgentTest(RunnerTestCase):
    def test_question_is_posted_to_the_declared_address_and_the_reply_is_the_report(self):
        agent = self.network(lambda request, release: (200, JSON_TYPE, {"报告": "# 主要结论\n" + request["题目"]}))
        self.space.network_agent("接口队", agent.address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.assertEqual(agent.requests, [{"题目": QUESTION, "往来": []}])
        report = self.space.run_folder("接口队", "淡水湖", "提问版") / "报告.md"
        self.assertEqual(report.read_text(encoding="utf-8"), "# 主要结论\n" + QUESTION)
        row = self.space.records()[0]
        self.assertEqual((row["队伍"], row["输入校验值是否一致"], row["文件名"]),
                         ("接口队", "一致", "接口队/淡水湖/提问版/报告.md"))

    def test_report_sent_as_a_pdf_body_is_kept_as_a_pdf(self):
        pdf = b"%PDF-1.4\n%fake report\n"
        agent = self.network(lambda request, release: (200, "application/pdf", pdf))
        self.space.network_agent("文件队", agent.address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        report = self.space.run_folder("文件队", "淡水湖", "提问版") / "报告.pdf"
        self.assertEqual(report.read_bytes(), pdf)
        self.assertEqual(self.space.records()[0]["文件名"], "文件队/淡水湖/提问版/报告.pdf")

    def test_agent_that_asks_is_called_again_with_its_question_and_the_unified_reply(self):
        def respond(request, release):
            if not request["往来"]:
                return 200, JSON_TYPE, {"反问": "要不要先确认研究计划？"}
            return 200, JSON_TYPE, {"报告": "收到答复：" + request["往来"][-1]["答复"]}

        agent = self.network(respond)
        self.space.network_agent("接口队", agent.address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        reply = appendix_two_reply()
        self.assertEqual(agent.requests[1], {
            "题目": QUESTION, "往来": [{"反问": "要不要先确认研究计划？", "答复": reply}],
        })
        report = self.space.run_folder("接口队", "淡水湖", "提问版") / "报告.md"
        self.assertEqual(report.read_text(encoding="utf-8"), "收到答复：" + reply)
        self.assertEqual(self.space.records()[0]["智能体是否提问，问了什么"], "是：要不要先确认研究计划？")

    def test_agent_that_only_ever_asks_is_stopped_after_twenty_questions(self):
        agent = self.network(lambda request, release: (200, JSON_TYPE, {"反问": "还有问题"}))
        self.space.network_agent("问不完队", agent.address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.assertEqual(len(agent.requests), 20)
        self.assertEqual(self.space.records()[0]["文件名"], "未交付")

    def test_agent_that_does_not_answer_by_the_limit_is_recorded_as_not_delivered(self):
        def respond(request, release):
            release.wait(30)
            return 200, JSON_TYPE, {"报告": "太晚了"}

        agent = self.network(respond)
        self.space.network_agent("慢接口队", agent.address)
        self.space.question("淡水湖", "提问版")
        began = time.monotonic()
        self.run_ok(minutes=SHORT_LIMIT_MINUTES)
        self.assertLess(time.monotonic() - began, 10)
        log = json.loads((self.space.run_folder("慢接口队", "淡水湖", "提问版") / "运行日志.json")
                         .read_text(encoding="utf-8"))
        self.assertTrue(log["是否超时"])
        self.assertEqual(self.space.records()[0]["文件名"], "未交付")

    def test_error_status_from_the_agent_is_logged_and_nothing_is_delivered(self):
        agent = self.network(lambda request, release: (500, "text/plain; charset=utf-8", "内部错误".encode("utf-8")))
        self.space.network_agent("故障队", agent.address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        log = json.loads((self.space.run_folder("故障队", "淡水湖", "提问版") / "运行日志.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(log["退出状态"], 500)
        self.assertEqual(self.space.records()[0]["文件名"], "未交付")


class DeclarationTest(RunnerTestCase):
    def test_incomplete_declaration_stops_everything_before_any_run(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        sloppy = self.space.command_agent("马虎队", ECHO_AGENT)
        declaration = json.loads(sloppy.read_text(encoding="utf-8"))
        del declaration["所用模型及其版本"]
        declaration["申报人"] = ""
        sloppy.write_text(json.dumps(declaration, ensure_ascii=False), encoding="utf-8")
        self.space.question("淡水湖", "提问版")
        result = self.space.run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("所用模型及其版本", result.stderr)
        self.assertIn("申报人", result.stderr)
        self.assertFalse((self.space.day_folder / "运行记录.csv").exists())

    def test_unknown_call_method_is_rejected(self):
        path = self.space.command_agent("回声队", ECHO_AGENT)
        declaration = json.loads(path.read_text(encoding="utf-8"))
        declaration["调用方式"] = {"方式": "邮件"}
        path.write_text(json.dumps(declaration, ensure_ascii=False), encoding="utf-8")
        self.space.question("淡水湖", "提问版")
        result = self.space.run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("调用方式", result.stderr)

    def test_same_question_and_version_listed_twice_is_rejected(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.space.question("淡水湖", "提问版")
        result = self.space.run("--parallel", "2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("重复", result.stderr)

    def test_log_keeps_checksums_of_the_declaration_and_the_system_prompt(self):
        path = self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        log = json.loads((self.space.run_folder("回声队", "淡水湖", "提问版") / "运行日志.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(log["申报文件校验值"], sha256(path.read_bytes()))
        self.assertEqual(log["系统提示词文件校验值"], sha256("你是一个调研助手。".encode("utf-8")))


COUNTING_AGENT = """
import pathlib, sys
sys.stdin.read()
counter = pathlib.Path("次数.txt")
count = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(count))
print(f"第 {count} 次运行的报告")
"""


class RerunTest(RunnerTestCase):
    def setUp(self):
        super().setUp()
        self.space.command_agent("回声队", COUNTING_AGENT)
        self.space.command_agent("鹦鹉队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.original = self.space.run_folder("回声队", "淡水湖", "提问版") / "报告.md"
        self.only_one = ("--team", "回声队", "--question", "淡水湖", "--version", "提问版")

    def test_running_the_plan_again_does_not_overwrite_earlier_results(self):
        self.run_ok()
        self.assertEqual(self.original.read_text(encoding="utf-8"), "第 1 次运行的报告\n")
        self.assertEqual(len(self.space.records()), 2)

    def test_rerun_with_a_reason_goes_to_its_own_folder_and_is_recorded(self):
        self.run_ok(*self.only_one, "--rerun-reason", "主办方机器断电")
        rerun = self.space.day_folder / "回声队" / "淡水湖" / "提问版-重跑" / "报告.md"
        self.assertEqual(rerun.read_text(encoding="utf-8"), "第 2 次运行的报告\n")
        self.assertEqual(self.original.read_text(encoding="utf-8"), "第 1 次运行的报告\n")
        rows = self.space.records()
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            (rows[-1]["队伍"], rows[-1]["是否重跑，原因"], rows[-1]["文件名"]),
            ("回声队", "是：主办方机器断电", "回声队/淡水湖/提问版-重跑/报告.md"),
        )

    def test_a_run_is_rerun_at_most_once(self):
        self.run_ok(*self.only_one, "--rerun-reason", "主办方机器断电")
        self.run_ok(*self.only_one, "--rerun-reason", "又断电了")
        self.assertEqual(len(self.space.records()), 3)


class ParallelTest(RunnerTestCase):
    def test_runs_can_go_at_the_same_time_so_a_whole_day_fits(self):
        for team in ["甲队", "乙队", "丙队"]:
            self.space.command_agent(team, """
                import sys, time
                sys.stdin.read()
                time.sleep(1.5)
                print("# 主要结论")
            """)
        self.space.question("淡水湖", "提问版")
        began = time.monotonic()
        self.run_ok("--parallel", "3")
        self.assertLess(time.monotonic() - began, 4.0)  # 一个接一个要 4.5 秒以上
        self.assertEqual(sorted(row["队伍"] for row in self.space.records()), ["丙队", "乙队", "甲队"])


class RunRecordTest(RunnerTestCase):
    def test_run_record_has_exactly_the_columns_of_appendix_four(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        with open(self.space.day_folder / "运行记录.csv", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        self.assertEqual(header, appendix_four_columns())

    def test_one_row_per_run_naming_question_version_team_date_and_report_file(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.command_agent("鹦鹉队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.space.question("淡水湖", "裸题版")
        self.run_ok()
        rows = self.space.records()
        self.assertEqual(
            sorted((r["题目"], r["版本"], r["队伍"], r["文件名"]) for r in rows),
            [
                ("淡水湖", "提问版", "回声队", "回声队/淡水湖/提问版/报告.md"),
                ("淡水湖", "提问版", "鹦鹉队", "鹦鹉队/淡水湖/提问版/报告.md"),
                ("淡水湖", "裸题版", "回声队", "回声队/淡水湖/裸题版/报告.md"),
                ("淡水湖", "裸题版", "鹦鹉队", "鹦鹉队/淡水湖/裸题版/报告.md"),
            ],
        )
        today = datetime.date.today().isoformat()
        for row in rows:
            self.assertEqual(row["日期"], today)
            self.assertRegex(row["开始"], r"^\d\d:\d\d:\d\d$")
            self.assertRegex(row["结束"], r"^\d\d:\d\d:\d\d$")
            self.assertLessEqual(row["开始"], row["结束"])
            self.assertEqual(row["智能体是否提问，问了什么"], "否")
            self.assertEqual(row["是否重跑，原因"], "否")


class InputChecksumTest(RunnerTestCase):
    def test_input_matching_the_frozen_checksum_is_recorded_as_consistent(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版", checksum=sha256(QUESTION.encode("utf-8")))
        self.run_ok()
        self.assertEqual(self.space.records()[0]["输入校验值是否一致"], "一致")

    def test_frozen_checksum_written_in_capitals_still_matches(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版", checksum=" " + sha256(QUESTION.encode("utf-8")).upper())
        self.run_ok()
        self.assertEqual(self.space.records()[0]["输入校验值是否一致"], "一致")

    def test_question_file_edited_after_freezing_is_recorded_as_inconsistent(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        frozen = sha256(QUESTION.encode("utf-8"))
        self.space.question("淡水湖", "提问版", text=QUESTION + "请重点查鄱阳湖。\n", checksum=frozen)
        self.run_ok()
        self.assertEqual(self.space.records()[0]["输入校验值是否一致"], "不一致")

    def test_input_cut_short_by_the_agent_is_recorded_as_inconsistent(self):
        long_question = QUESTION * 20000  # 远大于管道缓冲区
        self.space.command_agent("半句队", """
            import os, sys
            sys.stdin.buffer.read(10)
            os.close(0)
            print("只读了开头")
        """)
        self.space.question("淡水湖", "提问版", text=long_question)
        self.run_ok()
        self.assertEqual(self.space.records()[0]["输入校验值是否一致"], "不一致")

    def test_log_keeps_the_input_actually_given_and_its_checksum(self):
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        folder = self.space.run_folder("回声队", "淡水湖", "提问版")
        log = json.loads((folder / "运行日志.json").read_text(encoding="utf-8"))
        self.assertEqual((folder / "输入.txt").read_bytes(), QUESTION.encode("utf-8"))
        self.assertEqual(log["输入校验值"], sha256(QUESTION.encode("utf-8")))


class BrokenAgentTest(RunnerTestCase):
    def test_command_that_cannot_start_is_not_delivered_and_other_runs_go_on(self):
        path = self.space.command_agent("缺件队", ECHO_AGENT)
        declaration = json.loads(path.read_text(encoding="utf-8"))
        declaration["调用方式"]["命令"] = ["./没有这个程序"]
        path.write_text(json.dumps(declaration, ensure_ascii=False), encoding="utf-8")
        self.space.command_agent("回声队", ECHO_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        rows = {row["队伍"]: row["文件名"] for row in self.space.records()}
        self.assertEqual(rows, {"缺件队": "未交付", "回声队": "回声队/淡水湖/提问版/报告.md"})
        log = json.loads((self.space.run_folder("缺件队", "淡水湖", "提问版") / "运行日志.json")
                         .read_text(encoding="utf-8"))
        self.assertIn("没有这个程序", log["错误"])

    def test_unreachable_address_is_not_delivered(self):
        agent = FakeNetworkAgent(lambda request, release: (200, JSON_TYPE, {"报告": "不会到这里"}))
        address = agent.address
        agent.close()
        self.space.network_agent("断线队", address)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.assertEqual(self.space.records()[0]["文件名"], "未交付")


class CommandLineAskBackTest(RunnerTestCase):
    def test_agent_that_asks_gets_the_unified_reply_of_appendix_two(self):
        self.space.command_agent("追问队", ASKING_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        report = self.space.run_folder("追问队", "淡水湖", "提问版") / "报告.md"
        self.assertEqual(report.read_text(encoding="utf-8"), "收到答复：" + appendix_two_reply() + "\n")

    def test_question_the_agent_asked_goes_into_the_run_record(self):
        self.space.command_agent("追问队", ASKING_AGENT)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.assertEqual(
            self.space.records()[0]["智能体是否提问，问了什么"],
            "是：你说的最大是按面积算还是按蓄水量算？",
        )

    def test_every_question_gets_the_same_reply_and_all_are_recorded(self):
        self.space.command_agent("多问队", """
            import os, sys
            sys.stdin.read()
            for question in ["要不要先给你看研究计划？", "可以开始了吗？"]:
                print("[[反问]] " + question, flush=True)
                print(open(os.environ["REPLY_PIPE"], encoding="utf-8").read().strip())
        """)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        report = self.space.run_folder("多问队", "淡水湖", "提问版") / "报告.md"
        reply = appendix_two_reply()
        self.assertEqual(report.read_text(encoding="utf-8"), f"{reply}\n{reply}\n")
        self.assertEqual(
            self.space.records()[0]["智能体是否提问，问了什么"],
            "是：要不要先给你看研究计划？；可以开始了吗？",
        )


class RunLogTest(RunnerTestCase):
    def setUp(self):
        super().setUp()
        self.space.command_agent("出错队", """
            import sys
            sys.stdin.read()
            print("正在检索", file=sys.stderr)
            print("# 主要结论")
            sys.exit(3)
        """)
        self.space.question("淡水湖", "提问版")
        self.run_ok()
        self.folder = self.space.run_folder("出错队", "淡水湖", "提问版")
        self.log = json.loads((self.folder / "运行日志.json").read_text(encoding="utf-8"))

    def test_standard_error_is_saved_beside_the_report(self):
        self.assertEqual((self.folder / "标准错误.txt").read_text(encoding="utf-8"), "正在检索\n")

    def test_exit_status_is_logged_and_the_report_still_counts(self):
        self.assertEqual(self.log["退出状态"], 3)
        self.assertEqual((self.folder / "报告.md").read_text(encoding="utf-8"), "# 主要结论\n")

    def test_start_and_end_are_full_timestamps_with_time_zone(self):
        start = datetime.datetime.fromisoformat(self.log["开始"])
        end = datetime.datetime.fromisoformat(self.log["结束"])
        self.assertIsNotNone(start.tzinfo)
        self.assertLessEqual(start, end)


class AskLimitTest(RunnerTestCase):
    def test_command_line_agent_that_keeps_asking_is_stopped_after_twenty_questions(self):
        self.space.command_agent("问不完队", """
            import os, sys
            sys.stdin.read()
            print("# 主要结论", flush=True)
            while True:
                print("[[反问]] 还有问题", flush=True)
                open(os.environ["REPLY_PIPE"], encoding="utf-8").read()
        """)
        self.space.question("淡水湖", "提问版")
        began = time.monotonic()
        self.run_ok()
        self.assertLess(time.monotonic() - began, 30)
        cell = self.space.records()[0]["智能体是否提问，问了什么"]
        self.assertEqual(cell, "是：" + "；".join(["还有问题"] * 20))


class TimeLimitTest(RunnerTestCase):
    def run_with_short_limit(self):
        began = time.monotonic()
        self.run_ok(minutes=SHORT_LIMIT_MINUTES)
        return time.monotonic() - began

    def test_agent_past_the_limit_is_stopped_and_what_it_delivered_counts(self):
        self.space.command_agent("拖延队", """
            import sys, time
            sys.stdin.read()
            print("# 主要结论", flush=True)
            time.sleep(30)
            print("这一行到不了")
        """)
        self.space.question("淡水湖", "提问版")
        elapsed = self.run_with_short_limit()
        self.assertLess(elapsed, 10)
        folder = self.space.run_folder("拖延队", "淡水湖", "提问版")
        self.assertEqual((folder / "报告.md").read_text(encoding="utf-8"), "# 主要结论\n")
        log = json.loads((folder / "运行日志.json").read_text(encoding="utf-8"))
        self.assertTrue(log["是否超时"])
        self.assertEqual(self.space.records()[0]["文件名"], "拖延队/淡水湖/提问版/报告.md")

    def test_agent_that_delivered_nothing_by_the_limit_is_recorded_as_not_delivered(self):
        self.space.command_agent("沉默队", """
            import sys, time
            sys.stdin.read()
            time.sleep(30)
        """)
        self.space.question("淡水湖", "提问版")
        elapsed = self.run_with_short_limit()
        self.assertLess(elapsed, 10)
        folder = self.space.run_folder("沉默队", "淡水湖", "提问版")
        self.assertFalse((folder / "报告.md").exists())
        self.assertEqual(self.space.records()[0]["文件名"], "未交付")


def guide_block(heading, language):
    """取使用说明里某个二级标题下面第一个指定语言的代码块。"""
    text = GUIDE.read_text(encoding="utf-8")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return section.split(f"```{language}\n", 1)[1].split("\n```", 1)[0]


class GuideTest(unittest.TestCase):
    def setUp(self):
        self.text = GUIDE.read_text(encoding="utf-8")

    def test_guide_has_every_required_section(self):
        headings = [line[3:].strip() for line in self.text.splitlines() if line.startswith("## ")]
        for heading in ["用途", "一条命令", "运行计划", "申报文件", "两种调用方式", "反问约定",
                        "时长上限", "输入校验值", "运行结果", "重跑", "测试"]:
            self.assertIn(heading, headings)

    def test_local_links_in_the_guide_open(self):
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", self.text):
            if "://" in target:
                continue
            self.assertTrue((GUIDE.parent / target).exists(), target)

    def test_guide_states_the_conventions_the_program_uses(self):
        for phrase in ["[[反问]]", "REPLY_PIPE", '"往来"', '"报告"', '"反问"', '"答复"',
                       appendix_two_reply()]:
            self.assertIn(phrase, self.text)
        for column in appendix_four_columns():
            self.assertIn(column, self.text)

    def test_examples_in_the_guide_run_through_the_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = json.loads(guide_block("运行计划", "json"))
            declaration = json.loads(guide_block("申报文件", "json"))
            plan["智能体"] = plan["智能体"][:1]
            (root / plan["智能体"][0]).parent.mkdir(parents=True)
            agent_folder = (root / plan["智能体"][0]).parent
            (root / plan["智能体"][0]).write_text(json.dumps(declaration, ensure_ascii=False), encoding="utf-8")
            (agent_folder / declaration["系统提示词文件"]).write_text("示例", encoding="utf-8")
            (agent_folder / declaration["调用方式"]["命令"][-1]).write_text(
                guide_block("反问约定", "python"), encoding="utf-8")
            for entry in plan["题目"]:
                (root / entry["文件"]).parent.mkdir(parents=True, exist_ok=True)
                (root / entry["文件"]).write_text(QUESTION, encoding="utf-8")
            (root / "运行计划.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(RUNNER), str(root / "运行计划.json")],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            day = root / plan.get("输出目录", "运行结果") / datetime.date.today().isoformat()
            with open(day / "运行记录.csv", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), len(plan["题目"]))
            for row in rows:
                self.assertNotEqual(row["文件名"], "未交付")
                self.assertTrue(row["智能体是否提问，问了什么"].startswith("是："))


if __name__ == "__main__":
    unittest.main()
