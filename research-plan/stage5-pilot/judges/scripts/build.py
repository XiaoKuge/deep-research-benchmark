import json,sys
R='/Users/zonghuanwu/github/mofa-research/docs/deep-research-benchmarks-2026/research-plan/stage5-pilot/'
def rt(s,e,r): return {"score":s,"evidence":e,"reason":r}
def P(L,items):
    out=[]
    for i,(c,l,q) in enumerate(items,1):
        out.append({"id":f"{L}-{i}","content":c,"level":l,"quote":q})
    return out
reports={}

reports['A']={"ratings":{
"①":rt(0,"We compare the advanced **Deep Research** capabilities of major AI platforms – Google Gemini, OpenAI ChatGPT, Anthropic Claude, Perplexity AI, Moonshot AI’s Kimi, and China’s DeepSeek – along multiple dimensions.","只按字面做多维度功能罗列，没有交代对提问者需要的理解，也没有回答“哪家最好”；还把 ChatGPT Search 等同于 Deep Research。"),
"③":rt(1,"All information is drawn from official docs, technical blogs, and reputable sources (citations in brackets).","交代了来源类型，并说明部分细节为假设，但没有说明查了什么、没查到什么。"),
"④":rt(0,"Chinese news reports also claim they have “basically eliminated” hallucination【16†L247-L254】 (though that’s unverified PR).","仅个别处标注“未经证实”，总体对来源不加区分，且把 DeepSeek 写成“Moonshot’s models”等矛盾和错误没有发现。"),
"⑤":rt(0,"Early reports suggest Gemini Deep Research produces high-quality comparative analysis (a new category of output), but concrete metrics are not public.","大量“likely/presumably”的推测与事实混写，缺少对评价问题本身的推理，基本是各家特性罗列。"),
"⑦":rt(0,"In short, **Gemini** shines in enterprise/Workspace-integrated research with Google search and user data","只给各家“擅长什么”，没有对“哪家最好”给出可用判断，也没有说明把握。"),
"写作":rt(1,"**Mermaid Diagrams:** (Omitted – see referenced architecture descriptions above for how each system is structured.)","能读懂、分节清楚，但结论没有前置，残留图片和图表占位语，信息混乱处不少。")},
"points":P("A",[
("Gemini Deep Research 自主规划多步搜索，覆盖网页与私有数据并生成带引用的报告","现象","Google’s Gemini Deep Research agent autonomously plans and executes multi-step searches over the web and private data (Gmail, Drive, Chat), producing multi-page, cited reports"),
("Claude 的 Research 模式做迭代检索并附可核对的引用","现象","Anthropic’s Claude offers a “Research” mode that performs iterative searches and returns answers with “easy-to-check citations”"),
("Kimi Explore 让 AI 自主搜索并通读数百个网页","现象","Kimi Explore “adopted a different approach: letting the AI search autonomously … reading through hundreds of pages”"),
("Kimi-Researcher 是约 23 步、200+ 网址的多轮自主搜索智能体","全体","autonomous agentic model that performs multi-turn search (around 23 steps, 200+ URLs) via an internal parallel search tool"),
("Kimi 的引用格式没有清楚说明，侧重完整性而非可追溯性","全体","The documentation does not clearly state a citation format."),
("DeepSeek 没有内置搜索，要做有证据的研究需另配检索，因此不是现成的研究产品","内部联系","Without a built-in search, DeepSeek users must explicitly provide context (documents, or use a separate retrieval step) for evidence-based answers."),
("Gemini Deep Research 是异步、耗时数分钟的流程，不适合即时查询","内部联系","Async workflow (minutes-long tasks)"),
("Kimi 声称基本消除幻觉，属未经证实的宣传","全体","(though that’s unverified PR)"),
("Perplexity 的抓取做法受到法律关注","全体","Perplexity’s scraping practices have drawn legal scrutiny"),
("Perplexity 于 2026 年 2 月推出多模型编排的 Computer","现象","multi-agent research assistant using 19 models"),
("Claude Opus 4.6 于 2026 年 2 月支持 100 万 token 上下文（测试版）","现象","Claude Opus 4.6 (Feb 2026) supports up to **1M tokens** (beta)"),
("Gemini 的 Deep Research 代理目前不能接用户自定义工具","现象","currently cannot take custom tools from users"),
("一次典型 Gemini Deep Research API 任务的成本约几美元","现象","a typical Deep Research task (multiple searches and ~60K output tokens) costs a few dollars"),
]),
"off_topic":{"value":False,"reason":"围绕各家产品的研究能力做了对比，只是没有给出“最好”的判断且把 ChatGPT Search 当成 Deep Research，属偏题和不完整，不算回答另一个问题。"}}

