# 模型调用层使用说明（tools/models.py）

模拟出题者和模拟评审通过这个模块调用本机已登录的三家模型命令行：Anthropic 的 `claude`、OpenAI 的 `codex`、月之暗面的 `kimi`。每次调用写一条完整的调用记录，一次运行的记录放在一个文件里，随复核包公开。测试时用回放方式或假的命令行程序，不真的调用模型。

只用 Python 自带的标准库。测试：在仓库根目录运行 `python3 -I -m unittest discover -s tests -v`，本模块的测试在 `tests/test_models.py`。

## 怎样调用

```python
import os, sys
sys.path.insert(0, os.path.join(仓库根目录, "tools"))
import models

run = models.ModelRun("输出目录/calls.jsonl", mode=models.LIVE, max_calls=40)
answer, record = run.call(task="评审-断言核验", vendor="claude",
                          prompt=提示词全文, tools=models.MATERIALS_ONLY)
# model 不给就用该命令行的默认模型；要指定就加 model="……"
print(run.summary())
```

对外接口：

- `ModelRun(log_path, mode=LIVE, max_calls=None, replay_from=None, programs=None, run_id=None, timeout_seconds=1800)`：一次运行。
  - `log_path`：调用记录文件，每行一条 JSON 记录（这种格式叫 JSON Lines），每次调用追加一行；目录不存在会自动建。一次运行用一个文件。
  - `mode`：`LIVE`（真实调用）、`REPLAY`（回放）、`ESTIMATE`（只估算）。
  - `max_calls`：真实调用的次数上限，真实调用时必须给正整数，否则报错；只估算时用来判断是否会超过上限。
  - `replay_from`：回放时读的调用记录文件，一个路径或路径列表。
  - `programs`：`{厂商: 程序路径}`，测试时指向假的命令行程序；不给就在系统的命令查找路径（`PATH`）里找 `claude`、`codex`、`kimi`。
  - `run_id`：运行编号，不给就用开始时间，例如 `20261030-153000`。
  - `timeout_seconds`：单次调用的时长上限，到了就停止该命令行（连同它启动的子进程），记为超时。
- `run.call(task, vendor, prompt, tools, model=None, placeholder="")`，返回 `(回答文本, 调用记录)`。
  - `task`：任务名，例如「出题-题目卡」「评审-要点抽取」。回放按任务名、厂商和提示词校验值取回答。
  - `vendor`：`"claude"`、`"codex"` 或 `"kimi"`。
  - `prompt`：提示词全文，从标准输入交给命令行。
  - `tools`：`MATERIALS_ONLY`（字符串「只给材料」）或 `WEB_READ_ONLY`（字符串「只读网页」）。
  - `model`：模型名，可选。
  - `placeholder`：只估算模式下返回的占位回答，好让后面的步骤照常往下走（例如给一段格式正确的空结果）。
- `run.summary()`：到目前为止的调用次数，字段是 `run_id`、`mode`、`calls`（总次数）、`by_vendor`（按厂商）、`by_task`（按任务）、`max_calls`、`over_limit`（是否超过上限）。只估算模式下就是估算的调用次数。
- 出错时抛出的三种异常：
  - `ModelCallError`：命令行失败、超时、找不到命令行，或没有拿到回答。调用记录已经写进文件，也挂在异常的 `.record` 上。某一家不可用时，调用方据此如实记录，不要伪造结果。
  - `CallLimitExceeded`：真实调用已经到了上限。这一次不启动命令行，也不写记录。
  - `ReplayMissing`：回放时找不到录好的回答。不写记录。
- 传入不认识的厂商、工具限定或方式时抛出 `ValueError`，不启动命令行。

同一个 `ModelRun` 可以在多个线程里同时调用，调用次数和记录文件的写入有锁保护。

## 两档工具限定

| 档位 | 含义 | 用在哪里 |
|---|---|---|
| 只给材料 | 模型只能读提示词里给它的材料：不能上网，不能运行命令，不能写文件 | 评审各步；泄露检查；闭卷对照 |
| 只读网页 | 只允许检索网页和读网页：不能运行命令，不能写文件 | 出题调研；没有网页存档时的来源核验 |

三家命令行都是"智能体"，自带读写文件、运行命令等工具，所以两档都要用参数关掉多余的工具，见下一节。每次调用都在一个新建的空临时目录里运行，调用结束后删除，所以即便哪个读文件的工具没关干净，也读不到仓库里的东西。

## 三家命令行的参数

