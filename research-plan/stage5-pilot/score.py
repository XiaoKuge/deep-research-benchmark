"""第五阶段小规模检验：按《评审细则》和第四阶段方案第六、七节计算名次区间，并检查验收标准。

用法：python3 -I score.py <映射表路径> [1.0|1.1|1.2] [--data 目录] [--output 结果文件]
映射表记录匿名标签对应的产品，评委看不到它；只在最后报告时使用。
所有数字只由本程序从 out/（或 --data 指定的目录）下的评委输出生成，不手工修改。
结果默认写到本目录下的 results-v<版本>.json。

三个版本：
- 1.0：第一版。
- 1.1：硬伤只看对题目的直接回答（direct-answers.json）；两两比较不能否决由核验确认的硬伤。
- 1.2：在 1.1 之上加评审细则第四节末尾的两条：有争议的标注按对领先一方最不利的方式计分；
  重抽样只在至少一份参与排名的报告写到的要点中进行。另按规则手册第八节第 3、4 条：深度净分分不开时只比
  五个环节的评级，第 1.0、1.1 版把时效（②）也算在内；两两比较中与前面结果相反的次数至少占四分之三
  （向上取整：四次至少三次，两次就要两次）才改为并列，第 1.0、1.1 版要每次都相反。
  分开的标准和名次区间的算法不变。

有争议的标注写在要点池（pool.json）里：要点的 level 或 importance 写成候选列表，第一项是登记的标注，
例如 "importance": ["一般", "核心"]。第 1.0、1.1 版只用第一项；净分（net、net_scores）也按第一项计。

第 1.2 版的结果文件保留第 1.1 版的全部字段（main、acceptance、separated、vetoed、version），另加供页面读取的：
- reports：每份报告一项，按映射表的顺序。label 匿名标签，product 产品，rank_best 和 rank_worst 名次区间的
  两端，net_scores 三种权重下的深度净分，severe_problems 严重问题（即硬伤）名称列表，element_grades
  五个环节（①③④⑤⑦）的档位，timeliness 时效（②）的档位（第 1.2 版不进入名次），writing 写作档位（不进入名次）。
- separated_pairs：分开的对，每对一项。higher 在前的报告，lower 在后的报告，basis 分开依据（硬伤分档、
  深度净分或环节评级）；依据是深度净分时，bootstrap_share 是三种权重下领先一方在重抽样中领先的比例，
  disputed_labels 是两份报告写到的有争议的要点在每种权重下所用的标注；其余依据下两者为 null 和 {}。
- vetoed_pairs：被两两比较否决、改为并列的对（higher、lower）。
- element_names：环节编号对应的名称。
- resampling：rounds 重抽样次数，seed 随机种子，separation_share 分开所需的比例，pool_points 要点池条数，
  resampled_points 参与重抽样的条数，disputed_points 有争议的要点编号。
标准 2 至 8 只在映射表列出扰动版本（perturb）时计算，例如第五阶段试评数据。
"""
import argparse
import json
import os
import random
import sys
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ELEMENTS = ["①", "③", "④", "⑤", "⑦"]
ELEMENT_NAMES = {"①": "切题与真实需要", "②": "时效", "③": "查找过程的交代", "④": "甄别来源与处理矛盾",
                 "⑤": "分析", "⑦": "结论与把握"}

# 第四阶段方案第六节：三种预先声明的层级权重
LEVEL_W = {
    "甲": {"现象": 0, "全体": 1, "内部联系": 1, "本质": 1},
    "乙": {"现象": 0, "全体": 1, "内部联系": 2, "本质": 2},
    "丙": {"现象": 0.5, "全体": 1, "内部联系": 1.5, "本质": 2},
}
IMP_W = {"核心": 2, "一般": 1}
ERR_W = {"核心": 2, "一般": 1}
UNSUPPORTED_W = 0.5
BOOT = 1000
SEP = 0.9


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)


def collect(pert):
    ratings = {}  # report -> list of rating dicts (one per judge run)
    off = {}
    for name in sorted(os.listdir(OUT)):
        if name.startswith("rating-"):
            d = load(name)
            for r, v in d["reports"].items():
                ratings.setdefault(r, []).append(v["ratings"])
                off.setdefault(r, []).append(bool(v["off_topic"]["value"]))
    claims, timeliness, traceable = {}, {}, {}
    for name in sorted(os.listdir(OUT)):
        if name.startswith("verify-") and "reports" in load(name):
            for r, v in load(name)["reports"].items():
                claims[r] = v["claims"]
                timeliness[r] = v["timeliness"]["score"]
                traceable[r] = bool(v["traceable_sources"])
    for p in pert:
        d = load(f"single-{p}.json")
        ratings[p] = [d["ratings"]]
        off[p] = [bool(d["off_topic"]["value"])]
        claims[p] = d["claims"]
        timeliness[p] = d["timeliness"]["score"]
        traceable[p] = bool(d["traceable_sources"])
    pool = load("pool.json")["points"]
    return ratings, off, claims, timeliness, traceable, pool


