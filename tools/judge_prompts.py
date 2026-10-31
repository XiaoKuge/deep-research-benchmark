"""第五阶段试评评委提示词的存档与比对。

试评的评委都是主会话派出的子任务，交给它们的任务提示只存在会话记录里。
本程序按清单（评委目录下的 manifest.json）里每次运行的调用编号，
从会话记录中取出主会话交给评委的任务提示。

用法：
  python3 -I tools/judge_prompts.py extract [--transcript 会话记录] [--judges 评委目录]
  python3 -I tools/judge_prompts.py check   [--transcript 会话记录] [--judges 评委目录]

extract：把每次运行的任务提示原样写入清单所列的提示词文件（UTF-8，不加结尾换行）。
check：重新取出并与已存的提示词文件逐字比对。

会话记录是 JSON Lines 文件：一行一个 JSON 对象。派出评委的调用是助手消息里
type 为 tool_use、name 为 Agent 的条目，input 里有 description、prompt，可能还有 model。
同一条调用可能出现不止一次（另一份副本没有时间戳），按调用编号去重。
清单里的路径都相对于评委目录的上一级，即试评数据目录 stage5-pilot/。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import common  # noqa: E402

DEFAULT_JUDGES = os.path.join(ROOT, "research-plan", "stage5-pilot", "judges")


def _find_agent_calls(node, found):
    if isinstance(node, dict):
        if node.get("type") == "tool_use" and node.get("name") == "Agent":
            found.append(node)
        for value in node.values():
            _find_agent_calls(value, found)
    elif isinstance(node, list):
        for value in node:
            _find_agent_calls(value, found)


def read_agent_calls(transcript):
    """返回 {调用编号: {"input": 调用参数, "timestamp": 时间戳或 None}}。"""
    calls = {}
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            found = []
            _find_agent_calls(record, found)
            for call in found:
                entry = calls.setdefault(call["id"], {"input": call.get("input", {}),
                                                      "timestamp": None})
                if entry["timestamp"] is None and record.get("timestamp"):
                    entry["timestamp"] = record["timestamp"]
    return calls


def read_judge_models(transcript):
    """评委实际用的模型，记在评委自己的会话记录里：会话记录旁同名目录下的 subagents/。

    每个评委一对文件：agent-编号.meta.json（其中 toolUseId 是派出它的调用编号）和
    agent-编号.jsonl（其中助手消息的 message.model）。返回 {调用编号: 模型名的集合}；
    目录不存在时返回 None，表示无法核对。
    """
    folder = os.path.join(transcript[:-len(".jsonl")] if transcript.endswith(".jsonl")
                          else transcript, "subagents")
    if not os.path.isdir(folder):
        return None
    models = {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".meta.json"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            tool_id = json.load(f).get("toolUseId")
        log = os.path.join(folder, name[:-len(".meta.json")] + ".jsonl")
        if not tool_id or not os.path.exists(log):
            continue
        found = set()
        with open(log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") == "assistant":
                    model = record.get("message", {}).get("model")
                    if model and not model.startswith("<"):
                        found.add(model)
        models[tool_id] = found
    return models


def load_manifest(judges):
    with open(os.path.join(judges, "manifest.json"), encoding="utf-8") as f:
        return json.load(f)


def resolve_transcript(manifest, given):
    return os.path.expanduser(given or manifest["transcript"])


def cmd_extract(args):
    manifest = load_manifest(args.judges)
    calls = read_agent_calls(resolve_transcript(manifest, args.transcript))
    pilot = os.path.dirname(os.path.abspath(args.judges))
    missing = [run["output"] for run in manifest["runs"]
               if run.get("prompt") and run["tool_use_id"] not in calls]
    if missing:
        print("会话记录里找不到这些运行的调用，什么也没写：", "、".join(missing))
        return 1
    for run in manifest["runs"]:
        if not run.get("prompt"):
            continue
        call = calls[run["tool_use_id"]]
        path = os.path.join(pilot, run["prompt"])
        common.write_text_atomic(path, call["input"]["prompt"])
        print("已写出", run["prompt"])
    return 0


def cmd_check(args):
    manifest = load_manifest(args.judges)
    transcript = resolve_transcript(manifest, args.transcript)
    calls = read_agent_calls(transcript)
    models = read_judge_models(transcript)
    if models is None:
        print("找不到评委自己的会话记录，未核对实际模型")
    pilot = os.path.dirname(os.path.abspath(args.judges))
    problems = 0
    for run in manifest["runs"]:
        if not run.get("prompt"):
            print("没有提示词（清单已注明）", run["output"])
            continue
        differences = compare_run(run, calls.get(run["tool_use_id"]), pilot)
        if models is not None:
            actual = models.get(run["tool_use_id"])
            if actual is None:
                differences.append("找不到这次运行的评委会话记录")
            elif actual != {run.get("model")}:
                differences.append("实际模型应为 %s" % "、".join(sorted(actual)))
        if differences:
            problems += 1
            print("不一致", run["prompt"], "；".join(differences))
        else:
            print("一致", run["prompt"])
    print("共 %d 次运行，%d 次不一致" % (len(manifest["runs"]), problems))
    return 1 if problems else 0


def compare_run(run, call, pilot):
    """返回清单这一条与会话记录不一致之处的列表；一致时返回空列表。"""
    if call is None:
        return ["会话记录里找不到调用 %s" % run["tool_use_id"]]
    differences = []
    with open(os.path.join(pilot, run["prompt"]), encoding="utf-8", newline="") as f:
        if f.read() != call["input"].get("prompt"):
            differences.append("提示词文字与会话记录不同")
    if run.get("description") != call["input"].get("description"):
        differences.append("任务描述应为 %r" % call["input"].get("description"))
    if run.get("model_requested") != call["input"].get("model"):
        differences.append("派出时指定的模型应为 %r" % call["input"].get("model"))
    if run.get("dispatched_at") != call["timestamp"]:
        differences.append("派出时间应为 %s" % call["timestamp"])
    if call["timestamp"] and run.get("date") != call["timestamp"][:10]:
        differences.append("日期应为 %s" % call["timestamp"][:10])
    return differences


def main(argv=None):
    parser = argparse.ArgumentParser(description="第五阶段试评评委提示词的存档与比对")
    parser.add_argument("command", choices=["extract", "check"])
    parser.add_argument("--transcript", help="会话记录路径；不给时用清单里记的路径")
    parser.add_argument("--judges", default=DEFAULT_JUDGES, help="评委目录（含 manifest.json）")
    args = parser.parse_args(argv)
    return cmd_extract(args) if args.command == "extract" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
