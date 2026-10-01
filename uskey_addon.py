# mitmproxy addon（由 mitmdump 以 --script 加载）
# 作用：监听 Marvis 发往 yybadaccess 的 /v1/chat/completions，
#       把最新的 uskey / access_token / openid 回推给 bridge 的本地接口。
from mitmproxy import http
import json
import re
import urllib.request

BRIDGE_CALLBACK = "http://127.0.0.1:4605/_ingest"
TARGET = re.compile(r"yybadaccess.*/v1/chat/completions")


def request(flow: http.HTTPFlow):
    if not TARGET.search(flow.request.pretty_url):
        return
    h = flow.request.headers
    ext = h.get("Ual-Access-MarvisExt", "")
    m = re.search(r'"uskey":"([^"]*)"', ext)
    if not m:
        return
    payload = {
        "uskey": m.group(1),
        "access_token": h.get("Ual-Access-Access-Token", ""),
        "openid": h.get("Ual-Access-Openid", ""),
        "guid": h.get("Ual-Access-Guid") or h.get("X-Device-GUID", ""),
    }
    try:
        req = urllib.request.Request(
            BRIDGE_CALLBACK,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass
