// 尝试直接 dlopen libbeacon_wrapper.dylib 并调用 UKInstanceGetDefault/Init/GetUSkey
// 判定 uskey 能否脱离 Marvis 独立生成
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

typedef void* (*fn_get_default)(void);
typedef int   (*fn_init)(void* inst, const char* a, const char* b);
typedef void* (*fn_get_uskey)(void* inst, void* buf, const char* a, const char* b);
typedef void  (*fn_free)(void* p);

int main() {
    const char* path = "/Applications/Marvis.app/Contents/Resources/bin/libbeacon_wrapper.dylib";
    void* h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!h) { printf("dlopen FAILED: %s\n", dlerror()); return 1; }
    printf("dlopen OK\n");

    fn_get_default get_default = (fn_get_default)dlsym(h, "UKInstanceGetDefault");
    fn_init init = (fn_init)dlsym(h, "UKInstanceInit");
    fn_get_uskey get_uskey = (fn_get_uskey)dlsym(h, "UKInstanceGetUSkey");
    fn_free free_u = (fn_free)dlsym(h, "UKInstanceFreeUskey");
    printf("symbols: get_default=%p init=%p get_uskey=%p free=%p\n",
           (void*)get_default,(void*)init,(void*)get_uskey,(void*)free_u);

    if (!get_default || !init || !get_uskey) { printf("missing symbols\n"); return 2; }

    void* inst = get_default();
    printf("inst=%p\n", inst);

    // Init(appkey?, ?) —— 试两个空串
    int rc = init(inst, "0MAC06Y3ZMNM1MH4", "");
    printf("init rc=%d\n", rc);

    // GetUSkey(inst, out_buf, arg2, arg3)
    char buf[512]; memset(buf,0,sizeof buf);
    void* r = get_uskey(inst, buf, "0MAC06Y3ZMNM1MH4", "");
    printf("get_uskey ret=%p buf='%s'\n", r, buf);

    if (buf[0]) {
        // 若返回的是指针，尝试当字符串读
        if (r) printf("as string: '%s'\n", (char*)r);
    }
    return 0;
}
