import json, sys, os

BASE = "/Users/zonghuanwu/github/mofa-research/docs/deep-research-benchmarks-2026/research-plan/stage5-pilot"
OUT = os.path.join(BASE, "out", "rating-opus-1.json")
SEP = " …… "

texts = {k: open(os.path.join(BASE, "reports", k + ".md"), encoding="utf-8").read() for k in "ABCDEF"}


def R(score, evidence, reason):
    return {"score": score, "evidence": evidence, "reason": reason}


def P(content, level, quote):
    return {"content": content, "level": level, "quote": quote}


data = {}

# ---------------- A ----------------
data["A"] = {
    "ratings": {
        "①": R(0,
              "We compare the advanced **Deep Research** capabilities of major AI platforms – Google Gemini, OpenAI ChatGPT, Anthropic Claude, Perplexity AI, Moonshot AI’s Kimi, and China’s DeepSeek – along multiple dimensions." + SEP +
              "ChatGPT has introduced an integrated **Search** mode (GPT-4o) that fetches up-to-date web answers with live source links【25†L51-L59】.",
              "只按字面铺开多维度比较，没有交代怎样理解“哪家最好”和提问者的需要，ChatGPT 一项还拿 Search 模式顶替了它的 Deep Research 功能。"),
        "③": R(1,
              "All information is drawn from official docs, technical blogs, and reputable sources (citations in brackets).",
              "交代了来源类型（官方文档、技术博客），个别处提到资料未公开，但没有交代查找方法、范围和局限。"),
        "④": R(1,
              "Chinese news reports also claim they have “basically eliminated” hallucination【16†L247-L254】 (though that’s unverified PR).",
              "个别处区分了厂商宣传与可核实信息，但整体未说明来源可靠程度，也没有发现或处理相互矛盾的信息。"),
        "⑤": R(1,
              "It likely uses Bing-like search or an internal crawler but the details are proprietary.",
              "常用 likely、presumably 标出推测，大体分开了文档事实和自己的推断，但没有考虑其他解释，且有自相矛盾之处（把 DeepSeek 写成 Moonshot 的模型）。"),
        "⑦": R(1,
              "Our final comparison table highlights each vendor’s strengths, weaknesses, and ideal use-cases." + SEP +
              "Unspecified details (e.g. exact pricing tiers for some services) are noted as assumptions.",
              "给出了各家优劣和适用场景，可据以选择，但没有回答哪家最好；把握说明只有文末一句笼统的“未说明细节视为假设”，流于形式。"),
        "写作": R(1,
                "**Mermaid Diagrams:** (Omitted – see referenced architecture descriptions above for how each system is structured.)",
                "按维度分节、摘要在前，能读懂，但摘要没有给出可用的总判断，文中残留图片标记和“已省略”的占位内容。"),
    },
    "points": [
        P("所有产品回答中的“新鲜度”来自实时检索，而非底层模型的预训练语料。", "内部联系",
          "All base models are pre-trained on large text corpora (Common Crawl, etc.), but the freshness in answers comes from live search."),
        P("带检索的回答，其事实准确性取决于所检索来源的质量。", "内部联系",
          "With its Search mode, factuality is tied to source quality."),
        P("DeepSeek 不是开箱即用的研究助手产品，而是供开发者搭建研究助手的模型工具包。", "本质",
          "Not a turn-key “research assistant” product, but a toolkit for building one."),
        P("Kimi Explore 每次查询读约 500 页，可减少遗漏，但仍可能归纳错误。", "内部联系",
          "Kimi’s Explore, by scanning 500 pages per query, may reduce omission errors but could still summarize incorrectly."),
        P("Gemini Deep Research 是耗时数分钟的异步任务，不适合即时查询。", "内部联系",
          "Async workflow (minutes-long tasks)【12†L849-L857】 not suited to instant queries"),
        P("Gemini Deep Research 仍在预览，Google 提醒用户核对引用，且没有公开的准确率指标。", "全体",
          "Early reports suggest Gemini Deep Research produces high-quality comparative analysis (a new category of output), but concrete metrics are not public."),
        P("Kimi “基本消除幻觉”的说法属未经核实的宣传，也没有关于 Kimi 英文事实性的独立研究。", "全体",
          "There’s no independent study of Kimi’s factuality in English."),
        P("Perplexity 的网页抓取做法受到法律审查。", "全体",
          "(Note: Perplexity’s scraping practices have drawn legal scrutiny【34†L213-L220】.)"),
        P("Gemini Deep Research 能自主规划多步搜索，覆盖网页和用户的 Gmail、Drive、Chat 数据，输出多页带引用的报告。", "现象",
          "For example, Google’s Gemini Deep Research agent autonomously plans and executes multi-step searches over the web and private data (Gmail, Drive, Chat), producing multi-page, cited reports【8†L183-L189】【14†L49-L57】."),
        P("ChatGPT Search 借助第三方搜索服务商和合作媒体内容提供带来源链接的实时回答。", "现象",
          "The ChatGPT Search model (GPT‑4o) was “post-trained using … synthetic data” and explicitly “leverages third-party search providers, as well as content provided directly by our partners, to provide the information users are looking for”【25†L139-L144】."),
        P("Claude 的 Research 模式在内部数据（Gmail、Calendar、Docs）和网页上迭代搜索，并给出便于核对的引用。", "现象",
          "With Research on, “Claude will kick off the research process across your internal context (Gmail, Calendar, Docs) and the web,” conducting iterative searches【27†L59-L64】."),
        P("Perplexity 维护自己的实时网页索引，回答附脚注来源，并可通过连接器检索用户的 Google Drive 文件。", "现象",
          "**Perplexity AI** maintains its own continuously-refreshed web index and crawlers."),
        P("Kimi 自 2024 年 10 月起提供 Explore 模式，让 AI 自主搜索、每次读数百页。", "现象",
          "Kimi Explore “adopted a different approach: letting the AI search autonomously … reading through hundreds of pages”【19†L104-L112】."),
        P("Kimi-Researcher（2025 年中）是自主智能体模型，每个任务约 23 步、200 多个网址。", "现象",
          "Kimi also now has **Kimi-Researcher** (mid-2025), an autonomous agentic model that performs multi-turn search (around 23 steps, 200+ URLs) via an internal parallel search tool【22†L10-L18】【22†L45-L53】."),
        P("DeepSeek 没有公开的多轮搜索智能体界面，检索集成主要靠开发者自己做。", "现象",
          "**DeepSeek (China)** provides powerful LLMs but no public information suggests a dedicated multi-search agent UI."),
        P("Kimi 的回答通常不附正式来源链接，偏重完整而非可追溯。", "现象",
          "The focus is on completeness and multi-page output rather than traceability."),
        P("上下文窗口：Gemini 3.1 Pro 与 Claude Opus 4.6 达 100 万 token，Kimi 256K，ChatGPT 与 DeepSeek 约 128K。", "现象",
          "Claude Opus 4.6 (Feb 2026) supports up to **1M tokens** (beta)【31†L22-L26】, with 200K normally."),
        P("Gemini Deep Research 智能体通过 Interactions API 调用，一次典型任务花费几美元。", "现象",
          "Example estimates: a typical Deep Research task (multiple searches and ~60K output tokens) costs a few dollars【12†L874-L881】."),
        P("Perplexity 于 2026 年 2 月推出 Computer，用 19 个模型协同的多智能体研究助手，面向 Max 订阅用户。", "现象",
          "*Feb 2026:* Launched **Perplexity Computer** (multi-agent research assistant using 19 models)【37†L109-L118】【37†L151-L160】, available to Max subscribers."),
        P("按用途选择：Gemini 适合依托 Workspace 的企业研究，ChatGPT 适合通用问答，Claude 适合复杂的企业研究，Perplexity 适合快速带来源的回答，Kimi 适合中文长上下文，DeepSeek 适合开发者自建管道。", "现象",
          "In short, **Gemini** shines in enterprise/Workspace-integrated research with Google search and user data (long context, multimodal, chain-of-thought via a “thinking” panel)【14†L69-L76】【8†L183-L189】."),
    ],
    "off_topic": {"value": False,
                  "reason": "报告比较的就是各家深度研究与检索能力，属于所问的问题；虽然没有给出“哪家最好”的判断，ChatGPT 部分也偏到了 Search 模式，但没有改答另一个问题。"},
}

