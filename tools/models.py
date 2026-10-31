"""模型调用层：统一调用本机已登录的四家模型命令行（claude、codex、kimi，以及 Google 的 agy）。

用法、调用记录的字段和各家命令行参数的依据见同目录 models.md。
"""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime

VENDORS = ("claude", "codex", "kimi", "google")
COMPANIES = {"claude": "Anthropic", "codex": "OpenAI", "kimi": "月之暗面", "google": "Google"}
# 各家命令行的程序名；Google 一家用 Antigravity 命令行 agy。
COMMANDS = {"claude": "claude", "codex": "codex", "kimi": "kimi", "google": "agy"}
# 不指定模型时用的模型。agy 也能用 Claude 和 GPT 的模型，当 Google 评委时必须是 Gemini，
# 所以 google 不用 agy 自己的默认模型；其余三家不在这里，用各自命令行的默认模型。
DEFAULT_MODELS = {"google": "gemini-4-argon-medium"}

MATERIALS_ONLY = "只给材料"
WEB_READ_ONLY = "只读网页"

LIVE = "真实调用"
REPLAY = "回放"
ESTIMATE = "只估算"

SUCCEEDED = "成功"
FAILED = "失败"
TIMED_OUT = "超时"
NOT_CALLED = "未调用"

STDERR_KEPT = 20000  # 标准错误只留最后这么多字


class ModelCallError(Exception):
    """命令行调用失败、超时或找不到命令行。调用记录已经写进记录文件，也挂在 .record 上。"""

    def __init__(self, message, record):
        super().__init__(message)
        self.record = record


class ReplayMissing(Exception):
    """回放时在录好的调用记录里找不到对应的回答。"""


class CallLimitExceeded(Exception):
    """真实调用的次数已经到了上限；这一次没有启动任何命令行。"""


