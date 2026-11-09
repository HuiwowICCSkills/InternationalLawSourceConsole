"""Local server for the international-law search source console.

The source catalog belongs to the retrieval tool. This server only exposes that
catalog to the UI and persists the user's toggle state to sources-state.json.
"""

import json
import argparse
import hashlib
import os
import socket
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "sources-state.json")
PAGE = "search-sources.html"
DEFAULT_STATE = {"version": 1, "updated_at": None, "notes": "", "sources": {}}
PORT_RANGE = range(8765, 8780)
CATALOG_PATH = None


def load_catalog():
    """Read the external catalog supplied by the retrieval tool."""
    if not CATALOG_PATH:
        raise ValueError("source catalog is not configured")
    path = Path(CATALOG_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"source catalog not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid source catalog JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("groups"), list):
        raise ValueError("source catalog must contain a groups array")
    seen = set()
    for group in payload["groups"]:
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            raise ValueError("each catalog group must contain an items array")
        for item in group["items"]:
            source_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(source_id, str) or not source_id:
                raise ValueError("catalog source id must be a non-empty string")
            if source_id in seen:
                raise ValueError(f"duplicate source id: {source_id}")
            seen.add(source_id)
            if not isinstance(item.get("default_enabled"), bool):
                raise ValueError(f"{source_id}.default_enabled must be boolean")
    return payload


def catalog_fingerprint(catalog):
    canonical = json.dumps(
        catalog,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def read_state():
    if not os.path.exists(STATE_PATH):
        return json.loads(json.dumps(DEFAULT_STATE))
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_state(payload):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, STATE_PATH)


def normalize_state(payload):
    """Keep the state file limited to IDs owned by the retrieval tool."""
    if not isinstance(payload, dict):
        raise ValueError("state must be a JSON object")
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("state.sources must be a JSON object")
    if any(not isinstance(value, bool) for value in sources.values()):
        raise ValueError("state.sources values must be boolean")

    catalog = load_catalog()
    catalog_items = [item for group in catalog["groups"] for item in group["items"]]
    catalog_ids = [item["id"] for item in catalog_items]
    defaults = {item["id"]: item["default_enabled"] for item in catalog_items}
    unknown = sorted(set(sources) - set(catalog_ids))
    if unknown:
        raise ValueError("unknown source ids: " + ", ".join(unknown))

    sources = {
        source_id: bool(sources[source_id]) if source_id in sources else defaults[source_id]
        for source_id in catalog_ids
    }
    enabled = [source_id for source_id in catalog_ids if sources[source_id]]
    disabled = [source_id for source_id in catalog_ids if not sources[source_id]]
    return {
        **payload,
        "version": 1,
        "catalog_id": catalog["catalog_id"],
        "catalog_sha256": catalog_fingerprint(catalog),
        "enabled_count": len(enabled),
        "total_count": len(catalog_ids),
        "disabled": disabled,
        "sources": sources,
        "_readme": (
            "国际法检索来源开关。检索前先读本文件：sources 中 false 的来源不要使用。"
            "来源 ID、名称和说明由检索工具的 source-catalog.json 负责；本文件只保存开关与备注。"
        ),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/catalog":
            try:
                catalog = load_catalog()
                self.send_json(
                    200,
                    {
                        "catalog": catalog,
                        "path": str(CATALOG_PATH),
                        "sha256": catalog_fingerprint(catalog),
                    },
                )
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return
        if path == "/api/state":
            try:
                self.send_json(200, read_state())
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return
        if path in ("/", "/index.html"):
            self.path = "/" + PAGE
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/state":
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            write_state(normalize_state(payload))
            self.send_json(200, {"ok": True, "file": STATE_PATH})
        except Exception as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, fmt, *args):
        sys.stderr.write("[console] " + fmt % args + "\n")


def free_port():
    for candidate in PORT_RANGE:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", candidate)) != 0:
                return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the local service without opening a browser window.",
    )
    parser.add_argument(
        "--catalog",
        default=os.environ.get("INTL_LAW_SOURCE_CATALOG"),
        help="Path to the source catalog JSON owned by the retrieval tool.",
    )
    args = parser.parse_args()
    if not args.catalog:
        print("未指定来源目录。请用 --catalog 指向检索工具提供的 source-catalog.json。")
        return 1
    global CATALOG_PATH
    CATALOG_PATH = os.path.abspath(args.catalog)
    try:
        load_catalog()
    except Exception as exc:
        print(f"来源目录读取失败: {exc}")
        return 1
    if not os.path.exists(STATE_PATH):
        write_state(DEFAULT_STATE)
    port = free_port()
    if port is None:
        print("没有可用端口（8765-8779 都被占用）。")
        return 1
    url = "http://127.0.0.1:%d/%s" % (port, PAGE)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("国际法检索来源控制台已启动。")
    print("界面地址: %s" % url)
    print("来源目录: %s" % CATALOG_PATH)
    print("状态文件: %s" % STATE_PATH)
    print("关闭此窗口即停止服务。")
    if not args.no_browser:
        threading.Timer(0.9, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
