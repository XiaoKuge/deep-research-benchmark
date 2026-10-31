#!/usr/bin/env python3
"""文献索引页的本地服务：在 localhost:8766 提供 literature.local.html（只留本机的文献索引）、本目录的 PDF 和 notes/ 下的精读页，并接收「阅读状态 / 笔记」的写回。

- 只监听 127.0.0.1，只服务 index.html、本目录下的 PDF 和 notes/ 下的 .html。
- 写回只改被点的那一篇论文的 status / note / doneAt，以及顶层 updated；写之前先备份到 .backups/。
- 「给 Claude 留言」存在 comments.json：页面上新增 / 撤回留言，Claude 用同一个接口回复并改状态。
- 用法：python3 serve.py                  （加 --open 顺手打开浏览器）
        python3 serve.py --wait-comments  （不起服务；一直等，出现待处理留言就打印出来并退出，给 Claude 当闹钟）
"""
import datetime
import json
import os
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

PORT = 8766
ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "literature.local.html")
BACKUPS = os.path.join(ROOT, ".backups")
KEEP_BACKUPS = 30
HOSTS = {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}
ORIGINS = {f"http://{h}" for h in HOSTS}
BLOCK_RE = re.compile(r'(<script id="papers-data" type="application/json">\n)(.*?)(\n</script>)', re.S)
ID_RE = re.compile(r"^\d{4}\.\d{4,5}$")
NOTE_RE = re.compile(r"^notes/[\w.-]+\.html$")  # 只认 notes/ 下一层，不含第二个 "/"
STATUSES = {"unread", "reading", "done"}
COMMENTS = os.path.join(ROOT, "comments.json")
CID_RE = re.compile(r"^c\d{13,}$")
# open = 待 Claude 处理；working = Claude 已接手；waiting = Claude 已回复、等你确认；done = 已处理
C_STATUSES = {"open", "working", "waiting", "done"}
LOCK = threading.Lock()


def today():
    return datetime.date.today().isoformat()


def backup(text, prefix="index-", ext=".html"):
    os.makedirs(BACKUPS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    with open(os.path.join(BACKUPS, f"{prefix}{stamp}{ext}"), "w", encoding="utf-8") as f:
        f.write(text)
    old = sorted(n for n in os.listdir(BACKUPS) if n.startswith(prefix))
    for n in old[:-KEEP_BACKUPS]:
        os.remove(os.path.join(BACKUPS, n))


def now():
    return datetime.datetime.now().isoformat(timespec="minutes")


def load_comments():
    if not os.path.exists(COMMENTS):
        return {"comments": []}
    with open(COMMENTS, encoding="utf-8") as f:
        return json.load(f)


def comment_action(req):
    """add / delete 由页面调用；reply 由 Claude 调用（curl 同一个接口）。"""
    action = req.get("action")
    with LOCK:
        data = load_comments()
        cs = data["comments"]
        if action == "add":
            paper, text, re_id = req.get("paper") or "", req.get("text"), req.get("re") or ""
            if paper and not ID_RE.match(paper):
                raise ValueError("论文编号不对")
            if not isinstance(text, str) or not text.strip() or len(text) > 5000:
                raise ValueError("留言为空或太长")
            if re_id and not any(c["id"] == re_id for c in cs):
                raise ValueError("找不到要接着说的那条留言")
            c = {"id": f"c{time.time_ns() // 1000}", "paper": paper, "text": text.strip(), "re": re_id,
                 "created": now(), "status": "open", "reply": "", "replied": None}
            cs.append(c)
        else:
            hits = [c for c in cs if c["id"] == req.get("id")]
            if len(hits) != 1:
                raise ValueError("找不到这条留言，刷新一下页面")
            c = hits[0]
            if action == "delete":
                if c["status"] != "open":
                    raise ValueError("Claude 已经回复过，不能撤回了")
                cs.remove(c)
            elif action == "reply":
                if req.get("status") not in C_STATUSES - {"open"}:
                    raise ValueError("状态只能是 working / waiting / done")
                if not isinstance(req.get("reply"), str) or len(req["reply"]) > 20000:
                    raise ValueError("回复为空或太长")
                c.update(reply=req["reply"], status=req["status"], replied=now())
            else:
                raise ValueError("不认识的操作")
        if os.path.exists(COMMENTS):
            with open(COMMENTS, encoding="utf-8") as f:
                backup(f.read(), "comments-", ".json")
        tmp = COMMENTS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, COMMENTS)
        return {"ok": True, "comment": c, "comments": cs}


