"""统一运行程序：按运行计划调用每个参赛智能体，保存报告、日志和运行记录。

用法见同目录的 run_agents.md。只用 Python 标准库。
"""

import argparse
import concurrent.futures
import csv
import datetime
import errno
import json
import os
import queue
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# 规则手册附录二的统一答复原文，一字不改。
UNIFIED_REPLY = "题目已包含全部信息，请按你的理解直接进行，并在报告中写明你的理解和假设。"

# 命令行方式的反问记号：标准输出里以它开头的一行是反问，不算报告内容。
ASK_MARK = "[[反问]]"
ASK_MARK_BYTES = ASK_MARK.encode("utf-8")

# 反问不设次数上限：问多少次答多少次，运行只在时长上限时结束（规则手册第五节）。

# 命令行方式里，统一答复通过这个环境变量给出的管道文件交给智能体。
REPLY_PIPE_VARIABLE = "REPLY_PIPE"

# 交给队伍智能体的环境变量：只有这个固定的最小集合，加上申报里“需要的环境变量”点名要的，
# 不整份复制主办方的环境（主办方环境里可能有别的密钥）。只复制名字和值，从不打印值。
BASE_ENVIRONMENT = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL", "TERM")
ENVIRONMENT_FIELD = "需要的环境变量"
VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 申报文件必须填写的项目，对应规则手册附录三（“主办方计算的校验值”由本程序算出写进日志）。
DECLARATION_FIELDS = [
    "队伍名称", "版本号或代码提交号", "系统提示词文件", "所用模型及其版本", "工具和外部服务清单",
    "格式转换方式", "调用方式", "运行环境说明", "开源代码地址和许可证", "申报日期", "申报人",
]

VERSIONS = ("提问版", "裸题版")

# 时长上限〔120 分钟，默认〕，见规则手册第五节。
DEFAULT_LIMIT_MINUTES = 120

# 规则手册附录四的列，一字不改。
RECORD_COLUMNS = [
    "题目", "版本", "队伍", "日期", "开始", "结束",
    "输入校验值是否一致", "智能体是否提问，问了什么", "是否重跑，原因", "文件名",
]


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def now():
    return datetime.datetime.now().astimezone()


def sha256(data):
    return common.sha256_bytes(data)


def agent_environment(requested):
    """交给智能体的环境：固定的最小集合，加上申报里点名要的；主办方环境里没有的就不给。
    返回 (环境, 申报要的、主办方环境里没有的名字)。"""
    names = list(BASE_ENVIRONMENT) + [name for name in requested if name not in BASE_ENVIRONMENT]
    environment = {name: os.environ[name] for name in names if name in os.environ}
    missing = [name for name in requested if name not in os.environ]
    return environment, missing


def feed_input(stream, data, given):
    """把题目文本写进标准输入，只把真正写进去的部分记为“实际交给智能体的输入”。"""
    view = memoryview(data)
    try:
        while view:
            written = stream.write(view[:4096])
            given.extend(view[:written])
            view = view[written:]
    except OSError:
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def read_output(stream, report, asks, pending):
    """逐行读标准输出：反问行交给答复线程，其余行都是报告内容。"""
    for line in iter(stream.readline, b""):
        if line.startswith(ASK_MARK_BYTES):
            question = line[len(ASK_MARK_BYTES):].decode("utf-8", errors="replace").strip()
            asks.append({"问题": question, "时间": now().isoformat(timespec="seconds")})
            pending.put(question)
        else:
            report.extend(line)
    pending.put(None)


def send_replies(pipe_path, pending, process):
    """每收到一次反问，把统一答复写进管道文件一次。"""
    while True:
        question = pending.get()
        if question is None:
            return
        while process.poll() is None:
            try:
                handle = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as error:
                if error.errno != errno.ENXIO:  # ENXIO：智能体还没打开管道来读
                    return
                time.sleep(0.02)
                continue
            try:
                os.set_blocking(handle, True)
                os.write(handle, (UNIFIED_REPLY + "\n").encode("utf-8"))
            except OSError:
                pass
            finally:
                os.close(handle)
            break


