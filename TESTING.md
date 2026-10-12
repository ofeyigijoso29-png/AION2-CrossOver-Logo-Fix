# Developer validation

The source installer builds only the Wine loader, not the complete Wine tree; it requires Apple Command Line Tools and Python. The release ZIP includes the tested loader and needs Python without a compiler. MinGW is required only for the optional Windows probes below.

## Installer tests

```bash
python3 -m unittest discover -s tests -v
```

These tests use temporary launcher/profile fixtures. They check per-game routing, shell quoting, unknown layouts, rollback, reactivation and preservation of user data or newer launcher changes. CI runs these fixture tests; it does not run AION2 or proprietary Wine binaries.

## Isolated build and runtime probes

On a supported Mac with the exact prepared NotProton runner and original launcher:

```bash
python3 installer.py prepare --root "$PWD/build/validation"
python3 tests/run_probes.py --runtime "$PWD/build/validation/runtime"
```

`prepare` leaves the active launcher unchanged. The probe runner requires `x86_64-w64-mingw32-gcc`, creates its own temporary Wine prefix and stops only that prefix's wineserver afterward. It does not launch AION2. Expected results:

| Mode | Expected result |
| --- | --- |
| `baseline` | CPUID succeeds; exit 0 |
| `int3` | Wine delivers breakpoint to VEH; exit 0 |
| `guard-contract` | Data/dynamic/ordinary fixed allocations succeed; boundary RWX fails with error 487; exit 0 |
| `wrap-iret` | Allocation fails with error 487; exit 78; no transition is attempted |

An unguarded `wrap-iret` previously reached the reproducer's watchdog exit 124. This comparison shows that the workaround avoids the problematic transition, **not** that Rosetta now implements it correctly. Other selector modes in the C source are diagnostic experiments; the runner deliberately uses only the four checks above.

## Real-game evidence

In the tested AION2 launch under Rosetta on Apple Silicon, the matching locally built loader emitted the active-guard message and one declined boundary allocation. Fresh game breadcrumbs progressed through:

```text
Flow.PrePatch.Title
Flow.AfterPlatformLogined.None
Flow.LoginToLoginServer.Logined
Flow.MoveToLobbyFromLogined.Lobby
```

The player separately confirmed a working launch. This establishes startup, authentication and lobby progress for that run. World gameplay, sustained performance, Steam Cloud behavior, different hardware, different game updates and long-session stability have not been verified. Raw game logs, profiles and launch arguments are deliberately excluded.

## Version pins

| Input | SHA-256 |
| --- | --- |
| CrossOver 26.3.0.39832 Unix `ntdll.so` | `ab32585d767ae631154235861a2e0e8ea61bd09267a2dd341a439e3e8ed071fc` |
| NotProton 1.1.3 prepared Windows `ntdll.dll` | `c0e21a9a5250f0a97c08d3c3e1798566255387213e2553b1e555264fb9ded97e` |
| Original `notproton-26.3/run` | `52f3ba029f688df5cdad7c690d31ed45d4efe71905391ff48eee00ce6c588db6` |

The pinned exported-symbol offsets in Unix ntdll are `0x84c00` for `KeServiceDescriptorTable` and `0x634e0` for `NtAllocateVirtualMemory`. Never reuse these offsets for a different binary. A new supported version requires independently locating symbols, validating ABI and rerunning the relevant checks.