def wait_comments(interval=3):
    """阻塞到出现 status=open 的留言，把它们打印成 JSON 后退出。"""
    while True:
        try:
            pending = [c for c in load_comments()["comments"] if c["status"] == "open"]
        except (OSError, ValueError):
            pending = []  # 文件正被替换时偶尔读到半截，下一轮再读
        if pending:
            print(json.dumps(pending, ensure_ascii=False, indent=1), flush=True)
            return
        time.sleep(interval)


def dump(data):
    """按页面里的排版写回：顶层一键一行，groups / papers 一项一行；"<" 转义，防止笔记里写出 </script>。"""
    def j(v):
        return json.dumps(v, ensure_ascii=False).replace("<", "\\u003c")

    parts = []
    for k, v in data.items():
        if isinstance(v, list):
            items = ",\n".join("  " + j(x) for x in v)
            parts.append(f"{j(k)}: [\n{items}\n]")
        else:
            parts.append(f"{j(k)}: {j(v)}")
    return "{\n" + ",\n".join(parts) + "\n}"


def update_paper(req):
    pid = req.get("id") or ""
    if not ID_RE.match(pid):
        raise ValueError("论文编号不对")
    if "status" in req and req["status"] not in STATUSES:
        raise ValueError("状态只能是 unread / reading / done")
    if "note" in req and (not isinstance(req["note"], str) or len(req["note"]) > 20000):
        raise ValueError("笔记太长或格式不对")
    with LOCK:
        with open(INDEX, encoding="utf-8") as f:
            text = f.read()
        m = BLOCK_RE.search(text)
        if not m:
            raise ValueError("index.html 里找不到数据区")
        data = json.loads(m.group(2))
        hits = [p for p in data["papers"] if p.get("id") == pid]
        if len(hits) != 1:
            raise ValueError(f"找不到论文 {pid}，刷新一下页面")
        p = hits[0]
        if "status" in req:
            p["status"] = req["status"]
            p["doneAt"] = (p.get("doneAt") or today()) if req["status"] == "done" else None
        if "note" in req:
            p["note"] = req["note"]
        data["updated"] = today()
        block = dump(data)
        if len(json.loads(block)["papers"]) != len(data["papers"]):  # 写之前确认 JSON 仍然完整
            raise ValueError("论文数对不上，已放弃写入")
        backup(text)
        tmp = INDEX + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text[: m.start(2)] + block + text[m.end(2):])
        os.replace(tmp, INDEX)
        return {"ok": True, "paper": p}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return self.headers.get("Host", "") in HOSTS

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, '{"ok":false}')
        path = unquote(self.path.split("?", 1)[0])
        if path == "/ping":
            return self._send(200, "ok", "text/plain")
        if path == "/api/comments":
            with LOCK:
                return self._send(200, json.dumps(load_comments(), ensure_ascii=False))
        if path in ("/", "/index.html", "/papers.html"):
            with open(INDEX, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        name = path.lstrip("/")
        full = os.path.join(ROOT, name)
        if NOTE_RE.match(name) and os.path.isfile(full):
            with open(full, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if "/" in name or not name.lower().endswith(".pdf") or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        with open(full, "rb") as f:
            return self._send(200, f.read(), "application/pdf")

    def do_POST(self):
        origin = self.headers.get("Origin")
        handlers = {"/api/paper": update_paper, "/api/comment": comment_action}
        if (not self._host_ok() or self.path not in handlers
                or self.headers.get("X-Papers") != "1"
                or (origin is not None and origin not in ORIGINS)):
            return self._send(403, '{"ok":false,"error":"forbidden"}')
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 50000:
                raise ValueError("请求太大")
            res = handlers[self.path](json.loads(self.rfile.read(n) or b"{}"))
            self._send(200, json.dumps(res, ensure_ascii=False))
        except Exception as e:  # 页面上直接显示错误原因
            self._send(400, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))

    def log_message(self, fmt, *args):
        if self.command == "POST":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    if "--wait-comments" in sys.argv:
        wait_comments()
        sys.exit(0)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    print(f"文献索引：{url}  （Ctrl+C 停止）", flush=True)
    if "--open" in sys.argv:
        webbrowser.open(url)
    server.serve_forever()
