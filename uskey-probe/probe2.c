// probe2.c — Phase 1 (H1/H2): offline uskey generation experiment
// Signatures recovered from disassembly (see findings.md):
//   void*  UKInstanceGetDefault(void)
//   void   UKInstanceInit(void* inst, const char* appkey, const char* appver)
//   char*  UKInstanceGetUSkey(void* inst, const char* bus_id, const char* businfo1, const char* businfo2)
//   void   UKInstanceFreeUskey(char* p)
// Build: clang -O1 probe2.c -o probe2
// Run:   DYLD_FRAMEWORK_PATH=$HOME/marvis-bridge/marvis-copy ./probe2 <case>
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
    else printf("[%s] head='%.120s'...tail='%s'\n", label, p, p + n - 40);
}

int main(int argc, char** argv) {
    int case_id = (argc > 1) ? atoi(argv[1]) : 0; // 0 = run all
    const char* dylib = getenv("BEACON_DYLIB");
    if (!dylib) dylib = "bin/libbeacon_wrapper.dylib";

    void* h = dlopen(dylib, RTLD_NOW | RTLD_LOCAL);
    if (!h) { printf("dlopen FAILED: %s\n", dlerror()); return 1; }
    printf("dlopen OK: %s\n", dylib);

    fn_get_default get_default = (fn_get_default)dlsym(h, "UKInstanceGetDefault");
    fn_init init = (fn_init)dlsym(h, "UKInstanceInit");
    fn_get_uskey get_uskey = (fn_get_uskey)dlsym(h, "UKInstanceGetUSkey");
    fn_free free_u = (fn_free)dlsym(h, "UKInstanceFreeUskey");
    if (!get_default || !init || !get_uskey || !free_u) {
        printf("missing symbols: %p %p %p %p\n",
               (void*)get_default, (void*)init, (void*)get_uskey, (void*)free_u);
        return 2;
    }

    void* inst = get_default();
    printf("inst=%p\n", inst);

    init(inst, APPKEY, APPVER);
    printf("init done (appkey=%s appver=%s)\n", APPKEY, APPVER);

    char* r;
    if (case_id == 0 || case_id == 1) {
        r = get_uskey(inst, "marvis_client", "", "");
        show("case1 marvis_client,empty,empty", r); free_u(r);
    }
    if (case_id == 0 || case_id == 2) {
        r = get_uskey(inst, "marvis_client", "os=macOS-15.6.1-arm64", "");
        show("case2 marvis_client,osinfo,empty", r); free_u(r);
    }
    if (case_id == 0 || case_id == 3) {
        r = get_uskey(inst, "marvis_client", "", "{\"os\":\"macOS\"}");
        show("case3 marvis_client,empty,json", r); free_u(r);
    }
    if (case_id == 0 || case_id == 4) {
        r = get_uskey(inst, "", "", "");
        show("case4 empty bus_id (expect NULL)", r); free_u(r);
    }
    if (case_id == 0 || case_id == 5) {
        r = get_uskey(inst, "marvis_client", "", "");
        show("case5 repeat case1 (freshness check)", r); free_u(r);
    }
    printf("probe done\n");
    return 0;
}