def stop_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_command(call, folder, question_bytes, deadline, run_folder, requested=()):
    """命令行方式：启动申报的命令，题目原文从标准输入交给它，标准输出就是报告。"""
    pipe_folder = tempfile.mkdtemp(prefix="unified-reply-")
    pipe_path = os.path.join(pipe_folder, "reply")
    os.mkfifo(pipe_path)
    environment, missing = agent_environment(requested)
    environment[REPLY_PIPE_VARIABLE] = pipe_path
    given_names = sorted(environment)
    try:
        with open(run_folder / "标准错误.txt", "wb") as error_file:
            try:
                process = subprocess.Popen(
                    call["命令"], cwd=folder, env=environment,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_file, bufsize=0,
                    start_new_session=True,
                )
            except OSError as error:
                return {
                    "报告": b"", "输入": b"", "反问": [], "是否超时": False, "退出状态": None,
                    "标准错误文件": "标准错误.txt", "错误": f"无法启动申报的命令：{error}",
                    "环境变量": given_names, "缺少的环境变量": missing,
                }
            given, report, asks, pending = bytearray(), bytearray(), [], queue.Queue()
            threads = [
                threading.Thread(target=feed_input, args=(process.stdin, question_bytes, given)),
                threading.Thread(target=read_output, args=(process.stdout, report, asks, pending)),
                threading.Thread(target=send_replies, args=(pipe_path, pending, process)),
            ]
            for thread in threads:
                thread.daemon = True
                thread.start()
            timed_out = False
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(0.05)
            # 到时或正常结束后，都停掉整个进程组，免得留下后台子进程占着输出。
            stop_process_group(process)
            process.wait()
            for thread in threads:
                thread.join(timeout=2)
    finally:
        shutil.rmtree(pipe_folder, ignore_errors=True)
    outcome = {
        "报告": bytes(report),
        "输入": bytes(given),
        "反问": list(asks),
        "是否超时": timed_out,
        "退出状态": process.returncode,
        "标准错误文件": "标准错误.txt",
        "环境变量": given_names,
        "缺少的环境变量": missing,
    }
    if timed_out:
        outcome["退出状态"] = "到时长上限，由运行程序停止"
    return outcome


