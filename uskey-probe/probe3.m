// probe3.m — Phase 1 (H1/H2): offline uskey experiment, ObjC @try-guarded
// Recovered signatures (see findings.md):
//   void*  UKInstanceGetDefault(void)
//   void   UKInstanceInit(void* inst, const char* appkey, const char* appver)
//   char*  UKInstanceGetUSkey(void* inst, const char* bus_id, const char* q36, const char* businfo)
//          [arg order confirmed via ObjC selector gukWithQimeiAppkey:appVer:bus_id:q36:businfo:]
//   void   UKInstanceFreeUskey(char* p)
// Build: clang -O1 -framework Foundation probe3.m -o probe3
// Run:   DYLD_FRAMEWORK_PATH=$HOME/marvis-bridge/marvis-copy ./probe3 <q36>
#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef void* (*fn_get_default)(void);
typedef void  (*fn_init)(void*, const char*, const char*);
typedef char* (*fn_get_uskey)(void*, const char*, const char*, const char*);
typedef void  (*fn_free)(char*);

static const char* APPKEY = "0MAC06Y3ZMNM1MH4";
static const char* APPVER = "1.0.0.10634";

static void show(const char* label, char* p) {
    if (!p) { printf("[%s] => NULL\n", label); return; }
    size_t n = strlen(p);
    printf("[%s] => len=%zu prefix='%.16s'\n", label, n, p);
    if (n <= 400) printf("[%s] full='%s'\n", label, p);
    else printf("[%s] head='%.100s' tail='%s'\n", label, p, p + n - 40);
}

static char* safe_call(fn_get_uskey f, void* inst, const char* a, const char* b, const char* c) {
    char* r = nil;
    @try {
        r = f(inst, a, b, c);
    } @catch (NSException* e) {
        printf("  !! NSException: %s (%s)\n", e.name.UTF8String, e.reason.UTF8String);
        return nil;
    }
    return r;
}

int main(int argc, char** argv) {
    const char* q36 = (argc > 1) ? argv[1] : "<YOUR_DEVICE_GUID>";
    const char* dylib = getenv("BEACON_DYLIB");
    if (!dylib) dylib = "bin/libbeacon_wrapper.dylib";

    @try {
        void* h = dlopen(dylib, RTLD_NOW | RTLD_LOCAL);
        if (!h) { printf("dlopen FAILED: %s\n", dlerror()); return 1; }
        printf("dlopen OK: %s\n", dylib);

        fn_get_default get_default = (fn_get_default)dlsym(h, "UKInstanceGetDefault");
        fn_init init = (fn_init)dlsym(h, "UKInstanceInit");
        fn_get_uskey get_uskey = (fn_get_uskey)dlsym(h, "UKInstanceGetUSkey");
        fn_free free_u = (fn_free)dlsym(h, "UKInstanceFreeUskey");
        if (!get_default || !init || !get_uskey || !free_u) { printf("missing symbols\n"); return 2; }

        void* inst = get_default();
        printf("inst=%p\n", inst);
        @try { init(inst, APPKEY, APPVER); } @catch (NSException* e) {
            printf("init exception: %s\n", e.reason.UTF8String); return 3;
        }
        printf("init done (appkey=%s appver=%s)\n", APPKEY, APPVER);

        char* r;
        r = safe_call(get_uskey, inst, "marvis_client", q36, "");
        show("case1 bus_id=marvis_client q36=real businfo=empty", r); if (r) free_u(r);

        r = safe_call(get_uskey, inst, "marvis_client", q36, "{}");
        show("case2 businfo={}", r); if (r) free_u(r);

        r = safe_call(get_uskey, inst, "marvis_client", q36,
                      "{\"os\":\"macOS\",\"model\":\"Mac\"}");
        show("case3 businfo=json", r); if (r) free_u(r);

        r = safe_call(get_uskey, inst, "marvis_client", q36, "");
        show("case4 repeat case1 (freshness)", r); if (r) free_u(r);
    } @catch (NSException* e) {
        printf("FATAL exception: %s (%s)\n", e.name.UTF8String, e.reason.UTF8String);
        return 4;
    }
    printf("probe done\n");
    return 0;
}