reports['B']={"ratings":{
"①":rt(1,"各家 Deep Research 功能各有所长，没有一个绝对的\"最好\"，但可以按不同维度来梳理","点明“没有绝对最好、按维度看”，但没有说明对提问者和用途的理解，也没有进一步审视“最好”的标准。"),
"③":rt(1,"根据多方评测和用户反馈","只笼统交代了来源类型，没有说查了哪些、怎么查、有什么局限。"),
"④":rt(0,"一位测评者发现，ChatGPT 生成了长达 36 页、包含 25 个来源的报告，其中包含具体可操作的建议，与实际商业策略高度吻合。","单个测评者轶事与“多位评测者”混用，不区分来源可靠性，也没有处理任何矛盾。"),
"⑤":rt(0,"如果你看重引用和事实报告，Perplexity 是最佳选择。","事实与判断混在一起，依据只是转述，未考虑其他解释。"),
"⑦":rt(1,"需要**最深度的分析和推理** → ChatGPT Deep Research","按需求给出了明确的对应推荐，但没有说明各结论的把握，依据也很薄。"),
"写作":rt(2,"**总结建议**","短小清楚，开头点明结论，末尾有按需求对应的总结；个别开场寒暄可略。")},
"points":P("B",[
("没有绝对最好，选择取决于具体需求","现象","选择取决于你的具体需求"),
("ChatGPT Deep Research 自主浏览分析周期可长达半小时，擅长发现关联和跨来源不一致","现象","它的自主浏览和分析周期可以运行长达半小时"),
("Gemini Deep Research 先制定多步研究计划再反复搜索，覆盖面广","现象","会制定多步骤研究计划，反复搜索并逐步细化"),
("Gemini 一次测试产出 48 页、100 个来源的报告，全面但偏冗长","现象","Gemini 在一次测试中生成了 48 页、100 个来源的报告，内容全面但结论偏冗长。"),
("Perplexity 的 Deep Research 多数任务三分钟内完成","现象","多数研究任务能在 3 分钟内完成"),
("Claude 的输出可读性和结构感强，但具体建议偏通用","全体","具体建议有时偏通用"),
("DeepSeek、Kimi 以底层模型能力见长，但作为独立 Deep Research 产品的成熟度不及前几家","全体","但在\"Deep Research\"这个独立产品功能上，相比上述几家的成熟度和完善程度还有差距"),
]),
"off_topic":{"value":False,"reason":"直接回应了“哪家最好”，给出按需求的推荐。"}}