# 第一版：任何一条核心结论有误即算硬伤。第 1.1 版（检验后的修订）：只看对题目的直接回答。
DIRECT = None
# 第 1.2 版（评审细则第四节末尾）：有争议的标注按对领先一方最不利的方式计分；重抽样只用有报告写到的要点。
V12 = False


def hard_defects(r, off, claims, traceable):
    """第七节四种硬伤。返回硬伤名称列表。"""
    found = []
    if any(c["source_label"] == "找不到（疑似编造）" for c in claims[r]):
        found.append("编造来源")
    if DIRECT is None:
        wrong = any(c.get("core") and c["correct"] == "有误" for c in claims[r])
    else:
        wrong = any(c["id"] in DIRECT[r]["ids"] and c["correct"] == "有误" for c in claims[r])
    if wrong:
        found.append("主要结论与证据相反")
    votes = off[r]
    if sum(votes) * 2 > len(votes):
        found.append("答非所问")
    if not traceable[r]:
        found.append("全篇没有可追溯的出处")
    return found


def candidates(p, key, default=None):
    """层级或重要性的候选标注。列表表示有争议（第 1.2 版），第一项是登记的标注；否则只有一种。"""
    v = p.get(key, default)
    return list(v) if isinstance(v, list) else [v]


def labelings(p):
    """一条要点可能的（层级, 重要性）组合，第一个是登记的标注。多于一个，就是有争议的要点。"""
    return [(lv, imp) for lv in candidates(p, "level") for imp in candidates(p, "importance", "一般")]


def point_score(p, r, lw, level, imp):
    """一条要点给一份报告的分数：写对、切题加分，写错扣分，没写到为 0。"""
    reach = p.get("reach", {}).get(r)
    if reach is None:
        return 0.0
    if p["correct"] == "正确" and reach == "符合":
        return lw[level] * IMP_W[imp] if p.get("relevant", True) else 0.0
    if (p["correct"] == "正确" and reach == "相反") or (p["correct"] == "有误" and reach == "符合"):
        return -ERR_W[imp]
    return 0.0


def net_score(r, points, lw, claims):
    """深度净分：正确、切题、写到的要点加分；写错或写了错误的要点扣分；所引来源不支持的主要结论扣分。
    有争议的要点按登记的标注计分。"""
    s = 0.0
    for p in points:
        s += point_score(p, r, lw, *labelings(p)[0])
    s -= UNSUPPORTED_W * sum(1 for c in claims[r] if c["source_label"] == "不支持")
    return s


def element_profile(r, ratings, timeliness):
    """深度净分分不开时比较的各项档位。环节评级取各次评级的中位数。
    第 1.2 版按规则手册第八节第 3 条只比五个环节；第 1.0、1.1 版把时效（②）也算在内。"""
    prof = {e: median(run[e]["score"] for run in ratings[r]) for e in ELEMENTS}
    if not V12:
        prof["②"] = timeliness[r]
    return prof


def pareto_above(a, b):
    ks = list(a)
    return all(a[k] >= b[k] for k in ks) and any(a[k] > b[k] for k in ks)


def pairwise_winners(pw_files):
    """每个无序对，返回各次判定的胜者列表（'tie' 表示相当）。"""
    res = {}
    for name in pw_files:
        for it in load(name)["pairs"]:
            a, b, v = it["first"], it["second"], it["verdict"]
            w = a if v == "first" else b if v == "second" else "tie"
            res.setdefault(frozenset((a, b)), []).append(w)
    return res


def vetoes(wins, y):
    """两两比较是否否决"排在 y 前面"这一结果。wins 是各次判定的胜者。
    第 1.2 版（规则第八节第 4 条）：判 y 更好的次数至少占四分之三，向上取整，四次至少三次，两次就要两次；
    第 1.0、1.1 版：每次都判 y 更好。"""
    if not wins:
        return False
    against = sum(w == y for w in wins)
    if V12:
        return 4 * against >= 3 * len(wins)
    return against == len(wins)


