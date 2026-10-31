"""几个程序共用的小工具：校验值、带时区的当前时间、整份替换的写文件。

只用 Python 自带的标准库。写文件一律先写到同一目录下的临时文件，写完再整份替换，
中途出错时旧文件原样留着，不会留下写了一半的文件。
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime


def sha256_text(text):
    """文本按 UTF-8 编码后的 SHA-256 校验值（十六进制）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def now_iso(timespec="seconds"):
    """本机时区的当前时间，ISO 8601 格式，带时区，例如 2026-10-30T21:03:47-07:00。"""
    return datetime.now().astimezone().isoformat(timespec=timespec)


def write_text_atomic(path, text):
    """把 text 整份写进 path：目录不存在会自动建，写完才替换旧文件。"""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=folder, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass
        raise


def write_json_atomic(path, data, indent=2):
    """写 JSON：不转义中文，末尾带换行；indent 由调用方定，保持各自已有文件的格式。"""
    write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=indent) + "\n")
