# 第五阶段试评的评委提示词和整理脚本

2026-10-30 存档。规则要求复核包公开全部评委提示词。这个目录收录第五阶段小规模检验里每一次评委运行收到的提示词原文、一份清单，以及评委写出输出文件时留下的辅助脚本。

## 这里有什么

- [manifest.json](manifest.json)：清单。`out/` 下每个评委输出文件一条，记下对应的提示词文件、任务、派出时的任务描述和调用编号、派出时指定的模型、实际运行的模型、派出时间和日期、评委自己的会话记录在哪里、输出文件是怎样写出的，以及备注。清单里的路径都相对于 `stage5-pilot/`。
- [prompts/](prompts/)：提示词原文，每次评委运行一个文件，文件名与输出文件同名。
- [scripts/](scripts/)：评委写出输出文件时留下的辅助脚本。

## 提示词从哪里来

评委都是主会话派出的子任务，彼此看不到对方的输出（见检验设计 [design.md](../design.md)「评委运行」一节）。主会话交给评委的任务提示只存在本次会话的会话记录里：

`~/.claude/projects/-Users-zonghuanwu-projects-GOSIM-elite-game/efdc4f00-f3cf-4541-917e-bb46cf1f48bb.jsonl`

会话记录是 JSON Lines 文件，一行一个 JSON 对象。派出评委的调用，是助手消息里 type 为 tool_use、name 为 Agent 的条目，它的 input 里有任务描述 description、任务提示 prompt，指定了模型时还有 model。

- 2026-10-29 22:20（协调世界时，下同）以后，这样的调用共 14 次，正好对应 `out/` 下的 14 个文件，一个文件一次。没有重派的评委，也没有中途追加的指示：每个评委自己的会话记录里只有这一条任务提示，而且与主会话记录里的逐字相同。
- 提示词文件就是会话记录里 prompt 字段的原文，UTF-8 编码，一字未改，包括其中的绝对路径；结尾没有补换行。
- 同一次调用在会话记录里出现两次，另一份副本没有时间戳。两份内容相同，按调用编号去重。
- 评委另外还会收到运行环境自带的通用说明和工具列表。这部分不在主会话的会话记录里，没有存档。

## 清单

时间是派出评委的时间，按协调世界时。换成本机所在的太平洋夏令时，是 10 月 29 日 15:23 至 16:06，日期相同。实际运行的模型取自每个评委自己的会话记录。

| 输出文件 | 提示词 | 任务 | 模型 | 派出时间 |
|---|---|---|---|---|
| [rating-opus-1.json](../out/rating-opus-1.json) | [rating-opus-1.txt](prompts/rating-opus-1.txt) | 环节评级与要点抽取，第一次，按 A 至 F 的顺序读 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:23 |
| [rating-opus-2.json](../out/rating-opus-2.json) | [rating-opus-2.txt](prompts/rating-opus-2.txt) | 环节评级与要点抽取，第二次，按 F 至 A 的倒序读 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:23 |
| [rating-sonnet-1.json](../out/rating-sonnet-1.json) | [rating-sonnet-1.txt](prompts/rating-sonnet-1.txt) | 环节评级与要点抽取，Sonnet 一次 | claude-sonnet-5-5（派出时指定 sonnet） | 2026-10-29 22:23 |
| [verify-opus-ABCF.json](../out/verify-opus-ABCF.json) | [verify-opus-ABCF.txt](prompts/verify-opus-ABCF.txt) | 断言核验，报告 A、B、C、F | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [verify-opus-DE.json](../out/verify-opus-DE.json) | [verify-opus-DE.txt](prompts/verify-opus-DE.txt) | 断言核验，报告 D、E | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [pairwise-opus-fwd.json](../out/pairwise-opus-fwd.json) | [pairwise-opus-fwd.txt](prompts/pairwise-opus-fwd.txt) | 两两比较，第一次 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [pairwise-opus-rev.json](../out/pairwise-opus-rev.json) | [pairwise-opus-rev.txt](prompts/pairwise-opus-rev.txt) | 两两比较，第二次，交换每对的先后，并按 F 至 A 的倒序读 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [single-P1.json](../out/single-P1.json) | [single-P1.txt](prompts/single-P1.txt) | 扰动版的完整评审，P1 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [single-P2.json](../out/single-P2.json) | [single-P2.txt](prompts/single-P2.txt) | 扰动版的完整评审，P2 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [single-P3.json](../out/single-P3.json) | [single-P3.txt](prompts/single-P3.txt) | 扰动版的完整评审，P3 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [single-P4.json](../out/single-P4.json) | [single-P4.txt](prompts/single-P4.txt) | 扰动版的完整评审，P4 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:24 |
| [pool.json](../out/pool.json) | [pool.txt](prompts/pool.txt) | 要点池的合并与判定 | claude-opus-5-5（派出时未指定，沿用主会话的模型） | 2026-10-29 22:42 |
| [verify-sonnet-subset.json](../out/verify-sonnet-subset.json) | [verify-sonnet-subset.txt](prompts/verify-sonnet-subset.txt) | 断言核验的稳定性：独立重核 15 条断言 | claude-sonnet-5-5（派出时指定 sonnet） | 2026-10-29 22:42 |
| [direct-answers.json](../out/direct-answers.json) | [direct-answers.txt](prompts/direct-answers.txt) | 标出每份报告对题目的直接回答 | claude-sonnet-5-5（派出时指定 sonnet） | 2026-10-29 23:06 |

