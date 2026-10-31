# 深度研究评测基准

给智能体的"深度研究"下一个严格的定义，并据此给研究报告排名。这里是这项工作的公开材料：文献精读、研究计划、论文工作稿、比赛规则手册、出题手册、计分和模拟程序、试评数据和资料站。

- **资料站：** https://xiaokuge.github.io/deep-research-benchmark/
- **文献列表：** https://xiaokuge.github.io/deep-research-benchmark/papers.html

规则手册和评法都还是草案。试评名次只是演示，不是对产品的评价。

## 公开与本机

GitHub Pages 直接从 `main` 分支的仓库根目录发布，推送后自动更新。根目录的 `index.html` 只负责跳到 `site/`。

下面这些只留在本机，不进仓库，也不在提交历史里：

- **第三方全文：** 23 篇论文的 PDF 和 `outside-field/` 下的领域外原文。版权在原作者和出版方，公开版一律链接到 arXiv 和原始出处，出处清单见 [outside-field/index.html](outside-field/index.html)。
- **私人阅读笔记：** `literature.local.html`（作者分级、注意事项、阅读状态）和 `comments.json`（给 Claude 的留言）。运行 `python3 serve.py` 后在 http://localhost:8766/ 打开。改完之后运行 `python3 -I render_papers.py`，重新生成公开版 [papers.html](papers.html)，作者分级和注意事项不会写进去。
- **研究过程的原始记录：** `local-only/`，包括完整的会话记录、会话临时目录、三月的原始报告，以及整理公开版之前的完整提交历史（`git-history-before-publish.bundle`）。

## 文献（2025-08 ～ 2026-10）

2026-10-28 下载，共 23 篇，均为 arXiv 最新版本。
「为什么读」依据 arXiv 摘要页；中文摘要在 [papers.html](papers.html) 里，每篇可展开。
精读分析在 `notes/`，索引里每篇有「精读分析 →」按钮。
[评测工具一览](notes/overview-tools.html)：23 篇里哪些能"输入报告、输出分数/名次"，以及怎么拼给 5 个 Agent 用。
[Research / Deep Research 的定义](notes/overview-definitions.html)：23 篇里只有 LiveDRBench 给了正式定义；"Research"实指调研，"Deep"有 6 种意思。
[Benchmark 的定义](notes/overview-benchmark.html)：没人定义"benchmark"；隐含的四个零件、约 10 条要求、三种理解，以及最缺的效度。
[从共性提炼的四个定义](notes/overview-common-definitions.html)：按"多少篇支持"取共性，给出 Research / Benchmark / Deep Research / DR Benchmark 的定义，附 20 篇编码表。
[研究计划](research-plan/v3.md)：《智能体深度研究评测基准研究计划》第三稿（当前稿）。`v1.md` 为原稿，`v2.md` 因过早给出具体方法已作废。

[第一阶段概念说明](research-plan/stage1-concepts.md)：第三稿第一阶段的产出，开头有结论汇总，后文保留逐项讨论的经过。[对照报告收集规程](research-plan/collection-protocol.md)：按基础级规则收集真实报告的规程和两道题目草稿。

[第二阶段审视框架](research-plan/stage2-framework.md)、[18 份审视记录](research-plan/stage2-records/)、[第二阶段汇总](research-plan/stage2-summary.md)：系统审视 18 个评测工具。各精读页顶部的"勘误"框来自汇总第六节，正文未改动。引用的领域外原文（情报分析标准、AMSTAR 2、SANRA、《弗拉斯卡蒂手册》第二章、市场研究守则、《反对本本主义》《实践论》）以及谷歌、OpenAI、Perplexity、Anthropic 对自家深度研究产品的描述，存放在 `outside-field/`。

[第三阶段：关键问题](research-plan/stage3-problems.md)：把第二阶段的 17 类问题按"从题目到名次"的八个步骤归并成 8 个关键问题，每个附证据、现有办法、未知之处和子问题；优先级已按候选定稿（研究发起人授权自动完成）。

[第四阶段：改进方案](research-plan/stage4-design.md)、[评审细则](research-plan/stage4-rubric.md)、[第五阶段：试跑结果与修订](research-plan/stage5-report.md)：评法第 1.1 版，以及用三月那批六份真实报告试跑的结果；原始数据、评委输出和计分程序在 `research-plan/stage5-pilot/`。**先读 [一页总结](research-plan/summary.md)。**