共同做法：提示词一律从标准输入交给命令行（不放在命令行参数里，避免长度限制，也不会出现在进程列表里）；工作目录是新建的空临时目录；三家都用 `--model 模型名` 指定模型，不指定时不加这个参数。下面的参数依据 2026 年 10 月 30 日在本机查看的各命令行帮助信息（`--help`），以及下文写明的其他依据。实际用到的完整参数也逐条写在每条调用记录的 `command` 字段里。

### claude

版本：Claude Code 2.1.314。

只给材料：

```
claude -p --output-format stream-json --verbose --no-session-persistence --safe-mode --strict-mcp-config --disable-slash-commands --permission-mode dontAsk --tools ''
```

只读网页：

```
claude -p --output-format stream-json --verbose --no-session-persistence --safe-mode --strict-mcp-config --disable-slash-commands --permission-mode dontAsk --tools WebSearch,WebFetch --allowedTools WebSearch,WebFetch
```

每个参数的依据（帮助信息原话的意思）：

- `-p`（`--print`）：非交互运行，打印回答后退出；没有给提示词参数时从标准输入读。
- `--output-format stream-json --verbose`：逐行输出 JSON 事件。第一行是启动事件，写明实际使用的模型和可用工具列表，本模块把它们记进 `reported_model` 和 `reported_tools`；最后一行是结果事件，其中的 `result` 就是回答。
- `--no-session-persistence`：不把会话存到磁盘。
- `--safe-mode`：关掉所有个人定制（项目说明文件 CLAUDE.md、技能、已装插件、钩子、模型上下文协议服务器、自定义智能体等），登录和模型选择照常。用它避免本机的个人设置混进模拟出题和模拟评审。
- `--strict-mcp-config`：只用 `--mcp-config` 给出的模型上下文协议服务器（Model Context Protocol，给模型接外部工具的一种方式）。这里不给 `--mcp-config`，所以一个也没有。
- `--disable-slash-commands`：关掉所有技能和斜杠命令。
- `--permission-mode dontAsk`：没有事先允许的工具调用一律拒绝，不会停下来等人确认。
- `--tools ''`：帮助信息写明"用空字符串关掉所有工具"。只读网页档改为 `--tools WebSearch,WebFetch`，只留网页检索和网页读取两个工具；再用 `--allowedTools WebSearch,WebFetch` 事先允许它们，否则在 `dontAsk` 下会被拒绝。

试探调用时，启动事件报告：工具列表为空，模型上下文协议服务器为空，技能和斜杠命令为空，权限方式为 `dontAsk`。

没有用的参数：`--bare` 会跳过项目说明文件，但帮助信息写明它只认 `ANTHROPIC_API_KEY` 环境变量或 `apiKeyHelper`，不用本机登录，所以不用。

### codex

版本：codex-cli 0.164.0。

只给材料：

```
codex exec --json --output-last-message <临时目录>/last-message.txt --cd <临时目录>/work --ephemeral --skip-git-repo-check --ignore-user-config --ignore-rules --sandbox read-only -c 'approval_policy="never"' --disable shell_tool --disable unified_exec -c 'web_search="disabled"' -
```

只读网页：只把最后的网页检索设置换成 `-c 'web_search="live"'`（与 `--search` 相同），其余不变。

每个参数的依据：

- `exec`：非交互运行。最后的 `-` 表示从标准输入读提示词（帮助信息原话）。
- `--json`：把事件逐行输出成 JSON，原样存进 `raw_output`。
- `--output-last-message <文件>`：把最后一条回答写进这个文件。本模块从这个文件取回答，不依赖事件格式。
- `--cd <目录>`：工作根目录，用空临时目录。`--skip-git-repo-check`：允许在 git 仓库以外运行（临时目录不是仓库）。
- `--ephemeral`：不把会话文件存到磁盘。
- `--ignore-user-config`：不读用户的设置文件 `config.toml`（帮助信息写明登录仍然有效），避免用户设置里的模型上下文协议服务器和其他个人设置混进来；模型因此用 codex 的默认模型，除非调用时指定。
- `--ignore-rules`：不读用户和项目的命令执行规则文件。
- `--sandbox read-only`：沙箱只读，模型生成的任何写文件操作都写不进去。`codex debug prompt-input` 显示的权限说明是"沙箱只允许读文件，网络访问受限"。
- `-c 'approval_policy="never"'`：从不请人批准，模型申请放宽沙箱时直接拒绝。可选值由 codex 的报错信息确认（`untrusted`、`on-failure`、`on-request`、`granular`、`never`）；设成 `never` 后，`codex debug prompt-input` 显示的权限说明是"批准方式为从不，申请会被拒绝"。这个参数是试探调用之后加的，试探调用时还没有它。
- `--disable shell_tool --disable unified_exec`：关掉两种运行命令的工具。这两个名字来自 `codex features list` 列出的功能开关。
- `-c 'web_search="disabled"'` 和 `-c 'web_search="live"'`：网页检索的设置。可选值由 codex 自己的报错信息确认：传入一个错误的值时，它报"只能是 `disabled`、`cached`、`indexed`、`live`"。

