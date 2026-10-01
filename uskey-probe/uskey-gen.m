// uskey-gen.m — one-shot uskey generator (process-isolated).
// dlopen libbeacon_wrapper.dylib, init, GetUSkey (with @try retry), print uskey to stdout.
//
// Build:  clang -O2 -framework Foundation uskey-gen.m -o uskey-gen
// Usage:  ./uskey-gen [q36] [businfo] [bus_id] [dylib]
//   env:  BEACON_DYLIB, USKEY_APPKEY, USKEY_APPVER
// Exit:   0 = ok (uskey on stdout), non-zero = failure.
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef void* (*fn_gd)(void);
typedef void  (*fn_i)(void*, const char*, const char*);
typedef char* (*fn_gu)(void*, const char*, const char*, const char*);
typedef void  (*fn_f)(char*);

int main(int argc, char** argv) {
    const char* dylib   = getenv("BEACON_DYLIB");
    const char* appkey  = getenv("USKEY_APPKEY"); if (!appkey) appkey = "0MAC06Y3ZMNM1MH4";
    const char* appver  = getenv("USKEY_APPVER"); if (!appver) appver = "1.0.0.10634";
    const char* q36     = (argc > 1) ? argv[1] : "<YOUR_DEVICE_GUID>";
    const char* businfo = (argc > 2) ? argv[2] : "{}";
    const char* bus_id  = (argc > 3) ? argv[3] : "marvis_client";
    if (argc > 4) dylib = argv[4];
    if (!dylib) dylib = "libbeacon_wrapper.dylib";

    @try {
        void* h = dlopen(dylib, RTLD_NOW | RTLD_LOCAL);
        if (!h) { fprintf(stderr, "dlopen failed: %s\n", dlerror()); return 1; }

        fn_gd gd = (fn_gd)dlsym(h, "UKInstanceGetDefault");
        fn_i  in = (fn_i) dlsym(h, "UKInstanceInit");
        fn_gu gu = (fn_gu)dlsym(h, "UKInstanceGetUSkey");
        fn_f  fr = (fn_f) dlsym(h, "UKInstanceFreeUskey");
        if (!gd || !in || !gu || !fr) { fprintf(stderr, "missing symbols\n"); return 2; }

        void* inst = gd();
        in(inst, appkey, appver);

        for (int n = 0; n < 3; n++) {
            char* r = nil;
            @try { r = gu(inst, bus_id, q36, businfo); }
            @catch (NSException* e) { continue; }   // 首次 IOKit 竞态，重试
            if (r && r[0]) { fputs(r, stdout); return 0; }
        }
        fprintf(stderr, "GetUSkey returned empty after retries\n");
        return 3;
    } @catch (NSException* e) {
        fprintf(stderr, "fatal: %s\n", e.reason.UTF8String);
        return 4;
    }
}
