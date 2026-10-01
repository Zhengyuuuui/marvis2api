#import <Foundation/Foundation.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
typedef void* (*fn_gd)(void); typedef void (*fn_i)(void*,const char*,const char*);
typedef char* (*fn_gu)(void*,const char*,const char*,const char*); typedef void (*fn_f)(char*);
int main(int c,char**v){
  void*h=dlopen("/Users/zhengyusheng/marvis-bridge/marvis-copy/bin/libbeacon_wrapper.dylib",RTLD_NOW);
  fn_gd gd=(fn_gd)dlsym(h,"UKInstanceGetDefault"); fn_i i=(fn_i)dlsym(h,"UKInstanceInit");
  fn_gu gu=(fn_gu)dlsym(h,"UKInstanceGetUSkey"); fn_f f=(fn_f)dlsym(h,"UKInstanceFreeUskey");
  void*inst=gd(); i(inst,"0MAC06Y3ZMNM1MH4","1.0.0.10634");
  const char*q=(c>1)?v[1]:"<YOUR_DEVICE_GUID>";
  const char*bi=(c>2)?v[2]:"{}";
  for(int n=0;n<3;n++){ char*r=nil; @try{ r=gu(inst,"marvis_client",q,bi);}@catch(NSException*e){continue;}
    printf("%s", r?r:"NULL"); return 0; }
  printf("NULL"); return 1;
}
