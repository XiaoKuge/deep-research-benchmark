"""一次性的迁移：把已经提交的模拟数据改成统一的替代记录格式。2026-10-30 写，跑过一次。

替代记录原来有两种写法：模拟评审 run.json 的 substitutions 用英文键（step、slot、task、planned_vendor、vendor），
模拟出题 元数据.json 的"角色"下各角色的"替代"用另一套中文键（角色、步骤、配置的厂商、原来用的厂商、改用、原因）。
现在统一成 tools/substitutes.py 的五个字段：步骤、任务、原来的厂商、改用的厂商、原因。site/build_simulation.py
只读这一种，所以已经提交的数据用这个程序迁移一次，而不是在读取处兼容旧格式。

- 模拟评审：旧记录没有原因，按 run.json 的 unavailable 补写：原来的厂商第一次失败就在这个任务上的，写
  "调用失败：<当时的错误>"；其余写"在本次运行前面的调用里已经不可用"。另外补上 too_few_vendors
  （计划用三家以上、实际拿到回答的厂商不足三家的步骤），按 calls.jsonl 里成功的调用算。
- 模拟出题：旧记录的"步骤"是任务名，改记进"任务"，"步骤"取任务名里的步骤（例如 深度地图）。

已经是新格式的不动，所以重复运行没有影响。写回时保持各自原来的格式：run.json 缩进 1，元数据.json 缩进 2，
末尾一个换行；读进来再按原格式写出与原文不一致的文件，程序不改它，报告出来。
用法：python3 -I tools/migrate_substitution_records.py [--simulation simulation 目录]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import common  # noqa: E402
import models  # noqa: E402
import simulate_review  # noqa: E402
import simulate_setter  # noqa: E402
import substitutes  # noqa: E402

DEFAULT_SIMULATION = os.path.join(os.path.dirname(HERE), "simulation")


def review_record(old, unavailable):
    if list(old) == list(substitutes.FIELDS):
        return old
    planned = old["planned_vendor"]
    gone = unavailable.get(planned) or {}
    if gone.get("first_failed_task") == old["task"]:
        reason = "调用失败：%s" % gone.get("error")
    else:
        reason = substitutes.ALREADY_UNAVAILABLE
    return substitutes.record(old["step"], old["task"], planned, old["vendor"], [(planned, reason)])


def setter_record(old):
    if list(old) == list(substitutes.FIELDS):
        return old
    return {"步骤": simulate_setter.step_of(old["步骤"]), "任务": old["步骤"], "原来的厂商": old["原来用的厂商"],
            "改用的厂商": old["改用"], "原因": old["原因"]}


def too_few_vendors(run, calls):
    """与 simulate_review.too_few_vendors 同样的规则，按调用记录里成功的调用算。"""
    found = []
    for key, name in simulate_review.STEPS:
        planned = list(dict.fromkeys(run["config"]["steps"][key]["vendors"]))
        if len(planned) < simulate_review.MIN_VENDORS:
            continue
        used = sorted({c["vendor"] for c in calls if c.get("status") == models.SUCCEEDED
                       and c["task"].startswith("评审-%s：" % name)}, key=models.VENDORS.index)
        if used and len(used) < simulate_review.MIN_VENDORS:
            found.append({"step": name, "planned_vendors": planned, "used_vendors": used,
                          "rule": simulate_review.THREE_VENDORS_RULE})
    return found


def rewrite(path, indent, change):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    data = json.loads(text)
    if json.dumps(data, ensure_ascii=False, indent=indent) + "\n" != text:
        return "%s：按原格式写出与原文不一致，没有改" % path
    if change(data):
        common.write_json_atomic(path, data, indent=indent)
        return "%s：已迁移" % path
    return None


def migrate_review(data, folder):
    changed = False
    unavailable = {u["vendor"]: u for u in data.get("unavailable") or []}
    new = [review_record(item, unavailable) for item in data.get("substitutions") or []]
    if new != data.get("substitutions"):
        data["substitutions"] = new
        changed = True
    if "too_few_vendors" not in data:
        calls = [entry for _, entry in models.read_call_log(os.path.join(folder, "calls.jsonl"))]
        data["too_few_vendors"] = too_few_vendors(data, calls)
        changed = True
    return changed


def migrate_question(data):
    changed = False
    for info in (data.get("角色") or {}).values():
        new = [setter_record(item) for item in info.get("替代") or []]
        if new != info.get("替代"):
            info["替代"] = new
            changed = True
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="把已经提交的模拟数据改成统一的替代记录格式（一次性）。")
    ap.add_argument("--simulation", default=DEFAULT_SIMULATION, help="simulation 目录，默认仓库里的 simulation/")
    args = ap.parse_args(argv)
    notes = []
    reviews = os.path.join(args.simulation, "reviews")
    for name in sorted(os.listdir(reviews)) if os.path.isdir(reviews) else []:
        path = os.path.join(reviews, name, "run.json")
        if os.path.isfile(path):
            notes.append(rewrite(path, 1, lambda data: migrate_review(data, os.path.dirname(path))))
    questions = os.path.join(args.simulation, "questions")
    for name in sorted(os.listdir(questions)) if os.path.isdir(questions) else []:
        path = os.path.join(questions, name, "元数据.json")
        if os.path.isfile(path):
            notes.append(rewrite(path, 2, migrate_question))
    notes = [note for note in notes if note]
    print("\n".join(notes) if notes else "没有要迁移的文件")
    return 1 if any("没有改" in note for note in notes) else 0


if __name__ == "__main__":
    sys.exit(main())
