"""《一道题走完全程》页面里的示意计算：五份虚构报告按规则手册第八节排名次。

用法：python3 -I walkthrough_example.py
报告是虚构的示意，计分规则是真的：层级权重三种、重要性核心 2 一般 1、写错扣分、
重抽样一千次、有争议的标注按对领先一方最不利的方式计分、分不开时比环节评级。
页面上的数字都由本程序算出；改了下面的数据，重新运行，再把页面上的数字改过来。
"""
import itertools
import random

LEVEL_W = {
    "甲": {"现象": 0, "全体": 1, "内部联系": 1, "本质": 1},
    "乙": {"现象": 0, "全体": 1, "内部联系": 2, "本质": 2},
    "丙": {"现象": 0.5, "全体": 1, "内部联系": 1.5, "本质": 2},
}
IMP_W = {"核心": 2, "一般": 1}
ERR_W = {"核心": 2, "一般": 1}
UNSUPPORTED = 0.5
BOOT, SEP = 1000, 0.9
REPORTS = ["一号", "二号", "三号", "四号", "五号"]

# 要点池：深度地图 L1 到 L8，加一条只有报告写到的要点。
# importance 若是列表，表示评委组意见不到三分之二，算有争议。
POOL = [
    {"id": "L1", "text": "鄱阳湖通常被称为我国最大的淡水湖", "level": "现象", "importance": "核心", "relevant": True},
    {"id": "L2", "text": "湖面随季节涨落极大，洪水一片，枯水一线", "level": "全体", "importance": "核心", "relevant": True},
    {"id": "L3", "text": "近年枯水越来越常见，2022 年水位创最低", "level": "全体", "importance": "一般", "relevant": True},
    {"id": "L4", "text": "说最大要先说清按什么算：哪个水位、哪种口径", "level": "本质", "importance": "核心", "relevant": True},
    {"id": "L5", "text": "湖面高低由五条河的来水和长江水位共同决定", "level": "内部联系", "importance": "一般", "relevant": True},
    {"id": "L6", "text": "中俄界湖兴凯湖更大，但大部分不在中国境内", "level": "本质", "importance": "核心", "relevant": True},
    {"id": "L7", "text": "青海湖更大，但它是咸水湖", "level": "本质", "importance": ["一般", "核心"], "relevant": True},
    {"id": "L8", "text": "洞庭湖当年可能比今天的鄱阳湖还大", "level": "全体", "importance": "一般", "relevant": True},
    {"id": "X1", "text": "鄱阳湖是白鹤等候鸟的越冬地", "level": "现象", "importance": "一般", "relevant": False},
]
# 每份报告写到了哪几条：对 = 写对，反 = 写的与这条相反
REACH = {
    "一号": {"L1": "对", "L2": "反", "X1": "对"},
    "二号": {"L1": "对", "L2": "对", "L3": "对", "L4": "对"},
    "三号": {"L1": "对", "L2": "对", "L3": "对", "L4": "对", "L5": "对", "L6": "对", "L7": "对"},
    "四号": {"L1": "对", "L2": "对", "L3": "对", "L7": "对"},
    "五号": {"L1": "对"},
}
UNSUPPORTED_CLAIMS = {"二号": 1}          # 所引来源不支持该结论的主要结论条数
HARD_DEFECTS = {"五号": "编造来源"}        # 经第二次核查确认
RATINGS = {  # 五个环节：切题与真实需要、查找过程的交代、甄别来源与处理矛盾、分析、结论与把握
    "一号": (1, 0, 0, 0, 1),
    "二号": (2, 2, 1, 2, 1),
    "三号": (2, 2, 2, 2, 2),
    "四号": (2, 0, 1, 1, 2),
    "五号": (1, 1, 0, 1, 1),
}


def point_score(p, r, lw, imp):
    reach = REACH[r].get(p["id"])
    if reach is None:
        return 0.0
    if reach == "对":
        return lw[p["level"]] * IMP_W[imp] if p["relevant"] else 0.0
    return -ERR_W[imp]


