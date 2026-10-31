# 报告E

从公开评测和用户口碑来看，目前没有一个“绝对第一”的 Deep Research，但趋势比较清晰：

- 英文技术与综合研究：ChatGPT 的 Deep Research 综合实力最强，尤其在技术/严肃研究场景里整体评价略高于 Perplexity、Gemini 等竞品。clickittech+1
- 面向“搜索+资料综述”：Perplexity 的 Deep Research 在检索范围、引用透明度和报告结构化上非常突出，是最强的 AI 搜索型 Deep Research 之一。enago+2
- 中文与本土内容：Kimi 的「深度研究」+ DeepSeek R1 的推理组合，在处理中文长文档、本土网站和复杂数据分析任务上，目前整体体验优于大部分国内模型。lib.szu+2

------

## 主流 Deep Research 能力对比

| 产品                     | 整体定位               | Deep Research 主要优势                                       | 明显短板 / 争议                                              | 更推荐给谁                                                   |
| ------------------------ | ---------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| ChatGPT Deep Research    | 通用强推理 + 深研代理  | 第三方测评认为 ChatGPT 的 Deep Research 是目前最好的深度研究产品之一，在技术研究上比 Grok、Perplexity、Gemini 表现更好。[[creatoreconomy](https://creatoreconomy.so/p/an-opinionated-guide-on-which-ai-model-2025)] 深度研究版本在可靠性上被评为“显著比 Perplexity 更可靠”，适合严肃技术场景。[[clickittech](https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/)] | 深度研究配额有限（Plus 用户每月约 10 次，免费用户约 2 次），大规模重度使用的门槛较高。[[clickittech](https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/)] | 英文为主、需要严肃技术/学术分析，希望尽量减少幻觉风险的个人和团队。clickittech+1 |
| Perplexity Deep Research | AI 搜索 + 多轮调研代理 | 官方数据称 Deep Research 会执行数十次搜索、阅读上百个来源，并自动生成结构化研究报告；在 Humanity’s Last Exam 上达到 21.1% 准确率，超过 Gemini Thinking、o3-mini、o1、DeepSeek-R1 等模型。[[perplexity](https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research)] 在 SimpleQA factuality 基准上达到 93.9%，并对每条结论给出清晰引用，被多方视为“研究与事实核查”的首选工具之一。enago+2 | 第三方评测指出 Deep Research 虽然快，但仍存在一定幻觉，深度有时不如 OpenAI Deep Research；PCMag 也认为其 Deep Research 工具尚不如 ChatGPT 作为“通用深度聊天/研究助手”那样全面。clickittech+1 | 需要大量查找最新网页、论文、新闻，并很在意「有引用可点回去看原文」的用户，尤其是英语信息密集场景。enago+2 |
| Kimi 深度研究            | 中文长文本 + 本土网站  | 行业评测指出，Kimi k1.5 在长文本处理任务中，相比短文本更出色，既能保证提取准确，又能给出更全面的数据维度；在特征分类与多维度关联挖掘任务中表现最佳。[[lib.szu.edu](https://www.lib.szu.edu.cn/sites/szulib/files/2025-03/清华大学第四弹：DeepSeek+DeepResearch：让科研像聊天一样简单-.pdf)] 另一篇技术解读也强调 Kimi 的「深度研究功能」已经可以高质量搜索、研究并通过精美前端页面展示结果。[[m.zhiding](https://m.zhiding.cn/article/3169361.htm)] | 推理链条和数学严谨性整体弱于最新一代 OpenAI / DeepSeek R1，在纯推理解题和高难数学方面仍有差距。cnblogs+1 | 以中文长材料（报告、政策、财报、论文）为主，希望自动帮你“读完+归纳+结构化”的用户，尤其是国内内容场景。lib.szu+1 |
| DeepSeek R1 + 工具链     | 深度推理 + 数据分析    | 多份技术与媒体评测指出，DeepSeek R1 在内容总结、文字生成时会主动补充数据和案例来佐证观点，使文章“更落地”，在多款国产模型横评中整体表现超出豆包、Kimi 等主流模型。cnblogs+1 清华等机构的对比实验认为，R1 在数据分析任务上与 OpenAI o3-mini 相当且领先其他模型，分析逻辑更清晰严谨，适合做异常检测、数据相关性挖掘等深度分析场景。[[lib.szu.edu](https://www.lib.szu.edu.cn/sites/szulib/files/2025-03/清华大学第四弹：DeepSeek+DeepResearch：让科研像聊天一样简单-.pdf)] | 对极长文本任务容易超出上下文限制；早期版本联网搜索和多语种输出上存在不稳定问题，需要结合其他工具或代理封装来获得更完整的“深度研究”体验。cnblogs+1 | 需要复杂推理、数学/代码/量化分析，并且以中文技术圈为主的用户；适合与 Kimi 或定制 Agent 结合做“R1 负责算 & 想，外层负责搜 & 展示”。cnblogs+2 |
| Claude（含 Projects 等） | 长文写作 + 安全性      | 多方评价中，Claude 在长篇写作、合约/报告撰写、代码审阅等方面表现突出，适合作为“安全、稳重”的写作和企业助手。[[laksn](https://www.laksn.com/top-generative-ai-models-comparison-chatgpt-deepseek-claude-and-more)] 在部分机构的对比中，Claude 3.5 sonnet 在表格结构化输出、格式工整度上表现优于 o3 和部分国产模型。[[lib.szu.edu](https://www.lib.szu.edu.cn/sites/szulib/files/2025-03/清华大学第四弹：DeepSeek+DeepResearch：让科研像聊天一样简单-.pdf)] | 至少在 2025 年中期的测试中，Claude 3.5 sonnet 尚不支持直接在模型内部进行联网网页查询，需要通过外部工具集成，天然弱于 Perplexity/ChatGPT 这种一体化 Deep Research 体验。lib.szu+1 | 强调合规、安全和长文可读性，主要做英文报告、法规梳理、内部备忘录的团队，而不是以“全自动网页调研代理”为第一诉求的用户。lib.szu+1 |
| Gemini (Thinking / 2.x)  | 多模态 + Google 生态   | Gemini 在文字、图片、音频和视频上的多模态能力较强，并且深度集成 Gmail、Docs、Drive 等 Google 产品，适合办公自动化场景。sgu+1一些基准显示，Gemini Thinking 在复杂多步问题上仍有提升空间，其准确度在高度专业科学领域略低于顶级竞品。enago+1 | Deep Research 能力更多依赖 Google 搜索 + 文档生态的组合，而不是像 Perplexity/ChatGPT 那样提供高度专门化的“深度调研模式”，在纯“长篇综述+引用管理”上口碑略逊。enago+2 | 深度绑定 Google 生态、需要把邮件/文档/网盘一起串联分析的用户，而不是追求最强「独立 Deep Research 代理」的研究者。sgu+1 |

------

## 英文场景：ChatGPT vs Perplexity 哪个更强？

从多篇 2025–2026 年的评测来看，ChatGPT 的 Deep Research 在“严肃技术/学术研究”场景里普遍被认为略胜一筹，尤其是在推理严谨性和整体可靠性上更受信任。 有文章直接评价“Deep Research 是 ChatGPT 目前最好的产品”，在对比 Grok、Perplexity、Gemini 等同类功能时，ChatGPT Deep Research 的总结质量和问题分解能力被认为更好。creatoreconomy+1

另一方面，Perplexity 的 Deep Research 更像“超级版学术/情报搜索引擎”：它会自动执行大量搜索、阅读上百个来源，然后生成结构化报告，在 Humanity’s Last Exam 和 SimpleQA 等基准上都给出了非常亮眼的准确率成绩，同时保持在几分钟内完成任务。 多个独立评测认为，如果你的核心诉求是“查最新资料 + 快速看清文献和网页的版图 + 一键带引用”，Perplexity 的体验非常强；但在需要特别严肃、不容出错的技术论证时，OpenAI 的 Deep Research 目前被普遍视为更可靠。perplexity+4

------

## 中文场景：Kimi 和 DeepSeek 的优势边界

针对中文长文档、本土网站（政策、报告、新闻、公众号等）的“深度研究”，Kimi 的深度研究功能目前是产品化程度最高的一批：评测显示 Kimi k1.5 在长文本任务里不但提取准确，而且维度更全面，生成的结构化表格和多维分类非常适合直接拿去做分析。 同时，国内媒体也多次指出 Kimi 在总结年度趋势、消费洞察等面向中文内容的场景中，表现明显好于多数同类模型。36kr+2

DeepSeek R1 的优势更偏向“推理和分析深度”：清华等机构的对比实验显示，R1 在数据分析、异常检测、特征–指标关联挖掘等任务上，分析逻辑比其他模型更清晰严谨，整体与 OpenAI o3-mini 处于同一档位，明显领先包括 Kimi 在内的多数模型。 媒体横评也发现，在内容总结类任务中，R1 会主动引入数据和产品案例来支撑结论，使得文章更有“证据感”，综合表现超越 Kimi 等主流国产大模型。lib.szu+1

一个值得注意的趋势是：部分研究机构和实践者已经开始推荐 “DeepSeek R1 + Kimi 深度研究” 的组合使用——R1 负责深度分析和异常检测，Kimi 负责长文本整理和多维度挖掘，从而在中文场景下取得比单一模型更好的效果。[[lib.szu.edu](https://www.lib.szu.edu.cn/sites/szulib/files/2025-03/清华大学第四弹：DeepSeek+DeepResearch：让科研像聊天一样简单-.pdf)]

------

## Claude 和 Gemini：更像“写作/办公助手”，而不是纯 Deep Research 王

Claude 在多个独立对比中被认为是“长文写作和安全合规”上的标杆：它擅长合约、政策、技术文档的撰写与重写，输出风格稳妥、有条理，非常适合作为企业写作助手。 另外有实验表明，在结构化表格输出和排版整洁度上，Claude 3.5 sonnet 的表现优于一些竞品，包括 OpenAI o3-mini 和部分国产模型。laksn+1

但从“Deep Research”这一垂直能力看，至少在 2025 年的对比报告里，Claude 3.5 sonnet 本身并不直接支持像 Perplexity/ChatGPT 那样的内置联网搜索，需要额外接工具，这意味着其深度研究体验更依赖开发者集成，而非开箱即用。laksn+1

Gemini 则在多模态和 Google 生态集成方面有明显优势，例如与 Gmail、Docs、Drive 的联动，以及对图像/视频的理解和生成能力，被认为更适合办公自动化与创意场景。 但在“纯文本深度研究 + 引用管理”这条赛道上，主流测评大多把“研究首选”位置留给了 Perplexity 和 ChatGPT，而非 Gemini。sgu+3

------

## 结合使用场景给一点实用建议

如果你主要做的是英文技术、学术或严肃商业研究，而且可以接受订阅费用，可以优先把 ChatGPT Deep Research 作为主力，配合 Perplexity 做“广度搜索 + 引用补充”。clickittech+2

如果你更多是做市场竞品、行业趋势、政策解读一类的调研，尤其需要大量网页和报告、一键拉出引用，那么 Perplexity Deep Research 会给你最省时间的“搜索+综述”体验，再用自己常用的大模型（不论是 ChatGPT、Claude 还是 DeepSeek）去润色或做进一步推理即可。pcmag+3

如果你的工作以中文为主，经常需要读本土长文档、政府和行业报告，我会建议：

- 先用 Kimi 深度研究做“搜+读+整理”，拿到结构化的要点和表格。zhiding+1
- 再把关键问题丢给 DeepSeek R1 或 OpenAI 的高级模型，做更深的推导、计算和方案评估，这样既兼顾中文资料覆盖，又能获得一线水平的推理能力。cnblogs+2

如果你愿意，我可以按你自己的典型使用场景（比如：投研、产品调研、技术选型、学术写作等）帮你定制一套 “哪类问题找哪家 Deep Research / 组合哪几个服务” 的更细分策略。