"""网页存档程序：把一份报告里引用的网页逐个取回，按校验值保存内容，并写一份清单。

用法：
  python3 -I tools/archive_sources.py 报告文件 --list
  python3 -I tools/archive_sources.py 报告文件 --out 存档目录

使用说明见 tools/archive_sources.md。只用 Python 标准库，不调用任何第三方存档服务。
"""
import argparse
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urldefrag, urlsplit, urlunsplit
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; deep-research-benchmark-source-archiver/1.0)"
MIME_TYPES = mimetypes.MimeTypes()  # 只用内置对照表，不读本机配置，扩展名在各台机器上一致

# 裸网址只认网址允许的英文字符；遇到空白、中文字符、中文标点、引号、尖括号、方括号就结束。
BARE_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&()*+,;=%]+")
TRAILING_PUNCTUATION = ".,;:!?*"


def _clean_bare_url(url):
    """去掉粘在裸网址末尾的句读，以及没有配对的右括号。"""
    while url:
        last = url[-1]
        if last in TRAILING_PUNCTUATION:
            url = url[:-1]
        elif last == ")" and url.count(")") > url.count("("):
            url = url[:-1]
        else:
            break
    return url


def _opening_bracket(text, close):
    """从右方括号 text[close] 向左找与它配对的左方括号，找不到返回 -1。"""
    depth = 0
    for i in range(close, -1, -1):
        if text[i] == "]":
            depth += 1
        elif text[i] == "[":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _link_target(text, start):
    """从 text[start]（左圆括号之后）读出链接目标，返回 (目标起点, 目标终点)。"""
    i = start
    while i < len(text) and text[i] in " \t":
        i += 1
    if i < len(text) and text[i] == "<":
        end = text.find(">", i)
        if end == -1:
            return None
        return i + 1, end
    begin, depth = i, 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            break
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        i += 1
    return begin, i


def extract_markdown(text):
    """返回 [(位置, 网址)] 和跳过的图片地址个数。"""
    found = []
    skipped_images = 0
    masked = list(text)
    for m in re.finditer(r"\]\(", text):
        opening = _opening_bracket(text, m.start())
        if opening == -1:
            continue
        span = _link_target(text, m.end())
        if span is None:
            continue
        begin, end = span
        target = text[begin:end]
        is_image = opening > 0 and text[opening - 1] == "!"
        if is_image:
            if BARE_URL.match(target):
                skipped_images += 1
        elif BARE_URL.match(target):
            found.append((begin, target))
        for i in range(begin, end):
            masked[i] = " "
    masked_text = "".join(masked)
    for m in BARE_URL.finditer(masked_text):
        found.append((m.start(), _clean_bare_url(m.group())))
    return found, skipped_images


class _HtmlLinks(HTMLParser):
    """收集 <a> 和 <area> 的 href，以及正文文字里的裸网址；跳过脚本、样式和图片。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = []
        self.skipped_images = 0
        self._hidden = 0
        self._order = 0

    def _add(self, url):
        self.found.append((self._order, url))
        self._order += 1

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._hidden += 1
        elif tag in ("a", "area"):
            href = (attrs.get("href") or "").strip()
            if BARE_URL.match(href):
                self._add(href)
        elif tag == "img" and BARE_URL.match((attrs.get("src") or "").strip()):
            self.skipped_images += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._hidden:
            self._hidden -= 1

    def handle_data(self, data):
        if self._hidden:
            return
        for m in BARE_URL.finditer(data):
            self._add(_clean_bare_url(m.group()))


def extract_html(text):
    """返回 [(顺序号, 网址)] 和跳过的图片地址个数。"""
    parser = _HtmlLinks()
    parser.feed(text)
    parser.close()
    return parser.found, parser.skipped_images


def is_html_report(path):
    return path.lower().endswith((".html", ".htm"))


def extract_urls(text, html=False):
    """按出现顺序返回去重后的网址（去掉 # 之后的部分）和跳过的图片地址个数。"""
    found, skipped_images = (extract_html if html else extract_markdown)(text)
    urls, seen = [], set()
    for _, url in sorted(found):
        url = urldefrag(url).url
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls, skipped_images