[论文工作稿](research-plan/paper.md)：《什么是智能体的"深度研究"：一个严格的定义，及据此给报告排名的方法与检验》。主要贡献是"深度研究"的三层定义，评测方法和小规模检验是它的应用与印证。包括摘要、引言、相关工作、方法、实验、结论和参考文献（45 条）。作者栏待填。PDF 版是 [research-plan/paper.pdf](research-plan/paper.pdf)，改了 `paper.md` 之后运行 `python3 render_pdf.py` 重新生成。

[出题手册](notes/question-handbook.html)：给大学一年级同学的出题方法，含三个概念、出题七步、两个实例、红笔批改、自查清单和模板。源文件是 `research-plan/question-handbook.src.html`，运行 `python3 render_plan.py` 时加上网页的头尾，生成本地版。自 2026 年 10 月 30 日起以本地版为准，不再依赖在线版。

[比赛规则手册](notes/rules.html)：源文件是 `research-plan/rules.md`，由 `render_plan.py` 生成网页；内容取自 2026 年 10 月 30 日在线文档的第 17 次修订，此后以本地版为准。深度研究赛项的出题、冻结与申报、运行、交付、评审、名次、申诉和违规处理。现为草案第 3 版，附录五是版本变更记录。标有〔默认〕的条款待主办方确认。它和出题手册第 2 版一起，回应了三个问题：开发者能否按题目改提示词、提问者和用途是否符合真实场景、深度地图的质量怎样保证。

[对照巡天网站结构](research-plan/site-mapping.md)：把现有资料和程序按巡天黑客松网站（create.gosim.org/survey26）的公开页面、参赛者页面、后台与程序逐项对照，列出已有、部分、缺和待办。

[资料站](site/index.html)：把研究、规则、出题手册、文献和领域外资料收在一页，可筛选。首屏是用 Archify 画的[评测基准架构图](site/diagrams/architecture-dr-benchmark/benchmark-architecture-explained.html)，点任一环节会显示它是什么、做什么用。图的源文件是同一目录的 `candidate.json`，节点说明在 `node-notes.json`；改说明后运行 `build_explained.py` 生成讲解版，原图 `benchmark-architecture.html` 保持 Archify 生成的原样。[一道题走完全程](site/walkthrough.html)：以淡水湖这道题为例走完十一站，五份报告是虚构的示意，分数按真实规则算出，可用 `site/walkthrough_example.py` 复算。页面按 landing-page-design 技能的规则制作，大纲和与规则不一致之处见 `site/landing-plan.md`。

**资料站的比赛页面**：都在 `site/`，双击即可打开；首页导航的"比赛"下拉、手机菜单和资料库的"比赛"一组都能进入。页脚的行为准则、联系方式和数据使用许可还没有定，标〔待定〕。
- [赛事说明](site/brief.html)：比什么、练习和正式两个阶段、运行、评审、名次与公布、申诉、封闭组和开放组、随机抽查；日程、奖项和报名方式〔待定〕。
- [上手](site/start.html)：出题同学、参赛队伍、评委各自的第一步；现阶段出题和评审由大模型程序模拟，页上有运行命令。
- [公告](site/news.html)：日程变动和规则版本变更，新的在上面。
- [常见问题](site/faq.html)：资料站问答和出题手册的常见问题合在一页，按出题、参赛、评审分组。
- [参赛队伍技术文档](site/teams.html)：智能体怎样申报、主办方怎样调用它、运行环境、时长上限和统一答复。
- [新手包](site/starter-kit/README.md)：申报表模板、示例系统提示词、练习题、交付要求原文、示例智能体、示例运行计划，和检查报告五个必备部分的小程序 `check_report.py`。
- [试评名次](site/results/index.html)：第五阶段六份报告的名次区间、每份报告的复核页和要点池页，是试评演示，不是对产品的评价。由 `python3 -I site/build_results.py` 从 `research-plan/stage5-pilot/` 生成，不手工修改。
- [题库](site/simulation/questions.html)和[评审记录](site/simulation/reviews.html)：模拟出的题和每一次模拟评审，每一次模型调用都能点开看原文；正式题公开之前只显示深度地图的校验值。由 `python3 -I site/build_simulation.py` 从 `simulation/` 生成，不手工修改。

