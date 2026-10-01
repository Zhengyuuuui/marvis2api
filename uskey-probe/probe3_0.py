#!/usr/bin/env python3
"""Phase 3.0 — determine what uskey is actually validated for.

Test matrix (each cell uses a fresh value to avoid replay interference):
  a) 32B pure-random base64
  b) "CiDVDCER" + random tail
  c) real offline-generated uskey
  d) constant uskey but fresh Ual-Access-Requestid per request
  e) same uskey + fresh requestid, 5x  -> replay/risk-control binding test

Usage: python3 probe3_0.py <q36>   (q36 = <YOUR_DEVICE_GUID>)
"""
import base64, json, os, random, string, sys, time, uuid
import httpx

TOKEN = os.environ.get("MARVIS_TOKEN", "mv_<YOUR_TOKEN>")
OPENID = os.environ.get("MARVIS_OPENID", "oAN1<YOUR_OPENID>")
GUID = os.environ.get("MARVIS_GUID", "<YOUR_DEVICE_GUID>")
Q36 = sys.argv[1] if len(sys.argv) > 1 else GUID
URL = "https://yybadaccess.3g.qq.com/v1/chat/completions"


def hdrs(uskey, reqid=None, scene="agent_chat"):
    rid = reqid or ("resp_" + uuid.uuid4().hex)
    ext = {
        "qimei36": Q36, "osVersion": "macOS-15.6.1-arm64-arm-64bit", "guid": GUID,
        "uskey": uskey, "nonce": str(uuid.uuid4()), "reqScene": 0, "taskType": "user",
        "clientVersion": "1.0.0.10371", "clientPlatform": "Mac",
        "clientPlatformVersion": "1.0.0.10634", "isIoa": False,
    }
    return {
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "AsyncOpenAI/Python 2.32.0", "Authorization": "Bearer placeholder",
        "Ual-Access-Openid": OPENID, "Ual-Access-Access-Token": TOKEN,
        "Ual-Access-Login-Type": "6", "Ual-Access-Guid": GUID, "X-Device-GUID": GUID,
        "Ual-Access-MarvisExt": json.dumps(ext, ensure_ascii=False, separators=(",", ":")),
        "Marvis-AgentTag": "main", "Marvis-Scene": scene, "Marvis-Protocol-Version": "1000",
        "Marvis-Conversation-ID": "conv_" + uuid.uuid4().hex,
        "Marvis-Response-ID": rid, "Ual-Access-Requestid": rid,
    }


BODY = {"model": "main-auto", "messages": [{"role": "user", "content": "hi"}],
        "stream": False, "temperature": 1, "max_tokens": 8, "thinking_enabled": False}


def call(label, uskey, reqid=None):
    try:
        r = httpx.post(URL, headers=hdrs(uskey, reqid), json=BODY, timeout=60)
        code = ""
        if r.status_code != 200:
            try:
                code = r.json().get("code")
            except Exception:
                pass
        print(f"[{label:34s}] HTTP {r.status_code} code={code} model={r.headers.get('marvis-actual-model')}")
        return r.status_code, code
    except Exception as e:
        print(f"[{label:34s}] EXC {e}")
        return None, str(e)


def rnd_b64(nbytes=32):
    return base64.b64encode(os.urandom(nbytes)).decode()


def rnd_tail(n=330):
    return "".join(random.choices(string.ascii_letters + string.digits + "+/", k=n))


if __name__ == "__main__":
    print("== 3.0 matrix ==")
    # a) pure random base64
    for i in range(2):
        call(f"a{i} pure-random-b64(32B)", rnd_b64(32))
        time.sleep(0.6)
    # b) CiDVDCER + random tail
    for i in range(2):
        call(f"b{i} CiDVDCER+randtail", "CiDVDCER" + rnd_tail())
        time.sleep(0.6)
    # c) real offline (read file)
    off = open("/tmp/offline_uskey.txt").read().strip()
    call("c0 offline-real(992)", off)
    time.sleep(0.6)
    # d) constant uskey, fresh requestid, 5x
    const = "CiDVDCER" + rnd_tail()
    for i in range(5):
        call(f"d{i} const-uskey+fresh-reqid", const)
        time.sleep(0.6)
