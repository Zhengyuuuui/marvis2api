#!/usr/bin/env python3
"""Phase 3.6 — separate uskey vs requestid contribution (strict single-variable).

Cells:
  A) same-uskey + FRESH-reqid, burst x10 @0.3s
  B) FRESH-uskey + SAME-reqid, burst x10 @0.3s
  C) same-uskey + same-reqid, 60s x3
  D) reproduce early e (same-uskey @0.15s x6) 3 rounds
Writes full responses to /tmp/p36_<cell>.jsonl
"""
import base64, json, os, random, string, sys, time, uuid
import httpx

TOKEN = os.environ.get("MARVIS_TOKEN", "mv_<YOUR_TOKEN>")
OPENID = os.environ.get("MARVIS_OPENID", "oAN1<YOUR_OPENID>")
GUID = os.environ.get("MARVIS_GUID", "<YOUR_DEVICE_GUID>")
Q36 = GUID
URL = "https://yybadaccess.3g.qq.com/v1/chat/completions"


def rnd_uskey():
    return "CiDVDCER" + base64.b64encode(os.urandom(240)).decode().rstrip("=")


def hdrs(uskey, reqid):
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
        "Marvis-AgentTag": "main", "Marvis-Scene": "agent_chat", "Marvis-Protocol-Version": "1000",
        "Marvis-Conversation-ID": "conv_" + uuid.uuid4().hex,
        "Marvis-Response-ID": reqid, "Ual-Access-Requestid": reqid,
    }


BODY = {"model": "main-auto", "messages": [{"role": "user", "content": "hi"}],
        "stream": False, "temperature": 1, "max_tokens": 8, "thinking_enabled": False}


def send(label, uskey, reqid, fh):
    try:
        r = httpx.post(URL, headers=hdrs(uskey, reqid), json=BODY, timeout=60)
        rec = {"label": label, "status": r.status_code,
               "reqid": reqid, "uskey_tail": uskey[-8:], "body": r.text[:300]}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        code = ""
        if r.status_code != 200:
            try:
                code = r.json().get("code")
            except Exception:
                pass
        print(f"[{label:28s}] HTTP {r.status_code} code={code}")
        return r.status_code
    except Exception as e:
        fh.write(json.dumps({"label": label, "status": "EXC", "err": str(e)}) + "\n")
        print(f"[{label:28s}] EXC {e}")
        return None


def cell_A():
    print("\n== A: same-uskey + FRESH-reqid, x10 @0.3s ==")
    u = rnd_uskey()
    with open("/tmp/p36_A.jsonl", "w") as fh:
        for i in range(10):
            send(f"A#{i}", u, "resp_" + uuid.uuid4().hex, fh)
            if i < 9:
                time.sleep(0.3)


def cell_B():
    print("\n== B: FRESH-uskey + SAME-reqid, x10 @0.3s ==")
    rid = "resp_" + uuid.uuid4().hex
    with open("/tmp/p36_B.jsonl", "w") as fh:
        for i in range(10):
            send(f"B#{i}", rnd_uskey(), rid, fh)
            if i < 9:
                time.sleep(0.3)


def cell_C():
    print("\n== C: same-uskey + same-reqid, 60s x3 ==")
    u = rnd_uskey()
    rid = "resp_" + uuid.uuid4().hex
    with open("/tmp/p36_C.jsonl", "w") as fh:
        for i in range(3):
            send(f"C#{i}", u, rid, fh)
            if i < 2:
                time.sleep(60)


def cell_D():
    print("\n== D: reproduce early e (same-uskey @0.15s x6) x3 rounds ==")
    with open("/tmp/p36_D.jsonl", "w") as fh:
        for r in range(3):
            u = rnd_uskey()
            print(f"  -- round {r} uskey_tail={u[-8:]} --")
            for i in range(6):
                send(f"D{r}#{i}", u, "resp_" + uuid.uuid4().hex, fh)
                if i < 5:
                    time.sleep(0.15)
            if r < 2:
                time.sleep(5)


if __name__ == "__main__":
    which = sys.argv[1:] or ["A", "B", "C", "D"]
    for w in which:
        {"A": cell_A, "B": cell_B, "C": cell_C, "D": cell_D}[w]()