def rank(reports, ratings, off, claims, timeliness, traceable, pool, pw, seed=0):
    hard = {r: hard_defects(r, off, claims, traceable) for r in reports}
    net = {w: {r: net_score(r, pool, lw, claims) for r in reports} for w, lw in LEVEL_W.items()}
    prof = {r: element_profile(r, ratings, timeliness) for r in reports}
    # 第 1.2 版：重抽样只在至少一份（参与排名的）报告写到的要点中进行。没有报告写到的要点对每份报告都是 0 分，
    # 有争议与否都不影响净分，所以下面只需看这些要点。
    if V12:
        pool = [p for p in pool if any(r in p.get("reach", {}) for r in reports)]
    rng = random.Random(seed)
    # 每条要点给每份报告的分数（登记的标注），重抽样时按抽到的要点序号相加，与 net_score 的算法相同
    table = {w: {r: [point_score(p, r, lw, *labelings(p)[0]) for p in pool] for r in reports}
             for w, lw in LEVEL_W.items()}
    penalty = {r: UNSUPPORTED_W * sum(1 for c in claims[r] if c["source_label"] == "不支持") for r in reports}
    boots, draws = [], []
    for _ in range(BOOT):
        idx = [rng.randrange(len(pool)) for _ in pool]
        boots.append({w: {r: sum(table[w][r][i] for i in idx) - penalty[r] for r in reports} for w in LEVEL_W})
        draws.append(idx)
    disputed = [i for i, p in enumerate(pool) if V12 and len(labelings(p)) > 1]
    disputed_draws = [{i: idx.count(i) for i in disputed if i in idx} for idx in draws]

    def worst_case(x, y, lw):
        """有争议的要点各取对 x 领先 y 最不利的标注。返回 {要点序号: (x 的分数改变量, y 的分数改变量, 所用标注)}。"""
        change = {}
        for i in disputed:
            p = pool[i]
            lab = min(labelings(p), key=lambda L: point_score(p, x, lw, *L) - point_score(p, y, lw, *L))
            reg = labelings(p)[0]
            change[i] = (point_score(p, x, lw, *lab) - point_score(p, x, lw, *reg),
                         point_score(p, y, lw, *lab) - point_score(p, y, lw, *reg), lab)
        return change

    sep_cache = {}

    def net_sep(x, y):
        """三种权重下都高，并且在至少 90% 的重抽样中都高。第 1.2 版先把有争议的要点按对 x 最不利的标注计分。
        同时记下每种权重下 x 领先的重抽样比例，以及有争议的要点所用的标注。"""
        if (x, y) not in sep_cache:
            ok, share, used = True, {}, {}
            for w, lw in LEVEL_W.items():
                change = worst_case(x, y, lw)
                for i, c in change.items():
                    if x in pool[i].get("reach", {}) or y in pool[i].get("reach", {}):
                        used.setdefault(pool[i]["pid"], {})[w] = {"level": c[2][0], "importance": c[2][1]}
                fx = net[w][x] + sum(c[0] for c in change.values())
                fy = net[w][y] + sum(c[1] for c in change.values())
                if not fx > fy:
                    ok = False
                    break
                if change:
                    wins = 0
                    for b, cnt in zip(boots, disputed_draws):
                        bx = b[w][x] + sum(k * change[i][0] for i, k in cnt.items())
                        by = b[w][y] + sum(k * change[i][1] for i, k in cnt.items())
                        wins += bx > by
                else:
                    wins = sum(b[w][x] > b[w][y] for b in boots)
                share[w] = wins / BOOT
                if share[w] < SEP:
                    ok = False
                    break
            sep_cache[(x, y)] = dict(ok=ok, share=share, labels=used)
        return sep_cache[(x, y)]["ok"]

    above, pre_veto, vetoed, how = set(), set(), set(), {}
    for x in reports:
        for y in reports:
            if x == y:
                continue
            reason = None
            hx, hy = bool(hard[x]), bool(hard[y])
            if not hx and hy:
                reason = "硬伤分档"
            elif hx == hy:
                if net_sep(x, y):
                    reason = "深度净分"
                elif not net_sep(y, x) and pareto_above(prof[x], prof[y]):
                    reason = "环节评级"
            if reason:
                pre_veto.add((x, y))
                wins = pw.get(frozenset((x, y)), [])
                # 第 1.1 版修订 3：两两比较不能否决由核验确认的硬伤
                protected = DIRECT is not None and reason == "硬伤分档"
                if vetoes(wins, y) and not protected:
                    vetoed.add((x, y))
                else:
                    above.add((x, y))
                    how[(x, y)] = reason
    n = len(reports)
    interval = {r: (1 + sum((y, r) in above for y in reports), n - sum((r, y) in above for y in reports))
                for r in reports}
    return dict(hard=hard, net=net, prof=prof, timeliness={r: timeliness[r] for r in reports},
                above=above, pre_veto=pre_veto, vetoed=vetoed,
                how=how, interval=interval, sep=sep_cache, resampled=len(pool),
                disputed=[pool[i]["pid"] for i in disputed])