其他依据：`codex debug prompt-input` 能在本机列出模型看到的工具，不调用模型。用上面的参数列出时，运行命令的工具（`exec_command`、`write_stdin`）已经没有了。

没能关掉、如实说明：以下几样工具没有找到关闭的参数，仍在工具列表里。

- `apply_patch`（改文件）：在只读沙箱下写不进去。
- 子智能体协作（`spawn_agent` 等）：`--disable multi_agent` 之后仍在列表里。子智能体是否沿用同样的沙箱和网页检索设置，帮助信息里没有写明，未核实。
- 模型上下文协议资源的列举和读取：不读用户设置以后没有配置任何服务器，没有可读的资源。
- `request_user_input`（向人提问）、`sleep`（等待）：非交互运行时没有人回答，不涉及上网、运行命令或写文件。

只读网页档用的是 codex 自带的网页检索工具，检索和打开网页都在这个工具里完成，没有单独的读网页工具。

### kimi

版本：kimi 1.49.0。

两档都一样：

```
kimi --print --output-format stream-json --work-dir <临时目录>/work --agent-file <临时目录>/agent.yaml --mcp-config-file <临时目录>/mcp.json --skills-dir <临时目录>/skills
```

两档的区别在临时写出的智能体说明文件 `agent.yaml` 里（用 JSON 写法，kimi 按 YAML 读，两者兼容）：

- 只给材料：`{"version": 1, "agent": {"extend": "default", "tools": [], "subagents": {}}}`
- 只读网页：`"tools": ["kimi_cli.tools.web:SearchWeb", "kimi_cli.tools.web:FetchURL"]`，其余相同。

`mcp.json` 的内容是 `{"mcpServers": {}}`，`skills` 是一个空目录。这两个文件的原文都记进调用记录的 `config_files` 字段。

每个参数的依据：

- `--print`：非交互运行。帮助信息写明：这种方式会自动批准所有工具调用。所以必须先把工具限定好，自动批准的只能是允许的那几个工具。
- `--output-format stream-json`：逐行输出消息，每行一条 JSON。本模块取最后一条助手消息里的文字部分作为回答（思考部分不算）。
- 没有 `--prompt` 时从标准输入读提示词：帮助信息写明 `--input-format` 要求"输入从标准输入管道读入"；本机安装的 kimi 源码里也是这样处理的。注意 kimi 会去掉提示词首尾的空白，调用记录里的提示词和校验值是本模块交出去的原文。
- `--work-dir`：工作目录，用空临时目录。
- `--agent-file`：自定义的智能体说明文件。帮助信息没有写文件格式，格式依据本机安装的 kimi 源码（`kimi_cli/agentspec.py` 和自带的 `agents/default/agent.yaml`）：`extend: default` 继承默认智能体的系统提示词，`tools` 整个替换默认的工具列表，`subagents` 设成空，不能再派子智能体。
- `--mcp-config-file`：源码里，只有不给这个参数时才会读用户的默认模型上下文协议设置文件；所以给一个空设置，避免用户配置的服务器混进来。（只给 `--mcp-config` 不能阻止读默认文件。）
- `--skills-dir`：帮助信息写明"覆盖默认的技能查找位置"，给一个空目录，就没有技能。

没能关掉、如实说明：

- 插件目录里的插件工具：源码里，不论智能体说明文件怎么写，都会从 kimi 的插件目录加载插件工具，没有找到关闭的参数。没有查看本机装了哪些插件（那是 kimi 的配置目录）。
- 会话记录：kimi 没有不存会话的参数，每次调用会在它自己的目录里留一份会话记录。

## 调用记录

每次调用（含失败和超时，也含回放和只估算）写一条记录。记录文件每行一条 JSON，字段如下：

