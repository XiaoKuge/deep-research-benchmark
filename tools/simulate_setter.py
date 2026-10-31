"""模拟出题者：让大模型按《深度研究出题手册》的出题七步出一道题，输出一个题目目录。

用法、各角色的分工、输出目录和回放材料的写法见同目录 simulate_setter.md。
只用 Python 自带的标准库和同目录的 models.py（模型调用层）。
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from fractions import Fraction
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import models  # noqa: E402
import substitutes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDBOOK = os.path.join(ROOT, "research-plan", "question-handbook.src.html")
RULES = os.path.join(ROOT, "research-plan", "rules.md")
DEFAULT_OUT = os.path.join(ROOT, "simulation", "questions")

KINDS = ("练习题", "正式题")
TYPES = ("看似简单型", "开放时效型")
LEVELS = ("现象", "全体", "内部联系", "本质")
DEEP_LEVELS = ("内部联系", "本质")
CORE = "核心"
CUTOFF = "只使用截至〔运行当日〕已经公开的信息。"

SETTER, MAP_A, MAP_B, LEAK, CLOSED = "出题人", "甲", "乙", "泄露检查人", "闭卷对照"
ROLES = (SETTER, MAP_A, MAP_B, LEAK, CLOSED)
# 写深度地图要读网页，google 不能用于只读网页一档（models.usable），所以两位出题人是 claude 和 codex；
# google 做只给材料的泄露检查和闭卷对照，闭卷对照和写过地图的两家都不同。
DEFAULT_VENDORS = {SETTER: "claude", MAP_A: "claude", MAP_B: "codex", LEAK: "google", CLOSED: "google"}

LEAK_QUESTIONS = (
    ("暗示往哪里挖", "题面有没有暗示该往哪里挖？"),
    ("给出中间答案", "题面有没有直接给出中间答案？"),
    ("点名来源或方法", "题面有没有点名要查的来源或方法？"),
)

# 文件名
CARD_FILE, ASKER_FILE, BARE_FILE = "题目卡.txt", "提问版.txt", "裸题版.txt"
MAP_FILE, MAP_JSON, MAP_SUM = "深度地图.txt", "深度地图.json", "深度地图校验值.txt"
PAIR_FILE, LEAK_FILE, CLOSED_FILE = "两人对照记录.md", "泄露检查记录.md", "闭卷对照记录.md"
META_FILE, LOG_FILE = "元数据.json", "调用记录.jsonl"


class Stop(Exception):
    """出题中途停止：原因写进元数据，已经发生的调用都在调用记录里。"""


class NoVendor(Exception):
    """一个角色找不到可用、又符合要求的厂商。"""

    def __init__(self, role, task, tried):
        super().__init__("%s（步骤「%s」）找不到可用的厂商：%s" % (
            role, task, substitutes.reasons(tried) or "没有候选"))
        self.tried = tried


# ---- 读出题手册 ----------------------------------------------------------------

class _Text(HTMLParser):
    """把手册的网页源文件转成纯文字：段落分行，列表加编号或短横，表格的格用 ｜ 隔开，
    小标题和术语后面加冒号；样式、脚本、按钮、目录和装饰性的元素不要。"""

    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "tr", "div", "pre", "dt", "dd", "table",
             "ul", "ol", "section", "figure", "figcaption", "blockquote", "thead", "tbody"}
    SKIP = {"style", "script", "button", "nav", "svg"}
    VOID = {"br", "input", "img", "hr", "meta", "link", "source", "wbr"}
    LABEL_CLASSES = {"term", "lv"}
    ENDS = "。：，、？！）」”\"；"

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.lists, self.stack = [], [], []
        self.colon = False  # 刚结束一个小标题或术语：后面紧跟正文时补一个冒号

    def _hidden(self):
        return any(hide for _, hide, _ in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.VOID:
            if tag == "br" and not self._hidden():
                self.parts.append("\n")
            return
        hide = tag in self.SKIP or attrs.get("aria-hidden") == "true"
        label = tag in ("strong", "b") or (tag == "span" and attrs.get("class") in self.LABEL_CLASSES)
        self.stack.append((tag, hide, label))
        if self._hidden():
            return
        if tag in ("ol", "ul"):
            self.lists.append([tag, 0])
        if tag in self.BLOCK:
            self.parts.append("\n")
            self.colon = False
        if tag == "li":
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.parts.append("%d. " % self.lists[-1][1])
            else:
                self.parts.append("- ")
        if tag in ("td", "th"):
            self.parts.append(" ｜ ")

    def handle_endtag(self, tag):
        if tag not in [name for name, _, _ in self.stack]:
            return
        hidden = self._hidden()
        while self.stack:
            name, _, label = self.stack.pop()
            if name == tag:
                break
        if hidden:
            return
        if tag in ("ol", "ul") and self.lists:
            self.lists.pop()
        if tag in self.BLOCK:
            self.parts.append("\n")
        self.colon = label and self._last_char() not in self.ENDS

    def _last_char(self):
        for part in reversed(self.parts):
            if part.strip():
                return part.rstrip()[-1]
        return ""

    def handle_data(self, data):
        if self._hidden():
            return
        data = re.sub(r"\s+", " ", data)
        if self.colon and data.strip():
            if data.strip()[0] not in self.ENDS + "（(":
                self.parts.append("：")
            self.colon = False
        self.parts.append(data)

    def text(self):
        lines, pending = [], ""
        for line in "".join(self.parts).split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"(\d+\.|-)", line):  # 列表记号后面紧跟着一个小标题
                pending = line + " "
                continue
            lines.append(pending + line)
            pending = ""
        return "\n".join(lines)


def _read_handbook():
    with open(HANDBOOK, encoding="utf-8") as f:
        return f.read()


def handbook_text(first_id, stop_id):
    """手册里从 <h2 id=first_id> 到 <h2 id=stop_id> 之前的部分，转成纯文字。"""
    source = _read_handbook()
    start = source.index('<h2 id="%s"' % first_id)
    end = source.index('<h2 id="%s"' % stop_id)
    parser = _Text()
    parser.feed(source[start:end])
    parser.close()
    return parser.text()


def handbook_template(template_id):
    """手册第八节的模板原文（tpl-card 或 tpl-map）。"""
    match = re.search(r'<pre id="%s">(.*?)</pre>' % template_id, _read_handbook(), re.S)
    return html.unescape(match.group(1))


def card_delivery_block():
    """题目卡第四部分的交付要求和说明，原文取自出题手册的题目卡模板。"""
    card = handbook_template("tpl-card")
    return card[card.index("【交付要求】"):].rstrip("\n")


def agent_delivery_block():
    """交给智能体时接在提问版和裸题版后面的交付要求和说明，原文取自规则手册附录一。
    文字和题目卡模板里的相同，只是标题写成「交付要求：」；新手包里的练习题也是这样附的，
    所以每道题交给智能体的这一段一个字节都不差。"""
    with open(RULES, encoding="utf-8") as f:
        rules = f.read()
    match = re.search(r"^### 附录一[^\n]*\n(.*?)(?=^### )", rules, re.S | re.M)
    return match.group(1).strip("\n")


# ---- 小工具 --------------------------------------------------------------------

def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(_text(item) for item in value)
    return str(value).strip()


def _cell(value):
    return _text(value).replace("｜", "|").replace("\n", " ")


def _number(value):
    """估计总数的写法：整数不带小数点，否则保留两位小数。"""
    if value is None:
        return ""
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return ("%.2f" % float(value)).rstrip("0").rstrip(".")


def parse_json(answer, task):
    """取回答里的 JSON 对象：允许包在代码块里，或前后带几句话。"""
    text = answer.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise Stop("步骤「%s」的回答里没有 JSON 对象" % task)
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as error:
        raise Stop("步骤「%s」的回答不是可读的 JSON：%s" % (task, error)) from None
    if not isinstance(data, dict):
        raise Stop("步骤「%s」的回答不是 JSON 对象" % task)
    return data


def _vendor_label(vendor, model=None, reported=None):
    label = "%s（%s）" % (vendor, models.COMPANIES[vendor])
    if model:
        label += "，指定模型 %s" % model
    if reported and reported != model:
        label += "，命令行报告的模型 %s" % reported
    return label


# ---- 角色和厂商 ------------------------------------------------------------------

def step_of(task):
    """任务名里的步骤：出题-深度地图-乙-第1轮 的步骤是 深度地图，出题-闭卷对照-作答 的是 闭卷对照。"""
    return task.split("-")[1]


class Roles:
    """每个角色先用配置的厂商；不能用于这一档、或者不可用时，按 simulate_setter.md 写的规则换一家，并记下原因。

    挑厂商和替代记录的格式用 substitutes.py，与模拟评审共用。某一家调用失败，就整次运行不再用它，
    这个角色以后都用换来的这家；某一家只是不能用于这一档（google 不能用于只读网页一档），只换这一次，
    这个角色在别的档里照常用它。
    """

    def __init__(self, run, configured, model_of):
        self.run = run
        self.configured = dict(configured)
        self.current = dict(configured)
        self.model_of = dict(model_of)
        self.vendors = substitutes.Vendors()
        self.outages = []        # 每次发现不可用的记录
        self.substitutions = []  # [(角色, 替代记录)]
        self.steps = []
        self.map_vendors = []    # 写过深度地图的厂商

    def _order(self, role):
        first = self.current[role]
        rest = [vendor for vendor in models.VENDORS if vendor != first]

        def rank(vendor):
            if role in (MAP_A, MAP_B):
                other = MAP_B if role == MAP_A else MAP_A
                # 先给闭卷对照留出它配置的那一家，再尽量和另一位出题人不同
                return (vendor == self.current[CLOSED], vendor == self.current[other],
                        models.VENDORS.index(vendor))
            if role == LEAK:
                return (vendor == self.current[SETTER], models.VENDORS.index(vendor))
            return (models.VENDORS.index(vendor),)

        return [first] + sorted(rest, key=rank)

    def _exclude(self, role):
        if role != CLOSED:
            return None
        return lambda vendor: ("写过本题的深度地图，闭卷对照不能用它" if vendor in self.map_vendors else None)

    def _mark_unavailable(self, vendor, task, reason, call_index=None):
        if self.vendors.mark_unavailable(vendor, reason):
            self.outages.append({"厂商": vendor, "步骤": task, "原因": reason, "调用序号": call_index})

    def ask(self, role, task, prompt, tools, placeholder=""):
        failed = {}  # 这一步里调用失败了的厂商 -> 原因，写进替代记录
        while True:
            vendor, skipped = self.vendors.pick(self._order(role), tools, self._exclude(role), failed)
            if vendor is None:
                raise NoVendor(role, task, skipped)
            try:
                answer, record = self.run.call(task, vendor, prompt, tools,
                                               model=self.model_of.get(vendor),
                                               placeholder=placeholder)
            except models.ModelCallError as error:
                reason = error.record.get("error") or str(error)
                self._mark_unavailable(vendor, task, reason, error.record.get("call_index"))
                failed[vendor] = "调用失败：" + reason
                continue
            except models.ReplayMissing as missing:
                recorded = self.run.replay_failures.take(task, vendor)
                if recorded is None:
                    raise Stop(str(missing)) from None
                reason = "回放材料里录下这次调用「%s」：%s" % (recorded["status"],
                                                      recorded.get("error") or "没有写原因")
                self._mark_unavailable(vendor, task, reason)
                failed[vendor] = reason
                continue
            except models.CallLimitExceeded as limit:
                raise Stop(str(limit)) from None
            self._used(role, task, vendor, tools, record, skipped)
            return answer, record

    def _used(self, role, task, vendor, tools, record, skipped):
        planned = self.current[role]
        if vendor != planned:
            self.substitutions.append((role, substitutes.record(step_of(task), task, planned, vendor, skipped)))
            if self.vendors.is_unavailable(planned):
                self.current[role] = vendor  # 原来的厂商整次运行都不可用：这个角色以后都用换来的这家
        if role in (MAP_A, MAP_B) and vendor not in self.map_vendors:
            self.map_vendors.append(vendor)
        self.steps.append({
            "步骤": task, "角色": role, "厂商": vendor, "公司": models.COMPANIES[vendor],
            "指定的模型": record.get("model"), "命令行报告的模型": record.get("reported_model"),
            "工具限定": tools, "调用序号": record.get("call_index")})

    def used(self, role):
        vendors = []
        for step in self.steps:
            if step["角色"] == role and step["厂商"] not in vendors:
                vendors.append(step["厂商"])
        return vendors

    def label(self, role):
        """角色用到的厂商和模型，换过厂商的写明配置的是哪家；写进深度地图和各项记录。"""
        used = self.used(role)
        if not used:
            return "没有用到"
        labels = []
        for vendor in used:
            reported = [step["命令行报告的模型"] for step in self.steps
                        if step["角色"] == role and step["厂商"] == vendor
                        and step["命令行报告的模型"]]
            labels.append(_vendor_label(vendor, self.model_of.get(vendor),
                                        reported[-1] if reported else None))
        text = "、".join(labels)
        seen = set()
        for item in self.substitutions_of(role):
            pair = (item["原来的厂商"], item["改用的厂商"])
            if pair in seen:  # 同一种替代在后面几轮又发生，只写第一次
                continue
            seen.add(pair)
            text += "（配置的是 %s，在「%s」这一步换成了 %s，原因见%s）" % (
                item["原来的厂商"], item["任务"], item["改用的厂商"], META_FILE)
        return text

    def substitutions_of(self, role):
        return [item for who, item in self.substitutions if who == role]

    def summary(self):
        result = {}
        for role in ROLES:
            steps = [step for step in self.steps if step["角色"] == role]
            result[role] = {
                "配置的厂商": self.configured[role],
                "用到的厂商": self.used(role),
                "指定的模型": {vendor: self.model_of.get(vendor) for vendor in self.used(role)},
                "命令行报告的模型": sorted({step["命令行报告的模型"] for step in steps
                                     if step["命令行报告的模型"]}),
                "工具限定": sorted({step["工具限定"] for step in steps}),
                "替代": self.substitutions_of(role),
            }
        return result


# ---- 深度地图的整理 ----------------------------------------------------------------

def normalize_map(data):
    """把一份深度地图的回答整理成统一格式：要点按出现顺序重新编号 1、2、3……"""
    rows, renumber = [], {}
    for row in data.get("要点") or []:
        if not isinstance(row, dict):
            continue
        number = len(rows) + 1
        renumber[str(row.get("编号", number)).strip()] = number
        sources = row.get("依据") or []
        if isinstance(sources, str):
            sources = [sources]
        rows.append({
            "编号": number, "要点": _text(row.get("要点")), "层级": _text(row.get("层级")),
            "重要性": _text(row.get("重要性")), "依据": [_text(item) for item in sources if _text(item)],
            "把握": _text(row.get("把握")),
            "出自": [_text(item) for item in row.get("出自") or [] if _text(item)],
        })
    turning = []
    for ref in data.get("转折点用到的要点") or []:
        number = renumber.get(str(ref).strip())
        if number and number not in turning:
            turning.append(number)
    return {"浅答案": _text(data.get("浅答案")), "转折点": _text(data.get("转折点")),
            "转折点用到的要点": turning, "要点": rows,
            "找不到要点的层": _text(data.get("找不到要点的层"))}


def core_ids(depth_map, who):
    return ["%s%d" % (who, row["编号"]) for row in depth_map["要点"] if row["重要性"] == CORE]


def fish_estimate(a, b, c):
    """数鱼的办法（出题手册第三节第 4 步）：估计总数 = a × b ÷ c，合并后 = a + b − c，
    两者相差不到 1 条才算写全；c = 0 时无法估计，离写全还很远。"""
    combined = a + b - c
    if c == 0:
        return {"估计总数": None, "合并后的条数": combined, "相差": None, "写全了": False}
    estimate = Fraction(a * b, c)
    gap = estimate - combined
    return {"估计总数": round(float(estimate), 2), "合并后的条数": combined,
            "相差": round(float(gap), 2), "写全了": gap < 1}


def match_pairs(data, map_a, map_b):
    """两人都列到的核心要点：只认甲的核心和乙的核心之间、一对一的配对；不合规的舍去并写明原因。"""
    a_core, b_core = core_ids(map_a, MAP_A), core_ids(map_b, MAP_B)
    pairs, dropped, used_a, used_b = [], [], set(), set()
    for pair in data.get("都列到的") or []:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            dropped.append({"配对": pair, "原因": "不是两条要点配成的一对"})
            continue
        x, y = _text(pair[0]), _text(pair[1])
        if x.startswith(MAP_B) and y.startswith(MAP_A):
            x, y = y, x
        reason = None
        if x not in a_core:
            reason = "%s 不是甲的核心要点" % x
        elif y not in b_core:
            reason = "%s 不是乙的核心要点" % y
        elif x in used_a or y in used_b:
            reason = "一条要点只能配一对"
        if reason:
            dropped.append({"配对": [x, y], "原因": reason})
            continue
        pairs.append([x, y])
        used_a.add(x)
        used_b.add(y)
    return pairs, dropped, a_core, b_core


# ---- 提示词 --------------------------------------------------------------------

def _handbook_block():
    return ("下面附《深度研究出题手册》第一至六节的原文（不含模板和常见问题），出题时以它为准。\n\n"
            "===== 出题手册原文开始 =====\n%s\n===== 出题手册原文结束 =====\n"
            % handbook_text("words", "checklist"))


JSON_ONLY = "只回复一个 JSON 对象，不要写别的文字。格式如下：\n"

MAP_FORMAT = ('{"浅答案": "只看现象时的答案", "转折点": "挖深之后，结论或建议在哪里改变", '
              '"转折点用到的要点": [要点的编号], '
              '"要点": [{"编号": 1, "要点": "一句话，一条独立的认识", '
              '"层级": "现象、全体、内部联系、本质之一", "重要性": "核心或一般", '
              '"依据": ["出处网址"], "把握": "高、中、低之一"}], '
              '"找不到要点的层": "某一层确实找不到要点时，写明是哪一层、查了什么；四层都有就写空字符串"}')


def judge_card_lines(card):
    return ("【提问者】%s\n【用途】%s\n【问题】%s\n【截止时间】%s"
            % (card["提问者"], card["用途"], card["问题"], CUTOFF))


def prompt_judge_card(inputs, today):
    given = []
    if inputs["话题"]:
        given.append("- 话题：%s" % inputs["话题"])
    else:
        given.append("- 领域：%s（主办方只给了领域：请按第 1 步的条件，在这个领域里选一个话题）"
                     % inputs["领域"])
    given.append("- 提问者设定：%s" % (inputs["提问者设定"] or "没有给，请按手册设计一位具体的提问者"))
    given.append("- 题型：%s" % (inputs["题型"] or "没有给，请按话题在看似简单型和开放时效型中选一种"))
    return (_handbook_block() + "\n你在模拟一位出题人。今天是 %s。题目的运行日期还没有定，截止时间由程序统一写成"
            "「%s」；你查资料时，按今天能查到的公开信息。\n\n主办方给你的输入：\n%s\n"
            "不要选手册里用过的实例（中国最大的淡水湖、欧盟《人工智能法》、法国的首都）。\n\n"
            "请做出题七步的第 1 至 3 步中属于评委版的部分：\n"
            "1. 选话题：确认话题满足第 1 步的五个条件。\n"
            "2. 先写浅答案，再往深处查：可以检索和阅读网页。判断挖深会不会改变给提问者的结论或建议；不会改变，就把"
            "「挖深会改变结论」写成 false。\n"
            "3. 写评委版题目卡的提问者、用途、问题三项，遵守第 3 步「写评委版时注意」的各条（截止时间由程序写）。\n\n"
            + JSON_ONLY +
            '{"话题": "……", "题型": "看似简单型或开放时效型", "选题理由": "……", "浅答案": "……", '
            '"挖深会改变结论": true, "怎样改变": "……", "提问者": "……", "用途": "……", "问题": "……"}\n'
            ) % (today, CUTOFF, "\n".join(given))


def prompt_versions(card):
    return (_handbook_block() + "\n你在模拟一位出题人。下面是一道题的评委版题目卡，请按第 3 步写交给智能体的两个版本：\n"
            "- 提问版：用提问者的口吻，把四项写成一两句话，内容和评委版一致，不多也不少；不用「【提问者】」"
            "这样的标签；最后一句原样写「%s」\n"
            "- 裸题版：只有问题本身，就像用户只打了一句话。\n"
            "交付要求和说明由程序原样附上，你不要写。\n\n评委版：\n%s\n\n"
            % (CUTOFF, judge_card_lines(card))
            + JSON_ONLY + '{"提问版": "……", "裸题版": "……"}\n')


def _map_task_text():
    return ("请按出题七步第 4 步写这道题的深度地图：浅答案；挖深之后结论或建议在哪里改变（转折点）；要点表。"
            "检索和阅读网页，每条要点附出处网址和把握，尽量用原始出处。按「写到什么程度为止」的前四条写："
            "至少一处转折点落在内部联系或本质层，转折点用到的要点都有出处；四层都查过，找不到要点的层写明查了什么；"
            "核心要点一条不漏，一般要点不求全。核心要点写到十条以上还在增加，多半是题目太宽。\n\n")


def prompt_first_map(who, card, today):
    return (_handbook_block() + "\n你在模拟出题人%s。另一位出题人在独立地给同一道题写深度地图；你们看不到对方写的东西，"
            "对照之前不商量。今天是 %s。运行日期还没有定，请按今天能查到的公开信息写。\n\n"
            "题目（评委版）：\n%s\n\n" % (who, today, judge_card_lines(card))
            + _map_task_text() + JSON_ONLY + MAP_FORMAT + "\n")


def _map_lines(depth_map, who):
    lines = ["浅答案：%s" % depth_map["浅答案"], "转折点：%s" % depth_map["转折点"],
             "转折点用到的要点：%s" % "、".join("%s%d" % (who, n) for n in depth_map["转折点用到的要点"]),
             "要点（编号 ｜ 要点 ｜ 层级 ｜ 重要性 ｜ 依据 ｜ 把握）："]
    for row in depth_map["要点"]:
        lines.append("%s%d ｜ %s ｜ %s ｜ %s ｜ %s ｜ %s" % (
            who, row["编号"], _cell(row["要点"]), row["层级"], row["重要性"],
            _cell("; ".join(row["依据"])), row["把握"]))
    lines.append("找不到要点的层：%s" % (depth_map["找不到要点的层"] or "（空）"))
    return "\n".join(lines)


def prompt_more_map(who, card, today, previous, only_a, only_b, fish):
    if fish["估计总数"] is None:
        state = "两人一条都没重合，离写全还很远"
    else:
        state = "合并后的条数是 %d 条，估计总数是 %s 条，相差不到 1 条才算写全" % (
            fish["合并后的条数"], _number(fish["估计总数"]))
    listed = []
    for name, rows in (("只有甲列到的核心要点", only_a), ("只有乙列到的核心要点", only_b)):
        listed.append("%s：\n%s" % (name, "\n".join("- " + row["要点"] for row in rows) or "（没有）"))
    return (_handbook_block() + "\n你在模拟出题人%s。你和另一位出题人各自独立写了深度地图，对照以后，按数鱼的办法核心要点"
            "还没有写全：%s。按手册，两人针对只有一个人列到的方向，各自再查一轮。今天是 %s。\n\n"
            "题目（评委版）：\n%s\n\n你上一轮写的深度地图：\n%s\n\n%s\n\n"
            "请针对这些方向再查一轮：逐条查证，确有出处、确实是回答这道题不能缺少的认识，才列为核心；查的过程中发现别的"
            "漏掉的方向，也补上。然后重新写一份完整的深度地图，不是只写改动。\n\n"
            % (who, state, today, judge_card_lines(card), _map_lines(previous, who), "\n\n".join(listed))
            + _map_task_text() + JSON_ONLY + MAP_FORMAT + "\n")


def prompt_compare(map_a, map_b):
    return (_handbook_block() + "\n下面是两位出题人各自独立写的同一道题的深度地图。甲的要点编号写成甲1、甲2……，"
            "乙的写成乙1、乙2……。请做两件事。\n\n"
            "一、找出两人都列到的核心要点：甲的一条核心要点和乙的一条核心要点说的是同一条认识，就配成一对。只在两人"
            "都标为核心的要点之间配对；一条要点最多配一对；说法不同、认识相同的也算。\n\n"
            "二、把两份地图合并成一份：写一个浅答案和转折点；要点表去掉重复，同一条认识只留一行，在「出自」里写明来自"
            "哪几条；层级或重要性有分歧的，按来源和手册的定义裁决；不新增两人都没写的要点。\n\n"
            "甲的深度地图：\n%s\n\n乙的深度地图：\n%s\n\n" % (_map_lines(map_a, MAP_A), _map_lines(map_b, MAP_B))
            + JSON_ONLY +
            '{"都列到的": [["甲1", "乙2"]], "浅答案": "……", "转折点": "……", "转折点用到的要点": [合并后的编号], '
            '"要点": [{"编号": 1, "要点": "……", "层级": "……", "重要性": "核心或一般", "依据": ["出处网址"], '
            '"把握": "高、中、低之一", "出自": ["甲1", "乙2"]}], "找不到要点的层": "……"}\n')


def prompt_leak(asker_text, bare_text):
    return ("你在模拟另一位同学，帮出题人做泄露检查。下面是一道题交给智能体的两个版本的原文。你只拿到这两段文字，"
            "没有深度地图，也不知道出题人希望答案往哪里挖。\n\n"
            "参考：《深度研究出题手册》第六节「红笔批改」列了几种不合格的题，原文如下。\n"
            "===== 手册第六节原文开始 =====\n%s\n===== 手册第六节原文结束 =====\n\n"
            "请只根据这两段文字，回答三个问题：\n%s\n"
            "两个版本后面附的「交付要求」和「说明」每道题都一样，是统一规定，不算泄露。\n\n"
            "===== 提问版原文开始 =====\n%s\n===== 提问版原文结束 =====\n\n"
            "===== 裸题版原文开始 =====\n%s\n===== 裸题版原文结束 =====\n\n"
            % (handbook_text("redpen", "checklist"),
               "\n".join("%d. %s" % (i, q) for i, (_, q) in enumerate(LEAK_QUESTIONS, 1)),
               asker_text, bare_text)
            + JSON_ONLY + "{%s}\n" % ", ".join(
                '"%s": {"有没有": "有或没有", "说明": "……"}' % key for key, _ in LEAK_QUESTIONS))


def prompt_closed_compare(core_rows, answer):
    return ("下面是一道题的深度地图里的核心要点，以及一个不联网的模型对这道题的回答。请逐条判断：这个回答有没有答到"
            "这条核心要点。意思答到了就算，措辞可以不同；只沾边、没有说出这条认识的不算。\n\n核心要点：\n%s\n\n"
            "不联网的回答：\n===== 回答开始 =====\n%s\n===== 回答结束 =====\n\n"
            "如果它答到了大部分核心要点，说明这道题太浅，或者答案早已被模型记住了，请在「建议」里写「改题」"
            "（回到第 2 步，再往深处找能改变结论的地方）或「换题」（回到第 1 步换话题）；否则写「保留」。\n\n"
            % ("\n".join("%d. %s" % (row["编号"], row["要点"]) for row in core_rows), answer)
            + JSON_ONLY + '{"答到的核心要点": [{"编号": 1, "理由": "……"}], "建议": "保留、改题或换题", '
                          '"说明": "……"}\n')


# 只估算时的占位回答：格式正确的空结果。两人对照的占位结果没有重合，所以补查轮数会用满，估算出的是上限。
PLACEHOLDERS = {
    "评委版": json.dumps({"话题": "（只估算，没有调用）", "题型": "", "挖深会改变结论": True,
                       "提问者": "", "用途": "", "问题": ""}, ensure_ascii=False),
    "两个版本": json.dumps({"提问版": "", "裸题版": ""}, ensure_ascii=False),
    "地图": json.dumps({"要点": []}, ensure_ascii=False),
    "对照": json.dumps({"都列到的": [], "要点": []}, ensure_ascii=False),
    "泄露": "{}",
    "闭卷比对": "{}",
}


# ---- 出一道题 ------------------------------------------------------------------

class Setter:
    def __init__(self, roles, inputs, today, max_extra_rounds):
        self.roles = roles
        self.inputs = inputs
        self.today = today
        self.max_extra_rounds = max_extra_rounds

    def make(self):
        card = self.judge_card()
        versions = self.versions(card)
        rounds = self.depth_maps(card)
        final = rounds[-1]["合并"]
        leak = self.leak_check(versions)
        closed = self.closed_book(versions, final)
        return {"评委版": card, "版本": versions, "轮": rounds, "地图": final,
                "泄露检查": leak, "闭卷对照": closed}

    def _ask(self, role, task, prompt, tools, placeholder):
        try:
            return self.roles.ask(role, task, prompt, tools, placeholder)
        except NoVendor as error:
            raise Stop(str(error)) from None

    def _require(self, task, data, keys):
        """真实调用和回放时，题目卡缺了哪一项就停下；只估算时占位回答是空的，不检查。"""
        if self.roles.run.mode == models.ESTIMATE:
            return
        empty = [key for key in keys if not data.get(key)]
        if empty:
            raise Stop("步骤「%s」的回答缺少：%s" % (task, "、".join(empty)))

    # 第 1 至 3 步：评委版
    def judge_card(self):
        task = "出题-评委版"
        answer, record = self._ask(SETTER, task, prompt_judge_card(self.inputs, self.today),
                                   models.WEB_READ_ONLY, PLACEHOLDERS["评委版"])
        data = parse_json(answer, task)
        card = {key: _text(data.get(key)) for key in
                ("话题", "题型", "选题理由", "浅答案", "怎样改变", "提问者", "用途", "问题")}
        card["话题"] = card["话题"] or self.inputs["话题"]
        card["题型"] = self.inputs["题型"] or card["题型"]
        card["挖深会改变结论"] = data.get("挖深会改变结论") is True
        card["调用序号"] = record["call_index"]
        self._require(task, card, ("提问者", "用途", "问题"))
        if not card["挖深会改变结论"]:
            raise Stop("第 2 步不通过：出题人判断挖深不会改变结论。按手册应当回到第 1 步换题。理由：%s"
                       % (card["怎样改变"] or "没有写"))
        return card

    # 第 3 步：提问版和裸题版
    def versions(self, card):
        task = "出题-提问版和裸题版"
        answer, record = self._ask(SETTER, task, prompt_versions(card), models.MATERIALS_ONLY,
                                   PLACEHOLDERS["两个版本"])
        data = parse_json(answer, task)
        block = agent_delivery_block()
        result = {"调用序号": record["call_index"]}
        for name in ("提问版", "裸题版"):
            result[name] = _text(data.get(name))
            result[name + "全文"] = "%s\n\n%s\n" % (result[name], block)
        self._require(task, result, ("提问版", "裸题版"))
        return result

    # 第 4 步：两人各写深度地图，用数鱼的办法对照，没写全就补查
    def depth_maps(self, card):
        rounds, previous = [], None
        for number in range(1, self.max_extra_rounds + 2):
            maps = {}
            for who in (MAP_A, MAP_B):
                task = "出题-深度地图-%s-第%d轮" % (who, number)
                if previous is None:
                    prompt = prompt_first_map(who, card, self.today)
                else:
                    prompt = prompt_more_map(who, card, self.today, previous[who],
                                             previous["只有甲列到的"], previous["只有乙列到的"],
                                             previous["数鱼"])
                answer, record = self._ask(who, task, prompt, models.WEB_READ_ONLY, PLACEHOLDERS["地图"])
                maps[who] = normalize_map(parse_json(answer, task))
                maps[who + "调用序号"] = record["call_index"]
                maps[who + "厂商"] = record["vendor"]
            current = self.compare(number, maps)
            rounds.append(current)
            if current["数鱼"]["写全了"]:
                break
            previous = current
        return rounds

    def compare(self, number, maps):
        task = "出题-两人对照-第%d轮" % number
        answer, record = self._ask(SETTER, task, prompt_compare(maps[MAP_A], maps[MAP_B]),
                                   models.MATERIALS_ONLY, PLACEHOLDERS["对照"])
        data = parse_json(answer, task)
        pairs, dropped, a_core, b_core = match_pairs(data, maps[MAP_A], maps[MAP_B])
        paired_a = {x for x, _ in pairs}
        paired_b = {y for _, y in pairs}
        a, b, c = len(a_core), len(b_core), len(pairs)
        return {
            "轮": number, MAP_A: maps[MAP_A], MAP_B: maps[MAP_B],
            "甲厂商": maps[MAP_A + "厂商"], "乙厂商": maps[MAP_B + "厂商"],
            "调用序号": {MAP_A: maps[MAP_A + "调用序号"], MAP_B: maps[MAP_B + "调用序号"],
                     "对照": record["call_index"]},
            "甲的条数": a, "乙的条数": b, "都列到的条数": c,
            "都列到的": pairs, "舍去的配对": dropped,
            "只有甲列到的": [row for row in maps[MAP_A]["要点"]
                        if row["重要性"] == CORE and "甲%d" % row["编号"] not in paired_a],
            "只有乙列到的": [row for row in maps[MAP_B]["要点"]
                        if row["重要性"] == CORE and "乙%d" % row["编号"] not in paired_b],
            "数鱼": fish_estimate(a, b, c),
            "合并": normalize_map(data),
        }

    # 第 6 步：泄露检查，只看交给智能体的两个版本
    def leak_check(self, versions):
        task = "出题-泄露检查"
        answer, record = self._ask(LEAK, task, prompt_leak(versions["提问版全文"], versions["裸题版全文"]),
                                   models.MATERIALS_ONLY, PLACEHOLDERS["泄露"])
        data = parse_json(answer, task)
        items = []
        for key, question in LEAK_QUESTIONS:
            entry = data.get(key) if isinstance(data.get(key), dict) else {}
            verdict = _text(entry.get("有没有"))
            items.append({"问题": question, "回答": verdict or "没有回答", "说明": _text(entry.get("说明"))})
        passed = all(item["回答"] == "没有" for item in items)
        return {"厂商": record["vendor"], "调用序号": record["call_index"], "三个问题": items,
                "通过": passed}

    # 第 7 步：闭卷对照，换一家没写过地图的厂商，只给材料
    def closed_book(self, versions, final):
        task = "出题-闭卷对照-作答"
        try:
            answer, record = self.roles.ask(CLOSED, task, versions["提问版全文"], models.MATERIALS_ONLY)
        except NoVendor as error:
            return {"做了": False, "原因": str(error), "结论": "未做"}
        core_rows = [row for row in final["要点"] if row["重要性"] == CORE]
        task = "出题-闭卷对照-比对"
        compared, compare_record = self._ask(SETTER, task, prompt_closed_compare(core_rows, answer),
                                             models.MATERIALS_ONLY, PLACEHOLDERS["闭卷比对"])
        data = parse_json(compared, task)
        core_numbers = {row["编号"] for row in core_rows}
        reached = []
        for item in data.get("答到的核心要点") or []:
            item = item if isinstance(item, dict) else {"编号": item}
            try:
                number = int(item.get("编号"))
            except (TypeError, ValueError):
                continue
            if number in core_numbers and number not in [r["编号"] for r in reached]:
                reached.append({"编号": number, "理由": _text(item.get("理由"))})
        suggestion = _text(data.get("建议"))
        if not core_rows:
            verdict = "无法对照：深度地图上没有核心要点"
        elif len(reached) * 2 > len(core_rows):
            verdict = suggestion if suggestion in ("改题", "换题") else "换题"
        else:
            verdict = "保留"
        return {"做了": True, "厂商": record["vendor"], "调用序号": record["call_index"],
                "比对调用序号": compare_record["call_index"], "比对厂商": compare_record["vendor"],
                "回答": answer, "核心要点条数": len(core_rows), "答到的": reached,
                "说明": _text(data.get("说明")), "结论": verdict}


# ---- 自查：写完标准五条和两项检查 ------------------------------------------------------

# "找不到要点的层"里一句话写明某一层查过、没有：要有层的名字、查了什么，以及没有找到。
CHECKED = re.compile(r"查|检索|搜索")
NOTHING_FOUND = re.compile(r"没有|找不到|未找到|查不到|未发现|没发现|不存在")


def levels_checked(final):
    """四层都查过（写完标准第 3 条）：每一层要么要点表里有这一层的要点，要么"找不到要点的层"里有一句
    写明这一层查过、没有（一句里有层的名字、查了什么、没有找到）。只提到层的名字不算。
    返回 (要点表里没有要点的层, 其中没有写明查过的层)。"""
    present = {row["层级"] for row in final["要点"] if row["要点"]}
    missing = [level for level in LEVELS if level not in present]
    sentences = [part for part in re.split(r"[。；;！!\n]", final["找不到要点的层"]) if part.strip()]
    unexplained = [level for level in missing
                   if not any(level in part and CHECKED.search(part) and NOTHING_FOUND.search(part)
                              for part in sentences)]
    return missing, unexplained


def compared_by_two(result):
    """两人对过（写完标准第 5 条）：每一轮甲和乙的地图都真的写出了要点，并且做了对照。"""
    return all(item[MAP_A]["要点"] and item[MAP_B]["要点"] and item["调用序号"].get("对照") is not None
               for item in result["轮"])


def self_check(result):
    final = result["地图"]
    rows = {row["编号"]: row for row in final["要点"]}
    turning = [rows[n] for n in final["转折点用到的要点"] if n in rows]
    missing, unexplained = levels_checked(final)
    standard = {
        "浅答案": bool(final["浅答案"]),
        "转折点": bool(final["转折点"]) and any(row["层级"] in DEEP_LEVELS for row in turning)
                 and all(row["依据"] for row in turning),
        "四层都查过": not unexplained,
        "核心要点写全": result["轮"][-1]["数鱼"]["写全了"],
        "两人对过": compared_by_two(result),
    }
    closed = result["闭卷对照"]["结论"]
    leak = "通过" if result["泄露检查"]["通过"] else "未通过"
    return {"写完标准": standard, "四层里没有要点的层": missing, "泄露检查": leak, "闭卷对照": closed,
            "全部通过": all(standard.values()) and leak == "通过" and closed == "保留"}


# ---- 写题目目录 ------------------------------------------------------------------

def render_card(result):
    card, versions = result["评委版"], result["版本"]
    return ("一、评委版（只给评委）\n%s\n\n二、提问版（交给智能体）\n%s\n\n三、裸题版（交给智能体）\n%s\n\n"
            "四、附在提问版和裸题版之后，一字不改\n\n%s\n"
            % (judge_card_lines(card), versions["提问版"], versions["裸题版"], card_delivery_block()))


def _fish_lines(current, roles):
    fish = current["数鱼"]
    a, b, c = current["甲的条数"], current["乙的条数"], current["都列到的条数"]
    if fish["估计总数"] is None:
        estimate = "%d × %d ÷ %d，无法估计（两人一条都没重合，离写全还很远）" % (a, b, c)
    else:
        estimate = "%d × %d ÷ %d = %s" % (a, b, c, _number(Fraction(a * b, c)))
    if fish["写全了"]:
        verdict = "写全了"
    elif fish["估计总数"] is None:
        verdict = "继续查（针对只有一人列到的方向）"
    else:
        verdict = "继续查（针对只有一人列到的方向）：还差约 %s 条" % _number(fish["相差"])
    return ["甲：%s　列出核心要点 %d 条" % (_vendor_label(current["甲厂商"]), a),
            "乙：%s　列出核心要点 %d 条" % (_vendor_label(current["乙厂商"]), b),
            "两人都列到的：%d 条" % c,
            "估计总数 = 甲的条数 × 乙的条数 ÷ 都列到的条数 = %s" % estimate,
            "合并后的条数 = 甲 + 乙 − 都列到的 = %d + %d − %d = %d" % (a, b, c, fish["合并后的条数"]),
            "结论：%s" % verdict]


def render_map(result, meta):
    final, roles = result["地图"], meta["roles"]
    lines = ["题目编号：%s" % meta["id"],
             "出题人：甲：%s；乙：%s。由模拟出题者程序调用模型写成，过程见%s"
             % (roles.label(MAP_A), roles.label(MAP_B), PAIR_FILE),
             "写成日期：%s（在看到任何报告之前）" % meta["date"], "",
             "一、浅答案（只看现象时的答案）", final["浅答案"], "",
             "二、挖深之后，结论或建议在哪里改变", final["转折点"],
             "（转折点用到的要点：%s）" % ("、".join(str(n) for n in final["转折点用到的要点"]) or "没有写"),
             "", "三、要点表",
             "编号 ｜ 要点 ｜ 层级（现象／全体／内部联系／本质） ｜ 重要性（核心／一般） ｜ 依据（出处网址） ｜ 把握（高／中／低）"]
    for row in final["要点"]:
        lines.append("%d ｜ %s ｜ %s ｜ %s ｜ %s ｜ %s" % (
            row["编号"], _cell(row["要点"]), _cell(row["层级"]), _cell(row["重要性"]),
            _cell("; ".join(row["依据"])), _cell(row["把握"])))
    lines.append("（找不到要点的层，写明查了什么：%s）" % (final["找不到要点的层"] or "四层都有要点"))
    lines += ["", "四、两人对照记录（对照之前不商量）"] + _fish_lines(result["轮"][-1], roles)
    if len(result["轮"]) > 1:
        earlier = ["第 %d 轮：甲 %d 条、乙 %d 条、都列到 %d 条，%s" % (
            item["轮"], item["甲的条数"], item["乙的条数"], item["都列到的条数"],
            "写全了" if item["数鱼"]["写全了"] else "继续查") for item in result["轮"][:-1]]
        lines.append("（上面是第 %d 轮。之前：%s。详见%s）" % (len(result["轮"]), "；".join(earlier), PAIR_FILE))
    else:
        lines.append("（对照了 1 轮，详见%s）" % PAIR_FILE)
    leak = result["泄露检查"]
    found = "；".join("%s%s%s" % (item["问题"], item["回答"], "：" + item["说明"] if item["说明"] else "")
                     for item in leak["三个问题"])
    lines += ["", "五、泄露检查记录",
              "检查人：%s。只看了提问版和裸题版，没有看深度地图" % roles.label(LEAK),
              "日期：%s" % meta["date"],
              "发现了什么：%s%s" % ("没有发现泄露。" if leak["通过"] else "发现了泄露。", found),
              "怎么改的：%s" % ("不用改。" if leak["通过"] else
                            "程序没有自动改题。按手册应当回到第 3 步改题目卡，再重做泄露检查。")]
    closed = result["闭卷对照"]
    lines += ["", "六、闭卷对照记录"]
    if closed["做了"]:
        reached = "、".join(str(item["编号"]) for item in closed["答到的"]) or "一条也没有"
        lines += ["所用模型（不参赛，且和参赛者不是同一家公司的同一系列）：%s；只给材料，不联网。"
                  "参赛的智能体还没定，正式使用前要核对这一条" % roles.label(CLOSED),
                  "日期：%s" % meta["date"],
                  "不联网答到了哪些核心要点：%s（共 %d 条核心要点，答到 %d 条）"
                  % (reached, closed["核心要点条数"], len(closed["答到的"])),
                  "结论：%s" % closed["结论"]]
    else:
        lines += ["所用模型（不参赛，且和参赛者不是同一家公司的同一系列）：没有做闭卷对照",
                  "日期：%s" % meta["date"], "不联网答到了哪些核心要点：没有做",
                  "结论：未做。%s" % closed["原因"]]
    return "\n".join(lines) + "\n"


def _table(rows, who):
    lines = ["| 编号 | 要点 | 层级 | 重要性 | 依据 | 把握 |", "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append("| %s%d | %s | %s | %s | %s | %s |" % (
            who, row["编号"], _cell(row["要点"]).replace("|", "/"), row["层级"], row["重要性"],
            _cell("; ".join(row["依据"])).replace("|", "/"), row["把握"]))
    return "\n".join(lines)


def render_pairs(result, meta):
    roles = meta["roles"]
    lines = ["# 两人对照记录", "",
             "题目标识：%s。写成日期：%s。" % (meta["id"], meta["date"]), "",
             "- 甲：%s" % roles.label(MAP_A), "- 乙：%s" % roles.label(MAP_B),
             "- 对照：%s，只给材料" % roles.label(SETTER), "",
             "第 1 轮两人各自独立写深度地图（只读网页），提示词里没有对方写的任何东西，对照之前不商量。"
             "没有写全时，按出题手册，两人看到只有一人列到的核心要点，针对这些方向各自再查一轮，然后重新对照。"]
    for note in meta["notes"]:
        if note.startswith("两位出题人"):
            lines += ["", note]
    for current in result["轮"]:
        number = current["轮"]
        calls = current["调用序号"]
        lines += ["", "## 第 %d 轮" % number, "",
                  "甲的地图是第 %s 次调用，乙的是第 %s 次，对照是第 %s 次（见%s）。"
                  % (calls[MAP_A], calls[MAP_B], calls["对照"], LOG_FILE), ""]
        lines += ["```"] + _fish_lines(current, roles) + ["```", ""]
        lines += ["### 都列到的核心要点（%d 对）" % current["都列到的条数"], ""]
        lines += ["- %s = %s" % (x, y) for x, y in current["都列到的"]] or ["（没有）"]
        if current["舍去的配对"]:
            lines += ["", "### 舍去的配对", ""]
            lines += ["- %s：%s" % (_text(item["配对"]), item["原因"]) for item in current["舍去的配对"]]
        for who, key in ((MAP_A, "只有甲列到的"), (MAP_B, "只有乙列到的")):
            lines += ["", "### %s核心要点（%d 条）" % (key, len(current[key])), ""]
            lines += ["- %s%d %s" % (who, row["编号"], row["要点"]) for row in current[key]] or ["（没有）"]
        for who in (MAP_A, MAP_B):
            depth_map = current[who]
            lines += ["", "### %s的深度地图" % who, "", "浅答案：%s" % depth_map["浅答案"], "",
                      "转折点：%s（用到 %s）" % (depth_map["转折点"], "、".join(
                          "%s%d" % (who, n) for n in depth_map["转折点用到的要点"]) or "没有写"), "",
                      _table(depth_map["要点"], who), "",
                      "找不到要点的层：%s" % (depth_map["找不到要点的层"] or "（空）")]
    last = result["轮"][-1]
    lines += ["", "## 结论", "",
              "共对照 %d 轮，%s。合并后的深度地图见%s。" % (
                  len(result["轮"]), "核心要点写全了" if last["数鱼"]["写全了"] else
                  "到补查轮数上限仍没有写全（写完标准第 4 条没有满足）", MAP_FILE)]
    return "\n".join(lines) + "\n"


def render_leak(result, meta):
    leak, versions = result["泄露检查"], result["版本"]
    lines = ["# 泄露检查记录", "", "- 检查人：%s" % meta["roles"].label(LEAK), "- 日期：%s" % meta["date"],
             "- 工具限定：只给材料（不能上网、不能运行命令、不能写文件）",
             "- 看到的材料：只有交给智能体的提问版和裸题版原文（各附统一的交付要求和说明），"
             "没有深度地图；提示词全文见%s里的第 %s 次调用" % (LOG_FILE, leak["调用序号"]), "",
             "| 问题 | 回答 | 说明 |", "| --- | --- | --- |"]
    for item in leak["三个问题"]:
        lines.append("| %s | %s | %s |" % (item["问题"], item["回答"], _cell(item["说明"]).replace("|", "/")))
    lines += ["", "结论：%s。" % ("通过，没有发现泄露" if leak["通过"] else
                               "未通过。程序没有自动改题；按出题手册应当回到第 3 步改题目卡，再重做泄露检查"),
              "", "## 检查的原文", "", "提问版：", "", "> " + versions["提问版"], "",
              "裸题版：", "", "> " + versions["裸题版"]]
    return "\n".join(lines) + "\n"


def render_closed(result, meta):
    closed = result["闭卷对照"]
    lines = ["# 闭卷对照记录", "", "- 日期：%s" % meta["date"]]
    if not closed["做了"]:
        lines += ["- 结论：未做", "", "没有做闭卷对照，原因：%s" % closed["原因"], "",
                  "按出题手册，闭卷对照要换一家没有写过深度地图的厂商；找不到这样的厂商时如实记为未做，"
                  "不用别的回答代替。"]
        return "\n".join(lines) + "\n"
    lines += ["- 所用模型：%s" % meta["roles"].label(CLOSED),
              "- 工具限定：只给材料（不联网、不能运行命令、不能写文件）",
              "- 交给它的：提问版全文（%s），和交给智能体的一字不差；没有深度地图" % ASKER_FILE,
              "- 它和写深度地图的厂商（%s）都不同。参赛的智能体还没定，正式使用前要核对它和参赛者不是同一家公司的同一系列"
              % "、".join(meta["roles"].map_vendors),
              "- 比对：%s，只给材料；作答是第 %s 次调用，比对是第 %s 次（见%s）"
              % (meta["roles"].label(SETTER), closed["调用序号"], closed["比对调用序号"], LOG_FILE), "",
              "## 答到了哪些核心要点", "",
              "深度地图上共 %d 条核心要点，不联网答到 %d 条。" % (closed["核心要点条数"], len(closed["答到的"])), ""]
    rows = {row["编号"]: row for row in result["地图"]["要点"]}
    lines += ["- %d %s（%s）" % (item["编号"], rows[item["编号"]]["要点"], item["理由"] or "没有写理由")
              for item in closed["答到的"]] or ["（一条也没有）"]
    if closed["说明"]:
        lines += ["", "比对说明：%s" % closed["说明"]]
    lines += ["", "结论：%s。答到大部分核心要点（超过一半）时不能保留：说明这道题太浅，或者答案早已被模型记住了。"
              "闭卷对照只能筛掉坏题，不能证明题好。" % closed["结论"],
              "", "## 不联网的回答原文", "", "```", closed["回答"], "```"]
    return "\n".join(lines) + "\n"


def map_json(result, meta, checksum):
    final = result["地图"]
    last = result["轮"][-1]
    return {
        "题目标识": meta["id"], "类别": meta["kind"], "写成日期": meta["date"],
        "出题人": {MAP_A: meta["roles"].used(MAP_A), MAP_B: meta["roles"].used(MAP_B)},
        "浅答案": final["浅答案"], "转折点": final["转折点"], "转折点用到的要点": final["转折点用到的要点"],
        "要点": final["要点"], "找不到要点的层": final["找不到要点的层"],
        "两人对照": [{key: item[key] for key in ("轮", "甲的条数", "乙的条数", "都列到的条数", "都列到的", "数鱼")}
                 for item in result["轮"]],
        "核心要点写全了": last["数鱼"]["写全了"],
        "泄露检查": {"通过": result["泄露检查"]["通过"], "三个问题": result["泄露检查"]["三个问题"]},
        "闭卷对照": {key: value for key, value in result["闭卷对照"].items() if key != "回答"},
        "深度地图文件": MAP_FILE, "深度地图校验值": checksum,
    }


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def _write_json(folder, name, data):
    _write(folder, name, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def notes(roles):
    found = []
    shared = [vendor for vendor in roles.used(MAP_A) if vendor in roles.used(MAP_B)]
    if shared:
        found.append("两位出题人用了同一家（%s）。两次调用互相仍看不到对方的输出，但同一家的模型容易找到同样的几条，"
                     "数鱼的估计可能偏低。" % "、".join(shared))
    if set(roles.used(LEAK)) & set(roles.used(SETTER)):
        found.append("泄露检查人和出题人用了同一家，不如换一家看得出暗示。")
    if roles.used(CLOSED):
        found.append("参赛的智能体还没定：正式使用前，要核对闭卷对照所用的模型和参赛者不是同一家公司的同一系列。")
    return found


def write_folder(folder, result, meta, run):
    roles = meta["roles"]
    meta["notes"] = notes(roles)
    _write(folder, CARD_FILE, render_card(result))
    _write(folder, ASKER_FILE, result["版本"]["提问版全文"])
    _write(folder, BARE_FILE, result["版本"]["裸题版全文"])
    map_text = render_map(result, meta)
    _write(folder, MAP_FILE, map_text)
    checksum = _sha256(map_text)
    _write(folder, MAP_SUM, "%s  %s\n" % (checksum, MAP_FILE))
    _write_json(folder, MAP_JSON, map_json(result, meta, checksum))
    _write(folder, PAIR_FILE, render_pairs(result, meta))
    _write(folder, LEAK_FILE, render_leak(result, meta))
    _write(folder, CLOSED_FILE, render_closed(result, meta))
    checks = self_check(result)
    _write_json(folder, META_FILE, metadata(meta, run, "完成", checks=checks, checksum=checksum,
                                            card=result["评委版"]))
    return checks


def call_counts(run):
    summary = run.summary()
    return {"总次数": summary["calls"], "按厂商": summary["by_vendor"], "按步骤": summary["by_task"],
            "真实调用的上限": summary["max_calls"]}


def metadata(meta, run, state, checks=None, checksum=None, card=None, reason=None):
    roles = meta["roles"]
    data = {
        "题目标识": meta["id"], "类别": meta["kind"], "状态": state,
        "话题": (card or {}).get("话题") or meta["inputs"]["话题"],
        "题型": (card or {}).get("题型") or meta["inputs"]["题型"],
        "输入": meta["inputs"], "生成时间": meta["generated_at"], "写成日期": meta["date"],
        "方式": run.mode, "运行编号": run.run_id,
        "角色": roles.summary(), "步骤": roles.steps, "厂商不可用": roles.outages,
        "调用次数": call_counts(run), "说明": meta.get("notes", []),
    }
    if reason:
        data["停止的原因"] = reason
    if checksum:
        data["深度地图校验值"] = {"文件": MAP_FILE, "算法": "SHA-256", "值": checksum}
    if checks:
        data["检查结果"] = checks
    data["文件"] = sorted(name for name in os.listdir(meta["folder"])) if meta.get("folder") else []
    if META_FILE not in data["文件"] and meta.get("folder"):
        data["文件"] = sorted(data["文件"] + [META_FILE])
    return data


# ---- 命令行 --------------------------------------------------------------------

def _pairs(values, flag, parser):
    result = {}
    for value in values or []:
        vendor, sep, model = value.partition("=")
        if not sep or vendor not in models.VENDORS or not model:
            parser.error("%s 要写成 厂商=模型，厂商是 %s 之一：%r" % (flag, "、".join(models.VENDORS), value))
        result[vendor] = model
    return result


def build_parser():
    parser = argparse.ArgumentParser(
        description="模拟出题者：让大模型按出题手册的出题七步出一道题，输出一个题目目录")
    given = parser.add_argument_group("题目")
    given.add_argument("--topic", help="话题")
    given.add_argument("--asker", help="提问者设定（不给就让模型按手册设计）")
    given.add_argument("--domain", help="只给领域，让模型按出题手册第 1 步的条件选话题")
    given.add_argument("--question-type", choices=TYPES, help="题型（不给就让模型按话题选）")
    given.add_argument("--kind", choices=KINDS, required=True, help="练习题或正式题")
    given.add_argument("--id", help="题目标识，用作目录名；不给就用运行编号")
    given.add_argument("--out", default=DEFAULT_OUT, help="题目目录的上一级目录，默认 simulation/questions")
    who = parser.add_argument_group("各角色用哪家（%s）" % "、".join(models.VENDORS))
    web = "要读网页；google 不能用于只读网页一档，配置了也会换一家"
    who.add_argument("--setter", choices=models.VENDORS, default=DEFAULT_VENDORS[SETTER],
                     help="出题人：评委版（%s）、提问版和裸题版、两人对照、闭卷比对，默认 %s"
                          % (web, DEFAULT_VENDORS[SETTER]))
    who.add_argument("--map-a", choices=models.VENDORS, default=DEFAULT_VENDORS[MAP_A],
                     help="写深度地图的甲（%s），默认 %s" % (web, DEFAULT_VENDORS[MAP_A]))
    who.add_argument("--map-b", choices=models.VENDORS, default=DEFAULT_VENDORS[MAP_B],
                     help="写深度地图的乙（%s），默认 %s" % (web, DEFAULT_VENDORS[MAP_B]))
    who.add_argument("--leak-checker", choices=models.VENDORS, default=DEFAULT_VENDORS[LEAK],
                     help="泄露检查人，只给材料，默认 %s" % DEFAULT_VENDORS[LEAK])
    who.add_argument("--closed-book", choices=models.VENDORS, default=DEFAULT_VENDORS[CLOSED],
                     help="闭卷对照，只给材料，必须和写深度地图的两家都不同，默认 %s" % DEFAULT_VENDORS[CLOSED])
    who.add_argument("--model", action="append", metavar="厂商=模型",
                     help="给某一家指定模型，可以写多次；不给就用命令行的默认模型")
    how = parser.add_argument_group("怎样运行")
    how.add_argument("--max-extra-rounds", type=int, default=2,
                     help="两人对照没写全时最多补查几轮，默认 2")
    how.add_argument("--estimate", action="store_true", help="只估算：不调用模型，只报出将发起的调用次数")
    how.add_argument("--replay", action="append", metavar="调用记录文件",
                     help="回放：回答从录好的调用记录里取，不调用模型；可以写多次")
    how.add_argument("--max-calls", type=int, help="真实调用的次数上限，真实调用时必须给")
    how.add_argument("--timeout-seconds", type=int, default=1800, help="单次调用的时长上限，默认 1800 秒")
    return parser


def _estimate_report(run, max_extra_rounds):
    summary = run.summary()
    extra = sum(count for task, count in summary["by_task"].items()
                if re.search(r"-第(\d+)轮$", task) and int(re.search(r"-第(\d+)轮$", task).group(1)) > 1)
    lines = ["只估算，没有调用任何模型。",
             "将发起的调用：最多 %d 次（假定 %d 轮补查都用上）；第一轮就写全时 %d 次。"
             % (summary["calls"], max_extra_rounds, summary["calls"] - extra),
             "按厂商：%s" % "，".join("%s %d 次" % item for item in summary["by_vendor"].items()),
             "按步骤：%s" % "，".join("%s %d 次" % item for item in summary["by_task"].items()),
             "这是假定配置的厂商都可用时的次数；不能用于某一档的厂商（google 不能用于只读网页一档）已经按替代规则换好。"
             "某一家不可用时，每换一家会多一次失败的调用。"]
    if summary["max_calls"] is not None:
        lines.append("调用次数上限 %d 次：%s。" % (summary["max_calls"], "会超过上限" if summary["over_limit"]
                                                 else "不会超过"))
    return "\n".join(lines)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.topic and not args.domain:
        parser.error("要给 --topic（话题），或者只给 --domain（领域）")
    if args.closed_book in (args.map_a, args.map_b):
        parser.error("闭卷对照要换一家与写深度地图不同的厂商：--closed-book 不能和 --map-a、--map-b 相同")
    if args.estimate and args.replay:
        parser.error("--estimate 和 --replay 只能选一个")
    if args.max_extra_rounds < 0:
        parser.error("--max-extra-rounds 不能是负数")
    mode = models.ESTIMATE if args.estimate else models.REPLAY if args.replay else models.LIVE
    if mode == models.LIVE and not (args.max_calls and args.max_calls > 0):
        parser.error("真实调用必须给出调用次数上限 --max-calls（正整数）；先用 --estimate 看要调用几次")
    model_of = _pairs(args.model, "--model", parser)
    configured = {SETTER: args.setter, MAP_A: args.map_a, MAP_B: args.map_b,
                  LEAK: args.leak_checker, CLOSED: args.closed_book}
    inputs = {"话题": args.topic, "提问者设定": args.asker, "领域": args.domain, "题型": args.question_type}
    now = datetime.now().astimezone()
    today = now.date().isoformat()

    if mode == models.ESTIMATE:
        with tempfile.TemporaryDirectory() as scratch:
            run = models.ModelRun(os.path.join(scratch, LOG_FILE), mode=mode, max_calls=args.max_calls)
            roles = Roles(run, configured, model_of)
            Setter(roles, inputs, today, args.max_extra_rounds).make()
            print(_estimate_report(run, args.max_extra_rounds))
        return 0

    run_id = now.strftime("%Y%m%d-%H%M%S")
    question_id = args.id or "模拟-%s" % run_id
    if not question_id or os.sep in question_id or question_id in (".", ".."):
        parser.error("题目标识不能为空，也不能含路径分隔符：%r" % question_id)
    folder = os.path.join(os.path.abspath(args.out), question_id)
    if os.path.exists(folder):
        print("题目目录已经存在，没有覆盖：%s" % folder, file=sys.stderr)
        return 2
    os.makedirs(folder)
    run = models.ModelRun(os.path.join(folder, LOG_FILE), mode=mode, max_calls=args.max_calls,
                          replay_from=args.replay, run_id=run_id, timeout_seconds=args.timeout_seconds)
    roles = Roles(run, configured, model_of)
    meta = {"id": question_id, "kind": args.kind, "inputs": inputs, "generated_at": now.isoformat(
        timespec="seconds"), "date": today, "roles": roles, "folder": folder}
    try:
        result = Setter(roles, inputs, today, args.max_extra_rounds).make()
    except Stop as stop:
        meta["notes"] = notes(roles)
        _write_json(folder, META_FILE, metadata(meta, run, "中途停止", reason=str(stop)))
        print("出题中途停止：%s\n已经发生的调用记在 %s" % (stop, os.path.join(folder, LOG_FILE)), file=sys.stderr)
        return 1
    checks = write_folder(folder, result, meta, run)
    summary = run.summary()
    print("题目目录：%s" % folder)
    print("调用 %d 次：%s" % (summary["calls"], "，".join("%s %d 次" % item
                                                       for item in summary["by_vendor"].items())))
    print("写完标准：%s" % "；".join("%s %s" % (key, "满足" if value else "没有满足")
                                    for key, value in checks["写完标准"].items()))
    print("泄露检查：%s；闭卷对照：%s" % (checks["泄露检查"], checks["闭卷对照"]))
    for role, item in roles.substitutions:
        print("替代：%s 在「%s」改用 %s。原因：%s" % (role, item["任务"], item["改用的厂商"], item["原因"]))
    if not roles.used(CLOSED):
        print("闭卷对照没有做：%s" % result["闭卷对照"].get("原因", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
