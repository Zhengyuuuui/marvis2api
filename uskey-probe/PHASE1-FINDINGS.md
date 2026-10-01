# Phase 1 Findings — H1 verdict

## Corrected API signatures (from disassembly)
- `void*  UKInstanceGetDefault(void)`  — returns ptr to global singleton
- `void   UKInstanceInit(void* inst, const char* appkey, const char* appver)`  — returns void
- `char*  UKInstanceGetUSkey(void* inst, const char* bus_id, const char* q36, const char* businfo)`
  — RETURNS a malloc'd C string (NOT an out-param). Free with UKInstanceFreeUskey.
  arg order confirmed by ObjC selector `gukWithQimeiAppkey:appVer:bus_id:q36:businfo:`
- `void   UKInstanceFreeUskey(char* p)`

## Experiment (offline + fresh HOME)
Cmd:  sandbox-exec -f net-deny.sb ./probe3   (deny network*, verified: curl exit 6 inside; 501 outside)
      plus HOME=<empty temp dir>
Result: uskey generated, len=992, prefix CiDVDCER (matches mitm capture prefix)
- head ~100 chars DETERMINISTIC across online/offline/fresh-HOME runs
- tail varies per call (random nonce)
- fresh HOME + network denied  =>  no dependency on cached audit state, no network needed

## Notes / gotchas
- businfo must be a JSON string ("{}" ok); "" -> NSException (caught)
- FIRST GetUSkey call throws IOKit NSException (lazy init race); retry succeeds deterministically.
- appkey=0MAC06Y3ZMNM1MH4, appver=1.0.0.10634 work.
- generated uskey len=992 vs captured live uskey len=332 — param/businfo difference; to reconcile in Phase 2.
