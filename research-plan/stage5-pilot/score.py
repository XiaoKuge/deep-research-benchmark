"""第五阶段小规模检验：按《评审细则》和第四阶段方案第六、七节计算名次区间，并检查验收标准。

用法：python3 -I score.py <映射表路径> [1.0|1.1]
映射表记录匿名标签对应的产品，评委看不到它；只在最后报告时使用。
所有数字只由本程序从 out/ 下的评委输出生成，不手工修改。
"""
import json
import os
import random
import sys
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MAIN = list("ABCDEF")
PERT = ["P1", "P2", "P3", "P4"]
ELEMENTS = ["①", "③", "④", "⑤", "⑦"]

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


def collect():
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
        if name.startswith("verify-opus-"):
            for r, v in load(name)["reports"].items():
                claims[r] = v["claims"]
                timeliness[r] = v["timeliness"]["score"]
                traceable[r] = bool(v["traceable_sources"])
    for p in PERT:
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


def net_score(r, points, lw, claims):
    """深度净分：正确、切题、写到的要点加分；写错或写了错误的要点扣分；所引来源不支持的主要结论扣分。"""
    s = 0.0
    for p in points:
        reach = p.get("reach", {}).get(r)
        if reach is None:
            continue
        imp = p.get("importance", "一般")
        if p["correct"] == "正确" and reach == "符合":
            if p.get("relevant", True):
                s += lw[p["level"]] * IMP_W[imp]
        elif (p["correct"] == "正确" and reach == "相反") or (p["correct"] == "有误" and reach == "符合"):
            s -= ERR_W[imp]
    s -= UNSUPPORTED_W * sum(1 for c in claims[r] if c["source_label"] == "不支持")
    return s


def element_profile(r, ratings, timeliness):
    prof = {e: median(run[e]["score"] for run in ratings[r]) for e in ELEMENTS}
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


def rank(reports, ratings, off, claims, timeliness, traceable, pool, pw, seed=0):
    hard = {r: hard_defects(r, off, claims, traceable) for r in reports}
    net = {w: {r: net_score(r, pool, lw, claims) for r in reports} for w, lw in LEVEL_W.items()}
    prof = {r: element_profile(r, ratings, timeliness) for r in reports}
    rng = random.Random(seed)
    boots = []
    for _ in range(BOOT):
        sample = [pool[rng.randrange(len(pool))] for _ in pool]
        boots.append({w: {r: net_score(r, sample, lw, claims) for r in reports} for w, lw in LEVEL_W.items()})
    def net_sep(x, y):
        """三种权重下都高，并且在至少 90% 的重抽样中都高。"""
        return all(net[w][x] > net[w][y] for w in LEVEL_W) and all(
            sum(b[w][x] > b[w][y] for b in boots) / BOOT >= SEP for w in LEVEL_W)

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
                if wins and all(w == y for w in wins) and not protected:
                    vetoed.add((x, y))
                else:
                    above.add((x, y))
                    how[(x, y)] = reason
    n = len(reports)
    interval = {r: (1 + sum((y, r) in above for y in reports), n - sum((r, y) in above for y in reports))
                for r in reports}
    return dict(hard=hard, net=net, prof=prof, above=above, pre_veto=pre_veto, vetoed=vetoed,
                how=how, interval=interval)


def main():
    global DIRECT
    mapping = json.load(open(sys.argv[1], encoding="utf-8"))
    version = sys.argv[2] if len(sys.argv) > 2 else "1.0"
    if version == "1.1":
        DIRECT = load("direct-answers.json")
    ratings, off, claims, timeliness, traceable, pool = collect()
    pw_files = [n for n in sorted(os.listdir(OUT)) if n.startswith("pairwise-")]
    pw = pairwise_winners(pw_files)
    res = rank(MAIN, ratings, off, claims, timeliness, traceable, pool, pw)
    res2 = rank(MAIN, ratings, off, claims, timeliness, traceable, pool, pw)
    report = {"main": {}, "acceptance": {}}
    for r in MAIN:
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

    # 扰动：P1–P4 单独计分，与原版比较
    pm = {v: k for k, v in mapping["perturb"].items()}
    P = rank(PERT, ratings, off, claims, timeliness, traceable, pool, {})
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
    chat = [r for r in MAIN if mapping["reports"][r] in ("Claude", "DeepSeek")]
    dr = [r for r in MAIN if r not in chat]
    bad = [(c, d) for c in chat for d in dr
           if bool(res["hard"][c]) == bool(res["hard"][d]) and (c, d) in res["above"]]
    acc["5 已知组"] = {"对话模式": chat, "违反": bad, "通过": not bad}

    # 标准 6：判定稳定
    o1, o2 = load("rating-opus-1.json")["reports"], load("rating-opus-2.json")["reports"]
    cells = [(r, e) for r in MAIN for e in ELEMENTS]
    agree = sum(o1[r]["ratings"][e]["score"] == o2[r]["ratings"][e]["score"] for r, e in cells) / len(cells)
    sub_ok = None
    if os.path.exists(os.path.join(OUT, "verify-sonnet-subset.json")):
        sub = load("verify-sonnet-subset.json")["claims"]
        byid = {c["id"]: c for r in MAIN for c in claims[r]}
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

    report["version"] = version
    with open(os.path.join(HERE, f"results-v{version}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=list)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=list))


if __name__ == "__main__":
    main()