## 没有单独提示词的步骤

`out/` 下 14 个文件都找到了对应的提示词。要点池的合并与判定、对题目直接回答的标注，也都是派出的评委做的，各有提示词。但有两处准备工作是主会话自己做的，没有单独的提示词，已在清单的备注里写明：

1. **重核哪 15 条断言。** 由主会话从 verify-opus-ABCF.json 和 verify-opus-DE.json 中挑出，断言内容由主会话写进提示词的表格。会话记录里没有写明挑选规则。
2. **主要结论清单 `claims-list.md`。** 标注直接回答的评委读的是这份清单。它是主会话用一小段程序从 verify-opus-*.json 和 single-P*.json 原样抄出的，没有做任何判定。

## 辅助脚本

评委写出输出文件的方式有三种：用写文件工具直接写；在命令行里用一段内嵌的 Python 程序写；先写一个脚本文件再运行它。每个输出文件用的是哪种，见清单的 written_by 一栏。留下脚本文件的有五个，原样复制在 `scripts/`，一字未改：

| 脚本 | 写它的评委 | 写出的文件 |
|---|---|---|
| [build_rating.py](scripts/build_rating.py) | 环节评级与要点抽取，Opus 第一次 | rating-opus-1.json |
| [build_verify.py](scripts/build_verify.py) | 断言核验，报告 D、E | verify-opus-DE.json |
| [write_pairs.py](scripts/write_pairs.py) | 两两比较，第一次 | pairwise-opus-fwd.json |
| [build.py](scripts/build.py) | 环节评级与要点抽取，Sonnet | rating-sonnet-1.json |
| [build_pool.py](scripts/build_pool.py) | 要点池的合并与判定 | pool.json |

- 任务单原本列了前三个。整理时在会话临时目录里又找到 `build.py` 和 `pilot/pooltmp/build_pool.py`，查评委自己的会话记录，确认也是评委写的，一并存档。
- 这些脚本不是计分程序，只是把评委的判定写成 JSON 文件：评分、引文、理由都直接写在脚本里。有几个脚本还会顺带核对引文是否逐字出自报告。
- 两两比较第二次的评委，也在同一个位置写过一个 `write_pairs.py`，运行后自己删掉了；约 21 秒后，第一次的评委才写下现在这一份。所以存档的是第一次那份，第二次那份的原文只在它自己的会话记录里。
- 脚本里写死了原来的路径：从 `~/github/mofa-research/docs/deep-research-benchmarks-2026/research-plan/stage5-pilot/` 读报告，写到它下面的 `out/`。直接运行会覆盖 `out/` 下的文件。要复核，请复制一份，把输出路径改到别处再运行。
- 2026-10-30 这样做过一次：把输出路径改到临时目录后，五个脚本写出的文件与 `out/` 下对应的文件逐字节相同。`out/` 下 14 个文件的修改时间也都与各个评委结束的时间吻合；主会话此后只读过这些文件，没有改过。
- 脚本和提示词里没有密钥，只有路径、报告引文和评委的判定。测试会检查整个目录里没有像密钥的字符串。

## 怎样复核

在仓库根目录运行：

- `python3 -I tools/judge_prompts.py check`：重新从会话记录取出每次运行的提示词，与 `prompts/` 下的文件逐字比对，并核对清单里的任务描述、派出时指定的模型、派出时间和日期；如果评委自己的会话记录还在（会话记录旁同名目录下的 `subagents/`），还核对实际运行的模型。全部一致时退出码为 0，否则为 1，并列出哪一条、哪一处不一致。
- `python3 -I tools/judge_prompts.py extract`：按清单重新写出提示词文件。
- 测试：`python3 -I -m unittest discover -s tests`，其中 `tests/test_judge_prompts.py` 是这部分的测试。本机没有会话记录时，与会话记录比对的那一项会跳过。