# ---------------- B ----------------
data["B"] = {
    "ratings": {
        "①": R(1,
              "根据多方评测和用户反馈，各家 Deep Research 功能各有所长，没有一个绝对的\"最好\"，但可以按不同维度来梳理：",
              "写明了“没有绝对最好、按维度梳理”的理解并据此回答，但没有审视“最好”该按什么标准、为什么。"),
        "③": R(1,
              "这是一个很好的问题，让我搜索一下最新的评测和比较信息。",
              "只说明了来源类型（评测和用户反馈），没有交代查了哪些、怎么查、缺什么。"),
        "④": R(0,
              "Perplexity 的 Deep Research 在行业基准上得分很高，且多数研究任务能在 3 分钟内完成。",
              "“行业基准”“一位测评者”等来源不加区分，也不说明可靠程度，没有发现或处理任何矛盾信息。"),
        "⑤": R(0,
              "ChatGPT Deep Research 在深度和推理方面走在前列。" + SEP +
              "但在\"Deep Research\"这个独立产品功能上，相比上述几家的成熟度和完善程度还有差距。",
              "判断以事实口吻写出，部分判断没有任何依据，也没有考虑其他解释。"),
        "⑦": R(0,
              "目前最务实的做法可能是根据具体任务在不同平台之间灵活切换。",
              "给出了按需求对号入座的建议，但完全没有说明各判断有多大把握、依据是什么。"),
        "写作": R(2,
                "根据多方评测和用户反馈，各家 Deep Research 功能各有所长，没有一个绝对的\"最好\"，但可以按不同维度来梳理：",
                "简短清楚，总判断在开头，分家叙述后给出总结建议。"),
    },
    "points": [
        P("ChatGPT Deep Research 可自主浏览分析长达半小时，善于发现关联、推断和识别跨来源的不一致。", "现象",
          "它的自主浏览和分析周期可以运行长达半小时，不仅善于收集事实，还擅长发现关联、推断和识别跨来源的不一致之处。"),
        P("一次测评中 ChatGPT 生成 36 页、25 个来源的报告，建议具体可操作。", "现象",
          "一位测评者发现，ChatGPT 生成了长达 36 页、包含 25 个来源的报告，其中包含具体可操作的建议，与实际商业策略高度吻合。"),
        P("Gemini Deep Research 依托 Google 搜索，多步规划、反复搜索，因而覆盖面广，能挖到不常见的信息源。", "内部联系",
          "Google Gemini Deep Research 则充分利用了 Google 搜索的优势，会制定多步骤研究计划，反复搜索并逐步细化，覆盖面非常广，还能挖掘到不常见的网站和信息源。"),
        P("一次测试中 Gemini 生成 48 页、100 个来源的报告，内容全面但结论冗长。", "现象",
          "Gemini 在一次测试中生成了 48 页、100 个来源的报告，内容全面但结论偏冗长。"),
        P("Perplexity Deep Research 在行业基准上得分高，多数任务 3 分钟内完成。", "现象",
          "Perplexity 的 Deep Research 在行业基准上得分很高，且多数研究任务能在 3 分钟内完成。"),
        P("看重引用和事实报告、需要快速获得有来源支撑的概览时，Perplexity 是最佳选择。", "现象",
          "如果你看重引用和事实报告，Perplexity 是最佳选择。"),
        P("Claude Deep Research 生成 7 页、427 个来源的报告，长于综合而非堆砌信息。", "现象",
          "Claude 的 Deep Research 生成了 7 页、427 个来源的报告，在信息综合方面做得非常出色，而不是简单堆砌信息。"),
        P("评测者认为 Claude 的输出可读性和结构感最好，但具体建议有时偏通用。", "现象",
          "多位评测者认为 Claude 的输出最具\"可读性\"和结构感，但具体建议有时偏通用。"),
        P("DeepSeek 和 Kimi 以底层模型能力著称，但作为独立的 Deep Research 产品功能，成熟度落后于前几家。", "全体",
          "但在\"Deep Research\"这个独立产品功能上，相比上述几家的成熟度和完善程度还有差距。"),
        P("按需求选择：深度推理选 ChatGPT，广覆盖与 Google 生态选 Gemini，速度与引用选 Perplexity，可读性选 Claude，低成本选 DeepSeek/Kimi 作补充。", "现象",
          "选择取决于你的具体需求："),
        P("已因其他功能为某平台付费的用户，直接用该平台自带的 Deep Research 即可。", "内部联系",
          "如果你已经因为其他功能（比如 Claude Code 或 OpenAI Codex）而付费使用某个平台，那直接用它自带的 Deep Research 就很好。"),
        P("最务实的做法是按任务在不同平台之间切换。", "现象",
          "目前最务实的做法可能是根据具体任务在不同平台之间灵活切换。"),
    ],
    "off_topic": {"value": False, "reason": "直接回答各家 Deep Research 哪家好，并按需求给出选择建议。"},
}

