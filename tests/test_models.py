"""模型调用层（tools/models.py）的测试。

一律用假的命令行程序和回放方式，不真的调用模型。
假程序把收到的参数、标准输入和工作目录记到同目录的 invocations.jsonl，
再按各家命令行的输出格式给出一段回答。google（agy）的输出格式按帮助信息和更新记录写成，
尚未经真实调用确认（见 tools/models.md）。
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import models  # noqa: E402

FAKE_TEMPLATE = r'''#!{python}
import json, os, sys, time
VENDOR = {vendor!r}
REPLY = {reply!r}
EXIT = {exit_code!r}
SLEEP = {sleep!r}
GOOGLE = {google!r}
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
stdin = sys.stdin.read()
seen = {{"vendor": VENDOR, "args": args, "stdin": stdin, "cwd": os.getcwd(),
        "cwd_entries": sorted(os.listdir(os.getcwd()))}}
for flag in ("--agent-file", "--mcp-config-file"):
    if flag in args:
        with open(args[args.index(flag) + 1], encoding="utf-8") as f:
            seen[flag] = f.read()
if "--skills-dir" in args:
    seen["skills_entries"] = sorted(os.listdir(args[args.index("--skills-dir") + 1]))
if "--agent" in args:
    agent_md = os.path.join(os.getcwd(), ".agents", "agents", args[args.index("--agent") + 1],
                            "agent.md")
    if os.path.exists(agent_md):
        with open(agent_md, encoding="utf-8") as f:
            seen["agent_md"] = f.read()
with open(os.path.join(here, "invocations.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(seen, ensure_ascii=False) + "\n")
time.sleep(SLEEP)
if EXIT:
    print("Error code: 401 - 登录已失效")
    sys.stderr.write("假程序出错：没有登录\n")
    sys.exit(EXIT)
if VENDOR == "claude":
    print(json.dumps({{"type": "system", "subtype": "init", "model": "claude-fake-1",
                      "tools": []}}, ensure_ascii=False))
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                      "result": REPLY}}, ensure_ascii=False))
elif VENDOR == "codex":
    out = args[args.index("--output-last-message") + 1]
    with open(out, "w", encoding="utf-8") as f:
        f.write(REPLY)
    print(json.dumps({{"type": "item.completed",
                      "item": {{"type": "agent_message", "text": REPLY}}}}, ensure_ascii=False))
elif VENDOR == "kimi":
    print(json.dumps({{"role": "assistant",
                      "content": [{{"type": "think", "think": "想一想"}},
                                  {{"type": "text", "text": REPLY}}]}}, ensure_ascii=False))
elif VENDOR == "google":
    tools = []
    for line in seen.get("agent_md", "").splitlines():
        if line.startswith("tools:"):
            tools = json.loads(line[len("tools:"):])
    init = {{"type": "init", "model": "gemini-fake-1", "tools": GOOGLE.get("tools", tools)}}
    if GOOGLE.get("drop_tools"):
        del init["tools"]
    print(json.dumps(init, ensure_ascii=False))
    print(json.dumps({{"type": "step_update", "step_type": "PLANNER_RESPONSE"}}))
    result = {{"type": "result", "response": REPLY}}
    result.update(GOOGLE.get("result", {{}}))
    if not GOOGLE.get("no_result"):
        print(json.dumps(result, ensure_ascii=False))
'''


def make_fake(directory, vendor, reply="好", exit_code=0, sleep=0, google=None):
    """在 directory 下写一个名叫 vendor 的假命令行程序，返回它的路径。

    google 是给假 agy 的改动：tools 换掉启动事件里的工具列表，drop_tools 去掉工具列表，
    result 并进结果事件，no_result 不输出结果事件。
    """
    path = os.path.join(directory, vendor)
    with open(path, "w", encoding="utf-8") as f:
        f.write(FAKE_TEMPLATE.format(python=sys.executable, vendor=vendor, reply=reply,
                                     exit_code=exit_code, sleep=sleep, google=google or {}))
    os.chmod(path, 0o755)
    return path


def invocations(directory):
    path = os.path.join(directory, "invocations.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class FakeProgramCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.fakes = os.path.join(self.tmp, "fakes")
        os.mkdir(self.fakes)
        self.log = os.path.join(self.tmp, "run", "calls.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def live_run(self, max_calls=10, **fake_options):
        programs = {v: make_fake(self.fakes, v, **fake_options) for v in models.VENDORS}
        return models.ModelRun(self.log, mode=models.LIVE, max_calls=max_calls,
                               programs=programs)


class LiveCallTest(FakeProgramCase):
    def test_claude_call_returns_answer_and_sends_prompt_on_stdin(self):
        run = self.live_run(reply="评审意见：通过")
        answer, record = run.call(task="试探", vendor="claude", prompt="只回复一个字：好",
                                  tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, "评审意见：通过")
        seen = invocations(self.fakes)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["stdin"], "只回复一个字：好")
        self.assertIn("-p", seen[0]["args"])

    def test_codex_call_returns_the_last_message(self):
        run = self.live_run(reply="闭卷回答：不知道")
        answer, _ = run.call(task="闭卷对照", vendor="codex", prompt="题目",
                             tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, "闭卷回答：不知道")
        self.assertEqual(invocations(self.fakes)[0]["stdin"], "题目")

    def test_kimi_call_returns_the_text_of_the_last_assistant_message(self):
        run = self.live_run(reply="泄露检查：没有发现")
        answer, _ = run.call(task="泄露检查", vendor="kimi", prompt="两个版本",
                             tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, "泄露检查：没有发现")
        self.assertEqual(invocations(self.fakes)[0]["stdin"], "两个版本")

    def test_google_call_returns_the_response_of_the_result_event(self):
        run = self.live_run(reply="出题调研：找到三处来源")
        answer, _ = run.call(task="出题-调研", vendor="google", prompt="调研这个题目",
                             tools=models.WEB_READ_ONLY)
        self.assertEqual(answer, "出题调研：找到三处来源")
        seen = invocations(self.fakes)[0]
        self.assertEqual(seen["stdin"], "调研这个题目")
        self.assertNotIn("调研这个题目", seen["args"])


def value_after(args, flag):
    """命令行参数里紧跟在 flag 后面的那个值；没有这个 flag 时返回 None。"""
    if flag not in args:
        return None
    return args[args.index(flag) + 1]


def has_pair(args, flag, value):
    return any(args[i] == flag and args[i + 1] == value for i in range(len(args) - 1))


def frontmatter(markdown):
    """智能体说明文件（agent.md）开头两行 --- 之间的「键: 值」，值保留原文。"""
    lines = markdown.splitlines()
    end = lines.index("---", 1)
    return dict(line.split(": ", 1) for line in lines[1:end])


class ToolLimitTest(FakeProgramCase):
    """两档工具限定转成各家命令行的参数。期望值来自各命令行的帮助信息（见 tools/models.md）。"""

    def args_for(self, vendor, tools, model=None):
        run = self.live_run()
        run.call(task="试探", vendor=vendor, prompt="好", tools=tools, model=model)
        return invocations(self.fakes)[-1]

    def test_claude_materials_only_turns_off_every_tool(self):
        seen = self.args_for("claude", models.MATERIALS_ONLY)
        args = seen["args"]
        self.assertEqual(value_after(args, "--tools"), "")
        self.assertNotIn("--allowedTools", args)
        self.assertEqual(value_after(args, "--permission-mode"), "dontAsk")
        for flag in ("--strict-mcp-config", "--safe-mode", "--disable-slash-commands",
                     "--no-session-persistence"):
            self.assertIn(flag, args)
        self.assertEqual(seen["cwd_entries"], [])

    def test_claude_web_read_only_allows_only_search_and_fetch(self):
        args = self.args_for("claude", models.WEB_READ_ONLY)["args"]
        self.assertEqual(value_after(args, "--tools"), "WebSearch,WebFetch")
        self.assertEqual(value_after(args, "--allowedTools"), "WebSearch,WebFetch")
        self.assertEqual(value_after(args, "--permission-mode"), "dontAsk")
        self.assertIn("--strict-mcp-config", args)

    def test_codex_materials_only_has_no_shell_no_search_and_read_only_sandbox(self):
        seen = self.args_for("codex", models.MATERIALS_ONLY)
        args = seen["args"]
        self.assertEqual(args[0], "exec")
        self.assertEqual(args[-1], "-")
        self.assertEqual(value_after(args, "--sandbox"), "read-only")
        self.assertTrue(has_pair(args, "-c", 'web_search="disabled"'))
        self.assertTrue(has_pair(args, "--disable", "shell_tool"))
        self.assertTrue(has_pair(args, "--disable", "unified_exec"))
        self.assertTrue(has_pair(args, "-c", 'approval_policy="never"'))
        for flag in ("--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "--json"):
            self.assertIn(flag, args)
        self.assertEqual(seen["cwd_entries"], [])

    def test_codex_web_read_only_turns_on_live_search_only(self):
        args = self.args_for("codex", models.WEB_READ_ONLY)["args"]
        self.assertTrue(has_pair(args, "-c", 'web_search="live"'))
        self.assertFalse(has_pair(args, "-c", 'web_search="disabled"'))
        self.assertEqual(value_after(args, "--sandbox"), "read-only")
        self.assertTrue(has_pair(args, "--disable", "shell_tool"))
        self.assertTrue(has_pair(args, "-c", 'approval_policy="never"'))

    def test_kimi_materials_only_uses_an_agent_file_with_no_tools(self):
        seen = self.args_for("kimi", models.MATERIALS_ONLY)
        args = seen["args"]
        self.assertIn("--print", args)
        self.assertEqual(value_after(args, "--output-format"), "stream-json")
        agent = json.loads(seen["--agent-file"])["agent"]
        self.assertEqual(agent["extend"], "default")
        self.assertEqual(agent["tools"], [])
        self.assertEqual(agent["subagents"], {})
        self.assertEqual(json.loads(seen["--mcp-config-file"]), {"mcpServers": {}})
        self.assertEqual(seen["skills_entries"], [])
        self.assertEqual(seen["cwd_entries"], [])
        self.assertEqual(os.path.realpath(value_after(args, "--work-dir")),
                         os.path.realpath(seen["cwd"]))

    def test_google_materials_only_uses_an_agent_with_no_tools(self):
        seen = self.args_for("google", models.MATERIALS_ONLY)
        args = seen["args"]
        self.assertEqual(args[-1], "-p")  # 不带值的 -p：提示词从标准输入读
        self.assertEqual(value_after(args, "--output-format"), "stream-json")
        self.assertEqual(value_after(args, "--agent"), "materials-only")
        for flag in ("--sandbox", "--disable-slash-commands"):
            self.assertIn(flag, args)
        self.assertNotIn("--dangerously-skip-permissions", args)
        agent = frontmatter(seen["agent_md"])
        self.assertEqual(agent["name"], "materials-only")
        self.assertEqual(json.loads(agent["tools"]), [])
        self.assertEqual(agent["excludeDefaultComponents"], "true")
        self.assertEqual(agent["inheritCustomizations"], "false")
        self.assertEqual(agent["mainAgent"], "true")
        self.assertEqual(seen["cwd_entries"], [".agents"])

    def test_google_web_read_only_allows_only_web_search_and_url_reading(self):
        seen = self.args_for("google", models.WEB_READ_ONLY)
        args = seen["args"]
        self.assertEqual(value_after(args, "--agent"), "web-read-only")
        self.assertIn("--sandbox", args)
        self.assertNotIn("--dangerously-skip-permissions", args)
        agent = frontmatter(seen["agent_md"])
        self.assertEqual(agent["name"], "web-read-only")
        self.assertEqual(json.loads(agent["tools"]), ["search_web", "read_url_content"])
        self.assertEqual(agent["excludeDefaultComponents"], "true")
        self.assertEqual(agent["inheritCustomizations"], "false")

    def test_kimi_web_read_only_allows_only_search_and_fetch(self):
        seen = self.args_for("kimi", models.WEB_READ_ONLY)
        agent = json.loads(seen["--agent-file"])["agent"]
        self.assertEqual(agent["tools"], ["kimi_cli.tools.web:SearchWeb",
                                          "kimi_cli.tools.web:FetchURL"])
        self.assertEqual(json.loads(seen["--mcp-config-file"]), {"mcpServers": {}})


def read_log(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# 用 shasum -a 256 算出的独立参照值
SHA256_NIHAO = "670d9743542cae3ea7ebe36af56bd53648b0a1126162e78d81a32934a711302e"  # 你好
SHA256_HAO = "f867f34178594f891eb70a4260f62b1d9289cfa60394f9fee1cbbe4a8b4bf436"  # 好

RECORD_FIELDS = {
    "run_id", "call_index", "task", "vendor", "company", "model", "reported_model",
    "reported_tools", "tools", "mode", "status", "error", "prompt", "prompt_sha256",
    "answer", "answer_sha256", "started_at", "ended_at", "duration_seconds", "command",
    "config_files", "exit_code", "raw_output", "stderr", "replayed_from",
}


class CallRecordTest(FakeProgramCase):
    def test_record_has_every_field_and_is_written_to_the_run_log(self):
        programs = {v: make_fake(self.fakes, v, reply="好") for v in models.VENDORS}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=5, programs=programs,
                              run_id="测试运行一")
        _, record = run.call(task="评审-断言核验", vendor="claude", prompt="你好",
                             tools=models.MATERIALS_ONLY)
        self.assertEqual(set(record), RECORD_FIELDS)
        self.assertEqual(read_log(self.log), [record])
        self.assertEqual(record["run_id"], "测试运行一")
        self.assertEqual(record["call_index"], 1)
        self.assertEqual(record["task"], "评审-断言核验")
        self.assertEqual(record["vendor"], "claude")
        self.assertEqual(record["company"], "Anthropic")
        self.assertIsNone(record["model"])
        self.assertEqual(record["reported_model"], "claude-fake-1")
        self.assertEqual(record["reported_tools"], [])
        self.assertEqual(record["tools"], "只给材料")
        self.assertEqual(record["mode"], "真实调用")
        self.assertEqual(record["status"], "成功")
        self.assertIsNone(record["error"])
        self.assertEqual(record["prompt"], "你好")
        self.assertEqual(record["prompt_sha256"], SHA256_NIHAO)
        self.assertEqual(record["answer"], "好")
        self.assertEqual(record["answer_sha256"], SHA256_HAO)
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["command"][0], programs["claude"])
        self.assertIn('"type": "result"', record["raw_output"])
        self.assertIsNone(record["replayed_from"])

    def test_times_are_iso_with_timezone_and_ordered(self):
        from datetime import datetime
        run = self.live_run(sleep=0.2)
        _, record = run.call(task="试探", vendor="codex", prompt="好", tools=models.WEB_READ_ONLY)
        started = datetime.fromisoformat(record["started_at"])
        ended = datetime.fromisoformat(record["ended_at"])
        self.assertIsNotNone(started.tzinfo)
        self.assertLessEqual(started, ended)
        self.assertGreaterEqual(record["duration_seconds"], 0.2)

    def test_company_names_and_kimi_config_files_are_recorded(self):
        run = self.live_run()
        _, codex = run.call(task="试探", vendor="codex", prompt="好", tools=models.WEB_READ_ONLY)
        _, kimi = run.call(task="试探", vendor="kimi", prompt="好", tools=models.WEB_READ_ONLY)
        self.assertEqual(codex["company"], "OpenAI")
        self.assertEqual(kimi["company"], "月之暗面")
        self.assertEqual(kimi["tools"], "只读网页")
        self.assertEqual(kimi["call_index"], 2)
        agent = json.loads(kimi["config_files"]["agent.yaml"])
        self.assertEqual(agent["agent"]["tools"], ["kimi_cli.tools.web:SearchWeb",
                                                   "kimi_cli.tools.web:FetchURL"])
        self.assertEqual(len(read_log(self.log)), 2)


    def test_google_record_has_company_reported_model_and_tools_and_the_agent_file(self):
        run = self.live_run(reply="好")
        _, record = run.call(task="试探", vendor="google", prompt="你好",
                             tools=models.WEB_READ_ONLY)
        self.assertEqual(set(record), RECORD_FIELDS)
        self.assertEqual(read_log(self.log), [record])
        self.assertEqual(record["vendor"], "google")
        self.assertEqual(record["company"], "Google")
        self.assertEqual(record["status"], "成功")
        self.assertEqual(record["answer_sha256"], SHA256_HAO)
        self.assertEqual(record["reported_model"], "gemini-fake-1")
        self.assertEqual(record["reported_tools"], ["search_web", "read_url_content"])
        agent_md = record["config_files"]["work/.agents/agents/web-read-only/agent.md"]
        self.assertEqual(json.loads(frontmatter(agent_md)["tools"]),
                         ["search_web", "read_url_content"])
        self.assertEqual(record["command"][0], run.programs["google"])
        self.assertIn('"type": "result"', record["raw_output"])


def write_log(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class ReplayTest(FakeProgramCase):
    def replay_run(self, source):
        missing = {v: os.path.join(self.tmp, "没有这个程序") for v in models.VENDORS}
        return models.ModelRun(os.path.join(self.tmp, "replay", "calls.jsonl"),
                               mode=models.REPLAY, replay_from=source, programs=missing)

    def test_recorded_answer_comes_back_by_task_and_prompt_checksum(self):
        live = self.live_run(reply="录好的回答")
        live.call(task="出题-题目卡", vendor="claude", prompt="你好", tools=models.WEB_READ_ONLY)
        before = len(invocations(self.fakes))
        answer, record = self.replay_run(self.log).call(
            task="出题-题目卡", vendor="claude", prompt="你好", tools=models.WEB_READ_ONLY)
        self.assertEqual(answer, "录好的回答")
        self.assertEqual(len(invocations(self.fakes)), before)
        self.assertEqual(record["mode"], "回放")
        self.assertEqual(record["status"], "成功")
        self.assertEqual(record["prompt_sha256"], SHA256_NIHAO)
        self.assertEqual(record["replayed_from"]["file"], self.log)
        self.assertEqual(record["replayed_from"]["call_index"], 1)
        self.assertEqual(set(record), RECORD_FIELDS)

    def test_a_different_prompt_is_not_found(self):
        write_log(self.log, [{"task": "出题-题目卡", "vendor": "claude",
                              "prompt_sha256": SHA256_NIHAO, "answer": "录好的回答"}])
        run = self.replay_run(self.log)
        with self.assertRaises(models.ReplayMissing) as caught:
            run.call(task="出题-题目卡", vendor="claude", prompt="另一段提示词",
                     tools=models.WEB_READ_ONLY)
        self.assertIn("出题-题目卡", str(caught.exception))

    def test_a_different_vendor_is_not_found(self):
        write_log(self.log, [{"task": "评审", "vendor": "claude",
                              "prompt_sha256": SHA256_NIHAO, "answer": "甲"}])
        with self.assertRaises(models.ReplayMissing):
            self.replay_run(self.log).call(task="评审", vendor="kimi", prompt="你好",
                                           tools=models.MATERIALS_ONLY)

    def test_repeated_calls_get_the_recorded_answers_in_order(self):
        write_log(self.log, [
            {"task": "评审", "vendor": "codex", "prompt_sha256": SHA256_NIHAO, "answer": "第一份"},
            {"task": "评审", "vendor": "codex", "prompt_sha256": SHA256_NIHAO,
             "answer": "失败的那次", "status": "失败"},
            {"task": "评审", "vendor": "codex", "prompt_sha256": SHA256_NIHAO, "answer": "第二份"},
        ])
        run = self.replay_run(self.log)
        answers = [run.call(task="评审", vendor="codex", prompt="你好",
                            tools=models.MATERIALS_ONLY)[0] for _ in range(2)]
        self.assertEqual(answers, ["第一份", "第二份"])
        with self.assertRaises(models.ReplayMissing):
            run.call(task="评审", vendor="codex", prompt="你好", tools=models.MATERIALS_ONLY)

    def test_hand_written_entry_without_checksum_matches_any_prompt_of_its_task(self):
        write_log(self.log, [{"task": "泄露检查", "vendor": "kimi", "answer": "没有泄露"}])
        answer, _ = self.replay_run(self.log).call(
            task="泄露检查", vendor="kimi", prompt="随便什么提示词", tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, "没有泄露")


class CallLimitTest(FakeProgramCase):
    def test_call_beyond_the_limit_is_refused_before_any_program_starts(self):
        run = self.live_run(max_calls=2)
        run.call(task="评审", vendor="claude", prompt="一", tools=models.MATERIALS_ONLY)
        run.call(task="评审", vendor="codex", prompt="二", tools=models.MATERIALS_ONLY)
        with self.assertRaises(models.CallLimitExceeded):
            run.call(task="评审", vendor="kimi", prompt="三", tools=models.MATERIALS_ONLY)
        self.assertEqual(len(invocations(self.fakes)), 2)
        self.assertEqual(len(read_log(self.log)), 2)

    def test_real_calls_need_an_explicit_limit(self):
        with self.assertRaises(ValueError):
            models.ModelRun(self.log, mode=models.LIVE)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            models.ModelRun(self.log, mode="试跑", max_calls=1)


class EstimateTest(FakeProgramCase):
    def test_estimate_counts_calls_without_starting_any_program(self):
        programs = {v: make_fake(self.fakes, v) for v in models.VENDORS}
        run = models.ModelRun(self.log, mode=models.ESTIMATE, max_calls=2, programs=programs)
        answer, record = run.call(task="评审-要点抽取", vendor="claude", prompt="一",
                                  tools=models.MATERIALS_ONLY, placeholder='{"points": []}')
        run.call(task="评审-要点抽取", vendor="kimi", prompt="二", tools=models.MATERIALS_ONLY)
        run.call(task="评审-两两比较", vendor="claude", prompt="三", tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, '{"points": []}')
        self.assertEqual(record["mode"], "只估算")
        self.assertEqual(record["status"], "未调用")
        self.assertEqual(invocations(self.fakes), [])
        self.assertEqual(len(read_log(self.log)), 3)
        self.assertEqual(run.summary(), {
            "run_id": run.run_id, "mode": "只估算", "calls": 3,
            "by_vendor": {"claude": 2, "kimi": 1},
            "by_task": {"评审-要点抽取": 2, "评审-两两比较": 1},
            "max_calls": 2, "over_limit": True,
        })

    def test_estimate_without_placeholder_returns_empty_text(self):
        run = models.ModelRun(self.log, mode=models.ESTIMATE)
        answer, _ = run.call(task="试探", vendor="codex", prompt="好", tools=models.WEB_READ_ONLY)
        self.assertEqual(answer, "")
        self.assertFalse(run.summary()["over_limit"])


class FailureTest(FakeProgramCase):
    def test_failed_program_is_recorded_and_raised(self):
        run = self.live_run(exit_code=1)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="kimi", prompt="好", tools=models.MATERIALS_ONLY)
        record = caught.exception.record
        self.assertEqual(record["status"], "失败")
        self.assertEqual(record["exit_code"], 1)
        self.assertIn("没有登录", record["error"])
        self.assertIn("Error code: 401", record["error"])
        self.assertEqual(read_log(self.log), [record])

    def test_empty_answer_counts_as_failure(self):
        run = self.live_run(reply="")
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="codex", prompt="好", tools=models.MATERIALS_ONLY)
        self.assertEqual(caught.exception.record["status"], "失败")

    def test_program_that_runs_too_long_is_stopped(self):
        programs = {v: make_fake(self.fakes, v, sleep=5) for v in models.VENDORS}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs,
                              timeout_seconds=0.5)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="claude", prompt="好", tools=models.MATERIALS_ONLY)
        record = caught.exception.record
        self.assertEqual(record["status"], "超时")
        self.assertLess(record["duration_seconds"], 4)
        self.assertEqual(read_log(self.log)[0]["status"], "超时")

    def test_missing_program_is_reported_clearly(self):
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1,
                              programs={"codex": os.path.join(self.tmp, "没有这个程序")})
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="codex", prompt="好", tools=models.MATERIALS_ONLY)
        self.assertIn("找不到命令行", str(caught.exception))
        self.assertEqual(caught.exception.record["status"], "失败")

    def test_unknown_vendor_or_tool_limit_is_rejected(self):
        run = self.live_run()
        with self.assertRaises(ValueError):
            run.call(task="评审", vendor="gemini", prompt="好", tools=models.MATERIALS_ONLY)
        with self.assertRaises(ValueError):
            run.call(task="评审", vendor="claude", prompt="好", tools="全部工具")
        self.assertEqual(invocations(self.fakes), [])


class GoogleCheckTest(FakeProgramCase):
    """agy 的工具限定和输出格式都还没有经过真实调用确认，所以每次调用都按 agy 自己的报告核实；
    核实不了或不符合，就记为失败并写明原因，不把回答交出去。"""

    def google_call(self, limit=models.MATERIALS_ONLY, **google):
        programs = {"google": make_fake(self.fakes, "google", reply="回答", google=google)}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="google", prompt="好", tools=limit)
        record = caught.exception.record
        self.assertEqual(record["status"], "失败")
        self.assertEqual(record["answer"], "")
        self.assertEqual(read_log(self.log), [record])
        return record["error"]

    def test_tools_beyond_the_limit_fail_the_call(self):
        error = self.google_call(tools=["search_web", "run_command"])
        self.assertIn("run_command", error)
        self.assertIn("只给材料", error)

    def test_a_missing_tool_list_fails_the_call_because_the_limit_cannot_be_checked(self):
        error = self.google_call(limit=models.WEB_READ_ONLY, drop_tools=True)
        self.assertIn("无法核实", error)

    def test_refused_tool_calls_fail_the_call(self):
        denied = [{"tool_name": "read_url_content", "reason": "需要人确认"}]
        error = self.google_call(limit=models.WEB_READ_ONLY, result={"denied_actions": denied})
        self.assertIn("拒绝", error)
        self.assertIn("read_url_content", error)

    def test_a_turn_that_ended_early_fails_the_call(self):
        error = self.google_call(result={"finished_reason": "error"})
        self.assertIn("finished_reason", error)
        self.assertIn("error", error)

    def test_a_missing_result_event_fails_the_call(self):
        error = self.google_call(no_result=True)
        self.assertIn("结果事件", error)
        self.assertIn("待登录后用一次真实调用确认", error)

    def test_a_result_event_without_response_text_fails_the_call(self):
        error = self.google_call(result={"response": None})
        self.assertIn("response", error)
        self.assertIn("待登录后用一次真实调用确认", error)

    def test_a_program_that_exits_with_an_error_keeps_its_own_message(self):
        programs = {"google": make_fake(self.fakes, "google", exit_code=3)}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="google", prompt="好", tools=models.MATERIALS_ONLY)
        record = caught.exception.record
        self.assertEqual(record["exit_code"], 3)
        self.assertIn("没有登录", record["error"])


class NoSecretsTest(unittest.TestCase):
    """模块只用本机已登录的账号：不碰环境变量、不读任何凭据文件或钥匙串。"""

    def test_module_source_never_touches_credentials(self):
        with open(os.path.join(ROOT, "tools", "models.py"), encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("API_KEY", "TOKEN", "auth.json", "credential", "keychain",
                          "os.environ", "getenv", "env=", ".codex", ".kimi", ".claude",
                          ".gemini", "expanduser"):
            self.assertNotIn(forbidden, source, forbidden)


class GuideTest(unittest.TestCase):
    """使用说明 tools/models.md：必备章节齐全，调用记录的每个字段都有解释。"""

    def setUp(self):
        with open(os.path.join(ROOT, "tools", "models.md"), encoding="utf-8") as f:
            self.guide = f.read()

    def test_required_sections_exist(self):
        for heading in ("## 怎样调用", "## 两档工具限定", "## 各家命令行的参数",
                        "### claude", "### codex", "### kimi", "### google", "## 调用记录",
                        "## 回放", "## 只估算和调用次数上限", "## 不读取密钥",
                        "## 试探调用的结果"):
            self.assertIn(heading, self.guide)

    def test_google_section_states_login_and_what_is_still_unconfirmed(self):
        google = self.guide.split("### google", 1)[1].split("\n## ", 1)[0]
        for phrase in ("输出解析待登录后用一次真实调用确认", "登录", "会话记录", "--settings",
                       "--dangerously-skip-permissions", "denied_actions"):
            self.assertIn(phrase, google, phrase)

    def test_every_record_field_is_explained(self):
        for field in RECORD_FIELDS:
            self.assertIn("`%s`" % field, self.guide)


class ModelChoiceTest(FakeProgramCase):
    def test_named_model_is_passed_and_default_model_passes_nothing(self):
        run = self.live_run()
        for vendor in models.VENDORS:
            run.call(task="试探", vendor=vendor, prompt="好", tools=models.MATERIALS_ONLY,
                     model="某个模型")
            run.call(task="试探", vendor=vendor, prompt="好", tools=models.MATERIALS_ONLY)
        seen = invocations(self.fakes)
        for named, default in zip(seen[0::2], seen[1::2]):
            self.assertEqual(value_after(named["args"], "--model"), "某个模型", named["vendor"])
            self.assertNotIn("--model", default["args"])


if __name__ == "__main__":
    unittest.main()
