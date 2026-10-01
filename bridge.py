#!/usr/bin/env python3
"""
Marvis Bridge — 把腾讯 Marvis 桌面助手的私有 OpenAI 兼容接口，暴露为标准 OpenAI 网关。

来源：对 Marvis.app 的授权协议研究（mitm 抓包，见 sessions/2026-09-30-marvis）。
上游：POST https://yybadaccess.3g.qq.com/v1/chat/completions（标准 OpenAI 协议）
鉴权：Ual-Access-* 头（复用登录态 access_token），无需签名/验证码。

用法：
    python3 bridge.py                 # 读取同目录 config.toml
    python3 bridge.py --port 8000
然后任意 OpenAI 客户端指向 http://127.0.0.1:8000/v1 即可。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"

app = FastAPI(title="Marvis Bridge", version="1.0.0")
CFG: dict[str, Any] = {}

# 运行时从客户端流量捕获的最新凭证（由 mitm 提取器写入；uskey 每请求一变）
LIVE: dict[str, str | None] = {
    "uskey": None,
    "access_token": None,
    "openid": None,
    "guid": None,
    "updated_at": None,
}


# ---------------------------------------------------------------- config
def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _uskey_source() -> str:
    """uskey 来源：provider | mitm | config（config.toml [marvis].uskey_source，默认 provider）。"""
    return str(CFG["marvis"].get("uskey_source", "provider")).lower()


def _fetch_provider_uskey() -> str | None:
    """从独立 uskey provider 取一个全新的 uskey（每请求唯一）。"""
    m = CFG["marvis"]
    host = m.get("uskey_provider_host", "127.0.0.1")
    port = int(m.get("uskey_provider_port", 4607))
    url = f"http://{host}:{port}/uskey"
    try:
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=3.0)) as c:
            r = c.get(url)
            r.raise_for_status()
            u = r.json().get("uskey")
            if u:
                LIVE["uskey"] = u
                LIVE["updated_at"] = time.strftime("%H:%M:%S")
            return u
    except Exception as e:  # noqa
        print(f"[bridge] provider uskey 获取失败 ({url}): {e}", file=sys.stderr, flush=True)
        return None


def live_uskey() -> str | None:
    """按 uskey_source 决定当前 uskey：
      provider -> 每请求向 :4607 取新值（失败时回退 mitm 捕获/config）
      mitm     -> 用运行时捕获值（需 Marvis 常驻）
      config   -> 用 config.toml 固定值（通常已失效）
    """
    src = _uskey_source()
    if src == "provider":
        return _fetch_provider_uskey() or LIVE["uskey"] or CFG["marvis"].get("uskey")
    if src == "mitm":
        return LIVE["uskey"] or CFG["marvis"].get("uskey")
    return CFG["marvis"].get("uskey")


def live_token() -> str:
    return LIVE["access_token"] or CFG["marvis"]["access_token"]


def live_openid() -> str:
    return LIVE["openid"] or CFG["marvis"]["openid"]


def builtin_headers(cfg: dict) -> dict[str, str]:
    """构造 Marvis 上游要求的鉴权头（抓包还原）。uskey/token 用运行时最新值。"""
    m = cfg["marvis"]
    ext = {
        "qimei36": m["device_guid"],
        "osVersion": m["os_version"],
        "guid": m["device_guid"],
        "uskey": live_uskey() or "",
        "nonce": str(uuid.uuid4()),
        "reqScene": 0,
        "taskType": "user",
        "clientVersion": m["client_version"],
        "clientPlatform": m["client_platform"],
        "clientPlatformVersion": m["client_platform_version"],
        "isIoa": False,
    }
    rid = "resp_" + uuid.uuid4().hex
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # 与真实客户端一致的 UA（服务端可能据此识别）
        "User-Agent": "AsyncOpenAI/Python 2.32.0",
        "X-Stainless-Lang": "python",
        "X-Stainless-Package-Version": "2.32.0",
        "X-Stainless-OS": "MacOS",
        "X-Stainless-Arch": "arm64",
        "X-Stainless-Runtime": "CPython",
        "X-Stainless-Runtime-Version": "3.11.9",
        "X-Stainless-Async": "async:asyncio",
        "X-Stainless-Raw-Response": "true",
        "x-stainless-retry-count": "0",
        "x-stainless-read-timeout": "600.0",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        # 占位 Authorization（真实鉴权走 Ual-Access-*）
        "Authorization": "Bearer placeholder",
        # ---- 核心鉴权（优先运行时捕获值）----
        "Ual-Access-Openid": live_openid(),
        "Ual-Access-Access-Token": live_token(),
        "Ual-Access-Login-Type": m["login_type"],
        "Ual-Access-Guid": m["device_guid"],
        "X-Device-GUID": m["device_guid"],
        "Ual-Access-MarvisExt": json.dumps(ext, ensure_ascii=False, separators=(",", ":")),
        # ---- 场景/关联 ----
        "Marvis-AgentTag": "main",
        "Marvis-Scene": "agent_chat",
        "Marvis-Protocol-Version": "1000",
        "Marvis-Conversation-ID": "conv_" + uuid.uuid4().hex,
        "Marvis-Response-ID": rid,
        "Ual-Access-Requestid": rid,
    }


# ---------------------------------------------------------------- routes
@app.get("/v1/models")
async def list_models() -> JSONResponse:
    """Marvis 不暴露模型注册表（云端返回空），这里给出协议实测到的可用模型。"""
    now = int(time.time())
    models = [
        # 主对话（服务端默认路由）
        ("main-auto", "auto", "Marvis 主对话（服务端路由）"),
        ("default", "auto", "Marvis 默认档"),
        # 实测上游真实模型（供显式指定时尝试）
        ("ark_deepseek-v4-flash-ga-260731", "deepseek", "DeepSeek V4 Flash (火山ARk)"),
        ("hy3", "hunyuan", "腾讯混元 Hy3"),
        ("deepseek-v4-pro-external", "deepseek", "DeepSeek V4 Pro (external)"),
    ]
    return JSONResponse(
        {
            "object": "list",
            "data": [
                {"id": mid, "object": "model", "created": now, "owned_by": owner, "description": desc}
                for mid, owner, desc in models
            ],
        }
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    return await _proxy_chat(body)


@app.post("/chat/completions")  # 兼容不带 /v1 的客户端
async def chat_completions_nov1(request: Request):
    body = await request.json()
    return await _proxy_chat(body)


async def _proxy_chat(body: dict) -> Any:
    cfg = CFG["marvis"]
    headers = builtin_headers(CFG)
    url = cfg["base_url"].rstrip("/") + cfg["chat_path"]

    # 补齐关键参数（默认与真实客户端一致）
    body.setdefault("model", cfg.get("default_model", "main-auto"))
    body.setdefault("stream", True)
    body.setdefault("temperature", 1)
    body.setdefault("max_tokens", 32000)
    body.setdefault("thinking_enabled", True)
    if body.get("stream"):
        body.setdefault("stream_options", {"include_usage": True})

    if CFG.get("marvis", {}).get("debug"):
        print(f"[bridge] -> {url} model={body.get('model')} stream={body.get('stream')} "
              f"msgs={len(body.get('messages', []))} tools={len(body.get('tools', []))}", flush=True)

    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    if not body.get("stream"):
        resp = await client.post(url, headers=headers, json=body)
        await client.aclose()
        return _to_openai_response(resp)

    async def gen():
        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    raw = await resp.aread()
                    err = raw.decode("utf-8", "replace")
                    print(f"[bridge] upstream {resp.status_code}: {err[:500]}", file=sys.stderr, flush=True)
                    yield f"data: {json.dumps({'error': {'message': err, 'type': 'upstream_error', 'code': resp.status_code}}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                # 原样透传上游 SSE（已是标准 OpenAI 格式）
                async for line in resp.aiter_lines():
                    if line == "":
                        continue
                    yield line + "\n\n"
        finally:
            await client.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})


def _to_openai_response(resp: httpx.Response) -> JSONResponse:
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text, "type": "upstream_error", "code": resp.status_code}}
    return JSONResponse(data, status_code=resp.status_code)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "upstream": CFG["marvis"]["base_url"] + CFG["marvis"]["chat_path"],
        "uskey_source": _uskey_source(),
        "uskey_live": bool(LIVE["uskey"]),
        "uskey_len": len(LIVE["uskey"] or "") if LIVE["uskey"] else None,
        "uskey_updated_at": LIVE["updated_at"],
    }


@app.get("/uskey")
async def uskey_status():
    """查看当前捕获的凭证状态。"""
    u = live_uskey() or ""
    return {
        "has_uskey": bool(u),
        "uskey_prefix": u[:12],
        "uskey_len": len(u),
        "source": "live" if LIVE["uskey"] else "config",
        "updated_at": LIVE["updated_at"],
        "openid": live_openid(),
        "token_tail": (live_token() or "")[-6:],
    }


@app.post("/_ingest")
async def ingest(request: Request):
    """mitmproxy addon 回调：写入最新捕获的凭证。"""
    data = await request.json()
    if data.get("uskey"):
        LIVE["uskey"] = data["uskey"]
        LIVE["access_token"] = data.get("access_token") or LIVE["access_token"]
        LIVE["openid"] = data.get("openid") or LIVE["openid"]
        LIVE["guid"] = data.get("guid") or LIVE["guid"]
        LIVE["updated_at"] = time.strftime("%H:%M:%S")
        print(f"[extractor] 捕获 uskey ({len(LIVE['uskey'])}B) @ {LIVE['updated_at']}", flush=True)
    return {"ok": True, "uskey_len": len(LIVE["uskey"] or "")}


# ---------------------------------------------------------------- mitm 提取器（外部 mitmdump 子进程）
def start_uskey_extractor(proxy_port: int):
    """spawn mitmdump 子进程, 加载 uskey_addon.py, 旁听客户端流量。
    （mitmproxy 是独立打包 app, 不能在同一 python 进程 import）"""
    import shutil
    import subprocess

    mitmdump = shutil.which("mitmdump") or "/opt/homebrew/bin/mitmdump"
    addon = str(ROOT / "uskey_addon.py")
    if not Path(mitmdump).exists():
        print("[extractor] 未找到 mitmdump, uskey 提取器未启动", flush=True)
        return None

    proc = subprocess.Popen(
        [mitmdump, "-q", "-s", addon, "-p", str(proxy_port), "--set", "flow_detail=0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    print(f"[extractor] mitmdump 子进程 pid={proc.pid} 监听 :{proxy_port}", flush=True)
    return proc


# ---------------------------------------------------------------- main
def main():
    global CFG
    ap = argparse.ArgumentParser(description="Marvis Bridge")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-extractor", action="store_true", help="不启动 uskey 提取器")
    args = ap.parse_args()

    CFG = load_config(Path(args.config))
    host = args.host or CFG["marvis"]["host"]
    port = args.port or int(CFG["marvis"]["port"])
    proxy_port = int(CFG["marvis"].get("proxy_port", 4606))

    print(f"[bridge] Marvis Bridge on http://{host}:{port}/v1")
    print(f"[bridge] upstream = {CFG['marvis']['base_url']}{CFG['marvis']['chat_path']}")
    print(f"[bridge] uskey_source = {_uskey_source()}")

    # 仅 mitm 模式需要启动 mitmdump 提取器；provider 模式无需 Marvis 常驻
    if not args.no_extractor and _uskey_source() == "mitm":
        start_uskey_extractor(proxy_port)

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    CFG = load_config(CONFIG_PATH)
    main()