def parse_args(argv):
    ap = argparse.ArgumentParser(description="按评审细则计算名次区间，并检查验收标准。")
    ap.add_argument("mapping", help="映射表：匿名标签对应的产品")
    ap.add_argument("version", nargs="?", default="1.0", choices=["1.0", "1.1", "1.2"], help="评法版本，默认 1.0")
    ap.add_argument("--data", default=OUT, help="评委输出所在的目录，默认是本目录下的 out/")
    ap.add_argument("--output", help="结果文件路径，默认是本目录下的 results-v<版本>.json")
    return ap.parse_args(argv)


def pilot_acceptance(acc, mapping, main_reports, pert, res, ratings, off, claims, timeliness, traceable,
                     pool, pw):
    """第四阶段方案第十节的验收标准 2 至 8，用第五阶段试评的扰动版本和重复评审计算。"""
    # 扰动：P1–P4 单独计分，与原版比较
    pm = {v: k for k, v in mapping["perturb"].items()}
    P = rank(pert, ratings, off, claims, timeliness, traceable, pool, {})
    orig, err, pad, fab = pm["original"], pm["errors"], pm["padding"], pm["fabricated"]
    marks = ["41.1", "73.9", "两到三个小时"]
    detected = sum(any(m in (c.get("quote", "") + c.get("claim", "")) and c["correct"] == "有误"
                       for c in claims[err]) for m in marks)
    acc["2 扰动：改错"] = {
        "查出处数": detected,
        "净分低于原版": all(P["net"][w][err] < P["net"][w][orig] for w in LEVEL_W),
        "通过": detected >= 2 and all(P["net"][w][err] < P["net"][w][orig] for w in LEVEL_W),
    }
    acc["3 扰动：注水"] = {
        "净分": {w: (P["net"][w][pad], P["net"][w][orig]) for w in LEVEL_W},
        "通过": all(P["net"][w][pad] <= P["net"][w][orig] for w in LEVEL_W),
    }
    fabbed = [c for c in claims[fab] if "deepresearch-index" in c.get("cited", "")]
    acc["4 扰动：编造来源"] = {
        "标签": [c["source_label"] for c in fabbed],
        "通过": any(c["source_label"] == "找不到（疑似编造）" for c in fabbed),
    }
    acc["扰动版硬伤"] = {k: P["hard"][pm[k]] for k in pm}

    # 标准 5：已知组
    chat = [r for r in main_reports if mapping["reports"][r] in ("Claude", "DeepSeek")]
    dr = [r for r in main_reports if r not in chat]
    bad = [(c, d) for c in chat for d in dr
           if bool(res["hard"][c]) == bool(res["hard"][d]) and (c, d) in res["above"]]
    acc["5 已知组"] = {"对话模式": chat, "违反": bad, "通过": not bad}

    # 标准 6：判定稳定
    o1, o2 = load("rating-opus-1.json")["reports"], load("rating-opus-2.json")["reports"]
    cells = [(r, e) for r in main_reports for e in ELEMENTS]
    agree = sum(o1[r]["ratings"][e]["score"] == o2[r]["ratings"][e]["score"] for r, e in cells) / len(cells)
    sub_ok = None
    if os.path.exists(os.path.join(OUT, "verify-sonnet-subset.json")):
        sub = load("verify-sonnet-subset.json")["claims"]
        byid = {c["id"]: c for r in main_reports for c in claims[r]}
        pairs = [(byid[c["id"]], c) for c in sub if c["id"] in byid]
        sl = sum(a["source_label"] == b["source_label"] for a, b in pairs) / len(pairs)
        cl = sum(a["correct"] == b["correct"] for a, b in pairs) / len(pairs)
        sub_ok = {"条数": len(pairs), "来源标签一致率": round(sl, 3), "对错标签一致率": round(cl, 3)}
    acc["6 判定稳定"] = {
        "环节评级完全一致率": round(agree, 3),
        "核验标签": sub_ok,
        "通过": agree >= 0.7 and bool(sub_ok) and sub_ok["来源标签一致率"] >= 0.8 and sub_ok["对错标签一致率"] >= 0.8,
    }

    # 标准 7：位置偏向
    flips = sum(1 for k, ws in pw.items() if len(set(ws)) > 1)
    acc["7 位置偏向"] = {"改变的对数": flips, "总对数": len(pw), "通过": flips <= 0.25 * len(pw)}

    # 标准 8：路线不矛盾（否决之前）
    acc["8 路线不矛盾"] = {"矛盾": sorted(f"{x}>{y}" for x, y in res["vetoed"]), "通过": not res["vetoed"]}


