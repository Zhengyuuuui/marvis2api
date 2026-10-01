#!/usr/bin/env python3
"""3.5.1 uniqueness window boundary.

For each interval I in [5,15,60,300]: pick ONE fresh uskey, send 3 requests spaced I seconds.
Record status of each. If any 403 (4100404) => window/limit within I.
"""
import sys, time
sys.path.insert(0, "/tmp")
import accept_test as at  # noqa  (uses TOKEN/URL/hdrs/post)
import probe3_0 as p
import base64, os

def fresh():
    return "CiDVDCER" + base64.b64encode(os.urandom(120)).decode().rstrip("=")

def run(interval, n=3):
    u = fresh()
    print(f"--- interval={interval}s uskey_tail={u[-10:]} ---")
    res = []
    for i in range(n):
        st, code = at.post(f"I{interval}s#{i}", u)
        res.append(st)
        if i < n-1:
            time.sleep(interval)
    ok = all(s == 200 for s in res)
    print(f"    => {res}  unique_window_ok={ok}")
    return ok

if __name__ == "__main__":
    ivs = [int(x) for x in sys.argv[1:]] or [5, 15, 60, 300]
    for iv in ivs:
        run(iv)