reports['C']={"ratings":{
"①":rt(1,"自主多步骤推理是Deep Research区别于标准聊天机器人的核心特征。","界定了 Deep Research 的概念并按场景给推荐，但没有写明对提问者和用途的理解，也没有审视“最好”的标准。"),
"③":rt(0,"基于前述分析和多源评测，以下从十个维度进行量化评分：","全文没有交代查了什么、怎么查，也没有来源清单，只有“多源评测”四个字。"),
"④":rt(1,"需要强调的是，**幻觉率测量方法存在显著差异**，不同评测的定义、测试集、评估标准可能不同，直接比较需谨慎。","对幻觉率的可比性有提示，但对“内部评估”“用户反馈”等来源不加区分，评分与前文评价（ChatGPT 质量最高）的矛盾没有处理。"),
"⑤":rt(1,"ChatGPT的8-20分钟使其获得3分，在需要快速交付的场景中明显劣势。","有速度与深度的取舍分析，但评分表合计与单项加总不符（如 ChatGPT 各项相加为 45 而非 39），使“Claude 第一”的排序缺乏支撑。"),
"⑦":rt(1,"Claude以微弱优势领先，源于其在分析深度和创新性维度的满分表现。","给出明确排序和按场景推荐，但没有对各结论的把握作说明，仅在幻觉率处提示复核。"),
"写作":rt(1,"#### 3.3.1 第一梯队（41-42分）：Gemini、Claude","层次分明、能读懂，但篇幅冗长，没有摘要，结论在后半部分，表格重复啰嗦。")},
"points":P("C",[
("自主多步骤推理是 Deep Research 与普通聊天机器人的区别","本质","自主多步骤推理是Deep Research区别于标准聊天机器人的核心特征。"),
("Claude 的多智能体架构以约 15 倍于普通聊天的 token 消耗换取复杂任务性能，对简单查询是过度设计","内部联系","多智能体架构的优势在复杂分解任务中显现，但对于简单查询可能消耗大量资源却未带来相应价值"),
("Gemini 速度快源于基础设施、模型优化和较浅的迭代深度","内部联系","这种速度源于Google基础设施的高效检索、模型架构的优化，以及相对简化的迭代深度"),
("Perplexity 以轻量迭代牺牲深度换取速度，定位是信息综合而非原创研究","内部联系","其\"轻量级迭代\"策略牺牲了部分深度，但换取了极致的响应速度"),
("ChatGPT 报告只引用采用的来源，检索过程不可完全复现","全体","关键局限在于过程不可完全复现——系统仅引用实际采用的来源，对于检索过但未采信的资料不会全部列出。"),
("DeepSeek R1 不内置联网检索，知识受限于训练截止时间，需要自行集成搜索","内部联系","这意味着其\"知识\"完全局限于训练数据截止时间（约2024年初）"),
("松耦合的推理加检索方案，检索不当会让推理引擎对过时信息做“精致包装”","内部联系","如果外部检索服务配置不当，推理引擎可能基于过时或缺失的信息进行\"精致包装\"，产生更具误导性的输出"),
("横向评测中 ChatGPT 用 7 分钟调研 35 篇文献出 2 万多字综述，被评为质量最高","全体","在\"脂肪因子与痴呆症作用机制\"的横向评测中，ChatGPT Deep Research用时7分钟，调研35篇文献，输出2万多字完整综述"),
("同一评测中 Gemini 的表格总结对主题理解出现偏差，纳入了不相关项目","全体","Gemini的表格总结出现主题理解偏差，将\"所有炎症相关脂肪因子\"而非\"与痴呆相关的脂肪因子\"纳入总结"),
("Gemini 在 2025 年 3 月起向免费用户开放 Deep Research","现象","2025年3月更新后，免费用户即可使用（有用量限制）"),
("不同评测的幻觉率口径不同，不能直接比较，关键场景需人工复核","全体","不同评测的定义、测试集、评估标准可能不同，直接比较需谨慎"),
("头部产品正在向“速度与深度兼得”收敛","全体","速度优先者增强深度，深度优先者提升速度"),
("组合用法：Perplexity 做快速核查扫描，ChatGPT 做深度分析与撰写","现象","用Perplexity进行快速事实核查和初步扫描，用ChatGPT进行深度分析和报告撰写"),
("Kimi 生成速度慢、免费版有限制且被评价与 Gemini、ChatGPT 有明显差距","全体","生成报告质量还过得去，但是要和前面的Gemini和ChatGPT比较，Kimi还是存在较为明显的差距"),
("应关注动态基准而非一次性静态排名","内部联系","关注动态基准测试而非静态排名"),
]),
"off_topic":{"value":False,"reason":"系统比较了各家产品并给出排序与场景推荐，回应了原题。"}}