# ---------------- C ----------------
data["C"] = {
    "ratings": {
        "①": R(1,
              "与传统单次推理模式不同，Deep Research通过模拟人类专家的认知 workflow，实现复杂问题的系统性探究：自主分解研究目标、动态调整检索策略、交叉验证多源信息、最终生成结构化专业报告。",
              "先界定了 Deep Research 的含义，再按技术路径和场景组织回答；但没有审视“最好”按什么标准，又把自己说明没有原生检索的 DeepSeek-R1 照常当作同类产品排名。"),
        "③": R(1,
              "基于前述分析和多源评测，以下从十个维度进行量化评分：",
              "只笼统提到“多源评测”“实测”“用户反馈”等来源类型，全文没有来源清单，也没有交代查找范围、方法和局限。"),
        "④": R(1,
              "需要强调的是，**幻觉率测量方法存在显著差异**，不同评测的定义、测试集、评估标准可能不同，直接比较需谨慎。",
              "提示了不同评测口径不可直接比较，并标出“内部评估”“用户反馈”等来源性质；但没有说明来源可靠程度，对 Kimi 正反评价的取舍也没有给出理由。"),
        "⑤": R(0,
              "| **总分（满分50）** | **39**  | **41** |   **36**   |  **36**  | **42** | **39** |" + SEP +
              "Claude以微弱优势领先，源于其在分析深度和创新性维度的满分表现。",
              "评分表的总分与各项分数相加不符（如 ChatGPT 十项合计 45 而非 39），排名结论建立在算错的总分上；很多判断以事实口吻陈述，也没有考虑其他解释。"),
        "⑦": R(1,
              "Claude以微弱优势领先，源于其在分析深度和创新性维度的满分表现。",
              "给出了明确的梯队排序和分场景选型，但 1 到 5 分的评分没有说明依据和把握，只在幻觉率一处提示“直接比较需谨慎”。"),
        "写作": R(1,
                "当前Deep Research功能的技术架构可归纳为三种主流路径，分别对应不同的设计哲学和适用场景。",
                "结构完整、能读懂，但开篇是概念和架构，综合排序到第三节才出现，主要结论不在前，表格和内容多有重复。"),
    },
    "points": [
        P("Deep Research 的实质是从被动应答转为自主研究：分解目标、动态调整检索、交叉验证、生成结构化报告。", "本质",
          "与传统单次推理模式不同，Deep Research通过模拟人类专家的认知 workflow，实现复杂问题的系统性探究：自主分解研究目标、动态调整检索策略、交叉验证多源信息、最终生成结构化专业报告。"),
        P("各家技术架构可归为三条路径：端到端训练（ChatGPT、Gemini）、多智能体协作（Claude）、开源推理引擎加外部检索（DeepSeek），分别对应不同的设计取向和适用场景。", "本质",
          "当前Deep Research功能的技术架构可归纳为三种主流路径，分别对应不同的设计哲学和适用场景。"),
        P("Perplexity 的定位是快速的信息综合工具，而不是深度原创研究平台。", "本质",
          "Perplexity的自我定位清晰：**\"信息综合工具\"而非\"深度原创研究平台\"**。"),
        P("Gemini 速度快，来自 Google 检索基础设施、模型优化和相对简化的迭代深度，代价是准确性波动和分析深度不足。", "内部联系",
          "这种速度源于Google基础设施的高效检索、模型架构的优化，以及相对简化的迭代深度。"),
        P("Claude 的多智能体架构在复杂查询上比单智能体高出 90.2%，但 token 消耗约为普通聊天的 15 倍，因此只适合高价值任务。", "内部联系",
          "这种资源 intensity 决定了其最适合能够通过卓越性能创造足够高价值的任务，如法律案例研究、医疗证据整合、金融风险管理等专业场景。"),
        P("端到端训练方案的代价是训练成本高、迭代慢、可解释性弱；ChatGPT Deep Research 因此门槛高。", "内部联系",
          "端到端方案的主要代价在于**训练成本极高、模型迭代周期长、系统行为可解释性较弱**。"),
        P("DeepSeek-R1 不内置联网检索，完整的深度研究能力要靠开发者自行集成搜索模块。", "内部联系",
          "完整的Deep Research能力需要开发者自行集成搜索模块。"),
        P("松耦合架构下，外部检索配置不当会让推理引擎把过时或缺失的信息“精致包装”，输出更具误导性。", "内部联系",
          "如果外部检索服务配置不当，推理引擎可能基于过时或缺失的信息进行\"精致包装\"，产生更具误导性的输出。"),
        P("ChatGPT Deep Research 只列出采用的来源，检索过但未采信的资料不列，过程无法完全复现。", "全体",
          "关键局限在于过程不可完全复现——系统仅引用实际采用的来源，对于检索过但未采信的资料不会全部列出。"),
        P("趋势是速度优先者补深度、深度优先者提速度，预计 2026 年各家在速度与深度上趋同，差异转向垂直领域、生态和定价。", "全体",
          "**预测**：2026年，头部平台的Deep Research功能将在速度-深度光谱上趋于收敛，差异化将更多体现在垂直领域优化、生态集成、和定价策略上。"),
        P("各家共同风险之一是循环引用：AI 生成的内容又被后来的 AI 检索引用。", "内部联系",
          "AI生成内容被后续AI检索引用"),
        P("静态基准排名是快照、很快过时，用户应定期用代表性任务自行测试，而非依赖一次性排名。", "内部联系",
          "建议用户建立**持续评估机制**：定期用代表性任务测试各平台表现，跟踪其演进轨迹，而非依赖一次性排名做出长期工具选择。"),
        P("在“脂肪因子与痴呆症”横向评测中，ChatGPT Deep Research 用时 7 分钟、调研 35 篇文献、输出 2 万多字，被评为质量最高。", "现象",
          "在\"脂肪因子与痴呆症作用机制\"的横向评测中，ChatGPT Deep Research用时7分钟，调研35篇文献，输出2万多字完整综述，被评定为\"质量最高\"——\"报告足够有深度、准确性高、文献是最新的\"。"),
        P("同一评测中 Gemini 的表格总结误解主题，把所有炎症相关脂肪因子都纳入，而非只与痴呆相关的。", "现象",
          "实测案例揭示了具体问题：在\"脂肪因子与痴呆症\"研究中，Gemini的表格总结出现主题理解偏差，将\"所有炎症相关脂肪因子\"而非\"与痴呆相关的脂肪因子\"纳入总结。"),
        P("Gemini 正式执行前先生成研究大纲供用户确认，兼顾自主性和可控性。", "现象",
          "**Gemini Deep Research**增加了**研究大纲预确认**环节——正式执行前，系统生成多步骤研究计划供用户审核，确保研究方向与意图对齐。"),
        P("Gemini 2025 年底增强版在 HLE 达 46.4%、DeepSearchQA 66.1%、BrowseComp 59.2%。", "现象",
          "2025年底增强版在权威基准测试中表现优异：Humanity's Last Exam达**46.4%**，DeepSearchQA达**66.1%**，BrowseComp达**59.2%**。"),
        P("Kimi 深度研究月费约 25 元、生成约需 15 分钟、不能导出 PDF，整体质量与 Gemini、ChatGPT 仍有明显差距。", "现象",
          "综合评测显示，Kimi\"生成报告质量还过得去，但是要和前面的Gemini和ChatGPT比较，Kimi还是存在较为明显的差距\"。"),
        P("十维度评分的综合排序：Claude（42）与 Gemini（41）为第一梯队，ChatGPT 与 Kimi（39）次之，Perplexity 与 DeepSeek（36）第三。", "现象",
          "Claude以微弱优势领先，源于其在分析深度和创新性维度的满分表现。"),
        P("分场景选型：文献综述首选 ChatGPT，快速扫描用 Gemini 或 Perplexity，中文资料用 Kimi，法律与合规用 Claude，自建研报系统用 DeepSeek。", "现象",
          "学术研究的核心需求——**准确性、深度、可验证性**——与ChatGPT Deep Research的能力高度匹配："),
        P("独立评测的幻觉率为 Perplexity 7.7%、ChatGPT 9.7%，但各评测口径不同，直接比较需谨慎。", "现象",
          "更可靠的解读是：即使表现最优的系统，仍有约1/10的概率生成不可信内容，关键决策场景必须人工复核。"),
    ],
    "off_topic": {"value": False, "reason": "围绕各家 Deep Research 功能做了比较、排序和选型建议，回答的是所问的问题。"},
}

