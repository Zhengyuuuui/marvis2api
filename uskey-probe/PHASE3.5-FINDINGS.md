# Phase 3.5 Findings — mechanism pinning + robustness

## 3.5.1 uniqueness window boundary (same uskey + fresh requestid, 3 sends each)
| interval | result |
|---|---|
| 5s   | 200,200,200  ok |
| 15s  | 200,200,200  ok |
| 60s  | 200,200,200  ok |
| 300s | 200,200,200  ok |
| (0.1s/0.2s/0.3s/0.5s x5, re-test) | all 200 |

Earlier failures:
- e: same uskey 0.15s x6 -> 200,200,403,403,403,403
- f: same uskey + SAME requestid -> 403 immediately

### Verdict
There is NO fixed "N uses per uskey" or fixed time-window rule we could pin deterministically.
4100404 behaves as an ADAPTIVE account/session-level risk heuristic:
- triggered during a burst of many rapid requests (regardless of uskey), then it COOLS DOWN
  (the exact same 0.15s pattern that failed earlier later passed at 0.1s).
- same-requestid true replay correlates with immediate 403.
Practical rule: keep a FRESH unique uskey per request and normal pacing -> stable.
=> Do NOT downgrade to a cached/reused uskey. Every-request-unique is required in practice.

## 3.5.2 random-uskey persistence (content not validated)
- 50 sends, each a UNIQUE pure-random "CiDVDCER"+random -> 50/50 HTTP 200.
=> Current state: uskey content is not signature-validated.
【脆弱假设 / FRAGILE】服务端可能随时收紧内容校验；因此 provider 默认 beacon 模式
（真实 uskey），random 仅作降级。

## 3.5.3 provider robustness
- beacon (uskey-gen) 200 consecutive runs: ok=200 bad=0 (100%)
- fresh-process first-call (IOKit NSException path) 30/30 success (retry always covers)
- concurrency: 10 parallel /uskey -> 10/10 ok, 10/10 unique tails, wall=0.49s (subprocess isolation, no race)
- crash recovery: kill provider -> deploy.sh restart -> recovered (len 992 src beacon)

## Net conclusion
- provider (beacon) is robust: 100% gen, safe under concurrency, self-healing on restart.
- bridge uskey_source=provider with per-request fresh uskey is the correct design.
- random mode is a viable fallback given current server behavior, but flagged FRAGILE.