**程序**：在 `tools/`，只用 Python 自带的标准库，不需要装别的包；除评委提示词核对程序和下面最后三个共用的小程序外，每个程序都有同名的使用说明（`.md`）。
- [统一运行程序](tools/run_agents.md) `run_agents.py`：运行日按运行计划调用每个参赛智能体（命令行或网络接口），把题目原样交给它，记输入校验值，反问时给统一答复，到时长上限就停，按规则手册附录四写运行记录。
- [网页存档程序](tools/archive_sources.md) `archive_sources.py`：提取报告里的网址，逐个取回，按校验值保存，写一份清单；单个网址打不开只记原因，不中断，不用任何第三方存档服务。
- [模型调用层](tools/models.md) `models.py`：统一调用本机已登录的 Claude、Codex、Kimi 和 Google Antigravity 四家命令行，分"只给材料""只读网页"两档工具限定，每次调用写完整记录；有回放方式供测试，有调用次数上限和只估算模式。不读取任何密钥。
- [模拟出题者](tools/simulate_setter.md) `simulate_setter.py`：还没有真人出题者时，让模型按出题手册七步出一道题，输出题目卡三个版本、深度地图、两人对照、泄露检查、闭卷对照和调用记录。
- [模拟评审](tools/simulate_review.md) `simulate_review.py`：还没有真人评委时，让几家模型按评审细则评审一组报告，没有一种意见达到三分之二的判定记为有争议，再调用计分程序第 1.2 版。评委提示词模板在 `tools/review_prompts/`。
- 共用的小程序：`common.py`（校验值、带时区的当前时间、先写临时文件再整份替换的写文件）；`substitutes.py`（模拟出题和模拟评审共用的挑厂商办法和替代记录的格式，用法写在模拟出题者和模拟评审的说明里）；`migrate_substitution_records.py`（一次性的迁移，把已经提交的模拟数据改成统一的替代记录格式，已经跑过）。
- 评委提示词核对程序 `judge_prompts.py`：`python3 -I tools/judge_prompts.py check` 从会话记录里重新取出第五阶段每次评委运行的提示词，与 `research-plan/stage5-pilot/judges/` 的存档逐字比对；`extract` 重新写出存档。

**测试**：在 `tests/`，用 Python 自带的 `unittest`，在仓库根目录运行 `python3 -I -m unittest discover -s tests -v`。每个文件管一样东西：计分程序 `test_scorer.py`（含第五阶段 8 条验收标准）、规则手册 `test_rules.py`、评委提示词 `test_judge_prompts.py`、名次页 `test_results_pages.py`、四个说明页面 `test_info_pages.py`、技术文档 `test_team_docs.py`、新手包 `test_starter_kit.py`、资料站首页 `test_site_home.py`、运行程序 `test_run_agents.py`、存档程序 `test_archive_sources.py`（只用本地测试服务器）、模型调用层 `test_models.py`、模拟出题者 `test_simulate_setter.py`、模拟评审 `test_simulate_review.py`、题库页和评审记录页 `test_simulation_pages.py`、共用的小程序 `test_common.py` 和 `test_substitutes.py`、替代记录的迁移 `test_migrate_substitution_records.py`。模型相关的测试一律用回放方式和假的命令行程序，不真的调用模型。

**给 Claude 留言**（只在本机）：`literature.local.html` 顶部有总留言框，每篇论文下也有留言区。留言存在 `comments.json`，状态分「待 Claude 处理 / Claude 已回复 · 等你确认 / 已处理」，Claude 的回复显示在留言下方，页面每 15 秒刷新。Claude 那边在会话里后台运行 `python3 -I serve.py --wait-comments`，一有待处理留言就会被叫醒去处理，处理完回复并重新等待；会话关掉后，下次对 Claude 说"看看索引里的留言"即可。删除、提交、对外发送这类难以撤销的事，Claude 会先回复"等你确认"，你在页面上点「接着说」同意后才执行。

建议阅读顺序：A → D → C → B → E，其余随意。