# ---------------- D ----------------
data["D"] = {
    "ratings": {
        "①": R(2,
              "综合上述对核心技术架构、基准测试表现、幻觉控制机制以及商业成本的深入剖析，试图回答“哪家公司的Deep Research做得最好？”在2026年已经成为一个典型的伪命题。" + SEP +
              "因此，最优的深度研究服务完全取决于用户的具体业务场景约束、容错容忍度以及预算空间。",
              "审视了“最好”这个前提，指出没有平台能在速度、准确性、深度、生态和成本上同时最优，并据此按场景组织结论；不过正文常拿模型的编码基准和 API 价格代替深度研究功能本身。"),
        "③": R(2,
              "我接下来的行动将聚焦于搜集各平台的官方技术文档与最新的行业评测数据。" + SEP +
              "我注意到，关于这些工具在实际运行中的响应延迟以及不同级别订阅方案的性价比，目前还缺乏统一的横向对比。",
              "文末的研究过程记录交代了查找范围（官方文档、行业评测）、分轮检索过的网站和尚未查到的信息；但这些局限没有写进正文结论，也没有说明为什么查不到。"),
        "④": R(1,
              "OpenAI在2026年初发布的未经同行评审的学术报告深刻揭示了幻觉的系统性根源。",
              "偶有标注来源性质（如“未经同行评审”），但 Reddit、Medium 帖子和官方文档混用不分；BrowseComp 成绩多处只给区间（如 59.2% ~ 71.3%），不说明来源分歧，也不说明取舍。"),
        "⑤": R(0,
              "这也从侧面印证了，为什么像Perplexity这样专注于检索技术优化的平台，在提供严谨事实方面远胜于试图让大模型直接从权重中提取记忆的系统。",
              "从一项检索技术研究直接推出 Perplexity“远胜”他者，判断以绝对化的事实口吻写出，没有考虑其他解释或反例。"),
        "⑦": R(0,
              "首先，对于那些将**“事实的准确性”与“数据的可验证性”置于最高优先级**的用户（如金融量化分析师、法律合规审核员、硬新闻记者），**Perplexity Max**是当前无可争议的王者 。",
              "按场景给出了具体判断，但通篇用“无可争议”“绝对的零幻觉”等措辞，完全不说明把握程度；过程记录里提到的信息缺口也没有反映到结论中。"),
        "写作": R(1,
                "唯有深刻理解各家底层的架构哲学与能力边界，方能在2026年的智能体研究浪潮中驾驭海量信息，提炼出真正的商业与学术价值。",
                "正文分节清楚、能读懂，但辞藻堆砌，主要结论放在正文末尾，文后附了大量未整理的来源图标和过程记录。"),
    },
    "points": [
        P("“哪家最好”是伪命题：没有任何平台能同时在速度、准确性、逻辑深度、生态融合和成本上最优，最优选择取决于场景、容错度和预算。", "本质",
          "随着大语言模型技术栈的严重分化，没有任何一个单一的平台能够同时在执行极速、绝对的准确性、长程逻辑深度、生态系统融合与计算成本控制上达到完美的统一。"),
        P("幻觉源于训练激励：二元对错评分让模型在不知道时倾向猜测而非承认不知道。", "本质",
          "研究指出，模型产生幻觉并非单纯的代码缺陷或数据噪声，而是当前机器学习训练激励机制的直接后果 。"),
        P("行业存在四种深度研究架构取向：推理优先（OpenAI、DeepSeek）、并行智能体集群（Kimi）、生态加超长上下文（Gemini）、原生答案引擎与事实核查（Perplexity）。", "本质",
          "行业内当前主要存在四种主导的深度研究架构哲学。"),
        P("深度研究的核心机制是多步工作流：把模糊提示变成研究计划，迭代搜索、阅读、反思，最后合成带引文的长报告。", "本质",
          "深度研究的核心机制在于其复杂的多步工作流：系统首先将用户的模糊提示词转化为多节点的个性化研究计划，随后通过自主调用工具在广袤的公共互联网或企业私有数据库中进行迭代式搜索、阅读、自我反思与逻辑推演，最终将海量碎片化信息合成为具备严密引文支持的长篇专业报告 。"),
        P("Gemini 的百万 token 上下文让它少依赖 RAG 分块截断，从而保住跨文档的逻辑关联。", "内部联系",
          "在深度研究场景下，这意味着Gemini不需要像其他模型那样频繁依赖检索增强生成（RAG）中的向量分块与截断，从而避免了跨文档逻辑关联的丢失。"),
        P("ChatGPT 的深度反思机制使其在海量高频的实时数据抓取上不如专用搜索智能体敏捷。", "内部联系",
          "然而，这种深度反思机制也导致其在面对海量高频的实时数据抓取时，敏捷度不及专用的搜索智能体。"),
        P("为应对推理成本，OpenAI 2026 年在免费和入门层级测试广告，说明算力成本在塑造产品形态。", "内部联系",
          "此外，为应对高昂的推理成本，OpenAI在2026年开始在免费及入门订阅层级中测试广告植入，尽管其声称广告独立于生成内容，但这标志着算力成本对产品形态的深刻影响 。"),
        P("Kimi K2.5 的智能体集群并行执行，避免串行崩溃，端到端时间缩短 80%、速度提升 4.5 倍。", "内部联系",
          "这种并行机制不仅避免了“串行崩溃（Serial Collapse）”，还将极端复杂研究任务的端到端执行时间缩减了百分之八十，整体执行速度相比单智能体模型提升了4.5倍 。"),
        P("顶尖模型在复杂开放的长文档任务中为维持推理连贯，反而更易出现事实细节偏差。", "内部联系",
          "在应对极其复杂的、开放式的长文档分析任务时，顶尖模型为了维持推理逻辑的连贯性，反而更容易出现事实细节的偏差。"),
        P("智能体生成的关键词查询与神经排序器的训练分布不匹配，改写成自然语言问题（Q2Q）可提高召回和准确性。", "内部联系",
          "例如，在基于Agent的网络搜索中，模型生成的关键词查询往往与底层神经排序器（Neural Rankers）的训练分布不匹配。"),
        P("Gemini 的异步任务管理器在规划与执行模型间维护共享状态，子查询失败时可局部恢复而不必重启整个任务。", "内部联系",
          "该管理器在规划模型与任务执行模型之间维护了一个共享状态；一旦某个子查询失败，系统能够优雅地进行错误恢复，而无需重启整个长达数十分钟的进程 。"),
        P("评测在演变：评估孤立事实记忆的基准（如 SimpleQA）已饱和，GAIA 也基本被解决，转向反映真实复杂工作流的智能体基准。", "全体",
          "随着智能体技术的发展，传统的评估孤立事实记忆的基准（如SimpleQA）已处于饱和状态。"),
        P("关于各工具实际响应延迟和不同订阅层级性价比，目前缺乏统一的横向对比。", "全体",
          "我注意到，关于这些工具在实际运行中的响应延迟以及不同级别订阅方案的性价比，目前还缺乏统一的横向对比。"),
        P("2026 年初 ChatGPT Deep Research 加入交互式研究计划：先提澄清问题，生成可编辑的研究大纲。", "现象",
          "其最显著的变化在于引入了高度交互的研究计划阶段，模型在执行长程任务前会主动向用户提出澄清性问题，并生成一份可视化的、可动态编辑的研究大纲，确保最终报告不偏离用户的核心约束条件 。"),
        P("BrowseComp-Plus 准确率：Claude Opus 4.6 86.8%、Kimi K2.5 78.4%、GPT-5.2 59.2%~71.3%、Gemini 3 Pro 59.2%~63.2%、DeepSeek V3.2 32.5%~50%。", "现象",
          "| **Claude Opus 4.6 (结合多智能体框架)** | 86.8%                    |"),
        P("Vectara HHEM 摘要幻觉率：Gemini 2.5 Flash-Lite 3.3%、DeepSeek V3.2 Exp 5.3%、Kimi K2 17.9%、Claude Opus/GPT-5 系列约 20%~27%。", "现象",
          "根据Vectara于2026年更新的休斯幻觉评估模型（HHEM）排行榜，以及行业内的多项综合评测，各家模型在摘要生成及事实陈述中的幻觉率数据如下 ："),
        P("Claude Opus 4.6 可连续自主执行任务 14.5 小时而不丢失逻辑连贯性。", "现象",
          "测试表明，Claude Opus 4.6能够维持长达14.5小时的自主任务执行而不丢失逻辑连贯性，这是截至2026年初行业内已知运行时间最长的自主智能体记录 。"),
        P("API 价格差距悬殊：Claude Opus 4.6 输入/输出每百万 token 5/25 美元，Kimi K2.5 0.60/2.50 美元，DeepSeek V3.2 Exp 0.27/0.41 美元。", "现象",
          "| **DeepSeek V3.2 Exp**      | **$0.27**                | **$0.41**                |"),
        P("分场景选择：重准确与可验证选 Perplexity Max，依赖企业内部数据选 Gemini 3.1 Pro，工程级研究选 Claude 4.6，发散综合与前瞻报告选 ChatGPT Pro，大规模低成本选 Kimi 与 DeepSeek。", "现象",
          "因此，最优的深度研究服务完全取决于用户的具体业务场景约束、容错容忍度以及预算空间。"),
        P("最佳实践是混合组合：Kimi 广域扫描，Perplexity 事实核查，Gemini 结合私有数据，Claude 或 ChatGPT 完成最终分析报告。", "现象",
          "综上所述，2026年顶尖机构与专业研究者的最佳实践已全面转向**混合技术栈组合（Hybrid AI Stack Strategy）**  1 。"),
    ],
    "off_topic": {"value": False,
                  "reason": "主线回答哪家深度研究最好并给出分场景结论；部分篇幅偏到模型的编码基准和 API 价格，但没有改答另一个问题。"},
}