def _load_replay(sources):
    if isinstance(sources, (str, os.PathLike)):
        sources = [sources]
    entries = []
    for source in sources or []:
        with open(source, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("status", SUCCEEDED) != SUCCEEDED:
                    continue
                entries.append({"file": str(source), "entry": entry, "used": False})
    return entries


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _json_lines(stdout):
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _model_args(model):
    """各家都用 --model 指定模型；不指定时用命令行自己的默认模型。"""
    return ["--model", model] if model else []


# ---- claude ----------------------------------------------------------------

CLAUDE_WEB_TOOLS = "WebSearch,WebFetch"


def _claude_args(tools, model, scratch, work):
    args = ["-p", "--output-format", "stream-json", "--verbose",
            "--no-session-persistence", "--safe-mode", "--strict-mcp-config",
            "--disable-slash-commands", "--permission-mode", "dontAsk"]
    if tools == MATERIALS_ONLY:
        args += ["--tools", ""]
    else:
        args += ["--tools", CLAUDE_WEB_TOOLS, "--allowedTools", CLAUDE_WEB_TOOLS]
    return args + _model_args(model)


def _claude_answer(stdout, scratch, tools):
    found = {"answer": "", "reported_model": None, "reported_tools": None}
    for event in _json_lines(stdout):
        if event.get("type") == "system" and event.get("subtype") == "init":
            found["reported_model"] = event.get("model")
            found["reported_tools"] = event.get("tools")
        elif event.get("type") == "result":
            if event.get("is_error"):
                found["error"] = "命令行报告出错：%s" % (event.get("result") or "")
            else:
                found["answer"] = event.get("result") or ""
    return found


# ---- codex -----------------------------------------------------------------

# codex 的工具限定：关掉运行命令的两种工具，沙箱只读且不许申请放宽，网页检索按档位关或开。
CODEX_COMMON = ["--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
                "--sandbox", "read-only", "-c", 'approval_policy="never"',
                "--disable", "shell_tool", "--disable", "unified_exec"]
CODEX_LAST_MESSAGE = "last-message.txt"


def _codex_args(tools, model, scratch, work):
    search = "disabled" if tools == MATERIALS_ONLY else "live"
    args = ["exec", "--json", "--output-last-message", os.path.join(scratch, CODEX_LAST_MESSAGE),
            "--cd", work] + CODEX_COMMON + ["-c", 'web_search="%s"' % search]
    return args + _model_args(model) + ["-"]


def _codex_answer(stdout, scratch, tools):
    found = {"answer": "", "reported_model": None, "reported_tools": None}
    path = os.path.join(scratch, CODEX_LAST_MESSAGE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            found["answer"] = f.read()
    return found


# ---- kimi ------------------------------------------------------------------

# kimi 的工具限定写在一个临时的智能体说明文件里（JSON 写法，kimi 按 YAML 读，两者兼容）。
KIMI_TOOLS = {
    MATERIALS_ONLY: [],
    WEB_READ_ONLY: ["kimi_cli.tools.web:SearchWeb", "kimi_cli.tools.web:FetchURL"],
}


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _kimi_args(tools, model, scratch, work):
    agent_file = os.path.join(scratch, "agent.yaml")
    _write_json(agent_file, {"version": 1, "agent": {
        "extend": "default", "tools": KIMI_TOOLS[tools], "subagents": {}}})
    mcp_file = os.path.join(scratch, "mcp.json")
    _write_json(mcp_file, {"mcpServers": {}})
    skills = os.path.join(scratch, "skills")
    os.mkdir(skills)
    return ["--print", "--output-format", "stream-json", "--work-dir", work,
            "--agent-file", agent_file, "--mcp-config-file", mcp_file,
            "--skills-dir", skills] + _model_args(model)


def _kimi_answer(stdout, scratch, tools):
    found = {"answer": "", "reported_model": None, "reported_tools": None}
    for message in _json_lines(stdout):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            text = content
        else:
            text = "".join(part.get("text", "") for part in content or []
                           if isinstance(part, dict) and part.get("type") == "text")
        if text:
            found["answer"] = text
    return found


# ---- google（agy）--------------------------------------------------------------

# agy 的工具限定写在工作目录里的一个自定义智能体说明文件（.agents/agents/<名字>/agent.md）里，
# 用 --agent 选它。tools 列出允许的工具，excludeDefaultComponents 去掉默认的提示词段落和内置工具，
# inheritCustomizations 不沿用用户的技能、规则、插件、子智能体和模型上下文协议服务器。
GOOGLE_AGENTS = {MATERIALS_ONLY: "materials-only", WEB_READ_ONLY: "web-read-only"}
GOOGLE_TOOLS = {MATERIALS_ONLY: [], WEB_READ_ONLY: ["search_web", "read_url_content"]}
GOOGLE_PROMPTS = {
    MATERIALS_ONLY: "按用户消息里的要求作答，只依据消息里给出的材料。",
    WEB_READ_ONLY: "按用户消息里的要求作答，需要时可以检索网页和读取网页。",
}


def _google_agent_md(tools):
    name = GOOGLE_AGENTS[tools]
    return "\n".join([
        "---",
        "name: %s" % name,
        "description: 模型调用层的单次调用（%s）" % tools,
        "mainAgent: true",
        "subagent: false",
        "excludeDefaultComponents: true",
        "inheritCustomizations: false",
        "inheritMcp: false",
        "tools: %s" % json.dumps(GOOGLE_TOOLS[tools]),
        "---",
        "",
        "# %s" % name,
        "",
        GOOGLE_PROMPTS[tools],
        "",
    ])


def _google_args(tools, model, scratch, work):
    """提示词走流式输入（见 _google_stdin）；-p 必须带值，流式输入时给空串，命令行上不放提示词。"""
    folder = os.path.join(work, ".agents", "agents", GOOGLE_AGENTS[tools])
    os.makedirs(folder)
    with open(os.path.join(folder, "agent.md"), "w", encoding="utf-8") as f:
        f.write(_google_agent_md(tools))
    return (["--input-format", "stream-json", "--output-format", "stream-json",
             "--agent", GOOGLE_AGENTS[tools], "--sandbox", "--disable-slash-commands"]
            + _model_args(model) + ["-p", ""])


def _google_stdin(prompt):
    """agy 的流式输入：一行 JSON 是一条用户消息，后跟换行。

    非 ASCII 字符一律写成 \\u 转义，整行只有 ASCII 字符，提示词里的任何换行或行分隔符都断不开这一行。
    """
    return json.dumps({"event": "user", "message": {"role": "user", "content": prompt}}) + "\n"


# 只给材料档允许的步骤类型：收下用户消息、模型作答。别的步骤类型（例如调用工具）说明限定没生效。
GOOGLE_MATERIALS_STEPS = ("user_input", "agent_response")


def _google_problem(events, result, reported_model, tools):
    """按 agy 自己的报告核实这次调用；有问题返回原因，没有返回 None。"""
    if not events:
        return None  # 一行 JSON 也没有：交给通用的失败原因（退出状态和标准错误）
    if not (isinstance(reported_model, str) and reported_model.startswith("gemini")):
        shown = "「%s」" % reported_model if isinstance(reported_model, str) else "空的"
        return ("agy 的启动事件报告的模型是%s，不是以 gemini 开头的 Gemini 模型；"
                "当 Google 一家用时必须是 Gemini 模型" % shown)
    if tools == MATERIALS_ONLY:
        extra = []
        for event in events:
            if event.get("event") == "step_update":
                step = (event.get("step_update") or {}).get("step_type")
                if step not in GOOGLE_MATERIALS_STEPS and step not in extra:
                    extra.append(step)
        if extra:
            return ("「%s」档里 agy 报告了收下用户消息、模型作答以外的步骤类型：%s"
                    % (tools, "、".join(str(step) for step in extra)))
    if result is None:
        return "agy 的输出里没有结果事件（event 为 result 的一行）"
    if result.get("status") != "SUCCESS":
        return "agy 报告这一轮没有成功（status 为 %s）：%s" % (
            result.get("status"), result.get("error") or "没有给出原因")
    if not isinstance(result.get("response"), str) or not result["response"].strip():
        reason = "agy 报告成功，但回答为空"
        if tools == WEB_READ_ONLY:
            reason += ("。只读网页档里模型去读网页时，读网页需要人批准，非交互运行被拒绝，"
                       "回答就是空的；google 目前不能用于只读网页档")
        return reason
    return None


# agy 的 stream-json 输出（登录后用真实调用查明）：每行一个事件，事件名在 event 字段，
# 内容嵌在与事件名同名的键里：init（启动事件）、step_update（步骤）、result（结果事件）。
# 回答取 result.response；reported_model 取 init.model。init 里的 tools 是 agy 注册过的全部工具，
# 不是这个智能体能用的工具，所以 reported_tools 留空（智能体能用的工具见 config_files 里的 agent.md）。
def _google_answer(stdout, scratch, tools):
    found = {"answer": "", "reported_model": None, "reported_tools": None}
    events = list(_json_lines(stdout))
    result = None
    for event in events:
        if event.get("event") == "init":
            found["reported_model"] = (event.get("init") or {}).get("model")
        elif event.get("event") == "result":
            result = event.get("result") or {}
    problem = _google_problem(events, result, found["reported_model"], tools)
    if problem:
        found["error"] = problem
    elif result is not None:
        found["answer"] = result["response"]
    return found


# 每家：(拼参数, 取回答, 改写标准输入)。改写标准输入为 None 时，提示词原样写进标准输入。
ADAPTERS = {
    "claude": (_claude_args, _claude_answer, None),
    "codex": (_codex_args, _codex_answer, None),
    "kimi": (_kimi_args, _kimi_answer, None),
    "google": (_google_args, _google_answer, _google_stdin),
}


def _failure_reason(exit_code, stdout, stderr):
    """失败原因：退出状态，加上两路输出里不是 JSON 的最后几行（kimi 把出错信息写在标准输出）。"""
    parts = ["退出状态 %s" % exit_code]
    for label, text in (("标准错误", stderr), ("标准输出", stdout)):
        plain = [line for line in text.splitlines()
                 if line.strip() and not line.strip().startswith("{")]
        if plain:
            parts.append("%s最后几行：%s" % (label, "\n".join(plain[-8:])[-2000:]))
    if len(parts) == 1:
        parts.append("没有拿到回答")
    return "；".join(parts)


def _config_files(scratch):
    """调用前写进临时目录的设置文件（kimi 的两个、google 的智能体说明文件），原文记进调用记录。

    键是相对临时目录的路径，例如 "agent.yaml"、"work/.agents/agents/materials-only/agent.md"。
    """
    files = {}
    for folder, _, names in os.walk(scratch):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as f:
                files[os.path.relpath(path, scratch).replace(os.sep, "/")] = f.read()
    return dict(sorted(files.items()))


# ---- 一次运行 ----------------------------------------------------------------

class ModelRun:
    """一次运行：同一个调用记录文件、同一个调用次数上限、同一种方式（真实调用、回放或只估算）。

    log_path        调用记录文件（JSON Lines），每次调用追加一行；目录不存在会自动建。
    mode            LIVE（真实调用）、REPLAY（回放）或 ESTIMATE（只估算）。
    max_calls       真实调用的次数上限，真实调用时必须给；只估算时用来判断是否超过上限。
    replay_from     回放时读的调用记录文件，一个路径或路径列表。
    programs        {厂商: 程序路径}，测试时指向假的命令行程序；不给就在 PATH 里找 COMMANDS 里的程序名。
    run_id          运行编号，不给就用开始时间。
    timeout_seconds 单次调用的时长上限，到了就停止该命令行并记为超时。
    """

    def __init__(self, log_path, mode=LIVE, max_calls=None, replay_from=None, programs=None,
                 run_id=None, timeout_seconds=1800):
        if mode not in (LIVE, REPLAY, ESTIMATE):
            raise ValueError("不认识的方式：%r，只能是「%s」「%s」「%s」"
                             % (mode, LIVE, REPLAY, ESTIMATE))
        if mode == LIVE and not (isinstance(max_calls, int) and max_calls > 0):
            raise ValueError("真实调用必须给出调用次数上限（正整数 max_calls）")
        self.log_path = log_path
        self.mode = mode
        self.max_calls = max_calls
        self.programs = dict(programs or {})
        self.timeout_seconds = timeout_seconds
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.calls = 0
        self._started = 0
        self._lock = threading.Lock()
        self._replay = _load_replay(replay_from) if mode == REPLAY else []
        self._by_vendor = {}
        self._by_task = {}

    def call(self, task, vendor, prompt, tools, model=None, placeholder=""):
        """调用一次模型，返回 (回答文本, 调用记录)。调用记录同时追加到 log_path。

        task        任务名，例如「出题-题目卡」「评审-要点抽取」；回放按它和提示词校验值取回答。
        vendor      "claude"、"codex"、"kimi" 或 "google"。
        prompt      提示词全文，从标准输入交给命令行（google 先由 _google_stdin 包成一行 JSON）；
                    调用记录里记原文。
        tools       MATERIALS_ONLY（只给材料）或 WEB_READ_ONLY（只读网页）。
        model       模型名，不给时 google 用 DEFAULT_MODELS 里的模型，其余三家用命令行自己的默认模型。
        placeholder 只估算模式下返回的占位回答，好让后面的步骤照常往下走。

        失败或超时：写下记录后抛出 ModelCallError（记录在 .record 上）。
        超过上限：抛出 CallLimitExceeded，不启动命令行，也不写记录。
        回放找不到：抛出 ReplayMissing，不写记录。
        """
        if vendor not in VENDORS:
            raise ValueError("不认识的厂商：%r，只能是 %s" % (vendor, "、".join(VENDORS)))
        if tools not in (MATERIALS_ONLY, WEB_READ_ONLY):
            raise ValueError("不认识的工具限定：%r，只能是「%s」或「%s」"
                             % (tools, MATERIALS_ONLY, WEB_READ_ONLY))
        model = model or DEFAULT_MODELS.get(vendor)
        if self.mode == LIVE:
            with self._lock:
                if self._started >= self.max_calls:
                    raise CallLimitExceeded("已经发起 %d 次真实调用，到了上限，任务「%s」没有调用"
                                            % (self._started, task))
                self._started += 1
        record = {
            "run_id": self.run_id, "call_index": None, "task": task,
            "vendor": vendor, "company": COMPANIES[vendor], "model": model,
            "reported_model": None, "reported_tools": None, "tools": tools,
            "mode": self.mode, "status": None, "error": None,
            "prompt": prompt, "prompt_sha256": _sha256(prompt),
            "answer": "", "answer_sha256": None,
            "started_at": None, "ended_at": None, "duration_seconds": None,
            "command": None, "config_files": {}, "exit_code": None,
            "raw_output": "", "stderr": "", "replayed_from": None,
        }
        if self.mode == ESTIMATE:
            record["status"] = NOT_CALLED
            record["answer"] = placeholder
        elif self.mode == LIVE and vendor == "google" and tools == WEB_READ_ONLY:
            # agy 非交互运行时读网页要人批准，一律被拒；模型可能凭记忆作答而被当成成功，所以直接判为不可用
            record["status"] = FAILED
            record["error"] = ("Google（agy）不能用于只读网页一档：非交互运行时读取网页需要人批准，"
                               "一律被拒，没有启动 agy")
        elif self.mode == REPLAY:
            with self._lock:
                self._replay_into(record)
        else:
            self._run_program(record)
        record["answer_sha256"] = _sha256(record["answer"])
        self._write(record)
        if record["status"] in (FAILED, TIMED_OUT):
            raise ModelCallError("%s 调用%s（任务「%s」）：%s" % (
                vendor, record["status"], task, record["error"]), record)
        return record["answer"], record

    def _replay_into(self, record):
        for slot in self._replay:
            entry = slot["entry"]
            if slot["used"] or entry.get("task") != record["task"]:
                continue
            if entry.get("vendor") != record["vendor"]:
                continue
            if entry.get("prompt_sha256") not in (None, record["prompt_sha256"]):
                continue
            slot["used"] = True
            record["started_at"] = record["ended_at"] = _now()
            record["duration_seconds"] = 0
            record["answer"] = entry.get("answer") or ""
            record["reported_model"] = entry.get("reported_model")
            record["reported_tools"] = entry.get("reported_tools")
            record["status"] = SUCCEEDED
            record["replayed_from"] = {"file": slot["file"], "run_id": entry.get("run_id"),
                                       "call_index": entry.get("call_index")}
            return
        raise ReplayMissing("回放找不到录好的回答：任务「%s」，厂商 %s，提示词校验值 %s"
                            % (record["task"], record["vendor"], record["prompt_sha256"]))

    def _run_program(self, record):
        vendor, tools, model, prompt = (record["vendor"], record["tools"], record["model"],
                                        record["prompt"])
        program = self.programs.get(vendor) or shutil.which(COMMANDS[vendor])
        if not program or not os.path.exists(program):
            record["status"] = FAILED
            record["error"] = "找不到命令行 %s（%s）" % (COMMANDS[vendor], program or "不在 PATH 里")
            return
        with tempfile.TemporaryDirectory() as scratch:
            work = os.path.join(scratch, "work")
            os.mkdir(work)
            build_args, read_answer, to_stdin = ADAPTERS[vendor]
            argv = [program] + build_args(tools, model, scratch, work)
            record["command"] = argv
            record["config_files"] = _config_files(scratch)
            record["started_at"] = _now()
            clock = time.monotonic()
            process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                       errors="replace", cwd=work, start_new_session=True)
            try:
                stdin = to_stdin(prompt) if to_stdin else prompt
                stdout, stderr = process.communicate(stdin, timeout=self.timeout_seconds)
                timed_out = False
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)  # 连同它启动的子进程一起停掉
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
                timed_out = True
            record["duration_seconds"] = round(time.monotonic() - clock, 3)
            record["ended_at"] = _now()
            record["exit_code"] = process.returncode
            record["raw_output"] = stdout
            record["stderr"] = stderr[-STDERR_KEPT:]
            found = read_answer(stdout, scratch, tools)
        error = found.pop("error", None)
        record.update(found)
        if timed_out:
            record["status"] = TIMED_OUT
            record["error"] = "超过 %s 秒没有结束，已停止" % self.timeout_seconds
        elif process.returncode != 0 or error or not record["answer"].strip():
            record["status"] = FAILED
            record["error"] = error or _failure_reason(process.returncode, stdout, stderr)
        else:
            record["status"] = SUCCEEDED

    def summary(self):
        """这次运行到目前为止的调用次数；只估算模式下就是估算的调用次数。"""
        with self._lock:
            return {
                "run_id": self.run_id, "mode": self.mode, "calls": self.calls,
                "by_vendor": dict(self._by_vendor), "by_task": dict(self._by_task),
                "max_calls": self.max_calls,
                "over_limit": self.max_calls is not None and self.calls > self.max_calls,
            }

    def _write(self, record):
        with self._lock:
            self.calls += 1
            record["call_index"] = self.calls
            self._by_vendor[record["vendor"]] = self._by_vendor.get(record["vendor"], 0) + 1
            self._by_task[record["task"]] = self._by_task.get(record["task"], 0) + 1
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