def net(r, points, lw, labels):
    s = sum(point_score(p, r, lw, labels[p["id"]]) for p in points)
    return s - UNSUPPORTED * UNSUPPORTED_CLAIMS.get(r, 0)


def default_labels():
    return {p["id"]: (p["importance"][0] if isinstance(p["importance"], list) else p["importance"]) for p in POOL}


def worst_labels_for(x, y, lw):
    """有争议的标注：取让 x 相对 y 最不利的那一种。"""
    labels = default_labels()
    for p in POOL:
        if isinstance(p["importance"], list):
            labels[p["id"]] = min(p["importance"], key=lambda imp: point_score(p, x, lw, imp) - point_score(p, y, lw, imp))
    return labels


def separated(x, y, samples):
    """x 在三种权重下都高于 y，并且在至少 90% 的重抽样中都高，才算分开。"""
    detail = {}
    for w, lw in LEVEL_W.items():
        labels = worst_labels_for(x, y, lw)
        if not net(x, POOL, lw, labels) > net(y, POOL, lw, labels):
            return False, detail
        share = sum(net(x, s, lw, labels) > net(y, s, lw, labels) for s in samples) / BOOT
        detail[w] = share
        if share < SEP:
            return False, detail
    return True, detail


def main():
    labels = default_labels()
    print("深度净分（有争议的 L7 先按一般计）：")
    for r in REPORTS:
        print(" ", r, {w: net(r, POOL, lw, labels) for w, lw in LEVEL_W.items()},
              "硬伤：" + HARD_DEFECTS[r] if r in HARD_DEFECTS else "")
    written = [p for p in POOL if any(p["id"] in REACH[r] for r in REPORTS)]
    print("参与重抽样的要点：", [p["id"] for p in written], "（L8 没有报告写到，不参与）")
    rng = random.Random(0)
    samples = [[written[rng.randrange(len(written))] for _ in written] for _ in range(BOOT)]

    above, how = set(), {}
    clean = [r for r in REPORTS if r not in HARD_DEFECTS]
    for d in HARD_DEFECTS:
        for c in clean:
            above.add((c, d)); how[(c, d)] = "硬伤分档"
    for x, y in itertools.permutations(clean, 2):
        ok, detail = separated(x, y, samples)
        if ok:
            above.add((x, y)); how[(x, y)] = "深度净分 " + "，".join(f"{w} {v:.1%}" for w, v in detail.items())
        elif detail or (x, y) not in above:
            a, b = RATINGS[x], RATINGS[y]
            if (y, x) not in above and all(i >= j for i, j in zip(a, b)) and any(i > j for i, j in zip(a, b)):
                # 只有净分分不开时才比环节评级
                if not separated(y, x, samples)[0]:
                    above.add((x, y)); how[(x, y)] = "环节评级"
    print("分开的对：")
    for (x, y) in sorted(above):
        print(f"  {x} > {y}：{how[(x, y)]}")
    print("没分开的对：")
    for x, y in itertools.combinations(REPORTS, 2):
        if (x, y) not in above and (y, x) not in above:
            _, d1 = separated(x, y, samples)
            _, d2 = separated(y, x, samples)
            print(f"  {x} 与 {y}：{x} 领先的比例 {d1 or '净分不全领先'}；{y} 领先的比例 {d2 or '净分不全领先'}；"
                  f"环节评级 {RATINGS[x]} 与 {RATINGS[y]}")
    n = len(REPORTS)
    print("名次区间：")
    for r in REPORTS:
        best = 1 + sum((o, r) in above for o in REPORTS)
        worst = n - sum((r, o) in above for o in REPORTS)
        print(f"  {r}：第 {best} 名" if best == worst else f"  {r}：第 {best} 至 {worst} 名")


if __name__ == "__main__":
    main()