# ---------------- E ----------------
data["E"] = {
    "ratings": {
        "①": R(1,
              "从公开评测和用户口碑来看，目前没有一个“绝对第一”的 Deep Research，但趋势比较清晰：",
              "写明了“没有绝对第一、按场景看趋势”的理解，并据此分英文和中文场景回答；但没有审视“最好”的标准和 Deep Research 的边界，把 Claude 3.5 Sonnet、DeepSeek R1 等底层模型当作深度研究产品来比。"),
        "③": R(1,
              "从多篇 2025–2026 年的评测来看，ChatGPT 的 Deep Research 在“严肃技术/学术研究”场景里普遍被认为略胜一筹，尤其是在推理严谨性和整体可靠性上更受信任。",
              "交代了来源类型（公开评测、用户口碑），并逐条标出来源站点，但没有交代查找方法和局限。"),
        "④": R(1,
              "官方数据称 Deep Research 会执行数十次搜索、阅读上百个来源，并自动生成结构化研究报告；" + SEP +
              "第三方评测指出 Deep Research 虽然快，但仍存在一定幻觉，深度有时不如 OpenAI Deep Research；",
              "区分了官方数据和第三方评测，并列出对 Perplexity 的正反评价；但没有说明来源可靠程度，按场景折中而不说明取舍理由。"),
        "⑤": R(1,
              "多个独立评测认为，如果你的核心诉求是“查最新资料 + 快速看清文献和网页的版图 + 一键带引用”，Perplexity 的体验非常强；但在需要特别严肃、不容出错的技术论证时，OpenAI 的 Deep Research 目前被普遍视为更可靠。",
              "多用“评测认为”“官方数据称”标出判断出处，大体分开了事实和判断，并按场景权衡；但没有考虑其他解释。"),
        "⑦": R(1,
              "英文技术与综合研究：ChatGPT 的 Deep Research 综合实力最强，尤其在技术/严肃研究场景里整体评价略高于 Perplexity、Gemini 等竞品。",
              "按场景给出了明确结论，但把握说明只有开头“趋势比较清晰”一句，没有说明各结论的把握和依据强弱。"),
        "写作": R(2,
                "从公开评测和用户口碑来看，目前没有一个“绝对第一”的 Deep Research，但趋势比较清晰：",
                "结论在前，对比表和分节清楚，篇幅适中；夹杂“clickittech+1”一类残留标记，但不影响理解。"),
    },
    "points": [
        P("英文技术与综合研究场景中，ChatGPT Deep Research 综合实力最强，评价略高于 Perplexity、Gemini。", "现象",
          "英文技术与综合研究：ChatGPT 的 Deep Research 综合实力最强，尤其在技术/严肃研究场景里整体评价略高于 Perplexity、Gemini 等竞品。"),
        P("Perplexity Deep Research 在检索范围、引用透明度和报告结构化上突出，是最强的搜索型深度研究之一。", "现象",
          "面向“搜索+资料综述”：Perplexity 的 Deep Research 在检索范围、引用透明度和报告结构化上非常突出，是最强的 AI 搜索型 Deep Research 之一。"),
        P("中文和本土内容上，Kimi 深度研究加 DeepSeek R1 推理的组合优于大部分国内模型。", "现象",
          "中文与本土内容：Kimi 的「深度研究」+ DeepSeek R1 的推理组合，在处理中文长文档、本土网站和复杂数据分析任务上，目前整体体验优于大部分国内模型。"),
        P("ChatGPT Deep Research 配额有限（Plus 每月约 10 次，免费约 2 次），重度使用门槛高。", "现象",
          "深度研究配额有限（Plus 用户每月约 10 次，免费用户约 2 次），大规模重度使用的门槛较高。"),
        P("第三方评测认为 ChatGPT Deep Research 显著比 Perplexity 更可靠，适合严肃技术场景。", "现象",
          "深度研究版本在可靠性上被评为“显著比 Perplexity 更可靠”，适合严肃技术场景。"),
        P("Perplexity 官方称其 Deep Research 在 Humanity’s Last Exam 上达 21.1%，超过 Gemini Thinking、o3-mini、o1、DeepSeek-R1。", "现象",
          "在 Humanity’s Last Exam 上达到 21.1% 准确率，超过 Gemini Thinking、o3-mini、o1、DeepSeek-R1 等模型。"),
        P("Perplexity 在 SimpleQA 事实性基准上达 93.9%，每条结论给出清晰引用。", "现象",
          "在 SimpleQA factuality 基准上达到 93.9%，并对每条结论给出清晰引用，被多方视为“研究与事实核查”的首选工具之一。"),
        P("Perplexity Deep Research 虽快但仍有幻觉，深度有时不如 OpenAI，PCMag 也认为它不如 ChatGPT 全面。", "全体",
          "第三方评测指出 Deep Research 虽然快，但仍存在一定幻觉，深度有时不如 OpenAI Deep Research；PCMag 也认为其 Deep Research 工具尚不如 ChatGPT 作为“通用深度聊天/研究助手”那样全面。"),
        P("Perplexity Deep Research 本质上像超级版学术/情报搜索引擎，长于广度和带引用的版图梳理，而严肃技术论证上 OpenAI 更可靠。", "本质",
          "另一方面，Perplexity 的 Deep Research 更像“超级版学术/情报搜索引擎”：它会自动执行大量搜索、阅读上百个来源，然后生成结构化报告，在 Humanity’s Last Exam 和 SimpleQA 等基准上都给出了非常亮眼的准确率成绩，同时保持在几分钟内完成任务。"),
        P("评测显示 Kimi k1.5 长文本任务提取准确、维度更全，在特征分类和多维关联挖掘任务中最好。", "现象",
          "行业评测指出，Kimi k1.5 在长文本处理任务中，相比短文本更出色，既能保证提取准确，又能给出更全面的数据维度；在特征分类与多维度关联挖掘任务中表现最佳。"),
        P("Kimi 的推理链和数学严谨性弱于最新 OpenAI 模型和 DeepSeek R1。", "现象",
          "推理链条和数学严谨性整体弱于最新一代 OpenAI / DeepSeek R1，在纯推理解题和高难数学方面仍有差距。"),
        P("DeepSeek R1 做内容总结时会主动补充数据和案例，在国产模型横评中整体超过豆包、Kimi。", "现象",
          "多份技术与媒体评测指出，DeepSeek R1 在内容总结、文字生成时会主动补充数据和案例来佐证观点，使文章“更落地”，在多款国产模型横评中整体表现超出豆包、Kimi 等主流模型。"),
        P("清华等机构的实验认为 R1 在数据分析任务上与 o3-mini 相当并领先其他模型。", "现象",
          "清华等机构的对比实验认为，R1 在数据分析任务上与 OpenAI o3-mini 相当且领先其他模型，分析逻辑更清晰严谨，适合做异常检测、数据相关性挖掘等深度分析场景。"),
        P("DeepSeek R1 有上下文限制，早期联网搜索和多语种输出不稳定，完整的深度研究体验要靠外部工具或代理封装。", "内部联系",
          "对极长文本任务容易超出上下文限制；早期版本联网搜索和多语种输出上存在不稳定问题，需要结合其他工具或代理封装来获得更完整的“深度研究”体验。"),
        P("已有机构和实践者推荐组合使用：R1 负责深度分析，Kimi 负责长文本整理和多维挖掘。", "现象",
          "一个值得注意的趋势是：部分研究机构和实践者已经开始推荐 “DeepSeek R1 + Kimi 深度研究” 的组合使用——R1 负责深度分析和异常检测，Kimi 负责长文本整理和多维度挖掘，从而在中文场景下取得比单一模型更好的效果。"),
        P("Claude 长于长篇写作、合约报告撰写和代码审阅，3.5 Sonnet 的表格结构化输出优于 o3 和部分国产模型。", "现象",
          "多方评价中，Claude 在长篇写作、合约/报告撰写、代码审阅等方面表现突出，适合作为“安全、稳重”的写作和企业助手。"),
        P("Claude 3.5 Sonnet 本身不直接支持内置联网搜索，深度研究体验依赖开发者集成，因此弱于一体化产品。", "内部联系",
          "但从“Deep Research”这一垂直能力看，至少在 2025 年的对比报告里，Claude 3.5 sonnet 本身并不直接支持像 Perplexity/ChatGPT 那样的内置联网搜索，需要额外接工具，这意味着其深度研究体验更依赖开发者集成，而非开箱即用。"),
        P("Gemini 多模态能力强，深度集成 Gmail、Docs、Drive，适合办公自动化。", "现象",
          "Gemini 在文字、图片、音频和视频上的多模态能力较强，并且深度集成 Gmail、Docs、Drive 等 Google 产品，适合办公自动化场景。"),
        P("Gemini 的深度研究更多依赖 Google 搜索加文档生态的组合，而非专门的调研模式，因此在长篇综述和引用管理上口碑稍逊。", "内部联系",
          "Deep Research 能力更多依赖 Google 搜索 + 文档生态的组合，而不是像 Perplexity/ChatGPT 那样提供高度专门化的“深度调研模式”，在纯“长篇综述+引用管理”上口碑略逊。"),
        P("建议：英文严肃研究以 ChatGPT Deep Research 为主、Perplexity 补广度；中文工作先用 Kimi 搜读整理，再交给 R1 或 OpenAI 模型推导。", "现象",
          "如果你主要做的是英文技术、学术或严肃商业研究，而且可以接受订阅费用，可以优先把 ChatGPT Deep Research 作为主力，配合 Perplexity 做“广度搜索 + 引用补充”。"),
    ],
    "off_topic": {"value": False,
                  "reason": "回答了各家深度研究哪家更好并按场景给建议；虽然部分比较的是底层模型而非深度研究功能，但没有改答另一个问题。"},
}