| 字段 | 含义 |
|---|---|
| `run_id` | 运行编号 |
| `call_index` | 本次运行中的第几条记录，从 1 起 |
| `task` | 任务名 |
| `vendor` | 命令行：`claude`、`codex` 或 `kimi` |
| `company` | 厂商：Anthropic、OpenAI 或 月之暗面 |
| `model` | 调用时指定的模型；没指定时为空，表示用命令行的默认模型 |
| `reported_model` | 命令行自己报告的实际模型（目前只有 claude 报告），没有时为空 |
| `reported_tools` | 命令行自己报告的可用工具列表（目前只有 claude 报告），没有时为空 |
| `tools` | 工具限定：「只给材料」或「只读网页」 |
| `mode` | 方式：「真实调用」「回放」或「只估算」 |
| `status` | 结果：「成功」「失败」「超时」或「未调用」（只估算） |
| `error` | 失败或超时的原因：退出状态，加上标准错误和标准输出里不是 JSON 的最后几行；成功时为空 |
| `prompt` | 提示词全文 |
| `prompt_sha256` | 提示词（按 UTF-8 编码）的 SHA-256 校验值 |
| `answer` | 回答全文；失败时为空 |
| `answer_sha256` | 回答的 SHA-256 校验值 |
| `started_at` | 开始时间，带时区的 ISO 8601 格式，精确到毫秒 |
| `ended_at` | 结束时间，格式同上 |
| `duration_seconds` | 耗时，单位秒 |
| `command` | 实际执行的完整命令行参数列表（提示词不在其中，走标准输入） |
| `config_files` | 调用前写进临时目录的设置文件原文，`{文件名: 内容}`；目前只有 kimi 有 |
| `exit_code` | 命令行的退出状态 |
| `raw_output` | 命令行的标准输出原文（各家的 JSON 事件流），供复核 |
| `stderr` | 标准错误的最后两万字 |
| `replayed_from` | 回放时写明回答出自哪里：`{"file": 记录文件, "run_id": 原运行编号, "call_index": 原记录序号}`；其他方式为空 |

记录里没有任何凭据：模块不读环境变量，也不读各家的登录文件，见"不读取密钥"一节。

## 回放

`ModelRun(新的记录文件, mode=models.REPLAY, replay_from=录好的记录文件)` 之后照常调用 `call`，不启动任何命令行，回答从录好的记录里取：

- 按任务名、厂商和提示词校验值三者匹配；只取状态为「成功」的记录（失败、超时、只估算的记录跳过）。
- 同样的调用出现多次（例如同一家评委评两次），按录制时的先后依次取出；取完再调用就抛出 `ReplayMissing`。
- 手写的回放材料可以只写 `task`、`vendor`、`answer` 三个字段，不写 `prompt_sha256`，这时匹配该任务、该厂商的任何提示词。这是给后续模拟出题者和模拟评审的测试用的：测试不必事先算出提示词。
- 回放也写一条记录，`mode` 为「回放」，`replayed_from` 指向出处。

## 只估算和调用次数上限

- 只估算：`mode=models.ESTIMATE`。不启动任何命令行，`call` 返回 `placeholder`（默认空字符串），每次调用照样写一条记录（状态「未调用」），`run.summary()` 给出按厂商、按任务的调用次数和是否超过 `max_calls`。真跑之前先用这个方式算出将要发起的调用次数。
- 调用次数上限：真实调用必须给 `max_calls`。已经发起的真实调用（含失败和超时）达到上限后，再调用就抛出 `CallLimitExceeded`，不启动命令行。回放和只估算不受上限限制。

## 不读取密钥

模块只用本机已登录的账号：不读、不改、不打印任何凭据文件；除了按系统的命令查找路径找程序以外，不读环境变量；启动命令行时原样继承当前环境。测试里有一项检查模块源码不涉及环境变量、钥匙串和三家的配置目录。查参数时只看了帮助信息、`codex features list`、`codex debug prompt-input` 的工具列表和本机安装的 kimi 源码，没有打开任何配置文件。

## 试探调用的结果

2026 年 10 月 30 日，用本模块对每家各做了一次极小的真实调用：只给材料档，提示词「只回复一个字：好」，不指定模型。

| 命令行 | 结果 | 耗时 | 说明 |
|---|---|---|---|
| claude | 成功，回答「好」 | 1.6 秒 | 启动事件报告模型 `claude-opus-5-5`，工具列表为空，没有模型上下文协议服务器、技能和斜杠命令 |
| codex | 成功，回答「好」 | 3.8 秒 | 事件流里只有一条回答，没有运行任何命令；没有报告模型名 |
| kimi | 失败，退出状态 1 | 13.8 秒 | 参数都被接受，已经连到服务，但服务回 401 错误："The API Key appears to be invalid or may have expired"，即本机的 kimi 登录已失效或过期。没有尝试重新登录。kimi 的只读网页档和回答解析因此都未经真实调用核实 |

kimi 要用之前，需要有人在本机运行 `kimi login` 重新登录。
