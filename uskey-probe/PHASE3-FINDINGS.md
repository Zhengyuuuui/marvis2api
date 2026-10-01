# Phase 3 Findings — uskey validation semantics + independent provider

## 3.0 What is actually validated? (matrix, each cell fresh uskey)
| cell | uskey | spacing | result |
|---|---|---|---|
| a | 32B pure random base64 | 0.6s | 200, 200 |
| b | "CiDVDCER"+random tail | 0.6s | 200, 200 |
| c | offline-real (992B) | - | 200 |
| d | constant uskey + fresh reqid | 0.6s x5 | 200 x5 |
| e | SAME uskey, fresh reqid | 0.15s x6 | 200,200,403,403,403,403 |
| G | FRESH uskey each | 0.15s x6 | 200 x6 |
| H | SAME uskey | 3s x5 | 200 x5 |
| f | same uskey + same reqid | 0.15s | 403 immediately |

### VERDICT = 真相A
- uskey **content is NOT signature-validated**: pure random / prefixed-random / empty all pass.
- The 4100404 is a **per-uskey freshness/rate limit**: reusing the same uskey value faster than
  ~1 per >1s (or >2 uses in a tight window) -> risk control. Spacing out, or using a fresh value
  each request, always passes.
- => A per-request UNIQUE uskey is required; its content does not matter (currently).

## 3.1 Provider
Primary = **beacon mode** (real uskey via dylib), fallback = random.
- `uskey-probe/uskey-gen.m` -> `uskey-gen`: one-shot ObjC generator, process-isolated,
  handles first-call IOKit NSException with @try retry. 20/20 success, 992B, prefix CiDVDCER.
- `uskey_provider.py`: FastAPI on :4607, `GET /uskey` spawns uskey-gen per request (isolation),
  returns {"uskey","len","source"}. `USKEY_MODE=random` for dylib-free mode.
  - beacon mode: fresh 992B real uskey each call (fresh tail)
  - random mode: prefix CiDVDCER + random 240B
- Provider-generated uskeys: 6/6 HTTP 200 upstream.

## 3.2 bridge integration
- `uskey_source = provider|mitm|config` (config.toml, default provider)
- provider mode: bridge calls :4607/uskey per request (fresh uskey each time)
- mitm extractor only started when uskey_source == mitm
- deploy.sh / undeploy.sh added.

## ACCEPTANCE (Marvis GUI closed)
- Closed Marvis.app (Electron + helpers + MarvisHost gone; only background MarvisService remained).
- provider still generated beacon uskey (992B).
- bridge: **25/25 HTTP 200** (goal >=3). Full non-stream completion returned
  model=ark_deepseek-v4-flash-ga-260731.

## Files
- uskey_provider.py, uskey-probe/uskey-gen.m (+ binary), bridge.py (modified), config.toml (modified),
  deploy.sh, undeploy.sh