def export(main_reports, mapping, res, ratings, pool):
    """第 1.2 版结果文件里供页面读取的部分，字段说明见本文件开头。"""
    def pair(x, y, reason):
        item = {"higher": x, "lower": y, "basis": reason, "bootstrap_share": None, "disputed_labels": {}}
        if reason == "深度净分":
            d = res["sep"][(x, y)]
            item["bootstrap_share"] = d["share"]
            item["disputed_labels"] = d["labels"]
        return item

    reports = []
    for r in main_reports:
        best, worst = res["interval"][r]
        reports.append({
            "label": r,
            "product": mapping["reports"][r],
            "rank_best": best,
            "rank_worst": worst,
            "net_scores": {w: round(res["net"][w][r], 2) for w in LEVEL_W},
            "severe_problems": res["hard"][r],
            "element_grades": {e: res["prof"][r][e] for e in ELEMENTS},
            "timeliness": res["timeliness"][r],
            "writing": median(run["写作"]["score"] for run in ratings[r]),
        })
    return {
        "reports": reports,
        "separated_pairs": [pair(x, y, res["how"][(x, y)]) for x, y in sorted(res["above"])],
        "vetoed_pairs": [{"higher": x, "lower": y} for x, y in sorted(res["vetoed"])],
        "element_names": ELEMENT_NAMES,
        "resampling": {"rounds": BOOT, "seed": 0, "separation_share": SEP, "pool_points": len(pool),
                       "resampled_points": res["resampled"], "disputed_points": res["disputed"]},
    }


def main():
    global DIRECT, OUT, V12
    args = parse_args(sys.argv[1:])
    OUT = args.data
    mapping = json.load(open(args.mapping, encoding="utf-8"))
    version = args.version
    main_reports = list(mapping["reports"])
    pert = sorted(mapping.get("perturb", {}))
    if version in ("1.1", "1.2"):
        DIRECT = load("direct-answers.json")
    V12 = version == "1.2"
    ratings, off, claims, timeliness, traceable, pool = collect(pert)
    pw_files = [n for n in sorted(os.listdir(OUT)) if n.startswith("pairwise-")]
    pw = pairwise_winners(pw_files)
    res = rank(main_reports, ratings, off, claims, timeliness, traceable, pool, pw)
    res2 = rank(main_reports, ratings, off, claims, timeliness, traceable, pool, pw)
    report = {"main": {}, "acceptance": {}}
    for r in main_reports:
        report["main"][r] = {
            "product": mapping["reports"][r],
            "interval": res["interval"][r],
            "hard": res["hard"][r],
            "net": {w: round(res["net"][w][r], 2) for w in LEVEL_W},
            "profile": res["prof"][r],
            "writing": median(run["写作"]["score"] for run in ratings[r]),
        }
    report["separated"] = sorted(f"{x}>{y}（{res['how'][(x, y)]}）" for x, y in res["above"])
    report["vetoed"] = sorted(f"{x}>{y}" for x, y in res["vetoed"])
    acc = report["acceptance"]

    # 标准 1：复算一致
    acc["1 复算一致"] = res["interval"] == res2["interval"] and res["above"] == res2["above"]
    # 标准 2 至 8 要用试评的扰动版本和重复评审，只在映射表列出扰动版本时计算
    if pert:
        pilot_acceptance(acc, mapping, main_reports, pert, res, ratings, off, claims, timeliness, traceable,
                         pool, pw)

    report["version"] = version
    if V12:
        report.update(export(main_reports, mapping, res, ratings, pool))
    with open(args.output or os.path.join(HERE, f"results-v{version}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=list)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=list))


if __name__ == "__main__":
    main()