def utc_now():
    """协调世界时，精确到秒，例如 2026-10-30T08:15:02Z。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_ascii_url(url):
    """把网址里的中文等字符转成百分号编码，域名转成国际化域名编码，才能交给 urllib。"""
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        host = host.encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"  # 数字形式的第六版网际协议地址要放回方括号里
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    if parts.username:
        netloc = f"{parts.username}@{netloc}"
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="/%:@!$&'()*+,;=-._~?")
    return urlunsplit((parts.scheme, netloc, path, query, ""))


class TooLarge(Exception):
    pass


def _read_limited(response, max_bytes, deadline):
    """分块读正文；超过大小上限或超过时长上限就放弃。"""
    chunks, size = [], 0
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError("下载正文超过时长上限")
        chunk = response.read(CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        size += len(chunk)
        if size > max_bytes:
            raise TooLarge()
        chunks.append(chunk)


def _download(url, timeout, max_bytes, entry):
    """取回正文并把状态码、最终网址、内容类型填进条目。"""
    deadline = time.monotonic() + timeout
    request = Request(to_ascii_url(url), headers={"User-Agent": USER_AGENT})
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as error:
        response = error  # 错误状态也有响应头和正文，照样记下、存下
    with response:
        entry["final_url"] = response.geturl()
        entry["status"] = response.status
        entry["content_type"] = response.headers.get("Content-Type")
        body = _read_limited(response, max_bytes, deadline)
    if 300 <= entry["status"] < 400:
        entry["error"] = (f"重定向没有完成（状态码 {entry['status']}）：可能超过了重定向次数上限、"
                          "形成循环、没有给出新地址，或者转到了不支持的协议")
    elif entry["status"] >= 400:
        entry["error"] = f"服务器返回 {entry['status']} {getattr(response, 'reason', '')}".strip()
    return body


def _describe(error, timeout, max_bytes):
    if isinstance(error, TooLarge):
        return f"内容超过大小上限 {max_bytes} 字节，没有保存"
    if isinstance(error, URLError) and isinstance(error.reason, TimeoutError):
        error = error.reason
    if isinstance(error, TimeoutError):
        return f"超时：{timeout:g} 秒内没有取回"
    if isinstance(error, URLError):
        return f"无法连接：{error.reason}"
    return f"取回出错：{type(error).__name__}: {error}"


def fetch(url, timeout, max_bytes):
    """取回一个网址，返回 (清单条目, 内容)；失败时内容为 None，条目里写明原因。"""
    entry = {
        "url": url, "final_url": None, "status": None, "content_type": None,
        "bytes": None, "sha256": None, "file": None, "fetched_at": None, "error": None,
    }
    body = None
    try:
        body = _download(url, timeout, max_bytes, entry)
    except Exception as error:  # 单个网址出任何错都只记原因，不中断整次存档
        entry["error"] = _describe(error, timeout, max_bytes)
    entry["fetched_at"] = utc_now()
    if body is not None:
        entry["bytes"] = len(body)
        entry["sha256"] = common.sha256_bytes(body)
    return entry, body


def save_content(out_dir, entry, body):
    """内容按校验值命名，存在 content/ 下；扩展名按内容类型猜，猜不出用 .bin。"""
    media_type = (entry["content_type"] or "").split(";")[0].strip().lower()
    extension = MIME_TYPES.guess_extension(media_type) or ".bin"
    relative = f"content/{entry['sha256']}{extension}"
    path = os.path.join(out_dir, relative)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(body)
    entry["file"] = relative


def read_report(path):
    """返回报告的原始字节和文字；个别不是 UTF-8 的字节换成替代符，网址本身不受影响。"""
    with open(path, "rb") as f:
        raw = f.read()
    return raw, raw.decode("utf-8", errors="replace")


def archive(report_path, out_dir, timeout, max_bytes):
    raw, text = read_report(report_path)
    urls, skipped_images = extract_urls(text, html=is_html_report(report_path))
    os.makedirs(os.path.join(out_dir, "content"), exist_ok=True)
    manifest = {
        "report": report_path,
        "report_sha256": common.sha256_bytes(raw),
        "started_at": utc_now(),
        "finished_at": None,
        "timeout_seconds": timeout,
        "max_bytes": max_bytes,
        "skipped_image_urls": skipped_images,
        "entries": [],
    }
    for number, url in enumerate(urls, 1):
        entry, body = fetch(url, timeout, max_bytes)
        if body is not None:
            save_content(out_dir, entry, body)
        manifest["entries"].append(entry)
        outcome = f"失败（{entry['error']}）" if entry["error"] else f"{entry['status']}"
        print(f"[{number}/{len(urls)}] {outcome} {url}", flush=True)
    manifest["finished_at"] = utc_now()
    common.write_json_atomic(os.path.join(out_dir, "manifest.json"), manifest, indent=2)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="把报告里引用的网页存档。")
    parser.add_argument("report", help="报告文件（Markdown 或 HTML）")
    parser.add_argument("--list", action="store_true", help="只列出提取到的网址，不取回")
    parser.add_argument("--out", help="存档目录，存放清单 manifest.json 和 content/ 下的内容")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"每个网址的时长上限，单位秒（默认 {DEFAULT_TIMEOUT:g}）")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES,
                        help=f"每个网址的大小上限，单位字节（默认 {DEFAULT_MAX_BYTES}）")
    args = parser.parse_args(argv)

    if args.list:
        _, text = read_report(args.report)
        urls, skipped_images = extract_urls(text, html=is_html_report(args.report))
        for url in urls:
            print(url)
        print(f"共 {len(urls)} 个网址；跳过图片地址 {skipped_images} 个。", file=sys.stderr)
        return 0
    if not args.out:
        parser.error("需要 --out 存档目录，或者用 --list 只列出网址")
    manifest_path = os.path.join(args.out, "manifest.json")
    if os.path.exists(manifest_path):
        print(f"{manifest_path} 已经存在：这是之前的一次存档，不覆盖。请换一个新目录。", file=sys.stderr)
        return 2
    manifest = archive(args.report, args.out, args.timeout, args.max_bytes)
    failed = sum(1 for entry in manifest["entries"] if entry["error"])
    print(f"共 {len(manifest['entries'])} 个网址：成功 {len(manifest['entries']) - failed}，"
          f"失败 {failed}；跳过图片地址 {manifest['skipped_image_urls']} 个。清单：{manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
