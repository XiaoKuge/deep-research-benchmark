# 18: 代码审查后的修正（二）：模型调用层、模拟出题与评审、运行程序、模拟网页

**What to build:** 2026-10-30 两路代码审查（规范、需求）之后，修 `tools/` 和 `site/build_simulation.py` 里的问题。规则手册（`research-plan/rules.md` 草案第 3 版）是准绳；网页上已经写明"用 Claude（Anthropic）、Codex（OpenAI）、Gemini（Google）三家模型，Kimi（月之暗面）作备用"，程序的默认设置要与它一致。

**Blocked by:** 无（与 17 号并行，文件不重叠）

**Status:** resolved

只改：`tools/` 下的程序和说明、`site/build_simulation.py` 及生成的 `site/simulation/`、相应的测试。不改 `research-plan/`、`site/build_results.py`、手写网页（17 号在改）。

- [x] **按档判断哪家能用。** 在 `models.py` 加一个对外函数，说明某一家能不能用于某一档（目前只有 google 不能用于只读网页一档，与 `call()` 里的拒绝用同一处判断）。模拟评审和模拟出题挑厂商、找替代时先用它：计划的厂商不能用于这一档，就直接按替代顺序换一家，记一条替代，原因写明"不能用于只读网页一档"，不发一次注定失败的调用，也不把这一家判为整次运行都不可用。只估算模式同样按它挑厂商，估算出的各家调用次数才与真实运行一致。有测试
- [x] **默认厂商与网页一致。** 模拟评审 `DEFAULT_CONFIG`：原来用 kimi 的步骤改用 google，替代顺序 claude、codex、google、kimi。模拟出题 `DEFAULT_VENDORS`：写深度地图要读网页，google 不能当；改为地图甲 claude、地图乙 codex，泄露检查和闭卷对照 google（闭卷对照仍须与写地图的两家都不同）。命令行帮助、说明文件同步改
- [x] **至少三家厂商（规则第七节"评委组"第 1 条）。** 替代之后，凡是计划用三家以上的步骤，实际用到的厂商不足三家时，在 run.json 记下这一步不合这条规则，评审页上用醒目的一句话写明；不中止运行。有测试
- [x] **替代记录统一一种格式。** 模拟出题（`Roles`）和模拟评审（`Context`）的替代记录现在一种用中文键、一种用英文键，`build_simulation.py` 两处各读一种。统一成一种（字段：步骤、任务、原来的厂商、改用的厂商、原因），两边共用同一段挑选替代的代码（放进 `models.py` 或新模块均可），`build_simulation.py` 只读这一种；已经提交的 `simulation/` 数据按新格式迁移（写一次性的迁移脚本，或在读取处兼容旧格式，二选一，说明理由）
- [x] **合并要点时隐去出处要有程序检查。** 现在只靠 `merge.txt` 里的一句要求。合并后的要点文字里出现报告代号或产品名（取自对照表 mapping.json），就把这次合并判为回答无效，按已有的无效回答处理。有测试
- [x] **深度地图的完成标准如实记录。** 模拟出题里"两人对过"不再写死为是，按两张地图是否真的都写出并对照过来记；"四层都查过"不只做字符串包含判断，按地图表格里四个层级是否各有要点或写明"查过，没有"来判断。有测试
- [x] **运行程序按规则改。** `run_agents.py` 删掉 20 次反问就结束运行的上限（规则第五节：运行只在时长上限时结束）；说明里写明产品界面上只能选"批准计划"的直接批准（规则第五节），命令行和网络接口两种方式没有批准计划这种消息，每次反问都回附录二的原文。交给队伍智能体的环境变量不再整份复制主办方的环境：只传一个固定的最小集合（PATH、HOME、LANG、LC_ALL、TMPDIR、USER、SHELL、TERM），加上队伍在声明里点名要的变量名（声明里新增一项"需要的环境变量"，只写名字）；说明和队伍文档里提到声明格式的地方同步改。有测试
  - 已做：`run_agents.py` 和 `tools/run_agents.md`、测试。没做：`site/teams.html`、`site/starter-kit/README.md` 和 `申报表模板.json` 里讲环境变量（"沿用全部环境变量"）、20 次反问上限和申报格式的地方，这几个文件归 17 号，留给合并之后改；`tests/test_team_docs.py` 里两边共有的约定去掉了"20 次"。
- [x] **子进程。** `models.py`：命令行正常退出后也停掉它的整个进程组，免得留下子进程。`simulate_review.run_scorer` 调计分程序加时长上限。有测试（假程序起一个子进程后退出，检查子进程被停掉）
- [x] **网页文字和规范。** `build_simulation.py`：可见文字里的"UTC−07:00"改成"协调世界时减 7 小时"这种白话（与 `archive_sources.py` 一致），"SHA-256"改称"校验值"；与 `models.SUCCEEDED` 比较，不写字面的"成功"；删掉只转调 `results.tag` 的 `tag()`；输出目录先在旁边的新目录里写完，再换下旧目录（现在是先删旧目录再写，中途出错网站就空了）
- [x] **共用小工具。** `tools/` 各程序里各自写的校验值、当前时间、写 JSON 的函数改用 `tools/common.py`（已在集成分支上）；读录好的调用记录的代码（`models._load_replay`、`simulate_setter.ReplayFailures`、`simulate_review.replay_failures`）能合并的合并。各程序写出的文件格式不变（缩进、时间精度保持原样）
- [x] 重新生成 `site/simulation/`；全部测试通过（`python3 -I -m unittest discover -s tests`）
