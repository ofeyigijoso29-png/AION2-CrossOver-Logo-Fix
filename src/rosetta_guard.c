/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Experimental allocation workaround, not a CPU emulator.
 * Only CrossOver 26.3.0.39832 x86_64 ntdll.so is supported. The complete
 * image hash is checked before a copied syscall table is installed.
 * Linked into a locally built Wine loader in a separate runtime copy.
 * This module changes a copied syscall table in memory, not ntdll on disk.
 */
#if defined(__APPLE__) && defined(__x86_64__)
#include <CommonCrypto/CommonDigest.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/sysctl.h>
#include <unistd.h>

typedef uint32_t (*allocate_fn)(void *,void **,uintptr_t,size_t *,uint32_t,uint32_t);
struct service_table {
    uintptr_t *functions;
    uintptr_t *counters;
    uint32_t limit;
    uint32_t padding;
    unsigned char *arguments;
};
_Static_assert(sizeof(struct service_table)==32,"Unexpected Wine syscall ABI");
static allocate_fn original_allocate;
static atomic_uint blocked;
static int installed;

static uint32_t guarded_allocate(void *process,void **base,uintptr_t zero_bits,
                                size_t *size,uint32_t type,uint32_t protection)
{
    /* The reproduced failure uses this exact fixed RWX allocation. Do not
     * alter dynamic allocations, data mappings, other processes, or other
     * addresses. An allocation error is reported, never a fabricated success.
     */
    if(process==(void *)(intptr_t)-1 && base && size &&
       (uintptr_t)*base==UINT64_C(0xffff0000) && *size==0x10000 &&
       zero_bits==0 && type==0x3000 && protection==0x40)
    {
        static const char message[]="aion2-rosetta-guard: declined fixed 4-GiB-boundary RWX allocation\n";
        if(atomic_fetch_add_explicit(&blocked,1,memory_order_relaxed)==0)
            write(STDERR_FILENO,message,sizeof(message)-1);
        return UINT32_C(0xc0000018); /* STATUS_CONFLICTING_ADDRESSES */
    }
    return original_allocate(process,base,zero_bits,size,type,protection);
}

static int correct_image(const char *filename)
{
    static const unsigned char expected[32]={
        0xab,0x32,0x58,0x5d,0x76,0x7a,0xe6,0x31,0x15,0x42,0x35,0x86,0x1a,0x2e,0x0e,0x8e,
        0xa6,0x1b,0xd0,0x92,0x67,0xa2,0xdd,0x34,0x1a,0x43,0x9e,0x3e,0x8e,0xd0,0x71,0xfc
    };
    FILE *file=fopen(filename,"rb");
    unsigned char data[8192],digest[32];
    CC_SHA256_CTX context;
    size_t count;
    if(!file)return 0;
    CC_SHA256_Init(&context);
    while((count=fread(data,1,sizeof(data),file)))CC_SHA256_Update(&context,data,(CC_LONG)count);
    int ok=!ferror(file);
    fclose(file);
    CC_SHA256_Final(digest,&context);
    return ok && !memcmp(expected,digest,sizeof(expected));
}

static void image_loaded(const struct mach_header *header,intptr_t slide)
{
    if(installed || header->magic!=MH_MAGIC_64 || header->cputype!=CPU_TYPE_X86_64)return;
    const char *filename=NULL;
    for(uint32_t i=0;i<_dyld_image_count();i++)
        if(_dyld_get_image_header(i)==header){filename=_dyld_get_image_name(i);break;}
    if(!filename)return;
    const char *name=strrchr(filename,'/');
    if(strcmp(name?name+1:filename,"ntdll.so"))return;
    fputs("aion2-rosetta-guard: examining ntdll\n",stderr);
    if(!correct_image(filename))
    {
        static const char message[]="aion2-rosetta-guard: unsupported ntdll image; no change applied\n";
        write(STDERR_FILENO,message,sizeof(message)-1);
        return;
    }
    /* Symbol offsets are safe only after the pinned full-image hash matches. */
    struct service_table *table=(struct service_table *)(slide+0x84c00);
    allocate_fn target=(allocate_fn)(slide+0x634e0);
    if(!table->functions || !table->arguments || !table->limit || table->limit>1024){
        fprintf(stderr,"aion2-rosetta-guard: table not ready (limit=%u)\n",table->limit);return;
    }
    unsigned index=table->limit,matches=0;
    for(unsigned i=0;i<table->limit;i++)if(table->functions[i]==(uintptr_t)target){index=i;matches++;}
    if(matches!=1 || table->arguments[index]!=48){
        fprintf(stderr,"aion2-rosetta-guard: ABI validation failed (matches=%u args=%u)\n",matches,
                index<table->limit?table->arguments[index]:0);return;
    }
    size_t bytes=table->limit*sizeof(uintptr_t);
    uintptr_t *copy=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    if(copy==MAP_FAILED)return;
    memcpy(copy,table->functions,bytes);
    original_allocate=target;
    copy[index]=(uintptr_t)guarded_allocate;
    if(mprotect(copy,bytes,PROT_READ)){munmap(copy,bytes);original_allocate=NULL;return;}
    __atomic_store_n(&table->functions,copy,__ATOMIC_RELEASE);
    installed=1;
    static const char message[]="aion2-rosetta-guard: experimental allocation workaround active\n";
    write(STDERR_FILENO,message,sizeof(message)-1);
}

__attribute__((constructor)) static void start_guard(void)
{
    const char *app=getenv("STEAM_COMPAT_APP_ID");
    const char *test=getenv("AION2_GUARD_TEST");
    int translated=0;
    size_t size=sizeof(translated);
    fputs("aion2-rosetta-guard: library loaded\n",stderr);
    if((!app || strcmp(app,"3393110")) && (!test || strcmp(test,"1"))){
        fputs("aion2-rosetta-guard: outside requested scope\n",stderr);return;
    }
    if(sysctlbyname("sysctl.proc_translated",&translated,&size,NULL,0) || !translated)return;
    fputs("aion2-rosetta-guard: registering image callback\n",stderr);
    _dyld_register_func_for_add_image(image_loaded);
}
#endif