# ---------------- F ----------------
data["F"] = {
    "ratings": {
        "①": R(2,
              "关于哪家Deep Research功能做得最好，目前并没有一个绝对的答案，因为各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同。" + SEP +
              "你具体是想用Deep Research来做什么类型的研究呢？",
              "审视了“最好”这个前提，以评测互有胜负说明答案取决于任务，并据此按需求组织建议，最后追问提问者的具体用途。"),
        "③": R(1,
              "为了让你更清晰地了解当前各家实力的分野，我整理了近期几个权威第三方评测机构的结果，或许能提供一个更客观的视角。",
              "交代了来源类型（第三方评测基准），没有交代查找范围、方法和局限。"),
        "④": R(1,
              "不同评测结果“打架”，恰恰说明了当前的Deep Research功能正在快速演进，并且开始走向**专业化分工**。",
              "标出了各评测的发布方（包括厂商自评的 DRACO），并主动指出评测结果相互“打架”；但没有说明可靠程度差异，把矛盾直接解释为专业化分工，也没有据发布方作取舍。"),
        "⑤": R(1,
              "并且深度整合了百度搜索，对中文互联网生态的“信息孤岛”有独家的接入能力，这可能是其脱颖而出的关键护城河。",
              "评测数字和自己的解读大体分开，推测用“可能”标出；但对评测矛盾只给了“专业化分工”一种解释，没有考虑评测设计差异或厂商自评偏差。"),
        "⑦": R(1,
              "它在自己发布的DRACO评测中，特别是在医学、通用知识和技术领域，领先优势明显。",
              "按需求给出了明确推荐，并标明每条推荐依据哪项评测（包括厂商自评），但没有说明各结论有多大把握。"),
        "写作": R(2,
                "关于哪家Deep Research功能做得最好，目前并没有一个绝对的答案，因为各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同。",
                "简洁，先给总判断，再列评测对比和按需求的建议，结构清楚。"),
    },
    "points": [
        P("没有绝对最好的 Deep Research：各评测基准的冠军不同，答案取决于要完成的任务。", "全体",
          "关于哪家Deep Research功能做得最好，目前并没有一个绝对的答案，因为各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同。"),
        P("在 DeepResearch Bench（100 个博士级任务、22 个学科）上，百度千帆深度研究 Agent 排名第一，超过 OpenAI、Gemini。", "现象",
          "**百度千帆深度研究Agent**排名第一，超越OpenAI、Gemini等。"),
        P("Perplexity 发布的 DRACO 基准上，Perplexity 得 67.15%，领先 Gemini（58.97%）和 OpenAI（52.06%）。", "现象",
          "**Perplexity Deep Research**得分**67.15%**，领先Gemini (58.97%) 和 OpenAI (52.06%)。"),
        P("LiveDRBench（ICLR 2026）上 OpenAI 表现最佳，综合 F1 为 0.55。", "现象",
          "**OpenAI**的模型表现最佳，综合**F1分数为0.55**。"),
        P("LiveDRBench 发现各模型平均只能覆盖约一半的必要搜索查询，深度研究的深度普遍不足。", "全体",
          "评测聚焦科学话题和公共利益事件，分析发现各模型平均只能覆盖约一半的必要搜索查询，表明研究深度仍有提升空间。"),
        P("MMDR-Bench 上 Gemini Deep Research 在综合性任务中最好，GPT-5.2 在计算机科学等专业领域胜出。", "现象",
          "**谷歌Gemini Deep Research**在**综合性任务**中表现最优；**GPT-5.2**在计算机科学等**高度专业化领域**胜出。"),
        P("评测结果相互矛盾，反映深度研究功能正快速演进并走向专业化分工。", "内部联系",
          "不同评测结果“打架”，恰恰说明了当前的Deep Research功能正在快速演进，并且开始走向**专业化分工**。"),
        P("百度千帆深度整合百度搜索，能接入中文互联网的“信息孤岛”，这可能是它领先的关键。", "内部联系",
          "并且深度整合了百度搜索，对中文互联网生态的“信息孤岛”有独家的接入能力，这可能是其脱颖而出的关键护城河。"),
        P("需要综合性多领域研究时，Gemini Deep Research 是均衡稳健的选择。", "现象",
          "**需要综合性的多领域研究助手**：**谷歌Gemini Deep Research**是一个均衡而稳健的选择。"),
        P("高度专业的研究（尤其计算机科学）更适合 OpenAI GPT 系列，其近期升级允许用户指定搜索来源。", "现象",
          "近期升级也允许用户指定搜索来源，进一步提升了专业性。"),
        P("Perplexity 在自家发布的 DRACO 评测中，医学、通用知识和技术领域领先明显。", "现象",
          "它在自己发布的DRACO评测中，特别是在医学、通用知识和技术领域，领先优势明显。"),
        P("据用户反馈，Kimi 深度研究在编程相关任务上表现出色，甚至优于一些付费方案。", "现象",
          "**预算有限但有特定编程需求**：根据真实用户的反馈，**Kimi的深度研究功能在编程相关任务上表现出色，甚至优于一些付费方案**。"),
    ],
    "off_topic": {"value": False, "reason": "直接回答哪家 Deep Research 最好，以评测结果为据给出按需求的选择建议。"},
}

