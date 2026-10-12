#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const char *mode;
static LONG exception_count;

static LONG CALLBACK exception_handler(EXCEPTION_POINTERS *p)
{
    CONTEXT *c = p->ContextRecord;
    LONG count = InterlockedIncrement(&exception_count);
    printf("exception mode=%s count=%ld code=%08lx cs=%04x rip=%016llx rsp=%016llx eax=%08lx\n",
           mode, count, p->ExceptionRecord->ExceptionCode, c->SegCs,
           (unsigned long long)c->Rip, (unsigned long long)c->Rsp, (DWORD)c->Rax);
    fflush(stdout);
    if (!strncmp(mode, "selector", 8) || !strcmp(mode,"int3") || !strcmp(mode,"iret64"))
        ExitProcess(p->ExceptionRecord->ExceptionCode == EXCEPTION_BREAKPOINT ? 0 : 2);
    if (!strcmp(mode,"wrap64"))
        ExitProcess(p->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION
                    && c->Rip == UINT64_C(0x100000000) && c->Rsp != 0 ? 0 : 5);
    if (!strcmp(mode, "wrap") || !strcmp(mode,"wrap-iret"))
        ExitProcess(p->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION
                    && c->Rip == 0 && c->Rsp != 0 ? 0 : 3);
    ExitProcess(4);
    return EXCEPTION_CONTINUE_SEARCH;
}

static DWORD WINAPI watchdog(void *unused)
{
    (void)unused;
    Sleep(4000);
    fputs("watchdog: probe did not reach its exception handler\n", stdout);
    fflush(stdout);
    TerminateProcess(GetCurrentProcess(), 124);
    return 0;
}

int main(int argc, char **argv)
{
    uintptr_t rsp;
    unsigned short cs, ss;
    unsigned char *target, *entry;
    uint64_t address;
    unsigned char thunk[] = {
        0x31,0xc0,0x31,0xc9,             /* xor eax,eax; xor ecx,ecx */
        0x6a,0x23,                       /* push Windows 32-bit code selector */
        0x49,0xbb,0,0,0,0,0,0,0,0,     /* mov r11, target */
        0x41,0x53,                       /* push r11 */
        0x48,0xcb                        /* retfq */
    };
    unsigned char iret_thunk[] = {
        0x31,0xc0,0x31,0xc9,             /* xor eax,eax; xor ecx,ecx */
        0x49,0x89,0xe3,                  /* mov r11,rsp: save stack */
        0x6a,0x2b,                       /* push Windows stack selector */
        0x41,0x53,                       /* push r11 */
        0x9c,                            /* pushfq */
        0x6a,0x23,                       /* push Windows 32-bit code selector */
        0x49,0xba,0,0,0,0,0,0,0,0,     /* mov r10,target */
        0x41,0x52,                       /* push r10 */
        0x48,0xcf                        /* iretq */
    };
    int is_iret, is_wrap;
    setvbuf(stdout, NULL, _IONBF, 0);
    mode = argc > 1 ? argv[1] : "baseline";
    __asm__ volatile("movq %%rsp,%0; movw %%cs,%1; movw %%ss,%2" : "=r"(rsp), "=r"(cs), "=r"(ss));
    printf("probe mode=%s cs=%04x ss=%04x rsp=%016llx\n", mode, cs, ss, (unsigned long long)rsp);
    if (!strcmp(mode, "baseline"))
    {
        unsigned int a=0,b,c=0,d;
        __asm__ volatile("cpuid" : "+a"(a), "=b"(b), "+c"(c), "=d"(d));
        printf("baseline cpuid succeeded maximum_leaf=%u\n", a);
        return 0;
    }
    if (!strcmp(mode,"guard-contract"))
    {
        void *data=VirtualAlloc((void *)(uintptr_t)UINT64_C(0xffff0000),0x10000,
                               MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        printf("boundary data allocation=%s error=%lu\n",data?"success":"failure",data?0:GetLastError());
        if(!data)return 90;
        if(!VirtualFree(data,0,MEM_RELEASE))return 91;
        void *dynamic=VirtualAlloc(NULL,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
        printf("dynamic executable allocation=%s\n",dynamic?"success":"failure");
        if(!dynamic)return 92;
        if(!VirtualFree(dynamic,0,MEM_RELEASE))return 93;
        void *other=VirtualAlloc((void *)(uintptr_t)UINT64_C(0x20000000),0x10000,
                                MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
        printf("ordinary fixed executable allocation=%s\n",other?"success":"failure");
        if(!other)return 94;
        if(!VirtualFree(other,0,MEM_RELEASE))return 95;
        SetLastError(0);
        void *boundary=VirtualAlloc((void *)(uintptr_t)UINT64_C(0xffff0000),0x10000,
                                   MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
        DWORD error=GetLastError();
        printf("boundary executable allocation=%s error=%lu\n",boundary?"success":"failure",error);
        if(boundary){VirtualFree(boundary,0,MEM_RELEASE);return 96;}
        return error==ERROR_INVALID_ADDRESS?0:97;
    }
    if (strcmp(mode, "selector") && strcmp(mode, "wrap")
        && strcmp(mode,"int3") && strcmp(mode,"wrap64")
        && strcmp(mode,"selector-iret") && strcmp(mode,"selector-iret-hostss")
        && strcmp(mode,"wrap-iret") && strcmp(mode,"iret64")) return 64;
    is_iret = strstr(mode,"iret") != NULL;
    is_wrap = !strncmp(mode,"wrap",4);
    if (rsp > UINT32_MAX)
    {
        fputs("unsupported test environment: stack is outside 32-bit address range\n", stdout);
        return 77;
    }
    AddVectoredExceptionHandler(1, exception_handler);
    CloseHandle(CreateThread(NULL, 0, watchdog, NULL, 0, NULL));
    address = is_wrap ? UINT64_C(0xffff0000) : UINT64_C(0x20000000);
    target = VirtualAlloc((void *)(uintptr_t)address, 0x10000,
                          MEM_RESERVE|MEM_COMMIT, PAGE_EXECUTE_READWRITE);
    if (!target)
    {
        printf("allocation failed error=%lu\n", GetLastError());
        return 78;
    }
    if (is_wrap)
    {
        target += 0xfffe;
        target[0]=0x0f; target[1]=0xa2; /* CPUID ends precisely at 4 GiB. */
    }
    else target[0]=0xcc;              /* INT3 is the selector-only control. */
    if (!strcmp(mode,"int3") || !strcmp(mode,"wrap64"))
    {
        printf("executing 64-bit control at=%016llx\n",(unsigned long long)(uintptr_t)target);
        ((void (*)(void))target)();
        return 81;
    }
    address = (uintptr_t)target;
    if (is_iret)
    {
        memcpy(iret_thunk+16, &address, sizeof(address));
        if (!strcmp(mode,"selector-iret-hostss") || !strcmp(mode,"iret64")) iret_thunk[8]=(unsigned char)ss;
        if (!strcmp(mode,"iret64")) iret_thunk[13]=(unsigned char)cs;
    }
    else memcpy(thunk+8, &address, sizeof(address));
    entry=VirtualAlloc(NULL,is_iret ? sizeof(iret_thunk) : sizeof(thunk),MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
    if (!entry) return 79;
    memcpy(entry,is_iret ? iret_thunk : thunk,is_iret ? sizeof(iret_thunk) : sizeof(thunk));
    FlushInstructionCache(GetCurrentProcess(),NULL,0);
    printf("entering compatibility mode target=%016llx\n", (unsigned long long)address);
    ((void (*)(void))entry)();
    fputs("unexpected normal return\n", stdout);
    return 80;
}
