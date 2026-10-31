"""模型调用层（tools/models.py）的测试。

一律用假的命令行程序和回放方式，不真的调用模型。
假程序把收到的参数、标准输入和工作目录记到同目录的 invocations.jsonl，
再按各家命令行的输出格式给出一段回答。假 agy 的输入要求和输出格式照登录后真实调用查明的写
（2026 年 10 月，见 tools/models.md 的 google 一节）：参数和标准输入不合要求时像真的 agy 一样报错退出。
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
    def fail(message):
        sys.stderr.write(message + "\n")
        sys.exit(1)
    if "-p" not in args or args.index("-p") + 1 >= len(args):
        fail("flag needs an argument: -p")
    stream = "--input-format" in args and args[args.index("--input-format") + 1] == "stream-json"
    if not stream:
        fail("假 agy 只按流式输入运行")
    if args[args.index("-p") + 1] != "":
        fail("流式输入时命令行上不能再给提示词")
    for line in stdin.splitlines():
        message = json.loads(line)
        for field in ("event", "message"):
            if field not in message:
                fail('missing the "%s" field' % field)
    model = GOOGLE.get("model") or (args[args.index("--model") + 1] if "--model" in args
                                    else "gemini-fake-1")
    # 启动事件列出 agy 注册过的全部工具（真的有 60 个），与智能体文件里配置的工具无关
    registered = ["run_command", "view_file", "write_to_file", "search_web", "read_url_content"]
    print(json.dumps({{"event": "init", "init": {{"model": model, "cwd": os.getcwd(),
                                                "tools": registered}}}}, ensure_ascii=False))
    for index, step in enumerate(GOOGLE.get("steps", ["user_input", "agent_response"])):
        for state in ("ACTIVE", "DONE"):
            print(json.dumps({{"event": "step_update", "step_update": {{
                "step_index": index, "state": state, "step_type": step, "usage": {{}}}}}}))
    result = {{"status": "SUCCESS", "response": REPLY, "num_turns": 1,
              "usage": {{"input_tokens": 442}}}}
    result.update(GOOGLE.get("result", {{}}))
    if not GOOGLE.get("no_result"):
        print(json.dumps({{"event": "result", "result": result}}, ensure_ascii=False))
'''


def make_fake(directory, vendor, reply="好", exit_code=0, sleep=0, google=None):
    """在 directory 下写一个名叫 vendor 的假命令行程序，返回它的路径。

    google 是给假 agy 的改动：model 换掉启动事件报告的模型，steps 换掉步骤类型的序列
    （默认是 user_input、agent_response），result 并进结果事件，no_result 不输出结果事件。
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

    def test_google_call_sends_the_prompt_as_one_json_line_and_returns_the_response(self):
        run = self.live_run(reply="评审意见：通过")
        prompt = "评审这份报告\n第二行带\"引号\"\r\n第三行\u2028第四行"
        answer, record = run.call(task="评审", vendor="google", prompt=prompt,
                                  tools=models.MATERIALS_ONLY)
        self.assertEqual(answer, "评审意见：通过")
        seen = invocations(self.fakes)[0]
        args = seen["args"]
        self.assertEqual(value_after(args, "--input-format"), "stream-json")
        self.assertEqual(value_after(args, "--output-format"), "stream-json")
        self.assertEqual(args[-2:], ["-p", ""])  # -p 必须带值，流式输入时给空串
        self.assertNotIn(prompt, args)
        self.assertTrue(seen["stdin"].endswith("\n"))
        self.assertEqual(len(seen["stdin"].splitlines()), 1)  # 提示词里的各种换行都转义在 JSON 里
        self.assertEqual(json.loads(seen["stdin"]),
                         {"event": "user", "message": {"role": "user", "content": prompt}})
        self.assertEqual(record["prompt"], prompt)  # 调用记录仍记原始提示词


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
        self.assertEqual(args[-2:], ["-p", ""])  # 提示词走流式输入，不放在命令行上
        self.assertEqual(value_after(args, "--input-format"), "stream-json")
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


    def test_google_record_has_company_reported_model_and_the_agent_file(self):
        run = self.live_run(reply="好")
        _, record = run.call(task="试探", vendor="google", prompt="你好",
                             tools=models.MATERIALS_ONLY, model="gemini-4-argon-low")
        self.assertEqual(set(record), RECORD_FIELDS)
        self.assertEqual(read_log(self.log), [record])
        self.assertEqual(record["vendor"], "google")
        self.assertEqual(record["company"], "Google")
        self.assertEqual(record["status"], "成功")
        self.assertEqual(record["answer_sha256"], SHA256_HAO)
        self.assertEqual(record["prompt"], "你好")
        self.assertEqual(record["prompt_sha256"], SHA256_NIHAO)
        self.assertEqual(record["reported_model"], "gemini-4-argon-low")
        # 启动事件列的是 agy 注册过的全部工具，不是这个智能体能用的工具，所以不记
        self.assertIsNone(record["reported_tools"])
        agent_md = record["config_files"]["work/.agents/agents/materials-only/agent.md"]
        self.assertEqual(json.loads(frontmatter(agent_md)["tools"]), [])
        self.assertEqual(record["command"][0], run.programs["google"])
        self.assertIn('"event": "result"', record["raw_output"])


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
    """按 agy 自己的报告核实每次调用（报告的格式见 tools/models.md 的 google 一节）；
    不符合就记为失败并写明原因，不把回答交出去。"""

    def google_call(self, limit=models.MATERIALS_ONLY, reply="回答", **google):
        programs = {"google": make_fake(self.fakes, "google", reply=reply, google=google)}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="google", prompt="好", tools=limit)
        record = caught.exception.record
        self.assertEqual(record["status"], "失败")
        self.assertEqual(record["answer"], "")
        self.assertEqual(read_log(self.log), [record])
        return record["error"]

    def test_a_result_that_is_not_success_fails_with_the_error_agy_reports(self):
        error = self.google_call(result={"status": "ERROR", "response": "半截回答",
                                         "error": "模型服务暂时不可用"})
        self.assertIn("ERROR", error)
        self.assertIn("模型服务暂时不可用", error)

    def test_a_reported_model_that_is_not_gemini_fails_the_call(self):
        error = self.google_call(model="claude-opus-5-5-thinking")
        self.assertIn("claude-opus-5-5-thinking", error)
        self.assertIn("gemini", error)

    def test_materials_only_fails_when_agy_reports_steps_other_than_input_and_answer(self):
        error = self.google_call(steps=["user_input", "search_web", "agent_response",
                                        "read_url_content", "search_web"])
        self.assertIn("只给材料", error)
        self.assertIn("search_web、read_url_content", error)
        self.assertNotIn("agent_response", error)

    def test_a_successful_result_with_an_empty_response_fails_the_call(self):
        # agy 报告成功但回答是空串时，不能当成功
        error = self.google_call(reply="")
        self.assertIn("回答为空", error)

    def test_a_missing_result_event_fails_the_call(self):
        error = self.google_call(no_result=True)
        self.assertIn("结果事件", error)

    def test_a_program_that_exits_with_an_error_keeps_its_own_message(self):
        programs = {"google": make_fake(self.fakes, "google", exit_code=3)}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="评审", vendor="google", prompt="好", tools=models.MATERIALS_ONLY)
        record = caught.exception.record
        self.assertEqual(record["exit_code"], 3)
        self.assertIn("没有登录", record["error"])


