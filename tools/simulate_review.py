"""模拟评审：让几家模型按《评审细则》第 1.2 版评审一道题的一组报告，结果交给计分程序第 1.2 版。

用法：
  python3 -I tools/simulate_review.py --question 题目目录 --reports 报告文件... --estimate
  python3 -I tools/simulate_review.py --question 题目目录 --reports 报告文件... --max-calls 200
  python3 -I tools/simulate_review.py --question 题目目录 --reports 报告文件... --replay 调用记录.jsonl

流程、配置、输出目录和回放材料的写法见同目录 simulate_review.md。只用 Python 标准库；
模型调用一律经过 models.py，评委提示词的模板在 review_prompts/。
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
from itertools import combinations
from statistics import median
from urllib.parse import unquote, urldefrag

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import archive_sources  # noqa: E402
import common  # noqa: E402
import models  # noqa: E402
import substitutes  # noqa: E402

PROMPTS = os.path.join(HERE, "review_prompts")
RUBRIC = os.path.join(ROOT, "research-plan", "stage4-rubric.md")
SCORER = os.path.join(ROOT, "research-plan", "stage5-pilot", "score.py")
REVIEWS = os.path.join(ROOT, "simulation", "reviews")
SCORER_VERSION = "1.2"
RESULTS_NAME = "results-v%s.json" % SCORER_VERSION
SCORER_TIMEOUT = 600  # 计分程序的时长上限，秒；试评的六份报告几秒就算完

LEVELS = ["现象", "全体", "内部联系", "本质"]          # 由浅到深
IMPORTANCE = ["一般", "核心"]
CORRECT = ["正确", "有误", "无法判断"]
UNDECIDED = "无法判断"
# 来源标签按对报告的影响由轻到重排列：票数相同时取最轻的那个
SOURCE_LABELS = ["支持", "部分支持", "失效但有存档", "没有出处", "不支持", "找不到（疑似编造）"]
NO_SOURCE = "没有出处"
FABRICATED = "找不到（疑似编造）"
FOUND_LABELS = {"支持", "部分支持", "不支持", "失效但有存档"}
REACH = ["符合", "相反"]
NOT_WRITTEN = "没写到"
ELEMENTS = ["①", "③", "④", "⑤", "⑦", "写作"]
VERDICTS = ["first", "second", "tie"]

STEPS = [("claims_list", "结论清单"), ("verify", "断言核验"), ("extract", "要点抽取"),
         ("merge", "要点池合并"), ("reach", "写到核对"), ("judge", "要点判定"),
         ("rating", "环节评级"), ("pairwise", "两两比较"), ("direct", "直接回答")]
STEP_NAMES = dict(STEPS)
SINGLE_JUDGE_STEPS = ("claims_list", "merge")  # 细则：清单由一人抽出；要点池由一位评委合并
MIN_VENDORS = 3
THREE_VENDORS_RULE = '规则手册第七节"评委组"第 1 条：至少三家厂商的模型担任评委'

# 默认用 Claude（Anthropic）、Codex（OpenAI）、Gemini（Google）三家，Kimi（月之暗面）作备用，与资料站写明的一致。
DEFAULT_CONFIG = {
    "steps": {
        "claims_list": {"vendors": ["claude"], "times": 1},
        "verify": {"vendors": ["claude", "codex", "google"], "times": 2},
        "extract": {"vendors": ["claude", "codex", "google"], "times": 1},
        "merge": {"vendors": ["claude"], "times": 1},
        "reach": {"vendors": ["claude"], "times": 1},
        "judge": {"vendors": ["claude", "codex", "google"], "times": 2},
        "rating": {"vendors": ["claude", "codex", "google"], "times": 2},
        "pairwise": {"vendors": ["claude", "codex"], "times": 1},
        "direct": {"vendors": ["claude"], "times": 1},
    },
    "models": {vendor: None for vendor in models.VENDORS},
    "substitutes": ["claude", "codex", "google", "kimi"],
    "source_chars": 12000,
    "workers": 4,
    "seed": 0,
}


class UsageError(Exception):
    """输入或配置有误，还没有发起任何调用。退出状态 2。"""


class ReviewError(Exception):
    """评审进行中无法继续（例如各家都不可用、只有一位评委的步骤回答无效）。退出状态 1。"""


# ---- 读输入 ------------------------------------------------------------------

def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    """本程序写的 JSON 文件一律缩进 1、末尾换行，先写临时文件再整份替换。"""
    common.write_json_atomic(path, data, indent=1)


sha256_text = common.sha256_text


def shown(path):
    """记进运行元数据的路径：在仓库里的写相对于仓库根目录的路径，其余写绝对路径。"""
    path = os.path.abspath(path)
    relative = os.path.relpath(path, ROOT)
    return path if relative.startswith("..") else relative


def now():
    return common.now_iso("seconds")


def load_config(path):
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path:
        given = read_json(path)
        unknown = set(given) - set(DEFAULT_CONFIG)
        if unknown:
            raise UsageError("配置里有不认识的项：%s" % "、".join(sorted(unknown)))
        for key, value in given.items():
            if key == "steps":
                unknown = set(value) - set(STEP_NAMES)
                if unknown:
                    raise UsageError("配置里有不认识的步骤：%s" % "、".join(sorted(unknown)))
                config["steps"].update(value)
            elif key == "models":
                config["models"].update(value)
            else:
                config[key] = value
    for step, plan in config["steps"].items():
        vendors, times = plan.get("vendors"), plan.get("times")
        if not vendors or any(v not in models.VENDORS for v in vendors):
            raise UsageError("步骤 %s 的厂商要从 %s 中选，至少一家" % (step, "、".join(models.VENDORS)))
        if not isinstance(times, int) or times < 1:
            raise UsageError("步骤 %s 的次数要是正整数" % step)
    for step in SINGLE_JUDGE_STEPS:
        plan = config["steps"][step]
        if len(plan["vendors"]) * plan["times"] != 1:
            raise UsageError("步骤 %s 按评审细则只由一位评委做，只能配一家、一次" % step)
    if any(v not in models.VENDORS for v in config["substitutes"]):
        raise UsageError("替代顺序 substitutes 里只能写 %s" % "、".join(models.VENDORS))
    return config


# 题目目录的格式照模拟出题者（simulate_setter.md「输出目录」）
CARD_FILE, MAP_JSON, MAP_FILE, MAP_SUM, META_FILE = (
    "题目卡.txt", "深度地图.json", "深度地图.txt", "深度地图校验值.txt", "元数据.json")


def map_points(depth_map):
    """深度地图.json 的"要点"：编号、要点、层级、重要性。编号 1 在评审里记作 M1。"""
    points = []
    for row in depth_map.get("要点") or []:
        number = str(row.get("编号", "")).strip()
        mid = "M" + number if number.isdigit() else number
        if not mid or not str(row.get("要点", "")).strip():
            raise UsageError("深度地图.json 里有一条要点缺编号或内容")
        if row.get("层级") not in LEVELS or row.get("重要性") not in IMPORTANCE:
            raise UsageError("深度地图要点 %s 的层级或重要性写得不对：%s、%s"
                             % (mid, row.get("层级"), row.get("重要性")))
        if any(p["id"] == mid for p in points):
            raise UsageError("深度地图里要点编号 %s 重复" % mid)
        points.append({"id": mid, "content": str(row["要点"]).strip(), "level": row["层级"],
                       "importance": row["重要性"]})
    return points


def load_question(directory, cutoff=None):
    """读题目目录：题目卡.txt（评委版在内的全文）和 深度地图.json 必须有；深度地图.txt、
    深度地图校验值.txt、元数据.json 有就记下校验值和类别。"""
    for name in (CARD_FILE, MAP_JSON):
        if not os.path.exists(os.path.join(directory, name)):
            raise UsageError("题目目录 %s 里没有 %s" % (directory, name))
    card = read_text(os.path.join(directory, CARD_FILE))
    depth_map = read_json(os.path.join(directory, MAP_JSON))
    points = map_points(depth_map)
    if not points:
        raise UsageError("深度地图.json 里没有要点")
    if not cutoff:
        for line in card.splitlines():
            found = re.search(r"\d{4}-\d{2}-\d{2}", line)
            if "截止时间" in line and found:
                cutoff = found.group(0)
                break
    question = {"dir": os.path.abspath(directory), "card": card, "map_points": points, "cutoff": cutoff,
                "card_sha256": sha256_text(card), "depth_map_sha256": None, "checksum_matches": None,
                "kind": depth_map.get("类别")}
    map_path = os.path.join(directory, MAP_FILE)
    if os.path.exists(map_path):
        question["depth_map_sha256"] = sha256_text(read_text(map_path))
        sum_path = os.path.join(directory, MAP_SUM)
        if os.path.exists(sum_path):
            recorded = read_text(sum_path).split()
            question["checksum_matches"] = bool(recorded) and recorded[0] == question["depth_map_sha256"]
    meta_path = os.path.join(directory, META_FILE)
    if os.path.exists(meta_path):
        question["kind"] = read_json(meta_path).get("类别") or question["kind"]
    return question


def norm_url(url):
    return unquote(urldefrag(url.strip())[0]).rstrip("/")


def load_reports(paths, names_file, keep_labels, seed):
    names = {}
    if names_file:
        data = read_json(names_file)
        names = data["reports"] if isinstance(data.get("reports"), dict) else data
    items, seen = [], set()
    for path in paths:
        stem, ext = os.path.splitext(os.path.basename(path))
        if stem in seen:
            raise UsageError("两份报告的文件名相同：%s" % stem)
        seen.add(stem)
        text = read_text(path)
        html = ext.lower() in (".html", ".htm")
        urls, _ = archive_sources.extract_urls(text, html=html)  # 与存档程序同一套提取规则
        items.append({"stem": stem, "ext": ext or ".md", "path": os.path.abspath(path), "text": text,
                      "name": names.get(stem, stem), "sha256": sha256_text(text),
                      "urls": urls, "url_keys": {norm_url(u) for u in urls}})
    if keep_labels:
        for item in items:
            item["label"] = item["stem"]
    else:
        if len(items) > 26:
            raise UsageError("一次至多 26 份报告")
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        for i, item in enumerate(shuffled):
            item["label"] = chr(ord("A") + i)
        items.sort(key=lambda item: item["label"])
    return items


class _HtmlText(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "table", "pre", "blockquote", "ul", "ol", "header", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def archive_text(path, content_type):
    """存档内容的文字：网页去掉标签、脚本和样式；纯文字原样；PDF 等读不出文字的返回 None。"""
    content_type = (content_type or "").lower()
    is_html = "html" in content_type or path.lower().endswith((".html", ".htm"))
    is_text = content_type.startswith("text/") or "json" in content_type or "xml" in content_type
    if not (is_html or is_text):
        return None
    charset = re.search(r"charset=([\w-]+)", content_type)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode(charset.group(1) if charset else "utf-8", errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    if is_html:
        parser = _HtmlText()
        parser.feed(text)
        text = "".join(parser.parts)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def load_archive(directory):
    """读网页存档目录（tools/archive_sources.py 写出的一个或多个 manifest.json）。返回 {网址: 存档条目}。"""
    index, manifests = {}, []
    if not directory:
        return index, manifests
    if not os.path.isdir(directory):
        raise UsageError("网页存档目录不存在：%s" % directory)
    for dirpath, _, filenames in sorted(os.walk(directory)):
        if "manifest.json" not in filenames:
            continue
        manifest = os.path.join(dirpath, "manifest.json")
        manifests.append(manifest)
        for entry in read_json(manifest).get("entries", []):
            if not entry.get("url"):
                continue
            item = {"url": entry["url"], "final_url": entry.get("final_url"),
                    "fetched_at": entry.get("fetched_at"), "status": entry.get("status"),
                    "manifest": manifest, "file": None, "text": None,
                    "problem": entry.get("error")}
            if entry.get("file") and not entry.get("error") and (entry.get("status") or 0) < 400:
                item["file"] = os.path.join(dirpath, entry["file"])
                if os.path.exists(item["file"]):
                    item["text"] = archive_text(item["file"], entry.get("content_type"))
                    if item["text"] is None:
                        item["problem"] = "存档内容不是文字（例如 PDF），程序读不出来"
                else:
                    item["problem"] = "清单里写的存档文件不存在"
            key = norm_url(entry["url"])
            if key not in index or (index[key]["text"] is None and item["text"] is not None):
                index[key] = item
    return index, manifests


# ---- 提示词 ------------------------------------------------------------------

_templates = {}


def render(name, **values):
    """用 review_prompts/<name>.txt 生成提示词：模板里的 {{名字}} 换成给定的文字（只换一遍）。"""
    if name not in _templates:
        _templates[name] = read_text(os.path.join(PROMPTS, name + ".txt"))
    return re.sub(r"\{\{(.+?)\}\}", lambda m: values[m.group(1)], _templates[name])


def material(title, body):
    return "===== %s（开始） =====\n%s\n===== %s（结束） =====" % (title, body.strip(), title)


def parse_json_answer(text):
    """从回答里取出 JSON 对象：允许外面包了代码块或多了几句话。取不出时抛出 ValueError。"""
    text = text.strip()
    fence = re.match(r"^```[A-Za-z]*\s*\n(.*)\n```$", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("回答里没有 JSON 对象")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("回答不是 JSON 对象")
    return data


def _squash(text):
    """核对引文用：统一全角半角和引号，去掉空白和 Markdown 记号，不分大小写。"""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[“”„″«»]", '"', text)
    text = re.sub(r"[‘’′]", "'", text)
    return re.sub(r"[\s*_`#>|~]", "", text)


def quote_in_report(quote, report):
    """evidence 是否逐字出自报告。多段引文用省略号隔开，每段分别核对。"""
    if not quote or not quote.strip():
        return False
    plain = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", report)
    haystacks = (_squash(report), _squash(plain))
    segments = [s for s in re.split(r"……|…|\.\.\.", quote) if len(_squash(s)) >= 2]
    if not segments:
        return False
    return all(any(_squash(s) in h for h in haystacks) for s in segments)


# ---- 判定的合并规则 ----------------------------------------------------------

def plurality(votes, order, tie):
    """票数最多的选项；最多的不止一个时返回 tie。"""
    if not votes:
        return tie
    counts = Counter(votes)
    top = max(counts.values())
    leaders = [v for v in order if counts.get(v) == top]
    return leaders[0] if len(leaders) == 1 else tie


def least_harmful(votes, order):
    """票数最多的选项；最多的不止一个时，取 order 里靠前（对报告影响最轻）的那个。"""
    counts = Counter(votes)
    top = max(counts.values())
    return [v for v in order if counts.get(v) == top][0]


def two_thirds(votes, order, default=None):
    """层级或重要性的三分之二规则。返回 (标注, 是否有争议)。

    有一种意见达到三分之二（票数 × 3 ≥ 总票数 × 2）：就是它；但它若改动了地图登记的 default，
    记为有争议，候选列表为 [地图登记, 评委组的意见]。没有一种意见达到三分之二：有争议，
    候选列表第一项是登记值（地图上有的用地图登记；没有的用票数最多的，并列时取较浅或"一般"），
    其余按票数从多到少、再由浅到深排列。
    """
    counts = Counter(votes)
    total = len(votes)
    top = max(counts.values())
    leaders = [v for v in order if counts.get(v) == top]
    if len(leaders) == 1 and 3 * top >= 2 * total:
        winner = leaders[0]
        if default is not None and winner != default:
            return [default, winner], True
        return winner, False
    registered = default if default is not None else leaders[0]
    others = sorted((v for v in counts if v != registered), key=lambda v: (-counts[v], order.index(v)))
    return [registered] + others, True


def whole(number):
    """中位数是整数时写成整数（2 而不是 2.0）。"""
    return int(number) if float(number).is_integer() else number


def candidates(value):
    return list(value) if isinstance(value, list) else [value]


# ---- 调用模型：不可用时如实记录，并按替代顺序换一家 -------------------------

class _NowUnavailable(Exception):
    """这一家刚被判为不可用：等着发第一个调用时已经被别的调用判为不可用（reason 为空），
    或者回放时取不到它的回答、回放材料里又录下过它的失败（reason 写明）。"""

    def __init__(self, reason=None):
        super().__init__(reason or "")
        self.reason = reason


class Context:
    def __init__(self, run, config, question, reports, archive, out, rubric):
        self.run, self.config, self.question, self.reports = run, config, question, reports
        self.archive, self.out = archive, out
        self.estimate = run.mode == models.ESTIMATE
        self.workers = max(1, int(config["workers"]))
        self.seed = int(config["seed"])
        self.lock = threading.Lock()
        # 每一家在第一次调用成功之前，同一时间只发一个调用：这家不可用时，只白费一次失败的调用。
        self.first_call = {vendor: threading.Lock() for vendor in models.VENDORS}
        self.confirmed = set()
        self.vendors = substitutes.Vendors()
        self.unavailable, self.substitutions, self.invalid = {}, [], []
        self.usage = {name: [] for _, name in STEPS}
        self.notes = {"evidence_not_found": [], "not_merged": [], "unknown_sources": [],
                      "map_points_added": [], "map_points_merged_together": [],
                      "unjudged_points": [], "unverified_claims": [],
                      "ignored_map_changes": 0, "reach_added": 0}
        cutoff = question["cutoff"]
        self.cutoff = ("截止时间是 %s，判断对错和时效，以截至这一天已经存在的信息为准。" % cutoff if cutoff
                       else "截止时间以题目卡写明的为准，判断对错和时效，以截至那一天已经存在的信息为准。")
        self.rubric = material("评审细则", rubric)
        self.card = material("题目卡", question["card"])

    # 计划
    def slots(self, step):
        plan, slots = self.config["steps"][step], []
        for vendor in plan["vendors"]:
            for _ in range(plan["times"]):
                slots.append((len(slots) + 1, vendor))
        return slots

    def archived(self, url):
        item = self.archive.get(norm_url(url))
        return item if item and item["text"] is not None else None

    # 调用
    def pick(self, step, planned, tools, failed):
        """先看计划的厂商；它不能用于这一档或已经不可用时，按替代顺序换一家，先挑这一步没配的厂商
        （尽量让评委来自不同厂商）。返回 (厂商或 None, 跳过的各家和原因)。"""
        in_step = set(self.config["steps"][step]["vendors"])
        rest = [v for v in self.config["substitutes"] if v != planned]
        order = [planned] + [v for v in rest if v not in in_step] + [v for v in rest if v in in_step]
        return self.vendors.pick(order, tools, failed=failed)

    def mark_unavailable(self, vendor, task, error):
        if self.vendors.mark_unavailable(vendor, error):
            with self.lock:
                self.unavailable[vendor] = {
                    "vendor": vendor, "company": models.COMPANIES[vendor], "first_failed_task": task,
                    "error": error, "noticed_at": now()}

    def call_once(self, vendor, task, prompt, tools):
        """调用一次。失败时先把这一家记为不可用，再抛出异常；回放时取不到回答、又录下过这家失败的，同样处理。"""
        def call():
            try:
                return self.run.call(task=task, vendor=vendor, prompt=prompt, tools=tools,
                                     model=self.config["models"].get(vendor))
            except models.ModelCallError as error:
                self.mark_unavailable(vendor, task, error.record.get("error"))
                raise
            except models.ReplayMissing:
                recorded = self.run.replay_failures.first_for(vendor)
                if recorded is None:
                    raise
                reason = "回放材料里这家的调用失败：%s" % (recorded.get("error") or recorded.get("status"))
                self.mark_unavailable(vendor, task, reason)
                raise _NowUnavailable(reason)
        if vendor in self.confirmed:
            return call()
        with self.first_call[vendor]:
            if self.vendors.is_unavailable(vendor):
                raise _NowUnavailable()
            result = call()
            self.confirmed.add(vendor)
            return result

    def ask(self, step, slot, planned, task, prompt, tools):
        """调用一次，返回 (实际用的厂商, 解析出的 JSON 对象)。只估算或回答无效时对象为 None。"""
        name = STEP_NAMES[step]
        failed = {}  # 这一次调用里失败了的厂商 -> 原因，写进替代记录
        while True:
            vendor, skipped = self.pick(step, planned, tools, failed)
            if vendor is None:
                raise ReviewError("没有可用的厂商了（任务「%s」）：%s" % (task, substitutes.reasons(skipped)))
            try:
                answer, record = self.call_once(vendor, task, prompt, tools)
            except _NowUnavailable as gone:
                if gone.reason:
                    failed[vendor] = gone.reason
                continue
            except models.ModelCallError as error:
                with self.lock:
                    self.usage[name].append({"slot": slot, "vendor": vendor, "status": error.record["status"]})
                failed[vendor] = "调用失败：%s" % (error.record.get("error") or error.record["status"])
                continue
            break
        with self.lock:
            self.usage[name].append({"slot": slot, "vendor": vendor, "status": record["status"],
                                     "model": record.get("model"),
                                     "reported_model": record.get("reported_model")})
            if vendor != planned:
                self.substitutions.append(substitutes.record(name, task, planned, vendor, skipped))
        if self.estimate:
            return vendor, None
        try:
            return vendor, parse_json_answer(answer)
        except ValueError as error:
            self.problem(step, task, vendor, "回答不是合格的 JSON：%s" % error, answer)
            return vendor, None

    def problem(self, step, task, vendor, problem, answer=None):
        item = {"step": STEP_NAMES[step], "task": task, "vendor": vendor, "problem": problem}
        if answer is not None:
            item["answer_start"] = answer[:300]
        with self.lock:
            self.invalid.append(item)

    def run_jobs(self, jobs):
        if self.workers <= 1 or len(jobs) <= 1:
            return [job() for job in jobs]
        pool = ThreadPoolExecutor(self.workers)
        futures = [pool.submit(job) for job in jobs]
        try:
            return [future.result() for future in futures]
        except BaseException:
            pool.shutdown(cancel_futures=True)
            raise
        finally:
            pool.shutdown()

    def save(self, name, data):
        write_json(os.path.join(self.out, "judgments", name + ".json"), data)


def report_material(report):
    return material("报告", report["text"])


def task_name(step, unit, slot):
    return "评审-%s：%s评委 %d" % (STEP_NAMES[step], unit + "，" if unit else "", slot)


# ---- 各步 --------------------------------------------------------------------

def step_claims_list(ctx):
    """按固定规则列出每份报告的主要结论清单（一位清单员），网址只认报告里真有的。"""
    (slot, planned), = ctx.slots("claims_list")
    jobs = []
    for report in ctx.reports:
        task = task_name("claims_list", "报告 %s" % report["label"], slot)
        prompt = render("claims-list", 截止时间=ctx.cutoff, 细则=ctx.rubric, 题目卡=ctx.card,
                        报告=report_material(report))
        jobs.append(lambda t=task, p=prompt: ctx.ask("claims_list", slot, planned, t, p,
                                                     models.MATERIALS_ONLY))
    claims, saved = {}, {}
    for report, (vendor, data) in zip(ctx.reports, ctx.run_jobs(jobs)):
        label, items = report["label"], []
        raw = (data or {}).get("claims", [])
        if not ctx.estimate and not isinstance(raw, list):
            raise ReviewError("报告 %s 的结论清单无效，评审无法继续" % label)
        for c in raw if isinstance(raw, list) else []:
            if not isinstance(c, dict) or not str(c.get("claim", "")).strip():
                continue
            urls = c.get("urls") or []
            urls = [urls] if isinstance(urls, str) else urls if isinstance(urls, list) else []
            given = [u for u in urls if isinstance(u, str) and u.strip()]
            local = "c%d" % (len(items) + 1)
            items.append({
                "id": "%s-%s" % (label, local), "local": local, "claim": str(c.get("claim", "")),
                "quote": str(c.get("quote", "")), "cited": str(c.get("cited", "")),
                "urls": [u.strip() for u in given if norm_url(u) in report["url_keys"]],
                "urls_not_in_report": [u for u in given if norm_url(u) not in report["url_keys"]],
                "core": bool(c.get("core"))})
        claims[label] = items
        saved[label] = {"vendor": vendor, "claims": items}
    ctx.save("claims-list", saved)
    return claims


def claim_material(ctx, claims, tools):
    blocks = []
    for c in claims:
        lines = ["[%s] 结论：%s" % (c["local"], c["claim"]), "原文：“%s”" % c["quote"],
                 "报告标的来源：%s" % (c["cited"] or "无")]
        if not c["urls"]:
            lines.append('没有网址：来源标签已经定为"没有出处"，只判定对错。')
        for url in c["urls"]:
            item = ctx.archived(url)
            if item:
                text = item["text"]
                kept = text[:ctx.config["source_chars"]]
                note = ("全文 %d 字" % len(text) if len(kept) == len(text)
                        else "全文 %d 字，这里只附前 %d 字" % (len(text), len(kept)))
                lines.append("网址：%s\n主办方存档：取回于 %s，最终网址 %s。存档的文字内容如下（%s）：\n<<<\n%s\n>>>"
                             % (url, item["fetched_at"], item["final_url"] or url, note, kept))
            else:
                problem = (ctx.archive.get(norm_url(url)) or {}).get("problem") or "没有存档"
                lines.append("网址：%s\n这个网址没有可用的存档（%s），请打开核对。" % (url, problem))
        blocks.append("\n".join(lines))
    title = "主要结论（只给材料）" if tools == models.MATERIALS_ONLY else "主要结论（要打开网址核对）"
    return material(title, "\n\n".join(blocks) if blocks else "（无）")


def verification_groups(ctx, report, claims):
    """分成两组：有存档或没有网址的只给材料；有网址却没有可用存档的只读网页。
    只估算时还没有结论清单，按报告里的网址估一个上限。"""
    if ctx.estimate:
        groups = {models.MATERIALS_ONLY: []}
        if any(not ctx.archived(url) for url in report["urls"]):
            groups[models.WEB_READ_ONLY] = []
        return groups
    groups = {}
    for c in claims:
        web = any(not ctx.archived(url) for url in c["urls"])
        groups.setdefault(models.WEB_READ_ONLY if web else models.MATERIALS_ONLY, []).append(c)
    return {g: groups[g] for g in (models.MATERIALS_ONLY, models.WEB_READ_ONLY) if g in groups}


def step_verify(ctx, claims):
    jobs, units = [], []
    for report in ctx.reports:
        label = report["label"]
        for tools, group in verification_groups(ctx, report, claims[label]).items():
            web = tools == models.WEB_READ_ONLY
            tool_note = ("本任务只允许检索网页和读网页：不能运行命令，不能读写文件。下面这几条结论所引的网页没有可用的存档，"
                         "请打开所引网址核对；打不开时，可以读第三方网页存档，例如 "
                         "https://archive.org/wayback/available?url=<网址>，只读，不提交任何表单。"
                         if web else
                         "本任务只用这些材料：不能上网，不能运行命令，不能读写文件。所引网页的内容，"
                         "用主办方的网页存档（运行后取回、按校验值保存的副本）。")
            prompt = render("verify", 工具=tool_note, 截止时间=ctx.cutoff, 细则=ctx.rubric,
                            题目卡=ctx.card, 结论=claim_material(ctx, group, tools))
            for slot, planned in ctx.slots("verify"):
                task = task_name("verify", "报告 %s，%s" % (label, tools), slot)
                units.append((label, tools, group, slot))
                jobs.append(lambda t=task, p=prompt, s=slot, v=planned, tl=tools:
                            ctx.ask("verify", s, v, t, p, tl))
    opinions = {c["id"]: [] for items in claims.values() for c in items}
    saved = []
    for (label, tools, group, slot), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        if data is None:
            continue
        by_local = {c["local"]: c for c in group}
        kept, seen = [], set()
        for item in data.get("claims", []) if isinstance(data.get("claims"), list) else []:
            c = by_local.get(str(item.get("id", ""))) if isinstance(item, dict) else None
            if c is None or c["id"] in seen:  # 同一位核验员对同一条结论只算一票
                continue
            seen.add(c["id"])
            opinion = {"slot": slot, "vendor": vendor, "tools": tools,
                       "source_label": item.get("source_label"), "source_note": item.get("source_note", ""),
                       "second_check": item.get("second_check", ""), "correct": item.get("correct"),
                       "correct_basis": item.get("correct_basis", "")}
            task = task_name("verify", "报告 %s，%s" % (label, tools), slot)
            if c["urls"]:
                if opinion["source_label"] not in SOURCE_LABELS:
                    ctx.problem("verify", task, vendor, "%s 的来源标签不认识：%r" % (c["id"], opinion["source_label"]))
                    opinion["source_label"] = None
                elif opinion["source_label"] == FABRICATED and not str(opinion["second_check"]).strip():
                    ctx.problem("verify", task, vendor, "%s 判为找不到，但没有写第二次核查，不算数" % c["id"])
                    opinion["source_label"] = None
            else:
                opinion["source_label"] = None
            if opinion["correct"] not in CORRECT:
                if opinion["correct"] is not None:
                    ctx.problem("verify", task, vendor, "%s 的对错标签不认识：%r" % (c["id"], opinion["correct"]))
                opinion["correct"] = None
            opinions[c["id"]].append(opinion)
            kept.append(dict(opinion, id=c["id"]))
        saved.append({"report": label, "slot": slot, "vendor": vendor, "tools": tools, "claims": kept})
    ctx.save("verify", {"opinions": saved})
    verified = {}
    for label, items in claims.items():
        verified[label] = []
        for c in items:
            ops = opinions[c["id"]]
            sources = [o["source_label"] for o in ops if o["source_label"]]
            corrects = [o["correct"] for o in ops if o["correct"]]
            entry = dict(c)
            del entry["local"]
            if not c["urls"]:
                entry["source_label"] = NO_SOURCE
            else:
                entry["source_label"] = least_harmful(sources, SOURCE_LABELS) if sources else NO_SOURCE
            entry["correct"] = plurality(corrects, CORRECT, UNDECIDED)
            chosen_source = next((o for o in ops if o["source_label"] == entry["source_label"]), {})
            chosen_correct = next((o for o in ops if o["correct"] == entry["correct"]), {})
            entry["source_note"] = chosen_source.get("source_note", "") or (
                "" if c["urls"] else "没有网址，按没有出处处理")
            entry["second_check"] = chosen_source.get("second_check", "")
            entry["correct_basis"] = chosen_correct.get("correct_basis", "")
            entry["tools"] = sorted({o["tools"] for o in ops})
            entry["archived_urls"] = [u for u in c["urls"] if ctx.archived(u)]
            entry["votes"] = {"source_label": dict(Counter(sources)), "correct": dict(Counter(corrects))}
            if not ctx.estimate and (not corrects or (c["urls"] and not sources)):
                ctx.notes["unverified_claims"].append(c["id"])
            verified[label].append(entry)
    return verified


def step_extract(ctx):
    jobs, units = [], []
    for report in ctx.reports:
        prompt = render("extract", 细则=ctx.rubric, 题目卡=ctx.card, 报告=report_material(report))
        for slot, planned in ctx.slots("extract"):
            task = task_name("extract", "报告 %s" % report["label"], slot)
            units.append((report["label"], slot))
            jobs.append(lambda t=task, p=prompt, s=slot, v=planned:
                        ctx.ask("extract", s, v, t, p, models.MATERIALS_ONLY))
    points = []
    for (label, slot), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        raw = (data or {}).get("points", [])
        n = 0
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict) or not str(item.get("content", "")).strip():
                continue
            n += 1
            level = item.get("level") if item.get("level") in LEVELS else ""
            points.append({"id": "%s-%d:%s-%d" % (vendor, slot, label, n), "report": label, "slot": slot,
                           "vendor": vendor, "content": str(item["content"]), "level": level,
                           "quote": str(item.get("quote", ""))})
    ctx.save("extract", {"points": points})
    return points


def source_hints(ctx, text, entry_ids):
    """要点文字里透露出处的地方：报告代号（"报告 A"，两个字以上的代号单独出现也算）、条目编号
    （例如 claude-1:A-3、A-c2）、产品名（取自名称表）。两种产品名不算，它们是题目本身的内容，提到它们
    透露不了要点出自哪份报告：题目卡或深度地图要点里本来就有的；两份以上报告的原文里都提到的
    （例如题目就是比较这几家产品）。"""
    found = []
    given = (ctx.question["card"] + "\n" + "\n".join(m["content"] for m in ctx.question["map_points"])).lower()
    for report in ctx.reports:
        label, name = report["label"], report["name"]
        code = r"报告\s*%s(?![A-Za-z0-9])" % re.escape(label)
        if len(label) >= 2:
            code += r"|(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(label)
        if re.search(code, text):
            found.append("报告代号 %s" % label)
        if not name or name == label or name.lower() not in text.lower() or name.lower() in given:
            continue
        if sum(name.lower() in r["text"].lower() for r in ctx.reports) < 2:
            found.append("产品名 %s" % name)
    found += ["条目编号 %s" % i for i in sorted(entry_ids) if i in text]
    return found


def step_merge(ctx, points, verified):
    """一位评委把地图要点、抽取的要点和主要结论合并成要点池；写到哪份报告由来源推出。"""
    (slot, planned), = ctx.slots("merge")
    map_points = ctx.question["map_points"]
    owner = {p["id"]: p["report"] for p in points}
    owner.update({c["id"]: label for label, items in verified.items() for c in items})
    known = set(owner) | {m["id"] for m in map_points}
    map_lines = ["[%s] %s（地图登记：层级 %s，重要性 %s）" % (m["id"], m["content"], m["level"], m["importance"])
                 for m in map_points]
    point_lines = ["[%s] %s（抽取时所标层级：%s）原文：“%s”" % (p["id"], p["content"], p["level"] or "未标", p["quote"])
                   for p in points]
    claim_lines = ["[%s] %s（核验：%s；来源标签：%s）" % (c["id"], c["claim"], c["correct"], c["source_label"])
                   for items in verified.values() for c in items]
    prompt = render("merge", 截止时间=ctx.cutoff, 细则=ctx.rubric, 题目卡=ctx.card,
                    地图=material("深度地图要点", "\n".join(map_lines)),
                    抽取要点=material("评委抽取的要点", "\n".join(point_lines) or "（无）"),
                    主要结论=material("主要结论", "\n".join(claim_lines) or "（无）"))
    task = task_name("merge", "", slot)
    vendor, data = ctx.ask("merge", slot, planned, task, prompt, models.MATERIALS_ONLY)
    raw = (data or {}).get("points", [])
    if not ctx.estimate and (data is None or not isinstance(raw, list)):
        raise ReviewError("要点池合并的回答无效，评审无法继续")
    if not ctx.estimate:
        # 合并时隐去出处：要点文字里出现报告代号、条目编号或产品名，这次合并判为回答无效
        leaks = []
        for item in raw:
            content = str(item.get("content", "")) if isinstance(item, dict) else ""
            hints = source_hints(ctx, content, owner)
            if hints:
                leaks.append("「%s」（%s）" % (content, "、".join(hints)))
        if leaks:
            ctx.problem("merge", task, vendor, "合并后的要点文字里出现了报告代号、条目编号或产品名，透露了出处：%s"
                        % "；".join(leaks))
            raise ReviewError("要点池合并的回答无效：要点文字里透露了出处（见 invalid_answers），评审无法继续")
    pool, used = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not str(item.get("content", "")).strip():
            continue
        sources = [s for s in item.get("sources") or [] if isinstance(s, str)]
        unknown = [s for s in sources if s not in known]
        if unknown:
            ctx.notes["unknown_sources"].extend(unknown)
        sources = [s for s in sources if s in known]
        if not sources:
            continue
        opposite = {s for s in item.get("opposite") or [] if s in sources}
        pool.append({"content": str(item["content"]), "sources": sources, "opposite": opposite})
        used.update(sources)
    for m in map_points:
        if m["id"] not in used:
            pool.append({"content": m["content"], "sources": [m["id"]], "opposite": set()})
            ctx.notes["map_points_added"].append(m["id"])
    ctx.notes["not_merged"] = sorted(set(owner) - used) if not ctx.estimate else []
    map_by_id = {m["id"]: m for m in map_points}
    for i, p in enumerate(pool, 1):
        p["pid"] = "Q%d" % i
        from_map = next((s for s in p["sources"] if s in map_by_id), None)
        if len([s for s in p["sources"] if s in map_by_id]) > 1:
            ctx.notes["map_points_merged_together"].append(
                {"pid": p["pid"], "map_points": [s for s in p["sources"] if s in map_by_id],
                 "default_from": from_map})
        p["from_map"] = from_map
        p["map_default"] = ({"level": map_by_id[from_map]["level"],
                             "importance": map_by_id[from_map]["importance"]} if from_map else None)
        reach = {}
        for s in p["sources"]:
            if s in owner:
                reach.setdefault(owner[s], []).append("相反" if s in p["opposite"] else "符合")
        p["reach"] = {label: ("符合" if "符合" in marks else "相反") for label, marks in reach.items()}
        p["reach_from"] = {label: "合并" for label in p["reach"]}
        p["opposite"] = sorted(p["opposite"])
    ctx.save("merge", {"vendor": vendor, "answer": data})
    return pool


def step_reach(ctx, pool):
    """逐份报告核对它还写到了池中哪些要点（合并时没有从它那里来的要点）。"""
    jobs, units = [], []
    for report in ctx.reports:
        label = report["label"]
        todo = [p for p in pool if label not in p["reach"]]
        if not todo and not ctx.estimate:
            continue
        lines = ["[%s] %s" % (p["pid"], p["content"]) for p in todo]
        prompt = render("reach", 题目卡=ctx.card, 要点=material("要点池中的要点", "\n".join(lines) or "（无）"),
                        报告=report_material(report))
        for slot, planned in ctx.slots("reach"):
            task = task_name("reach", "报告 %s" % label, slot)
            units.append((label, {p["pid"] for p in todo}, slot))
            jobs.append(lambda t=task, p=prompt, s=slot, v=planned:
                        ctx.ask("reach", s, v, t, p, models.MATERIALS_ONLY))
    votes, saved = {}, []
    for (label, asked, slot), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        if data is None:
            continue
        marks = {}
        for item in data.get("written", []) if isinstance(data.get("written"), list) else []:
            if (isinstance(item, dict) and isinstance(item.get("pid"), str) and item["pid"] in asked
                    and item.get("reach") in REACH):
                marks[item["pid"]] = item["reach"]
        for pid in asked:
            votes.setdefault((pid, label), []).append(marks.get(pid, NOT_WRITTEN))
        saved.append({"report": label, "slot": slot, "vendor": vendor, "written": marks})
    by_pid = {p["pid"]: p for p in pool}
    for (pid, label), marks in votes.items():
        decision = plurality(marks, REACH + [NOT_WRITTEN], NOT_WRITTEN)
        if decision != NOT_WRITTEN:
            by_pid[pid]["reach"][label] = decision
            by_pid[pid]["reach_from"][label] = "写到核对"
            ctx.notes["reach_added"] += 1
    ctx.save("reach", {"checks": saved})


def step_judge(ctx, pool):
    """多位评委逐条判定池中要点。提示词里只有要点编号和内容（地图要点另附登记值），不写出处。"""
    jobs, orders = [], []
    for slot, planned in ctx.slots("judge"):
        order = pool[:]
        random.Random(ctx.seed * 1000 + slot).shuffle(order)
        lines = []
        for p in order:
            line = "[%s] %s" % (p["pid"], p["content"])
            if p["map_default"]:
                line += "（地图登记：层级 %s，重要性 %s）" % (p["map_default"]["level"], p["map_default"]["importance"])
            lines.append(line)
        prompt = render("judge", 截止时间=ctx.cutoff, 细则=ctx.rubric, 题目卡=ctx.card,
                        要点=material("要点池", "\n".join(lines) or "（无）"))
        orders.append((slot, [p["pid"] for p in order]))
        jobs.append(lambda t=task_name("judge", "", slot), p=prompt, s=slot, v=planned:
                    ctx.ask("judge", s, v, t, p, models.MATERIALS_ONLY))
    opinions = {p["pid"]: [] for p in pool}
    saved = []
    for (slot, order), (vendor, data) in zip(orders, ctx.run_jobs(jobs)):
        if data is None:
            continue
        kept, seen = [], set()
        for item in data.get("points", []) if isinstance(data.get("points"), list) else []:
            if (not isinstance(item, dict) or not isinstance(item.get("pid"), str)
                    or item["pid"] not in opinions or item["pid"] in seen):  # 同一位评委对同一条只算一票
                continue
            seen.add(item["pid"])
            opinion = {"slot": slot, "vendor": vendor, "pid": item["pid"],
                       "correct": item.get("correct") if item.get("correct") in CORRECT else None,
                       "basis": str(item.get("basis", "")),
                       "relevant": item.get("relevant") if isinstance(item.get("relevant"), bool) else None,
                       "level": item.get("level") if item.get("level") in LEVELS else None,
                       "importance": item.get("importance") if item.get("importance") in IMPORTANCE else None,
                       "change_reason": str(item.get("change_reason") or "").strip()}
            opinions[item["pid"]].append(opinion)
            kept.append(opinion)
        saved.append({"slot": slot, "vendor": vendor, "order": order, "points": kept})
    ctx.save("judge", {"opinions": saved})
    for p in pool:
        ops, default = opinions[p["pid"]], p["map_default"]
        corrects = [o["correct"] for o in ops if o["correct"]]
        p["correct"] = plurality(corrects, CORRECT, UNDECIDED)
        p["basis"] = next((o["basis"] for o in ops if o["correct"] == p["correct"]), "")
        relevant = [o["relevant"] for o in ops if o["relevant"] is not None]
        p["relevant"] = plurality(relevant, [True, False], True)
        votes, reasons = {}, []
        for key, order in (("level", LEVELS), ("importance", IMPORTANCE)):
            given = []
            for o in ops:
                if o[key] is None:
                    continue
                if default and o[key] != default[key] and not o["change_reason"]:
                    ctx.notes["ignored_map_changes"] += 1
                    given.append(default[key])  # 不写理由的改动不算数，按默认值计
                else:
                    given.append(o[key])
                    if default and o[key] != default[key]:
                        reasons.append({"slot": o["slot"], "vendor": o["vendor"], key: o[key],
                                        "reason": o["change_reason"]})
            votes[key] = dict(Counter(given))
            if given:
                p[key], disputed = two_thirds(given, order, default[key] if default else None)
            else:
                p[key], disputed = (default[key] if default else order[0]), False
            p.setdefault("disputed_on", [])
            if disputed:
                p["disputed_on"].append(key)
        p["disputed"] = bool(p["disputed_on"])
        p["votes"] = {"correct": dict(Counter(corrects)),
                      "relevant": {str(k).lower(): v for k, v in Counter(relevant).items()}, **votes}
        p["map_changes"] = reasons
        p["audit"] = not p["from_map"] and "核心" in candidates(p["importance"])
        if not ops and not ctx.estimate:
            ctx.notes["unjudged_points"].append(p["pid"])


def step_rating(ctx):
    jobs, units = [], []
    for report in ctx.reports:
        prompt = render("rating", 截止时间=ctx.cutoff, 细则=ctx.rubric, 题目卡=ctx.card,
                        报告=report_material(report))
        for slot, planned in ctx.slots("rating"):
            task = task_name("rating", "报告 %s" % report["label"], slot)
            units.append((report, slot, task))
            jobs.append(lambda t=task, p=prompt, s=slot, v=planned:
                        ctx.ask("rating", s, v, t, p, models.MATERIALS_ONLY))
    files = {slot: {"judge": "评委 %d" % slot, "reports": {}} for slot, _ in ctx.slots("rating")}
    for (report, slot, task), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        if data is None:
            continue
        rating = valid_rating(data)
        if rating is None:
            ctx.problem("rating", task, vendor, "环节评级缺项或档位不在 0、1、2 之中，这一次不计")
            continue
        for element in ELEMENTS:
            item = rating["ratings"][element]
            item["evidence_in_report"] = quote_in_report(str(item.get("evidence", "")), report["text"])
            if not item["evidence_in_report"]:
                ctx.notes["evidence_not_found"].append({"report": report["label"], "slot": slot,
                                                        "vendor": vendor, "element": element})
        rating["vendor"] = vendor
        files[slot]["reports"][report["label"]] = rating
    if not ctx.estimate:
        for report in ctx.reports:
            if not any(report["label"] in f["reports"] for f in files.values()):
                raise ReviewError("报告 %s 没有一次有效的环节评级，评审无法继续" % report["label"])
    return files


def valid_rating(data):
    ratings = data.get("ratings")
    if not isinstance(ratings, dict):
        return None
    for element in ELEMENTS:
        item = ratings.get(element)
        if not isinstance(item, dict) or item.get("score") not in (0, 1, 2) or isinstance(item.get("score"), bool):
            return None
    timeliness, off_topic, traceable = (data.get("timeliness"), data.get("off_topic"),
                                        data.get("traceable_sources"))
    if (not isinstance(timeliness, dict) or timeliness.get("score") not in (0, 1, 2)
            or isinstance(timeliness.get("score"), bool)):
        return None
    for flag in (off_topic, traceable):
        if not isinstance(flag, dict) or not isinstance(flag.get("value"), bool):
            return None
    return {"ratings": {e: dict(ratings[e]) for e in ELEMENTS}, "timeliness": timeliness,
            "off_topic": off_topic, "traceable_sources": traceable}


def step_pairwise(ctx):
    """每一对报告、每位评委，两种先后各比一次。哪种先后算"第一种"由随机种子定。"""
    rng = random.Random(ctx.seed)
    by_label = {r["label"]: r for r in ctx.reports}
    orders = []
    for x, y in combinations([r["label"] for r in ctx.reports], 2):
        orders.append((x, y) if rng.random() < 0.5 else (y, x))
    jobs, units = [], []
    for slot, planned in ctx.slots("pairwise"):
        for direction in ("fwd", "rev"):
            for x, y in orders:
                first, second = (x, y) if direction == "fwd" else (y, x)
                prompt = render("pairwise", 细则=ctx.rubric, 题目卡=ctx.card,
                                第一份=material("第一份报告", by_label[first]["text"]),
                                第二份=material("第二份报告", by_label[second]["text"]))
                task = task_name("pairwise", "%s 在前，%s 在后" % (first, second), slot)
                units.append((slot, direction, first, second, task))
                jobs.append(lambda t=task, p=prompt, s=slot, v=planned:
                            ctx.ask("pairwise", s, v, t, p, models.MATERIALS_ONLY))
    files = {}
    for (slot, direction, first, second, task), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        entry = files.setdefault((slot, direction), {"judge": "评委 %d" % slot, "order": direction, "pairs": []})
        if data is None:
            continue
        if data.get("verdict") not in VERDICTS:
            ctx.problem("pairwise", task, vendor, "verdict 只能是 first、second 或 tie：%r" % data.get("verdict"))
            continue
        entry["pairs"].append({"first": first, "second": second, "verdict": data["verdict"],
                               "reason": str(data.get("reason", "")), "vendor": vendor})
    return files


def step_direct(ctx, verified):
    jobs, units = [], []
    for report in ctx.reports:
        label = report["label"]
        items = verified[label]
        if not items and not ctx.estimate:
            continue
        lines = ["[c%d] %s" % (i, c["claim"]) for i, c in enumerate(items, 1)]
        prompt = render("direct", 题目卡=ctx.card, 结论=material("主要结论清单", "\n".join(lines) or "（无）"))
        for slot, planned in ctx.slots("direct"):
            task = task_name("direct", "报告 %s" % label, slot)
            units.append((label, slot, task))
            jobs.append(lambda t=task, p=prompt, s=slot, v=planned:
                        ctx.ask("direct", s, v, t, p, models.MATERIALS_ONLY))
    votes, reasons, saved = {}, {}, []
    for (label, slot, task), (vendor, data) in zip(units, ctx.run_jobs(jobs)):
        if data is None:
            continue
        local = {"c%d" % i: c["id"] for i, c in enumerate(verified[label], 1)}
        ids = [local[i] for i in data.get("ids", []) if isinstance(i, str) and i in local] \
            if isinstance(data.get("ids"), list) else []
        ids = list(dict.fromkeys(ids))
        if not 1 <= len(ids) <= 3:
            ctx.problem("direct", task, vendor, "直接回答要挑 1 至 3 条，这次挑了 %d 条，不计" % len(ids))
            continue
        votes.setdefault(label, []).append(ids)
        reasons.setdefault(label, str(data.get("reason", "")))
        saved.append({"report": label, "slot": slot, "vendor": vendor, "ids": ids,
                      "reason": str(data.get("reason", ""))})
    ctx.save("direct", {"opinions": saved})
    direct = {}
    for report in ctx.reports:
        label = report["label"]
        runs = votes.get(label, [])
        counts = Counter(i for ids in runs for i in ids)
        order = [c["id"] for c in verified[label]]
        chosen = [i for i in order if counts[i] * 2 > len(runs)]
        if runs and not chosen:
            top = max(counts.values())
            chosen = [i for i in order if counts[i] == top][:3]
        direct[label] = {"ids": chosen[:3], "reason": reasons.get(label, ""), "votes": dict(counts),
                         "runs": len(runs)}
    return direct


# ---- 写出数据目录、调用计分程序 ----------------------------------------------

def write_data(ctx, verified, pool, ratings, pairwise, direct):
    data = os.path.join(ctx.out, "data")
    os.makedirs(data, exist_ok=True)
    reports = {}
    for report in ctx.reports:
        label = report["label"]
        given = [f["reports"][label] for f in ratings.values() if label in f["reports"]]
        traceable_votes = [g["traceable_sources"]["value"] for g in given]
        traceable = plurality(traceable_votes, [True, False], True) or any(
            c["source_label"] in FOUND_LABELS for c in verified[label])
        reports[label] = {
            "claims": verified[label],
            "timeliness": {"score": whole(median(g["timeliness"]["score"] for g in given)),
                           "reason": "环节评级各次的时效档位取中位数：%s"
                                     % "、".join(str(g["timeliness"]["score"]) for g in given)},
            "traceable_sources": traceable,
            "notes": "可追溯来源：环节评级各次 %s；有来源标签为支持、部分支持、不支持或失效但有存档的结论时直接算有"
                     % "、".join("有" if v else "没有" for v in traceable_votes)}
    write_json(os.path.join(data, "verify-majority.json"),
               {"verifier": "多位核验员，标签取多数", "reports": reports})
    for slot, content in ratings.items():
        write_json(os.path.join(data, "rating-%d.json" % slot), content)
    for (slot, direction), content in pairwise.items():
        write_json(os.path.join(data, "pairwise-%d-%s.json" % (slot, direction)), content)
    write_json(os.path.join(data, "pool.json"), {"points": [
        {key: p[key] for key in ("pid", "content", "sources", "opposite", "from_map", "map_default",
                                 "correct", "basis", "relevant", "level", "importance", "disputed",
                                 "disputed_on", "votes", "map_changes", "audit", "reach", "reach_from")}
        for p in pool]})
    write_json(os.path.join(data, "direct-answers.json"), direct)
    return data


def run_scorer(scorer, mapping, data, results, timeout=SCORER_TIMEOUT):
    """调用计分程序；超过 timeout 秒没有结束就停掉它，记为超时（timed_out 为是，退出状态为空）。"""
    command = [sys.executable, "-I", scorer, mapping, SCORER_VERSION, "--data", data, "--output", results]
    meta = {"program": os.path.relpath(scorer, ROOT), "version": SCORER_VERSION,
            "command": [os.path.basename(sys.executable), "-I"] + [
                os.path.relpath(a, ROOT) if os.path.isabs(a) else a for a in command[2:]],
            "timeout_seconds": timeout, "timed_out": False}
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired as expired:
        stderr = expired.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return dict(meta, exit_code=None, timed_out=True, stderr=stderr[-4000:])
    return dict(meta, exit_code=done.returncode, stderr=done.stderr[-4000:])


# ---- 一次运行 ----------------------------------------------------------------

def summarize_steps(ctx):
    steps = {}
    for key, name in STEPS:
        used = ctx.usage[name]
        model_seen = {}
        for u in used:
            model = u.get("reported_model") or u.get("model") or "命令行默认模型"
            model_seen.setdefault(u["vendor"], set()).add(model)
        steps[name] = {
            "planned": [{"slot": s, "vendor": v} for s, v in ctx.slots(key)],
            "calls": len(used),
            "by_vendor": dict(sorted(Counter(u["vendor"] for u in used).items())),
            "models": {v: sorted(m) for v, m in sorted(model_seen.items())},
        }
    return steps


def too_few_vendors(ctx):
    """计划用三家以上的步骤，替代之后实际用到的厂商不足三家的：记下来，不中止运行。
    只算拿到回答的调用（只估算时是未调用的记录）；一次也没有调用的步骤不算。"""
    found = []
    for key, name in STEPS:
        planned = list(dict.fromkeys(ctx.config["steps"][key]["vendors"]))
        if len(planned) < MIN_VENDORS:
            continue
        used = sorted({u["vendor"] for u in ctx.usage[name]
                       if u["status"] in (models.SUCCEEDED, models.NOT_CALLED)}, key=models.VENDORS.index)
        if used and len(used) < MIN_VENDORS:
            found.append({"step": name, "planned_vendors": planned, "used_vendors": used,
                          "rule": THREE_VENDORS_RULE})
    return found


def execute(args, config, question, reports, archive, manifests, mode, out, rubric):
    """跑一遍全部步骤；返回运行元数据（同时写进 out/run.json）。"""
    os.makedirs(out, exist_ok=True)
    run = models.ModelRun(os.path.join(out, "calls.jsonl"), mode=mode, max_calls=args.max_calls,
                          replay_from=args.replay if mode == models.REPLAY else None,
                          run_id=args.run_id)
    ctx = Context(run, config, question, reports, archive, out, rubric)
    meta = {
        "run_id": run.run_id, "mode": mode, "started_at": now(), "finished_at": None,
        "status": None, "error": None,
        "question": {"dir": shown(question["dir"]), "kind": question["kind"],
                     "cutoff": question["cutoff"], "card_sha256": question["card_sha256"],
                     "depth_map_sha256": question["depth_map_sha256"],
                     "checksum_matches": question["checksum_matches"],
                     "map_points": [m["id"] for m in question["map_points"]]},
        "reports": [{"label": r["label"], "name": r["name"], "file": shown(r["path"]), "sha256": r["sha256"],
                     "characters": len(r["text"]), "urls": len(r["urls"]),
                     "copy": "reports/%s%s" % (r["label"], r["ext"])} for r in reports],
        "archive": {"dir": shown(args.archive) if args.archive else None,
                    "manifests": [shown(m) for m in manifests],
                    "usable_urls": sum(1 for a in archive.values() if a["text"] is not None)},
        "config": config,
    }
    os.makedirs(os.path.join(out, "reports"), exist_ok=True)
    for r in reports:  # 匿名化：副本只用编号命名，原名只在 mapping.json 里
        common.write_text_atomic(os.path.join(out, "reports", r["label"] + r["ext"]), r["text"])
    write_json(os.path.join(out, "mapping.json"), {
        "reports": {r["label"]: r["name"] for r in reports},
        "files": {r["label"]: shown(r["path"]) for r in reports}})
    pool = []
    try:
        claims = step_claims_list(ctx)
        verified = step_verify(ctx, claims)
        points = step_extract(ctx)
        pool = step_merge(ctx, points, verified)
        step_reach(ctx, pool)
        step_judge(ctx, pool)
        ratings = step_rating(ctx)
        pairwise = step_pairwise(ctx)
        direct = step_direct(ctx, verified)
        if mode != models.ESTIMATE:
            data = write_data(ctx, verified, pool, ratings, pairwise, direct)
            results = os.path.join(out, RESULTS_NAME)
            meta["scorer"] = run_scorer(args.scorer, os.path.join(out, "mapping.json"), data, results,
                                        args.scorer_timeout)
            if meta["scorer"]["timed_out"]:
                raise ReviewError("计分程序超过 %g 秒没有结束，已停止" % args.scorer_timeout)
            if meta["scorer"]["exit_code"] != 0:
                raise ReviewError("计分程序出错（退出状态 %d）" % meta["scorer"]["exit_code"])
        meta["status"] = "完成"
    except (ReviewError, models.CallLimitExceeded, models.ReplayMissing) as error:
        meta["status"] = "中止"
        meta["error"] = str(error)
    finally:
        summary = run.summary()
        meta["finished_at"] = now()
        meta["calls"] = {"calls": summary["calls"], "by_vendor": summary["by_vendor"],
                         "by_step": {name: len(ctx.usage[name]) for _, name in STEPS},
                         "max_calls": summary["max_calls"], "over_limit": summary["over_limit"]}
        meta["steps"] = summarize_steps(ctx)
        meta["too_few_vendors"] = too_few_vendors(ctx)
        meta["unavailable"] = list(ctx.unavailable.values())
        meta["substitutions"] = sorted(ctx.substitutions, key=lambda s: (s["步骤"], s["任务"]))
        meta["invalid_answers"] = ctx.invalid
        meta["disputed_points"] = [p["pid"] for p in pool if p.get("disputed")]
        meta["audit_points"] = [p["pid"] for p in pool if p.get("audit")]
        meta["notes"] = ctx.notes
        meta["outputs"] = {"calls": "calls.jsonl", "mapping": "mapping.json", "reports": "reports",
                           "judgments": "judgments"}
        if mode != models.ESTIMATE and meta["status"] == "完成":
            meta["outputs"].update({"data": "data", "results": RESULTS_NAME})
        write_json(os.path.join(out, "run.json"), meta)
    return meta


def parse_args(argv):
    ap = argparse.ArgumentParser(description="模拟评审：几家模型按评审细则第 1.2 版评审一道题的一组报告，"
                                             "结果交给计分程序第 1.2 版。用法见 tools/simulate_review.md。")
    ap.add_argument("--question", required=True, help="题目目录，至少有 question-card.md 和 depth-map.md")
    ap.add_argument("--reports", nargs="+", required=True, help="报告文件（Markdown 或网页）")
    ap.add_argument("--names", help="名称表 JSON：{文件名（不带扩展名）: 产品或队伍名}，也接受试评 mapping.json 的写法")
    ap.add_argument("--keep-labels", action="store_true",
                    help="报告已经匿名，用文件名作编号；不加时按随机种子打乱后编为 A、B、C……")
    ap.add_argument("--archive", help="网页存档目录：其中（或各子目录中）的 manifest.json 由 tools/archive_sources.py 写出")
    ap.add_argument("--config", help="配置 JSON：各步用哪几家、每家几次，见说明")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--estimate", action="store_true", help="只估算：不调用任何模型，报出将要发起的调用次数")
    mode.add_argument("--replay", nargs="+", help="回放：从这些调用记录文件里取回答，不调用模型")
    ap.add_argument("--max-calls", type=int, help="真实调用的次数上限，真实调用时必须给")
    ap.add_argument("--run-id", help="运行标识，默认用开始时间，例如 20261030-153000")
    ap.add_argument("--out", help="输出目录，默认 simulation/reviews/<运行标识>")
    ap.add_argument("--cutoff", help="截止日期，例如 2026-03-03；默认从题目卡的截止时间一行读出")
    ap.add_argument("--workers", type=int, help="同时进行的调用数，默认按配置（4）")
    ap.add_argument("--seed", type=int, help="随机种子（报告编号、两两比较的先后、要点判定的排列），默认按配置（0）")
    ap.add_argument("--rubric", default=RUBRIC, help=argparse.SUPPRESS)
    ap.add_argument("--scorer", default=SCORER, help=argparse.SUPPRESS)
    ap.add_argument("--scorer-timeout", type=float, default=SCORER_TIMEOUT, help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def describe(meta):
    calls = meta["calls"]
    vendors = "，".join("%s %d" % (v, n) for v, n in sorted(calls["by_vendor"].items()))
    steps = "，".join("%s %d" % (name, n) for name, n in calls["by_step"].items())
    lines = ["模拟评审 %s（%s）：%s" % (meta["run_id"], meta["mode"], meta["status"]),
             "调用次数：%d（%s）" % (calls["calls"], vendors or "无"), "各步：%s" % steps]
    if calls["max_calls"] is not None:
        lines.append("调用次数上限：%d%s" % (calls["max_calls"], "，会超过上限" if calls["over_limit"] else ""))
    for item in meta["unavailable"]:
        lines.append("不可用：%s（%s），原因：%s" % (item["vendor"], item["company"], item["error"]))
    if meta["substitutions"]:
        lines.append("替代：%d 次调用换了厂商，见 run.json 的 substitutions" % len(meta["substitutions"]))
    for item in meta["too_few_vendors"]:
        lines.append("不合规则：%s计划用 %s，实际只用了 %s，不合%s" % (
            item["step"], "、".join(item["planned_vendors"]), "、".join(item["used_vendors"]), item["rule"]))
    if meta["error"]:
        lines.append("中止原因：%s" % meta["error"])
    return "\n".join(lines)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
        if args.workers is not None:
            config["workers"] = args.workers
        if args.seed is not None:
            config["seed"] = args.seed
        mode = models.ESTIMATE if args.estimate else models.REPLAY if args.replay else models.LIVE
        if mode == models.LIVE and not (args.max_calls and args.max_calls > 0):
            raise UsageError("真实调用必须用 --max-calls 给出调用次数上限；只想先看次数，用 --estimate")
        question = load_question(args.question, args.cutoff)
        if not question["cutoff"]:
            print("提醒：题目卡的截止时间一行没有具体日期（例如〔运行当日〕），提示词里只能写「以题目卡为准」。"
                  "请用 --cutoff 给出智能体的运行日期。", file=sys.stderr)
        reports = load_reports(args.reports, args.names, args.keep_labels, config["seed"])
        if len(reports) < 2:
            raise UsageError("至少要两份报告")
        archive, manifests = load_archive(args.archive)
        rubric = read_text(args.rubric)
        args.run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        out = os.path.abspath(args.out or os.path.join(REVIEWS, args.run_id))
        if os.path.exists(out) and os.listdir(out):
            raise UsageError("输出目录已经有内容，不覆盖：%s" % out)
        estimate = None
        if mode == models.LIVE:
            with tempfile.TemporaryDirectory() as scratch:
                estimate = execute(args, config, question, reports, archive, manifests, models.ESTIMATE,
                                   scratch, rubric)["calls"]
            if estimate["calls"] > args.max_calls:
                raise UsageError("估算要发起 %d 次调用，超过上限 %d 次，没有开始。先用 --estimate 看各步的次数"
                                 % (estimate["calls"], args.max_calls))
    except UsageError as error:
        print("模拟评审没有开始：%s" % error, file=sys.stderr)
        return 2
    meta = execute(args, config, question, reports, archive, manifests, mode, out, rubric)
    if estimate is not None:
        meta["estimate"] = estimate
        write_json(os.path.join(out, "run.json"), meta)
    print(describe(meta))
    print("输出目录：%s" % out)
    if meta["status"] == "完成" and mode != models.ESTIMATE:
        results = read_json(os.path.join(out, RESULTS_NAME))
        for item in results["reports"]:
            print("报告 %s：第 %d 至 %d 名" % (item["label"], item["rank_best"], item["rank_worst"]))
    return 0 if meta["status"] == "完成" else 1


if __name__ == "__main__":
    sys.exit(main())