reports['D']={"ratings":{
"①":rt(2,"试图回答“哪家公司的Deep Research做得最好？”在2026年已经成为一个典型的伪命题","明确审视“最好”这一前提，指出取决于用途、容错和预算，并按场景组织结论；但对“Deep Research”的范围界定偏宽（混入编程和模型层面的指标）。"),
"③":rt(1,"我接下来的行动将聚焦于搜集各平台的官方技术文档与最新的行业评测数据。","附了来源清单和研究过程笔记，范围有交代，局限只在笔记里提到“信息鸿沟”，正文未交代没查到什么。"),
"④":rt(1,"OpenAI在2026年初发布的未经同行评审的学术报告深刻揭示了幻觉的系统性根源。","对个别来源标明“未经同行评审”，同一指标给出区间（如 59.2% ~ 71.3%）但未解释取舍；多数来源不加区分，博客、Reddit 与官方文档并列。"),
"⑤":rt(1,"根据Vectara于2026年更新的休斯幻觉评估模型（HHEM）排行榜，以及行业内的多项综合评测","有结构性解释（如幻觉的激励根源、串行崩溃），但把摘要幻觉率当作 Deep Research 的可靠性，称 Perplexity“零幻觉”“无可争议的王者”，与自己的幻觉分析不一致，事实与判断多处混杂。"),
"⑦":rt(1,"首先，对于那些将**“事实的准确性”与“数据的可验证性”置于最高优先级**的用户（如金融量化分析师、法律合规审核员、硬新闻记者），**Perplexity Max**是当前无可争议的王者","按场景给出具体明确的判断，但措辞过满，没有说明把握程度。"),
"写作":rt(1,"## 场景化模型适配与深度研究的最佳实践结论","结构清楚、能读，但结论放在最后，正文引用标记丢失留下空位，末尾夹杂大量来源图标和研究笔记，混乱。")},
"points":P("D",[
("行业从对话式问答转向智能体驱动的深度研究，系统先生成研究计划再迭代检索、反思、合成长报告","本质","截至2026年，人工智能领域的核心竞争与底层技术逻辑已从传统的“对话式问答（Conversational Q&A）”全面转向“智能体驱动的深度研究（Agentic Deep Research）”"),
("“哪家最好”没有脱离场景的单一答案，因为各家在速度、准确、深度、生态、成本上无法同时最优","本质","试图回答“哪家公司的Deep Research做得最好？”在2026年已经成为一个典型的伪命题"),
("业内有四种架构路线：推理优先、并行智能体集群、生态加长上下文、原生答案引擎","全体","行业内当前主要存在四种主导的深度研究架构哲学"),
("Kimi 用并行子智能体避免串行执行的延迟，端到端时间缩短约八成","内部联系","这种并行机制不仅避免了“串行崩溃（Serial Collapse）”，还将极端复杂研究任务的端到端执行时间缩减了百分之八十"),
("Gemini 的超长上下文使其少依赖向量分块，避免跨文档关联丢失","内部联系","Gemini不需要像其他模型那样频繁依赖检索增强生成（RAG）中的向量分块与截断，从而避免了跨文档逻辑关联的丢失"),
("ChatGPT 的深度反思机制使其在高频实时抓取上不如专用搜索智能体敏捷","内部联系","然而，这种深度反思机制也导致其在面对海量高频的实时数据抓取时，敏捷度不及专用的搜索智能体"),
("幻觉源于训练评估的二元评分激励模型猜测，而非单纯的数据或代码缺陷","本质","模型产生幻觉并非单纯的代码缺陷或数据噪声，而是当前机器学习训练激励机制的直接后果"),
("传统事实记忆基准已饱和，评估转向更接近真实工作流的智能体基准","全体","传统的评估孤立事实记忆的基准（如SimpleQA）已处于饱和状态"),
("顶尖模型在开放式长文档任务中为保持连贯性反而更容易出现事实细节偏差","内部联系","顶尖模型为了维持推理逻辑的连贯性，反而更容易出现事实细节的偏差"),
("中国模型靠稀疏注意力和混合专家架构把 API 成本压到极低","内部联系","通过算法架构优化（如稀疏注意力机制和混合专家模型），在2026年实现了成本的指数级坍塌"),
("DeepSeek 推理强但自带网页抓取工具的鲁棒性偏弱，更适合给定干净语料后推演","内部联系","尽管逻辑推理能力极强，但其配套的内置网络抓取工具的鲁棒性略逊于西方顶流，更适合在给定干净语料后进行深度推演"),
("ChatGPT 深度研究在执行前会提澄清问题并生成可编辑的研究大纲","现象","模型在执行长程任务前会主动向用户提出澄清性问题，并生成一份可视化的、可动态编辑的研究大纲"),
("Claude Opus 4.6 可维持约 14.5 小时自主任务","现象","Claude Opus 4.6能够维持长达14.5小时的自主任务执行而不丢失逻辑连贯性"),
("Perplexity 的 Spaces 把研究限定在用户圈定的可信资料内，排除外部无关数据","现象","模型在进行深度研究时将严格受限于这些可信信息源，从而彻底排除了外部无关数据的污染"),
("最佳实践是按阶段混合多家产品的技术栈","全体","最佳实践已全面转向**混合技术栈组合（Hybrid AI Stack Strategy）**"),
]),
"off_topic":{"value":False,"reason":"围绕“哪家最好”做了全面分析并给出场景化结论，虽混入较多模型层面的内容，仍在回答原题。"}}