class GoogleWebTierTest(FakeProgramCase):
    """google 的只读网页一档读不了网页（非交互运行时读网页要人批准，一律被拒），
    模型可能直接凭记忆作答而被当成成功；所以真实调用时直接判为不可用，不启动 agy。"""

    def test_a_live_google_call_in_the_web_tier_fails_without_starting_agy(self):
        programs = {"google": make_fake(self.fakes, "google", reply="8848.86")}
        run = models.ModelRun(self.log, mode=models.LIVE, max_calls=1, programs=programs)
        with self.assertRaises(models.ModelCallError) as caught:
            run.call(task="出题-深度地图", vendor="google", prompt="查一下珠峰高程",
                     tools=models.WEB_READ_ONLY)
        record = caught.exception.record
        self.assertEqual(record["status"], "失败")
        self.assertIn("只读网页", record["error"])
        self.assertIsNone(record["command"])
        self.assertEqual(invocations(self.fakes), [])
        self.assertEqual(read_log(self.log), [record])


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

    def section(self, heading):
        return self.guide.split(heading + "\n", 1)[1].split("\n## ", 1)[0]

    def test_google_section_states_the_facts_confirmed_by_real_calls(self):
        google = self.section("### google")
        for phrase in ("已用真实调用确认", "2026 年 10 月 30 日", "--input-format stream-json",
                       '-p ""', '"event": "user"', "step_type", "gemini-4-argon-medium",
                       "只读网页档暂不可用", "会话", "关不掉", "--settings",
                       "--dangerously-skip-permissions"):
            self.assertIn(phrase, google, phrase)
        for guess in ("待登录", "denied_actions", "finished_reason", "还没有登录"):
            self.assertNotIn(guess, google, guess)

    def test_probe_results_include_the_google_calls_after_login(self):
        probes = self.section("## 试探调用的结果")
        for phrase in ("gemini-4-argon-low", "没有工具", "user_input", "agent_response"):
            self.assertIn(phrase, probes, phrase)
        self.assertNotIn("没有做试探调用", probes)

    def test_every_record_field_is_explained(self):
        for field in RECORD_FIELDS:
            self.assertIn("`%s`" % field, self.guide)


class ModelChoiceTest(FakeProgramCase):
    def test_named_model_is_passed_and_default_model_passes_nothing(self):
        run = self.live_run()
        for vendor in ("claude", "codex", "kimi"):
            run.call(task="试探", vendor=vendor, prompt="好", tools=models.MATERIALS_ONLY,
                     model="某个模型")
            run.call(task="试探", vendor=vendor, prompt="好", tools=models.MATERIALS_ONLY)
        seen = invocations(self.fakes)
        for named, default in zip(seen[0::2], seen[1::2]):
            self.assertEqual(value_after(named["args"], "--model"), "某个模型", named["vendor"])
            self.assertNotIn("--model", default["args"])

    def test_google_uses_gemini_4_argon_medium_unless_a_model_is_named(self):
        # agy 也能用 Claude 和 GPT 的模型，当 Google 评委时必须是 Gemini，所以不用 agy 自己的默认模型
        run = self.live_run()
        _, default = run.call(task="试探", vendor="google", prompt="好",
                              tools=models.MATERIALS_ONLY)
        _, named = run.call(task="试探", vendor="google", prompt="好",
                            tools=models.MATERIALS_ONLY, model="gemini-4-argon-low")
        seen = invocations(self.fakes)
        self.assertEqual(value_after(seen[0]["args"], "--model"), "gemini-4-argon-medium")
        self.assertEqual(default["model"], "gemini-4-argon-medium")
        self.assertEqual(value_after(seen[1]["args"], "--model"), "gemini-4-argon-low")
        self.assertEqual(named["model"], "gemini-4-argon-low")


if __name__ == "__main__":
    unittest.main()