def run_network(call, question_bytes, deadline):
    """网络接口方式：把题目发到申报的地址，回应就是报告；回应是反问时，带上统一答复再发一次。"""
    text = question_bytes.decode("utf-8", errors="replace")
    exchanges, asks = [], []
    outcome = {"报告": b"", "反问": asks, "是否超时": False, "退出状态": None, "输入": None}
    while True:
        body = json.dumps({"题目": text, "往来": exchanges}, ensure_ascii=False).encode("utf-8")
        if outcome["输入"] is None:
            outcome["输入"] = json.loads(body)["题目"].encode("utf-8")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome["是否超时"] = True
            break
        request = urllib.request.Request(
            call["地址"], data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                outcome["退出状态"] = response.status
                content_type = response.headers.get_content_type()
                payload = response.read()
        except urllib.error.HTTPError as error:
            outcome["退出状态"] = error.code
            outcome["错误"] = error.read().decode("utf-8", errors="replace")[:2000]
            break
        except OSError as error:
            if time.monotonic() >= deadline - 0.05:
                outcome["是否超时"] = True
            else:
                outcome["错误"] = f"无法取得回应：{error}"
            break
        if time.monotonic() > deadline:
            outcome["是否超时"] = True
            break
        if content_type != "application/json":
            outcome["报告"] = payload
            break
        try:
            answer = json.loads(payload.decode("utf-8"))
        except ValueError:
            outcome["错误"] = "回应声明是 JSON，但无法解析"
            break
        if isinstance(answer, dict) and "反问" in answer:
            question = str(answer["反问"]).strip()
            asks.append({"问题": question, "时间": now().isoformat(timespec="seconds")})
            exchanges.append({"反问": question, "答复": UNIFIED_REPLY})
            continue
        if isinstance(answer, dict) and isinstance(answer.get("报告"), str):
            outcome["报告"] = answer["报告"].encode("utf-8")
        else:
            outcome["错误"] = "JSON 回应里既没有“报告”，也没有“反问”"
        break
    return outcome


def report_suffix(report):
    """按内容开头判断报告是 PDF、网页还是 Markdown。"""
    if report.startswith(b"%PDF"):
        return ".pdf"
    head = report.removeprefix(b"\xef\xbb\xbf").lstrip()[:64].lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return ".html"
    return ".md"


def safe_name(text):
    """把队伍名称、题目名称变成可以当目录名的文字。"""
    cleaned = "".join("_" if char in '/\\:*?"<>|' or ord(char) < 32 else char for char in str(text))
    return cleaned.strip().lstrip(".") or "_"


def describe_asks(asks):
    if not asks:
        return "否"
    return "是：" + "；".join(ask["问题"] for ask in asks)


RECORD_LOCK = threading.Lock()


def append_record(path, row):
    with RECORD_LOCK:
        write_record(path, row)


def write_record(path, row):
    new_file = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECORD_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


class PlanProblem(Exception):
    """运行计划或申报文件有问题；列出全部问题后停止，一次也不运行。"""


def load_agent(path, problems):
    """读一份申报文件，检查附录三的各项是否填了，调用方式是否可用。"""
    try:
        declaration = load_json(path)
    except (OSError, ValueError) as error:
        problems.append(f"{path}：读不了申报文件（{error}）")
        return None
    if not isinstance(declaration, dict):
        problems.append(f"{path}：申报文件应当是一个 JSON 对象")
        return None
    missing = [field for field in DECLARATION_FIELDS if not declaration.get(field)]
    if missing:
        problems.append(f"{path}：申报文件缺少或未填写：{'、'.join(missing)}")
    folder = path.parent
    prompt_checksum = None
    if declaration.get("系统提示词文件"):
        prompt_path = folder / declaration["系统提示词文件"]
        if prompt_path.is_file():
            prompt_checksum = sha256(prompt_path.read_bytes())
        else:
            problems.append(f"{path}：找不到系统提示词文件 {prompt_path}")
    requested = declaration.get(ENVIRONMENT_FIELD, [])
    if not (isinstance(requested, list)
            and all(isinstance(name, str) and VARIABLE_NAME.match(name) for name in requested)):
        problems.append(f"{path}：“{ENVIRONMENT_FIELD}”只写变量名的列表，例如 [\"SEARCH_KEY\"]，"
                        f"名字由字母、数字和下划线组成，不写值；现在是 {requested!r}")
        requested = []
    call = declaration.get("调用方式")
    if call and not isinstance(call, dict):
        problems.append(f"{path}：调用方式应当是一个 JSON 对象")
        call = None
    if call:
        method = call.get("方式")
        if method == "命令行":
            command = call.get("命令")
            if isinstance(command, str):
                command = shlex.split(command)
            if not command or not all(isinstance(part, str) for part in command):
                problems.append(f"{path}：调用方式是命令行，但没有写“命令”")
            call = dict(call, 命令=command)
        elif method == "网络接口":
            address = call.get("地址", "")
            if not isinstance(address, str) or not address.startswith(("http://", "https://")):
                problems.append(f"{path}：调用方式是网络接口，但“地址”不是 http:// 或 https:// 开头的网址")
        else:
            problems.append(f"{path}：调用方式里的“方式”只能是“命令行”或“网络接口”，现在是 {method!r}")
    return {
        "队伍": declaration.get("队伍名称"),
        "调用方式": call,
        "需要的环境变量": requested,
        "工作目录": folder / (call or {}).get("工作目录", "."),
        "申报文件": str(path),
        "申报文件校验值": sha256(path.read_bytes()),
        "系统提示词文件校验值": prompt_checksum,
    }


def load_plan(plan_path):
    """读运行计划和其中列出的申报文件、题目文件。有任何问题都抛出 PlanProblem。"""
    problems = []
    try:
        plan = load_json(plan_path)
    except (OSError, ValueError) as error:
        raise PlanProblem(f"{plan_path}：读不了运行计划（{error}）")
    folder = plan_path.parent

    if not isinstance(plan, dict):
        raise PlanProblem(f"{plan_path}：运行计划应当是一个 JSON 对象")
    agents = []
    for item in plan.get("智能体") or []:
        if not isinstance(item, str):
            problems.append(f"“智能体”里每一项应当是申报文件的路径，现在有 {item!r}")
            continue
        agent = load_agent(folder / item, problems)
        if agent:
            agents.append(agent)
    if not agents and not problems:
        problems.append("运行计划里没有列出智能体")
    teams = [agent["队伍"] for agent in agents]
    for team in sorted({team for team in teams if teams.count(team) > 1}):
        problems.append(f"队伍名称重复：{team}")

    questions = []
    for item in plan.get("题目") or []:
        if not isinstance(item, dict):
            problems.append(f"“题目”里每一项应当是一个 JSON 对象，现在有 {item!r}")
            continue
        name, version, file_name = item.get("题目"), item.get("版本"), item.get("文件")
        if not name or not file_name:
            problems.append(f"运行计划里的题目缺少“题目”或“文件”：{item}")
            continue
        if version not in VERSIONS:
            problems.append(f"题目 {name} 的版本只能是“提问版”或“裸题版”，现在是 {version!r}")
            continue
        path = folder / file_name
        if not path.is_file():
            problems.append(f"找不到题目文件 {path}")
            continue
        text = path.read_bytes()
        questions.append({
            "题目": name,
            "版本": version,
            "文本": text,
            "校验值": str(item.get("校验值") or sha256(text)).strip().lower(),
            "校验值来源": "运行计划" if item.get("校验值") else "题目文件",
        })
    if not questions and not problems:
        problems.append("运行计划里没有列出题目")
    pairs = [(question["题目"], question["版本"]) for question in questions]
    for name, version in sorted({pair for pair in pairs if pairs.count(pair) > 1}):
        problems.append(f"题目和版本重复：{name} {version}")

    if problems:
        raise PlanProblem("\n".join(problems))
    try:
        limit_minutes = float(plan.get("时长上限分钟", DEFAULT_LIMIT_MINUTES))
    except (TypeError, ValueError):
        raise PlanProblem("“时长上限分钟”应当是一个数")
    return {
        "智能体": agents,
        "题目": questions,
        "时长上限秒": limit_minutes * 60,
        "输出目录": folder / plan.get("输出目录", "运行结果"),
    }


def run_once(agent, question, limit_seconds, day_folder, run_folder, rerun_reason):
    """跑一次：一个智能体、一道题的一个版本。保存报告和日志，追加一行运行记录。"""
    team = agent["队伍"]
    run_folder.mkdir(parents=True)
    started = now()
    deadline = time.monotonic() + limit_seconds
    call = agent["调用方式"]
    if call["方式"] == "网络接口":
        outcome = run_network(call, question["文本"], deadline)
    else:
        outcome = run_command(call, agent["工作目录"], question["文本"], deadline, run_folder,
                              agent["需要的环境变量"])
    ended = now()

    delivered = bool(outcome["报告"].strip())
    report_path = run_folder / ("报告" + report_suffix(outcome["报告"]))
    if delivered:
        report_path.write_bytes(outcome["报告"])
    (run_folder / "输入.txt").write_bytes(outcome["输入"])
    given_checksum = sha256(outcome["输入"])
    consistent = "一致" if given_checksum == question["校验值"] else "不一致"
    log = {
        "队伍": team,
        "题目": question["题目"],
        "版本": question["版本"],
        "调用方式": call,
        "开始": started.isoformat(timespec="seconds"),
        "结束": ended.isoformat(timespec="seconds"),
        "用时秒": round((ended - started).total_seconds(), 3),
        "时长上限秒": limit_seconds,
        "是否超时": outcome["是否超时"],
        "退出状态": outcome["退出状态"],
        "是否交付": delivered,
        "报告文件": report_path.name if delivered else None,
        "报告校验值": sha256(outcome["报告"]) if delivered else None,
        "输入文件": "输入.txt",
        "输入校验值": given_checksum,
        "题目文本校验值": question["校验值"],
        "题目文本校验值来源": question["校验值来源"],
        "输入校验值是否一致": consistent,
        "反问": [dict(ask, 答复=UNIFIED_REPLY) for ask in outcome["反问"]],
        "标准错误文件": outcome.get("标准错误文件"),
        "交给智能体的环境变量": outcome.get("环境变量"),
        "申报要的、主办方环境里没有的环境变量": outcome.get("缺少的环境变量"),
        "错误": outcome.get("错误"),
        "是否重跑": bool(rerun_reason),
        "重跑原因": rerun_reason,
        "申报文件": agent["申报文件"],
        "申报文件校验值": agent["申报文件校验值"],
        "系统提示词文件校验值": agent["系统提示词文件校验值"],
    }
    common.write_text_atomic(run_folder / "运行日志.json",
                             json.dumps(log, ensure_ascii=False, indent=2, default=str))
    append_record(day_folder / "运行记录.csv", {
        "题目": question["题目"],
        "版本": question["版本"],
        "队伍": team,
        "日期": started.date().isoformat(),
        "开始": started.strftime("%H:%M:%S"),
        "结束": ended.strftime("%H:%M:%S"),
        "输入校验值是否一致": consistent,
        "智能体是否提问，问了什么": describe_asks(outcome["反问"]),
        "是否重跑，原因": f"是：{rerun_reason}" if rerun_reason else "否",
        "文件名": report_path.relative_to(day_folder).as_posix() if delivered else "未交付",
    })
    return describe_outcome(delivered, outcome)


def describe_outcome(delivered, outcome):
    if outcome["是否超时"]:
        result = "到时长上限，以届时已交付的内容为准" if delivered else "到时长上限，未交付"
    else:
        result = "已交付" if delivered else "未交付"
    if outcome["反问"]:
        result += f"；反问 {len(outcome['反问'])} 次"
    if outcome.get("错误"):
        result += f"；错误：{outcome['错误'][:200]}"
    return result


def planned_runs(plan, args, day_folder):
    """按运行计划和命令行上的筛选条件，列出这次要跑的运行；已有结果的不覆盖。"""
    runs = []
    for question in plan["题目"]:
        if args.question and question["题目"] != args.question:
            continue
        if args.version and question["版本"] != args.version:
            continue
        for agent in plan["智能体"]:
            if args.team and agent["队伍"] != args.team:
                continue
            label = f"{question['题目']} {question['版本']} {agent['队伍']}"
            base = day_folder / safe_name(agent["队伍"]) / safe_name(question["题目"])
            original = base / question["版本"]
            rerun = base / (question["版本"] + "-重跑")
            if not args.rerun_reason:
                if original.exists():
                    print(f"跳过：{label}，今天已经运行过；需要重跑请加 --rerun-reason 写明原因")
                    continue
                runs.append((agent, question, original, None, label))
            elif not original.exists():
                print(f"跳过：{label}，今天还没有运行过，谈不上重跑")
            elif rerun.exists():
                print(f"跳过：{label}，已经重跑过一次，规则只允许重跑一次")
            else:
                runs.append((agent, question, rerun, args.rerun_reason, label))
    return runs


def main(argv=None):
    parser = argparse.ArgumentParser(description="按运行计划调用参赛智能体")
    parser.add_argument("plan", help="运行计划文件（JSON）")
    parser.add_argument("--team", help="只跑这支队伍")
    parser.add_argument("--question", help="只跑这道题（写运行计划里的题目名称）")
    parser.add_argument("--version", choices=VERSIONS, help="只跑这个版本")
    parser.add_argument("--rerun-reason", help="重跑一次已经跑过的运行，并写明原因（会写进运行记录）")
    parser.add_argument("--parallel", type=int, default=1, metavar="N",
                        help="同时进行的运行数，默认 1（一个接一个）")
    args = parser.parse_args(argv)
    if args.parallel < 1:
        parser.error("--parallel 至少是 1")

    try:
        plan = load_plan(Path(args.plan).resolve())
    except PlanProblem as problem:
        print("运行计划有问题，没有开始运行：\n" + str(problem), file=sys.stderr)
        return 2
    day_folder = plan["输出目录"] / datetime.date.today().isoformat()
    day_folder.mkdir(parents=True, exist_ok=True)

    def run_and_report(agent, question, run_folder, rerun_reason, label):
        print(f"开始：{label}", flush=True)
        result = run_once(agent, question, plan["时长上限秒"], day_folder, run_folder, rerun_reason)
        print(f"结束：{label}：{result}", flush=True)

    runs = planned_runs(plan, args, day_folder)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        for future in [pool.submit(run_and_report, *run) for run in runs]:
            future.result()
    return 0


if __name__ == "__main__":
    sys.exit(main())