reports['E']={"ratings":{
"①":rt(1,"从公开评测和用户口碑来看，目前没有一个“绝对第一”的 Deep Research，但趋势比较清晰：","点明没有绝对第一并按英文/中文场景拆分，但没写对提问者和用途的理解，且把底层模型（Kimi k1.5、R1）与 Deep Research 产品混在一起。"),
"③":rt(1,"从多篇 2025–2026 年的评测来看，ChatGPT 的 Deep Research 在“严肃技术/学术研究”场景里普遍被认为略胜一筹","交代了来源类型（评测、官方数据、媒体）并逐条附来源，但没说明怎么查、没查到什么。"),
"④":rt(1,"官方数据称 Deep Research 会执行数十次搜索、阅读上百个来源","区分了官方数据和第三方评测，并标注了测试时间（“至少在 2025 年中期的测试中”）；但仍大量引用过时的 Claude 3.5 资料，对取舍未说明理由。"),
"⑤":rt(1,"第三方评测指出 Deep Research 虽然快，但仍存在一定幻觉，深度有时不如 OpenAI Deep Research","大体区分了官方宣称和第三方评价，有对比和组合建议，但把 Kimi k1.5 模型评测外推到深度研究产品，缺少其他解释。"),
"⑦":rt(1,"如果你主要做的是英文技术、学术或严肃商业研究，而且可以接受订阅费用，可以优先把 ChatGPT Deep Research 作为主力","结论具体、按场景可用，用“略胜一筹”“普遍认为”做了软性限定，但没有明确说明把握和依据。"),
"写作":rt(2,"从公开评测和用户口碑来看，目前没有一个“绝对第一”的 Deep Research，但趋势比较清晰：","开头三条要点先给出结论，之后分表分场景展开，较清晰；表格单元格偏长，来源标记有残留。")},
"points":P("E",[
("英文技术与综合研究场景下 ChatGPT 的 Deep Research 综合评价最高","现象","ChatGPT 的 Deep Research 综合实力最强"),
("Perplexity 的突出点在检索范围、引用透明度和报告结构化","现象","Perplexity 的 Deep Research 在检索范围、引用透明度和报告结构化上非常突出"),
("中文与本土内容场景的体验和英文场景不同，Kimi 加 DeepSeek R1 组合被认为更好","全体","Kimi 的「深度研究」+ DeepSeek R1 的推理组合，在处理中文长文档、本土网站和复杂数据分析任务上，目前整体体验优于大部分国内模型"),
("ChatGPT Deep Research 配额有限，重度使用门槛高","现象","深度研究配额有限（Plus 用户每月约 10 次，免费用户约 2 次）"),
("Perplexity 官方称 Deep Research 在 Humanity’s Last Exam 上达 21.1%","现象","在 Humanity’s Last Exam 上达到 21.1% 准确率"),
("Perplexity 快但仍有幻觉，深度有时不如 OpenAI","全体","第三方评测指出 Deep Research 虽然快，但仍存在一定幻觉，深度有时不如 OpenAI Deep Research"),
("严肃、不容出错的技术论证中，ChatGPT 比 Perplexity 更被视为可靠","全体","在需要特别严肃、不容出错的技术论证时，OpenAI 的 Deep Research 目前被普遍视为更可靠"),
("Kimi 负责中文长文本整理，DeepSeek R1 负责深度分析，分工组合效果更好","内部联系","R1 负责深度分析和异常检测，Kimi 负责长文本整理和多维度挖掘"),
("Claude 3.5 Sonnet 当时无内置联网，使其深度研究体验依赖外部集成","内部联系","Claude 3.5 sonnet 本身并不直接支持像 Perplexity/ChatGPT 那样的内置联网搜索，需要额外接工具，这意味着其深度研究体验更依赖开发者集成，而非开箱即用"),
("Gemini 的 Deep Research 更依赖 Google 搜索和文档生态，而非专门的深研模式，因而口碑略逊","内部联系","Deep Research 能力更多依赖 Google 搜索 + 文档生态的组合"),
("DeepSeek R1 对极长文本易超上下文，早期联网搜索不稳定","现象","对极长文本任务容易超出上下文限制；早期版本联网搜索和多语种输出上存在不稳定问题"),
("以 ChatGPT 为主力、Perplexity 补广度与引用的组合用法","内部联系","可以优先把 ChatGPT Deep Research 作为主力，配合 Perplexity 做“广度搜索 + 引用补充”"),
]),
"off_topic":{"value":False,"reason":"直接回答了“哪家做得最好”，按场景给出判断。"}}

