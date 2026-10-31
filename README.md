# Deep Research Benchmark 文献（2025-08 ～ 2026-10）

2026-10-28 下载，共 23 篇，均为 arXiv 最新版本。文件名格式：`首发年月_arXiv编号_简称.pdf`。
阅读状态和笔记在 [index.html](index.html) 里管理（运行 `python3 serve.py` 后打开 http://localhost:8766/）。
「为什么读」依据 arXiv 摘要页；中文摘要在 index.html 里，每篇可展开。
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

[比赛规则手册](notes/rules.html)：源文件是 `research-plan/rules.md`，由 `render_plan.py` 生成网页；内容取自 2026 年 10 月 30 日在线文档的第 17 次修订，此后以本地版为准。深度研究赛项的出题、冻结与申报、运行、交付、评审、名次、申诉和违规处理。标有〔默认〕的条款待主办方确认。它和出题手册第 2 版一起，回应了三个问题：开发者能否按题目改提示词、提问者和用途是否符合真实场景、深度地图的质量怎样保证。

[对照巡天网站结构](research-plan/site-mapping.md)：把现有资料和程序按巡天黑客松网站（create.gosim.org/survey26）的公开页面、参赛者页面、后台与程序逐项对照，列出已有、部分、缺和待办。

[本地资料站](site/index.html)：把研究、规则、出题手册、文献和领域外资料收在一页，可筛选，双击即可打开。首屏是用 Archify 画的[评测基准架构图](site/diagrams/architecture-dr-benchmark/benchmark-architecture-explained.html)，点任一环节会显示它是什么、做什么用。图的源文件是同一目录的 `candidate.json`，节点说明在 `node-notes.json`；改说明后运行 `build_explained.py` 生成讲解版，原图 `benchmark-architecture.html` 保持 Archify 生成的原样。[一道题走完全程](site/walkthrough.html)：以淡水湖这道题为例走完十一站，五份报告是虚构的示意，分数按真实规则算出，可用 `site/walkthrough_example.py` 复算。页面按 landing-page-design 技能的规则制作，大纲和与规则不一致之处见 `site/landing-plan.md`。

**给 Claude 留言**：索引页顶部有总留言框，每篇论文下也有留言区。留言存在 `comments.json`（不进 index.html），状态分「待 Claude 处理 / Claude 已回复 · 等你确认 / 已处理」，Claude 的回复显示在留言下方，页面每 15 秒刷新。Claude 那边在会话里后台运行 `python3 -I serve.py --wait-comments`，一有待处理留言就会被叫醒去处理，处理完回复并重新等待；会话关掉后，下次对 Claude 说"看看索引里的留言"即可。删除、提交、对外发送这类难以撤销的事，Claude 会先回复"等你确认"，你在页面上点「接着说」同意后才执行。

建议阅读顺序：A → D → C → B → E，其余随意。