## A. 记忆与污染：Agent 真的在搜吗
- [LiveBrowseComp](https://arxiv.org/abs/2605.28721) — 揭示 Agent 先猜后搜；用 90 天冷门新事实出题，闭卷 0–2% · [精读分析](notes/2605.28721_LiveBrowseComp.html)
- [Search-Time Contamination](https://arxiv.org/abs/2606.05241) — 评测时搜到 benchmark 元数据或答案，三级污染，最多虚高 4%

## B. 引用伪造
- [Reference Hallucinations in DR Agents](https://arxiv.org/abs/2604.03173) — 用 Wayback 区分伪造 URL 与链接失效；伪造 3–13%，Deep Research Agent 最高

## C. 评分条目（rubric）怎么建
- [DeepResearch Bench II](https://arxiv.org/abs/2601.08536) — 132 题、9,430 条二元条目，最强模型满足不到一半（本地 PDF 为 2026-09 修订版）· [精读分析](notes/2601.08536_DeepResearch-Bench-II.html)
- [FinResearchBench II](https://arxiv.org/abs/2607.12252) — 「三 judge 一致 + 能区分系统」双重筛选；注意其效度隐患
- [DailyReport](https://arxiv.org/abs/2606.12871) — 150 道真实时效需求题，3,546 条级联条目（数据和代码未公开）· [精读分析](notes/2606.12871_DailyReport.html)
- [From Simple QA to Deep Research](https://arxiv.org/abs/2608.02163) — 从简单问答滚雪球式全自动出题；分证据和分析打分，附闭卷基线 · [精读分析](notes/2608.02163_From-Simple-QA-to-Deep-Research.html)
- [DRACO](https://arxiv.org/abs/2602.11685) — Perplexity 发布，题目来自脱敏的真实用户请求；发布方即第一名

## D. 人类专家与效度
- [DeepFact](https://arxiv.org/abs/2603.05912) — 专家一次性标注准确率仅 60.8%，「先审计后评分」4 轮后 90.9%
- [LifeSearch](https://arxiv.org/abs/2610.18092) — 最新；与人类排名 Spearman 0.89 / Kendall 0.81；judge 按人工标签选定
- [Expert Consulting Work](https://arxiv.org/abs/2605.17554) — 确定性检查 + 专家评分 + 认知陷阱；门槛指标在 70 题下无分辨力（v2 曾撤回，结论打折扣）

## E. 可复现环境
- [DR³-Eval](https://arxiv.org/abs/2604.14683) — 每题一个静态沙箱语料（支撑文档 + 干扰 + 噪声）
- [BrowseComp-Plus](https://arxiv.org/abs/2508.06600) — 约 10 万篇人工核验的固定语料，ACL 2026 · [精读分析](notes/2508.06600_BrowseComp-Plus.html)

## F. 计分规则的理论依据
- [Why Language Models Hallucinate](https://arxiv.org/abs/2509.04664) — 二元计分鼓励瞎猜；支撑「答错扣分、弃答 0 分」

## G. Deep Research 的定义与过程指标
- [LiveDRBench / Characterizing Deep Research](https://arxiv.org/abs/2508.04183) — 主张 Deep Research 的本质是搜索时的高扇出，而非长报告；ICLR 2026 · [精读分析](notes/2508.04183_LiveDRBench.html)
- [DREAM](https://arxiv.org/abs/2602.18940) — 评测框架：让评委也成为能上网的 Agent，查事实、时效与推理 · [精读分析](notes/2602.18940_DREAM.html)
- [MiroEval](https://arxiv.org/abs/2603.28407) — 同时评报告、事实、过程；逐题数据可复算，"自家第一"站不住 · [精读分析](notes/2603.28407_MiroEval.html)

## H. 其他 benchmark（未看摘要）
- [IDRBench（交互能力）](https://arxiv.org/abs/2601.06676) — 测 Agent 中途反问用户能否让报告更贴合意图，及其代价 · [精读分析](notes/2601.06676_IDRBench.html)
- [DR-Arena](https://arxiv.org/abs/2601.10504) — 考官现场出题并追问的两两擂台；对局记录公开，可复算 · [精读分析](notes/2601.10504_DR-Arena.html)
- [MMDeepResearch-Bench](https://arxiv.org/abs/2601.12346) — 看图写带引用报告；但不看图也能考高分，数字多处对不上 · [精读分析](notes/2601.12346_MMDeepResearch-Bench.html)
- [DeepResearch-9K](https://arxiv.org/abs/2603.01152) — 用 LLM 改写老多跳题批量造训练数据；附完整轨迹，可作反面教材 · [精读分析](notes/2603.01152_DeepResearch-9K.html)

## I. 综述
- [Autonomous Research Agents: the Verification Gap](https://arxiv.org/abs/2608.05179) — 以"可核验性"为主线的 AI 科学家综述，附审稿清单与验证阶梯 · [精读分析](notes/2608.05179_Survey-Verification-Gap.html)
- [Rubric-Guided RL Survey](https://arxiv.org/abs/2608.27505)