reports['F']={"ratings":{
"①":rt(1,"目前并没有一个绝对的答案，因为各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同。","指出答案取决于任务并在末尾追问用户场景，但没有写明对提问者的理解，也没有审视“最好”的衡量标准。"),
"③":rt(1,"我整理了近期几个权威第三方评测机构的结果","以评测基准列表交代了来源范围，但没有说明怎么查、没查到什么。"),
"④":rt(1,"它在自己发布的DRACO评测中，特别是在医学、通用知识和技术领域，领先优势明显","标注了评测发布方并点出各评测结果“打架”，但仍称 Perplexity 自己发布的评测为“权威第三方”，对取舍没有给出理由。"),
"⑤":rt(1,"不同评测结果“打架”，恰恰说明了当前的Deep Research功能正在快速演进，并且开始走向**专业化分工**。","用“专业化分工”解释结果分歧，并在个别处标注推测（“可能是”），但没有考虑自家基准偏向等其他解释。"),
"⑦":rt(1,"**需要综合性的多领域研究助手**：**谷歌Gemini Deep Research**是一个均衡而稳健的选择。","按需求给出明确推荐，但没有说明把握，并以追问收尾。"),
"写作":rt(2,"目前并没有一个绝对的答案，因为各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同。","短小清楚，结论在前，表格与按需求对应的建议一目了然。")},
"points":P("F",[
("各评测基准结论不一，各家在不同维度各有胜负","全体","各大模型在不同维度的评测中各有胜负，表现优异的场景也各不相同"),
("DRACO 基准上 Perplexity 67.15% 领先 Gemini 与 OpenAI","现象","**Perplexity Deep Research**得分**67.15%**，领先Gemini (58.97%) 和 OpenAI (52.06%)。"),
("DRACO 由 Perplexity 自己发布，其领先结果有利益相关","全体","它在自己发布的DRACO评测中，特别是在医学、通用知识和技术领域，领先优势明显"),
("DeepResearch Bench 上百度千帆深度研究 Agent 排名第一","现象","**百度千帆深度研究Agent**排名第一，超越OpenAI、Gemini等。"),
("百度的优势可能来自深度整合百度搜索，对中文互联网有独家接入","内部联系","深度整合了百度搜索，对中文互联网生态的“信息孤岛”有独家的接入能力，这可能是其脱颖而出的关键护城河"),
("LiveDRBench 显示各模型平均只覆盖约一半必要搜索查询，研究深度仍有提升空间","全体","分析发现各模型平均只能覆盖约一半的必要搜索查询，表明研究深度仍有提升空间"),
("评测结果的分歧说明产品开始专业化分工","内部联系","不同评测结果“打架”，恰恰说明了当前的Deep Research功能正在快速演进，并且开始走向**专业化分工**"),
("MMDR-Bench 上 Gemini 在综合性任务最优，GPT-5.2 在计算机科学等专业领域胜出","现象","**谷歌Gemini Deep Research**在**综合性任务**中表现最优；**GPT-5.2**在计算机科学等**高度专业化领域**胜出"),
("用户反馈 Kimi 深度研究在编程相关任务上表现出色","现象","**Kimi的深度研究功能在编程相关任务上表现出色，甚至优于一些付费方案**"),
]),
"off_topic":{"value":False,"reason":"围绕各家 Deep Research 的评测结果与选择建议作答。"}}

# verify quotes
bad=0
for k,v in reports.items():
    txt=open(R+f'reports/{k}.md',encoding='utf-8').read()
    for name,r in v['ratings'].items():
        if r['evidence'] not in txt: print('EVID FAIL',k,name,r['evidence'][:50]); bad+=1
    for p in v['points']:
        if p['quote'] not in txt: print('QUOTE FAIL',p['id'],p['quote'][:50]); bad+=1
print('bad',bad)
out={"judge":"sonnet-1","reports":reports}
json.dump(out,open(R+'out/rating-sonnet-1.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
print({k:len(v['points']) for k,v in reports.items()})
