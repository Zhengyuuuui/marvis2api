#!/usr/bin/env python3
"""
uskey_provider — 独立 uskey 生成服务（无需 Marvis GUI）

原理（Phase 1-3 逆向结论，见 uskey-probe/PHASE1-FINDINGS.md / PHASE2-FINDINGS.md）：
  dlopen(libbeacon_wrapper.dylib)
    UKInstanceGetDefault() -> inst
    UKInstanceInit(inst, appkey, appver)               # void
    UKInstanceGetUSkey(inst, bus_id, q36, businfo)      # -> malloc'd char*（每次调用值不同）
    UKInstanceFreeUskey(p)
  首次 GetUSkey 会抛 IOKit NSException（惰性初始化竞态），捕获后重试即成功。

服务：
  GET /uskey   -> {"uskey": "CiDVDCER...", "len": 992, "source": "beacon"|"random", "ts": ...}
  GET /health  -> {"status":"ok", ...}

用法：
  python3 uskey_provider.py                 # 读 config.toml，监听 config.marvis.uskey_provider_port(默认4607)
  python3 uskey_provider.py --port 4607 --mode beacon
  USKEY_MODE=random python3 uskey_provider.py     # 降级：纯随机 uskey（Phase3.0 真相A）

模式：
  beacon : dlopen dylib 生成真实 uskey（默认，最稳，内容真实）
  random : 纯随机 uskey（无 dylib 依赖；Phase3.0 实测内容不被校验，仅需每请求唯一）
"""
from __future__ import annotations

import argparse
import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.toml"

# ---- defaults (overridable by config.toml / env) ----
DEFAULT_DYLIB = str(ROOT / "marvis-copy" / "bin" / "libbeacon_wrapper.dylib")
DEFAULT_APPKEY = "0MAC06Y3ZMNM1MH4"
DEFAULT_APPVER = "1.0.0.10634"
DEFAULT_BUS_ID = "marvis_client"
DEFAULT_Q36 = "<YOUR_DEVICE_GUID>"
DEFAULT_BUSINFO = "{}"

app = FastAPI(title="Marvis uskey provider", version="1.0.0")
STATE: dict[str, Any] = {"uskey": None, "source": None, "ts": None, "err": None}


# ---------------------------------------------------------------- beacon backend
# 通过一次性子进程 uskey-gen 调用 dylib：隔离首次调用的 ObjC/IOKit 异常（会崩溃进程），
# 且避免把不稳定的 dylib 加载进常驻服务进程。
class Beacon:
    """以子进程方式调用 libbeacon_wrapper.dylib 生成真实 uskey。"""

    def __init__(self, gen_bin: str, dylib: str, appkey: str, appver: str):
        self.gen_bin = gen_bin
        self.dylib = dylib
        self.appkey = appkey
        self.appver = appver

    def uskey(self, bus_id: str, q36: str, businfo: str, timeout: float = 20.0) -> str:
        import subprocess

        if not Path(self.gen_bin).exists():
            raise RuntimeError(f"uskey-gen not found: {self.gen_bin}")
        env = dict(os.environ)
        env["BEACON_DYLIB"] = self.dylib
        env["USKEY_APPKEY"] = self.appkey
        env["USKEY_APPVER"] = self.appver
        # uskey-gen 需要 DYLD_FRAMEWORK_PATH 找不到时，靠 bin/ 内的 framework 回退
        env.setdefault("DYLD_FRAMEWORK_PATH", str(Path(self.dylib).resolve().parent.parent))
        try:
            p = subprocess.run([self.gen_bin, q36, businfo, bus_id],
                               capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            raise RuntimeError("uskey-gen timeout")
        s = (p.stdout or "").strip()
        if p.returncode != 0 or not s:
            raise RuntimeError(f"uskey-gen rc={p.returncode} err={(p.stderr or '').strip()[:200]}")
        return s


_BEACON: Beacon | None = None


def gen_random(prefix: str = "CiDVDCER") -> str:
    tail = base64.b64encode(os.urandom(240)).decode().rstrip("=")
    return prefix + tail


def make_uskey(cfg: dict, mode: str) -> tuple[str, str]:
    m = cfg.get("marvis", {})
    bus_id = m.get("uskey_bus_id", DEFAULT_BUS_ID)
    q36 = m.get("uskey_q36") or m.get("device_guid") or DEFAULT_Q36
    businfo = m.get("uskey_businfo", DEFAULT_BUSINFO)

    if mode == "random":
        return gen_random(), "random"

    global _BEACON
    if _BEACON is None:
        gen_bin = os.environ.get("USKEY_GEN", m.get("uskey_gen", str(ROOT / "uskey-probe" / "uskey-gen")))
        _BEACON = Beacon(
            gen_bin=gen_bin,
            dylib=os.environ.get("BEACON_DYLIB", m.get("beacon_dylib", DEFAULT_DYLIB)),
            appkey=os.environ.get("USKEY_APPKEY", m.get("uskey_appkey", DEFAULT_APPKEY)),
            appver=os.environ.get("USKEY_APPVER", m.get("uskey_appver", DEFAULT_APPVER)),
        )
    return _BEACON.uskey(bus_id, q36, businfo), "beacon"


# ---------------------------------------------------------------- http
@app.get("/uskey")
async def uskey_endpoint():
    mode = STATE.get("mode", "beacon")
    try:
        u, src = make_uskey(STATE["cfg"], mode)
        STATE.update(uskey=u, source=src, ts=time.strftime("%H:%M:%S"), err=None)
        return {"uskey": u, "len": len(u), "source": src, "ts": STATE["ts"]}
    except Exception as e:
        STATE.update(err=str(e), ts=time.strftime("%H:%M:%S"))
        code = 503
        # 若 beacon 失败，按配置回退 random（可用 fallback_random=false 关闭）
        if STATE["cfg"].get("marvis", {}).get("uskey_fallback_random", True):
            u = gen_random()
            STATE.update(uskey=u, source="random(fallback)", err=str(e))
            return {"uskey": u, "len": len(u), "source": "random(fallback)", "error": str(e)}
        return JSONResponse({"error": str(e)}, status_code=code)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mode": STATE.get("mode"),
        "last_source": STATE.get("source"),
        "last_len": len(STATE["uskey"] or "") if STATE.get("uskey") else None,
        "last_ts": STATE.get("ts"),
        "last_err": STATE.get("err"),
    }


def load_config(path: Path) -> dict:
    if path.exists():
        with path.open("rb") as f:
            return tomllib.load(f)
    return {}


def main():
    ap = argparse.ArgumentParser(description="Marvis uskey provider")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--mode", choices=["beacon", "random"], default=None)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    m = cfg.get("marvis", {})
    host = args.host or m.get("uskey_provider_host", "127.0.0.1")
    port = args.port or int(m.get("uskey_provider_port", 4607))
    mode = args.mode or os.environ.get("USKEY_MODE", m.get("uskey_mode", "beacon"))

    STATE["cfg"] = cfg
    STATE["mode"] = mode
    print(f"[provider] uskey_provider on http://{host}:{port}/uskey  mode={mode}", flush=True)

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
