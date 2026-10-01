# Phase 3.6 Findings — separating uskey vs requestid contribution

IMPORTANT correction discovered during 3.6:
- The 401 {code:4100403 "登录态过期/未登录"} seen in early 3.6 C/D was NOT token expiry.
  The token (mv_...jzZ8Gx) still returns 200 after cooldown. => 4100403 here was a
  TEMPORARY account risk-control/lockdown state (same family as 4100404), triggered by
  my own heavy prior burst testing. Interpreting codes:
    * 401/4100403  -> not necessarily expiry; can be temporary lockdown / or real expiry
    * 403/4100404  -> risk control (request blocked)

## Clean-state matrix (account had cooled down; each cell preceded by a 200 baseline)
| cell | design | spacing | result |
|---|---|---|---|
| A | same-uskey + FRESH-reqid | 0.3s x10 | 200 x10 |
| B | FRESH-uskey + SAME-reqid | 0.3s x10 | 200 x10 |
| C | same-uskey + same-reqid | 60s x3 | 200 x3 |
| D | reproduce early e (same-uskey x6) | 0.15s x3 rounds | 200 x18 (no repro) |
| F | same-uskey + same-reqid | 0.2s x6 | 200 x6 |
| BURST | FRESH-uskey each | no sleep x30 | 200 x30 |

Historical failures (during/after heavy burst):
- e : same-uskey 0.15s x6 -> 200,200,403,403,403,403
- f : same-uskey + same-reqid -> 403 immediately
- replay: same-uskey -> 200,200,403,403,403,403

## VERDICT
- Neither uskey identity ALONE nor requestid identity ALONE causes 403 (cells A, B passed).
- Same-uskey+same-reqid does NOT permanently dedup (cell C passed after 60s; cell F passed).
- Early failures did NOT reproduce on a clean account => they were an ADAPTIVE
  account-level risk/lockdown state, strongly correlated with cumulative burst volume
  from repeated identical requests over a session, and it COOLS DOWN.
- => There is no fixed uniqueness key we can exploit or must avoid; the safe invariant is:
      **每请求唯一 uskey（+ 每请求唯一 requestid）+ 正常节奏**

## Final rule for provider
provider must return a value that is UNIQUE per request (fresh tail). requestid is already
per-request-unique in bridge. With that, no 403/401 observed, including 30x no-sleep burst.

## Fragility note (unchanged)
uskey content is currently not signature-validated (see 3.5.2). Default provider = beacon
(real uskey); random = fallback.
