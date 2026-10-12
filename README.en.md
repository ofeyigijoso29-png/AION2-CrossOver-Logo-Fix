# AION2 Rosetta Guard

**An unofficial, experimental workaround for an AION2 startup-logo hang with Rosetta, CrossOver and NotProton.** [Русская инструкция](README.md)

On the tested configuration, AION2 progressed through the title screen, platform authentication, login server and lobby. The player confirmed a working launch. Long-session stability, other machines and FPS improvements have not been verified.

Need help applying it? Telegram: **[@bingobangobong](https://t.me/bingobangobong)**.

## Requirements

| Component | Supported configuration |
| --- | --- |
| Mac | Apple Silicon with Rosetta 2 |
| CrossOver | **26.3.0.39832** |
| NotProton | **1.1.3**, installed with components fetched and this CrossOver runner prepared |
| Steam | Native Steam for macOS; AION2 App ID **3393110** |
| Installer | Python 3.9+; Apple Command Line Tools only for source builds |

Startup was tested under Rosetta on Apple Silicon. Compatibility with every Mac model or macOS version has not been established. The installer pins the complete hashes of Unix ntdll, Windows ntdll and the original NotProton launcher. Unknown or modified versions are rejected; do not bypass these checks.

## Install

1. Set up CrossOver and [NotProton 1.1.3](https://github.com/NotProtonNot/NotProton/releases/tag/v1.1.3), including its components and prepared CrossOver runner.
2. Select NotProton for AION2 in **Steam for Mac**. Launch once to create the compatibility prefix, then **fully close AION2**. Successful game login is not required at this point.
3. Download **AION2-Rosetta-Guard-v0.1.0-macos.zip** from [the release](https://github.com/ofeyigijoso29-png/aion2-crossover-rosetta-guard/releases/tag/v0.1.0). It includes the tested loader, installer, source and LGPL license. Verify `python3 --version` (3.9+).
4. Extract and run `install.command`, or run `python3 installer.py install` from Terminal in the extracted directory.

For a source build instead, install Apple Command Line Tools with `xcode-select --install`, then:

```bash
git clone https://github.com/ofeyigijoso29-png/aion2-crossover-rosetta-guard.git
cd aion2-crossover-rosetta-guard
./install.command
```

**Source code (zip)** contains source only. The ready ZIP includes the locally built LGPL Wine loader, verified by SHA-256. If macOS blocks the downloaded loader, use a source build instead; disabling macOS security is unnecessary.

After `Active for AION2 only`, press **Play in Steam for Mac** with NotProton still selected. Windows Steam inside a CrossOver bottle does not use this installer.

## Isolation and rollback

The installer clones the prepared Wine runtime and existing AION2 prefix into `~/Library/Application Support/AION2RosettaGuard`. It installs the bundled x86_64 Wine loader or compiles it from source, then routes **only App ID 3393110** to the separate runtime, prefix and launcher directory. The installed CrossOver app, source runtime, game files and original prefix are preserved. Copy-on-write cloning is requested on compatible filesystems. No `sudo` is used.

While active, new local settings/data go into the **cloned** `compatdata/pfx`. Rollback returns to the original profile; it retains the clone but does not merge profiles. Steam Cloud behavior across these profiles has not been validated. Keep the guard directory while the workaround is active.

```bash
./status.command
./uninstall.command    # close AION2 first; restore original launcher, retain cloned data
./activate.command     # reactivate the existing prepared installation without recloning
```

Rollback refuses to overwrite a launcher modified since installation. NotProton updates may replace the launcher; check status before reinstalling. This release is specific to the supported versions. The installer does not change FPS, graphics, overlay or synchronization settings.

Custom paths are supported:

```bash
python3 installer.py install \
  --runtime '/path/to/prepared/CrossOver' \
  --tool '/path/to/compatibilitytools.d/notproton-26.3/run' \
  --prefix '/path/to/steamapps/compatdata/3393110' \
  --root '/path/to/separate/installation'
```

Point `--prefix` at the directory containing `pfx`. Use the same `--root` for `status`, `uninstall` and `activate`. `prepare` builds an isolated installation without changing the active Steam launcher.

## Mechanism and limits

A standalone reproducer entering a 32-bit code segment and executing CPUID at the 4-GiB boundary hung inside Rosetta before Wine received its exception. Refusing its allocation avoids entering that path. The working AION2 launch recorded one matching allocation refusal and subsequently reached login/lobby. This supports a problematic-path hypothesis; it does not establish every internal cause of the game's hang.

The loader intercepts `NtAllocateVirtualMemory` only when all arguments match: current process, base **0xffff0000**, size **0x10000**, ZeroBits **0**, allocation type **0x3000**, protection **0x40**. It returns **STATUS_CONFLICTING_ADDRESSES (0xc0000018)**, mapped to Windows error **487**. All other calls are forwarded unchanged. This is an allocation failure, not CPU emulation or a fabricated successful result. It does not disable NCGuard or patch game executables.

Before interception, the full ntdll.so hash and syscall-table ABI are checked. One entry in a copied, read-only syscall table is replaced in memory; the ntdll file is unchanged. The guard requires Rosetta and App ID 3393110, or the explicit standalone test flag `AION2_GUARD_TEST=1`.

Published-source compilation, CPUID/INT3 controls, targeted-allocation behavior and installer isolation/rollback were checked. The reproducer stops at allocation refusal instead of entering the failing transition. See [TESTING.md](TESTING.md) for reproducible developer checks. This is not a universal crash fix.

## Support and privacy

Contact **[@bingobangobong](https://t.me/bingobangobong)** or [open an issue](https://github.com/ofeyigijoso29-png/aion2-crossover-rosetta-guard/issues). Include Mac model, macOS, CrossOver/NotProton versions, failure stage and `status.command` output. Share only lines starting with `aion2-rosetta-guard:`; full game logs or launch commands may contain login tokens. No error in a log is not proof of a successful login.

## License and credits

LGPL-2.1-or-later; see [LICENSE](LICENSE). Wine loader copyright notices are preserved. `vendor/wine-loader/main.c` and `main.h` come from `sources/wine/loader/` in the official [CrossOver 26.3.0 source archive](https://media.codeweavers.com/pub/crossover/source/crossover-sources-26.3.0.tar.gz), available through [CodeWeavers' source page](https://www.codeweavers.com/crossover/source). `config.h` is the minimal local loader-build configuration.

Thanks to [Wine](https://www.winehq.org/) and [NotProton](https://github.com/NotProtonNot/NotProton). No proprietary CrossOver/Steam/game binaries, licenses, user profiles or tokens are distributed. This independent project is not an official patch from NCSOFT, Apple, CodeWeavers or NotProton.