# ---------------- verify ----------------
errors = []
for k, rep in data.items():
    t = texts[k]
    for name, r in rep["ratings"].items():
        for part in r["evidence"].split(SEP):
            if part not in t:
                errors.append(f"{k} rating {name}: evidence not found: {part[:80]}")
        assert r["score"] in (0, 1, 2)
    for i, p in enumerate(rep["points"], 1):
        p_id = f"{k}-{i}"
        if p["quote"] not in t:
            errors.append(f"{p_id}: quote not found: {p['quote'][:80]}")
        assert p["level"] in ("现象", "全体", "内部联系", "本质"), p_id
    assert len(rep["points"]) <= 20, k

if errors:
    print("\n".join(errors))
    sys.exit(1)

out = {"judge": "opus-1", "reports": {}}
for k in "ABCDEF":
    rep = data[k]
    pts = [{"id": f"{k}-{i}", "content": p["content"], "level": p["level"], "quote": p["quote"]}
           for i, p in enumerate(rep["points"], 1)]
    out["reports"][k] = {"ratings": rep["ratings"], "points": pts, "off_topic": rep["off_topic"]}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("written", OUT)
for k in "ABCDEF":
    print(k, len(out["reports"][k]["points"]), {n: r["score"] for n, r in out["reports"][k]["ratings"].items()})