## A. 记忆与污染：Agent 真的在搜吗
- [LiveBrowseComp](2026-05_2605.28721_LiveBrowseComp.pdf) · [arXiv](https://arxiv.org/abs/2605.28721) — 揭示 Agent 先猜后搜；用 90 天冷门新事实出题，闭卷 0–2% · [精读分析](notes/2605.28721_LiveBrowseComp.html)
- [Search-Time Contamination](2026-06_2606.05241_Search-Time-Contamination.pdf) · [arXiv](https://arxiv.org/abs/2606.05241) — 评测时搜到 benchmark 元数据或答案，三级污染，最多虚高 4%

## B. 引用伪造
- [Reference Hallucinations in DR Agents](2026-04_2604.03173_Reference-Hallucinations-in-DR-Agents.pdf) · [arXiv](https://arxiv.org/abs/2604.03173) — 用 Wayback 区分伪造 URL 与链接失效；伪造 3–13%，Deep Research Agent 最高

## C. 评分条目（rubric）怎么建
- [DeepResearch Bench II](2026-01_2601.08536_DeepResearch-Bench-II.pdf) · [arXiv](https://arxiv.org/abs/2601.08536) — 132 题、9,430 条二元条目，最强模型满足不到一半（本地 PDF 为 2026-09 修订版）· [精读分析](notes/2601.08536_DeepResearch-Bench-II.html)
- [FinResearchBench II](2026-07_2607.12252_FinResearchBench-II.pdf) · [arXiv](https://arxiv.org/abs/2607.12252) — 「三 judge 一致 + 能区分系统」双重筛选；注意其效度隐患
- [DailyReport](2026-06_2606.12871_DailyReport.pdf) · [arXiv](https://arxiv.org/abs/2606.12871) — 150 道真实时效需求题，3,546 条级联条目（数据和代码未公开）· [精读分析](notes/2606.12871_DailyReport.html)
- [From Simple QA to Deep Research](2026-08_2608.02163_From-Simple-QA-to-Deep-Research.pdf) · [arXiv](https://arxiv.org/abs/2608.02163) — 从简单问答滚雪球式全自动出题；分证据和分析打分，附闭卷基线 · [精读分析](notes/2608.02163_From-Simple-QA-to-Deep-Research.html)
- [DRACO](2026-02_2602.11685_DRACO.pdf) · [arXiv](https://arxiv.org/abs/2602.11685) — Perplexity 发布，题目来自脱敏的真实用户请求；发布方即第一名

## D. 人类专家与效度
- [DeepFact](2026-03_2603.05912_DeepFact.pdf) · [arXiv](https://arxiv.org/abs/2603.05912) — 专家一次性标注准确率仅 60.8%，「先审计后评分」4 轮后 90.9%
- [LifeSearch](2026-10_2610.18092_LifeSearch.pdf) · [arXiv](https://arxiv.org/abs/2610.18092) — 最新；与人类排名 Spearman 0.89 / Kendall 0.81；judge 按人工标签选定
- [Expert Consulting Work](2026-05_2605.17554_Expert-Consulting-Work-Benchmark.pdf) · [arXiv](https://arxiv.org/abs/2605.17554) — 确定性检查 + 专家评分 + 认知陷阱；门槛指标在 70 题下无分辨力（v2 曾撤回，结论打折扣）

## E. 可复现环境
- [DR³-Eval](2026-04_2604.14683_DR3-Eval.pdf) · [arXiv](https://arxiv.org/abs/2604.14683) — 每题一个静态沙箱语料（支撑文档 + 干扰 + 噪声）
- [BrowseComp-Plus](2025-08_2508.06600_BrowseComp-Plus.pdf) · [arXiv](https://arxiv.org/abs/2508.06600) — 约 10 万篇人工核验的固定语料，ACL 2026 · [精读分析](notes/2508.06600_BrowseComp-Plus.html)

## F. 计分规则的理论依据
- [Why Language Models Hallucinate](2025-09_2509.04664_Why-Language-Models-Hallucinate.pdf) · [arXiv](https://arxiv.org/abs/2509.04664) — 二元计分鼓励瞎猜；支撑「答错扣分、弃答 0 分」

## G. Deep Research 的定义与过程指标
- [LiveDRBench / Characterizing Deep Research](2025-08_2508.04183_LiveDRBench-Characterizing-Deep-Research.pdf) · [arXiv](https://arxiv.org/abs/2508.04183) — 主张 Deep Research 的本质是搜索时的高扇出，而非长报告；ICLR 2026 · [精读分析](notes/2508.04183_LiveDRBench.html)
- [DREAM](2026-02_2602.18940_DREAM.pdf) · [arXiv](https://arxiv.org/abs/2602.18940) — 评测框架：让评委也成为能上网的 Agent，查事实、时效与推理 · [精读分析](notes/2602.18940_DREAM.html)
- [MiroEval](2026-03_2603.28407_MiroEval.pdf) · [arXiv](https://arxiv.org/abs/2603.28407) — 同时评报告、事实、过程；逐题数据可复算，"自家第一"站不住 · [精读分析](notes/2603.28407_MiroEval.html)

## H. 其他 benchmark（未看摘要）
- [IDRBench（交互能力）](2026-01_2601.06676_Interactive-Capabilities-of-DR-Agents.pdf) · [arXiv](https://arxiv.org/abs/2601.06676) — 测 Agent 中途反问用户能否让报告更贴合意图，及其代价 · [精读分析](notes/2601.06676_IDRBench.html)
- [DR-Arena](2026-01_2601.10504_DR-Arena.pdf) · [arXiv](https://arxiv.org/abs/2601.10504) — 考官现场出题并追问的两两擂台；对局记录公开，可复算 · [精读分析](notes/2601.10504_DR-Arena.html)
- [MMDeepResearch-Bench](2026-01_2601.12346_MMDeepResearch-Bench.pdf) · [arXiv](https://arxiv.org/abs/2601.12346) — 看图写带引用报告；但不看图也能考高分，数字多处对不上 · [精读分析](notes/2601.12346_MMDeepResearch-Bench.html)
- [DeepResearch-9K](2026-03_2603.01152_DeepResearch-9K.pdf) · [arXiv](https://arxiv.org/abs/2603.01152) — 用 LLM 改写老多跳题批量造训练数据；附完整轨迹，可作反面教材 · [精读分析](notes/2603.01152_DeepResearch-9K.html)

## I. 综述
- [Autonomous Research Agents: the Verification Gap](2026-08_2608.05179_Survey-Verification-Gap.pdf) · [arXiv](https://arxiv.org/abs/2608.05179) — 以"可核验性"为主线的 AI 科学家综述，附审稿清单与验证阶梯 · [精读分析](notes/2608.05179_Survey-Verification-Gap.html)
- [Rubric-Guided RL Survey](2026-08_2608.27505_Survey-Rubric-Guided-RL.pdf) · [arXiv](https://arxiv.org/abs/2608.27505)
