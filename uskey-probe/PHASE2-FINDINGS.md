# Phase 2 Findings — uskey real-param cross-check + server acceptance

## 2.0 Real capture cross-check
Source: sessions/2026-09-30-marvis/artifacts/flows-full-with-tools.jsonl (line 1, /v1/chat/completions)
- Real uskey len = 332 (base64) -> 248 bytes
- Offline uskey len = 992 (base64) -> 744 bytes
- Both prefixes `CiDVDCER`; base64-decoded both start `0a 20 d5 0c 21 11` (TLV: field=0x0a len=0x20 + 32 bytes)
- First 4 raw bytes `d5 0c 21 11` identical => deterministic device component
- Real MarvisExt: qimei36 == guid == <YOUR_DEVICE_GUID> (SAME as what offline probe used)
- => length differs (992 vs 332) but both accepted by server (see 2.1). Interpretation: uskey embeds a variable-size TLV blob (businfo/audit extras); server does not require a specific length.

## 2.1 Server acceptance (DECISIVE) — SUCCESS
Headers copied from real capture; only uskey substituted.
Control matrix (POST https://yybadaccess.3g.qq.com/v1/chat/completions):
- OFFLINE uskey (fresh, 992B) x3 -> HTTP 200 (Marvis-Actual-Model=ark_deepseek-v4-flash-ga-260731)
- OFFLINE uskey fresh loop x8 -> 8/8 HTTP 200
- memory scene + offline uskey -> HTTP 200 (actual-model=hy3)
- bad token control -> HTTP 401 {code 4100403 登录态过期/未登录}   (token IS enforced)
- corrupted/empty/short/random uskey -> HTTP 200 initially (see replay)
- REPLAY same uskey: 200,200,403,403,403,403 -> {code 4100404 风控拦截}
  => uskey freshness IS enforced: reusing the same uskey >2x triggers 4100404.
  => our generator produces a unique uskey per call (fresh tail) => accepted.

VERDICT: T-A confirmed. Offline-generated uskey works end-to-end. Phase 2.2 (lldb) NOT needed.

## Nuance / correction to SPEC premise
- 4100404 is triggered by *replay of a fixed uskey*, not by a single use of an invalid uskey.
- Server currently does not validate uskey signature strictly (empty/garbage also pass once),
  but freshness matters. Keep per-request fresh uskey (provider design already does).
