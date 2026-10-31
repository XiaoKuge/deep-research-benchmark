# 17: 代码审查后的修正（一）：计分程序、名次页、出题手册和手写网页

**What to build:** 2026-10-30 对 `main...xuntian-site` 做了两路代码审查（规范一路、需求一路）。这一张单子修计分、名次页、出题手册和手写网页里与规则手册（`research-plan/rules.md` 草案第 3 版）不一致的地方，以及这些文件里的规范问题。规则手册是准绳：程序与它不一致时改程序，不改规则。

**Blocked by:** 无（与 18 号并行，文件不重叠）

**Status:** resolved

只改这些文件：`research-plan/stage5-pilot/score.py` 及其输出 `results-v1.2.json`、`site/build_results.py` 及生成的 `site/results/`、`research-plan/question-handbook.src.html` 及生成的 `notes/question-handbook.html`、`site/` 下手写的网页（index、brief、news、faq、start、teams、walkthrough）、`site/starter-kit/` 下的文字文件、相应的测试。不改 `tools/` 和 `site/build_simulation.py`（18 号在改）；`build_results.py` 里被 `build_simulation.py` 用到的函数和常量（build、esc、href、interval、join_cn、model_name、num、read_jsonl、repo_path、STYLE、table、tag、task_text）不改名、不改参数。

- [x] **两两比较的否决（规则第八节第 4 条）。** 第 1.2 版：一对已分开的报告，两两比较里与前面结果相反的次数至少占四分之三（向上取整：四次至少三次，两次就要两次都相反）才改为并列；不能否决由核验确认的硬伤。第 1.0、1.1 版的复现结果一个字节都不变。有测试（四次里三次相反改并列、两次相反不改、两次比较时两次都相反才改）
- [x] **分不开时只比五个环节（规则第八节第 3 条，第四阶段方案第 181 行）。** 第 1.2 版的环节比较去掉时效（②），只比切题与真实需要、查找过程的交代、甄别来源与处理矛盾、分析、结论与把握五项。第 1.0、1.1 版的复现结果不变。有测试
- [x] 重新生成 `results-v1.2.json` 和 `site/results/`；在提交说明里写明名次区间改前改后的对照（需求审查者用五项重跑，预计 E 与 A 由并列第 3–4 名变为 E 第 3、A 第 4，以实际重跑为准）
- [x] 名次页上说明排法的文字（`build_results.py` 约第 706 行）改成第 1.2 版的规则：分不开时比五个环节的评级；两两比较四次中至少三次相反才改为并列。删掉"再比较环节评级和时效"里的"和时效"
- [x] `build_results.py`：用 `score.ELEMENT_NAMES` 作环节名的唯一来源；`"results-v1.2.json"` 只写在常量 `RESULTS_NAME` 一处；输出文件改用 `tools/common.py` 的 `write_text_atomic`（先写临时文件再整份替换）。`score.py` 的输出文件同样改为整份替换
- [x] **交付要求的原文（规则附录一，"一字不改"）。** 出题手册第八节模板里的【交付要求】【说明】改成与规则附录一逐字相同，手册里说"一字不改"的地方写明原文以规则附录一为准；`site/starter-kit/交付要求.txt`、练习题的提问版和裸题版、`site/` 各页引用交付要求的地方，凡是引原文的都与附录一逐字相同。有测试：从规则附录一取原文，检查上面这些文件里的那一段逐字相同
- [x] **网页文字。** `index.html` 的"7 天申诉期"按规则写成默认条款（标〔默认〕）；brief、news 讲"地图上没有的要点判定时不告诉评委"的地方补上"出自几份报告"（规则第七节第 3 条）；faq 的问题标题"评委是 AI"改成白话；teams 等页可见文字里的"SHA-256"改称"校验值"，只在队伍必须自己计算时点一次算法名并用白话解释
- [x] brief、faq、news、start、teams 五页里完全相同的样式（约 87 行）抽成一个样式文件 `site/pages.css`，五页链接它；页面看起来不变（用无头浏览器截图对比或逐条核对样式规则）
- [x] 全部测试通过（`python3 -I -m unittest discover -s tests`）
