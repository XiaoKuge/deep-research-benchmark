"""新手包里的示例智能体。

它只演示统一运行程序（tools/run_agents.py）怎样用命令行方式调用参赛智能体，
不调用任何模型，不做任何调研，交出的报告写明是示例。

1. 题目原文从标准输入交进来，读到输入结束就是全文。
2. 反问：在标准输出单独写一行“[[反问]] 问题”，立即刷新；
   再打开环境变量 REPLY_PIPE 给出的文件，读到结束，就是统一答复。
3. 报告写到标准输出，写完退出。反问行不算报告内容。
4. 进度写到标准错误，运行程序把它另存成日志，也不算报告。

不经过运行程序也能直接试：

    python3 agent.py < 练习题/淡水湖/提问版.txt

这时没有 REPLY_PIPE，示例就不反问，直接写报告。
只用 Python 自带的标准库。
"""

import hashlib
import os
import sys

ASK_MARK = "[[反问]]"

# 对所有题目都一样的反问。真正的智能体也不能针对某一道题单独配置。
QUESTION_TO_ASK = "要不要先确认研究计划？"


def progress(message):
    """进度写到标准错误。"""
    print(message, file=sys.stderr, flush=True)


def ask(question):
    """按反问约定反问一次，返回统一答复；不是由运行程序启动的，返回 None。"""
    pipe = os.environ.get("REPLY_PIPE")
    if not pipe:
        progress("没有 REPLY_PIPE，说明不是由统一运行程序启动的，不反问。")
        return None
    print(f"{ASK_MARK} {question}", flush=True)
    with open(pipe, encoding="utf-8") as handle:
        return handle.read().strip()


def report(received, reply):
    text = received.decode("utf-8", errors="replace")
    lines = text.splitlines()
    first_line = lines[0] if lines else ""
    if reply is None:
        asked = "没有反问：不是由统一运行程序启动的，拿不到统一答复。"
    else:
        asked = f"问：{QUESTION_TO_ASK}\n- 收到的答复：{reply}"
    return f"""# 示例报告：由新手包里的示例智能体生成，没有调用任何模型，也没有做任何调研

## 主要结论

这是示例，不是调研结论。示例智能体只演示统一运行程序怎样调用参赛智能体：题目原文从标准输入交进来，反问一次并收到统一答复，报告写到标准输出。真正的报告在这里先写对题目的直接回答。

## 论证与解释

- 收到的题目共 {len(text)} 个字，第一行是：{first_line}
- 收到的文字的校验值（SHA-256）是 {hashlib.sha256(received).hexdigest()}，应当与运行日志里的“输入校验值”相同。
- 反问。{asked}
- 我的理解和假设：示例不理解题目，只把收到的内容照录下来。真正的报告在这里写论证和解释；有不清楚的地方，写明自己的理解和假设，裸题版还要写明对提问者和用途的理解。

## 出处

示例没有查阅任何来源，所以这里没有网址。真正的报告给每个关键结论标明来源，给出可以点开的网址和取用日期，尽量使用原始出处。

## 把握程度

示例不下任何判断，谈不上把握。真正的报告写明主要判断各有多大把握，为什么。

## 查找与来源说明

示例没有检索，也没有用任何来源。真正的报告写明查了哪些方面，用了哪些来源，其中哪些可靠、哪些不可靠，还有哪些信息缺口。
"""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    received = sys.stdin.buffer.read()
    progress(f"读到题目，共 {len(received)} 个字节。")
    reply = ask(QUESTION_TO_ASK)
    if reply is not None:
        progress("收到统一答复，开始写报告。")
    sys.stdout.write(report(received, reply))
    sys.stdout.flush()
    progress("报告写完。")


if __name__ == "__main__":
    main()
