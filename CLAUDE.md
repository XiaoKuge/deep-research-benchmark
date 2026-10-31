# 深度研究评测基准

文献、研究计划、论文、规则手册、出题手册、试评数据和本地资料站。目录说明见 `README.md`。

- 规则手册和出题手册以本地版为准：源文件在 `research-plan/`，改完运行 `python3 render_plan.py` 生成 `notes/` 下的网页。
- 文字一律用平实的中文：不用缩写，不用要人猜的短语，不用"台账"这个词。
- 测试用 Python 自带的 `unittest`，运行 `python3 -I -m unittest discover -s tests`。

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root, created only when needed. See `docs/agents/domain.md`.
