#!/usr/bin/env python3
"""Build and route an isolated, version-pinned AION2 Wine runtime.

SPDX-License-Identifier: LGPL-2.1-or-later
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

VERSION = "0.1.0"
BUILD = "26.3.0.39832"
UNIX_HASH = "ab32585d767ae631154235861a2e0e8ea61bd09267a2dd341a439e3e8ed071fc"
PE_HASH = "c0e21a9a5250f0a97c08d3c3e1798566255387213e2553b1e555264fb9ded97e"
TOOL_HASH = "52f3ba029f688df5cdad7c690d31ed45d4efe71905391ff48eee00ce6c588db6"
BUNDLED_LOADER_HASH = "af0de62e2b7e3321b510b3228a5bcdea900417e76f22d6dab9fd8ffac3446279"
PACKAGE = Path(__file__).resolve().parent
SUPPORT = Path.home() / "Library/Application Support"
DEFAULT_ROOT = SUPPORT / "AION2RosettaGuard"
DEFAULT_RUNTIME = SUPPORT / f"notproton/runners/crossover-{BUILD}/CrossOver"
DEFAULT_TOOL = SUPPORT / "Steam/compatibilitytools.d/notproton-26.3/run"
DEFAULT_PREFIX = SUPPORT / "Steam/steamapps/compatdata/3393110"
MARKER = "# AION2_ROSETTA_GUARD_BEGIN"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(command, **options):
    return subprocess.run(command, check=True, **options)


def game_running():
    result = subprocess.run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    return any(line.strip().replace("\\", "/").rsplit("/", 1)[-1].lower() == "aion2.exe"
               for line in result.stdout.splitlines())


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("NotProton launcher layout differs from the tested version; no change applied.")
    return text.replace(old, new, 1)


def patched_script(original, root):
    if MARKER in original:
        raise RuntimeError("Launcher is already patched; use status.command or uninstall.command first.")
    runtime = shlex.quote(str(root / "runtime"))
    prefix = shlex.quote(str(root / "compatdata"))
    launcher = shlex.quote(str(root / "launcher"))
    old = 'CX_ROOT="$np_support/runners/crossover-$np_build/CrossOver"\nexport CX_ROOT\n'
    new = ('CX_ROOT="$np_support/runners/crossover-$np_build/CrossOver"\n'
           + MARKER + '\n'
           'aion2_guard_test=0\n'
           'if [ "${STEAM_COMPAT_APP_ID:-}" = 3393110 ]; then\n'
           f'  CX_ROOT={runtime}\n'
           f'  STEAM_COMPAT_DATA_PATH={prefix}\n'
           '  export STEAM_COMPAT_DATA_PATH\n'
           '  aion2_guard_test=1\n'
           'fi\n'
           '# AION2_ROSETTA_GUARD_END\n'
           'export CX_ROOT\n')
    text = replace_once(original, old, new)
    old = 'loader_root="$HOME/Library/Application Support/notproton/launchers/$app_id"\n'
    new = (old + 'if [ "$aion2_guard_test" = 1 ]; then\n'
           f'  loader_root={launcher}\n'
           'fi\n')
    return replace_once(text, old, new)


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".aion2-guard-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_platform(need_compiler=True):
    if sys.platform != "darwin":
        raise RuntimeError("This installer supports macOS only.")
    arm = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True)
    if arm.stdout.strip() != "1":
        raise RuntimeError("Apple Silicon is required.")
    if not need_compiler:
        return None
    clang = subprocess.run(["/usr/bin/xcrun", "--find", "clang"], capture_output=True, text=True)
    if clang.returncode:
        raise RuntimeError("Install Apple's Command Line Tools with xcode-select --install, then retry.")
    return clang.stdout.strip()


def check_inputs(runtime, tool, prefix):
    checks = [(runtime / "lib/wine/x86_64-unix/ntdll.so", UNIX_HASH),
              (runtime / "lib/wine/x86_64-windows/ntdll.dll", PE_HASH),
              (tool, TOOL_HASH)]
    for file, expected in checks:
        if not file.is_file() or digest(file) != expected:
            raise RuntimeError(f"Unsupported or modified {file.name}. Requires the prepared NotProton 1.1.3 / CrossOver {BUILD} runner.")
    if tool.is_symlink():
        raise RuntimeError("Refusing to replace a symlinked compatibility-tool launcher.")
    if not (prefix / "pfx").is_dir():
        raise RuntimeError("AION2's native-Steam prefix is missing. Launch it once with NotProton, close it, then retry.")
    return tool.read_bytes()


def build_loader(clang, runtime):
    loader = runtime / "lib/wine/x86_64-unix/wine"
    bundled = PACKAGE / "bin/wine-loader"
    if bundled.is_file():
        if digest(bundled) != BUNDLED_LOADER_HASH:
            raise RuntimeError("Bundled loader checksum mismatch; no launcher changes applied.")
        shutil.copyfile(bundled, loader)
        loader.chmod(0o755)
        return loader
    sdk = run(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"],
              capture_output=True, text=True).stdout.strip()
    flags = ("-pagezero_size,0x1000,-no_pie,-image_base,0x200000000,-no_huge,"
             "-no_fixup_chains,-segalign,0x1000,-segaddr,WINE_RESERVE,0x1000,"
             "-segaddr,WINE_TOP_DOWN,0x7ff000000000")
    run([clang, "-isysroot", sdk, "-arch", "x86_64", "-mmacosx-version-min=10.15", "-O2", "-Wall", "-Wextra",
         "-Wno-deprecated-declarations", "-I", str(PACKAGE / "vendor/wine-loader"), "-pthread",
         "-Wl," + flags, "-o", str(loader), str(PACKAGE / "vendor/wine-loader/main.c"),
         str(PACKAGE / "src/rosetta_guard.c")])
    return loader


def install(args):
    root, runtime, tool, prefix = args.root, args.runtime, args.tool, args.prefix
    if root.exists():
        raise RuntimeError("Installation directory already exists. Use status, activate, or uninstall; select a new --root for a separate preparation.")
    if any(source == root or source in root.parents for source in (runtime, prefix)):
        raise RuntimeError("The installation directory must be outside the source runtime and game prefix.")
    if args.action == "install" and game_running():
        raise RuntimeError("Close AION2 before installation. No launcher was changed.")
    clang = check_platform(need_compiler=not (PACKAGE / "bin/wine-loader").is_file())
    original = check_inputs(runtime, tool, prefix)
    patch = patched_script(original.decode("utf-8"), root).encode("utf-8")
    root.mkdir(parents=True)
    # macOS cp -c requests copy-on-write clones on compatible filesystems.
    print("Preparing a separate runtime and AION2 prefix...")
    run(["/bin/cp", "-cR", str(runtime), str(root / "runtime")])
    run(["/bin/cp", "-cR", str(prefix), str(root / "compatdata")])
    # The launcher must have its own directory: NotProton stages Wine with
    # hard links. Sharing the stock launcher directory could overwrite Wine.
    (root / "launcher").mkdir()
    print("Preparing the guard Wine loader...")
    loader = build_loader(clang, root / "runtime")
    backup = root / "notproton-run.original"
    atomic_write(backup, original, tool.stat().st_mode & 0o777)
    staged = root / "notproton-run.patched"
    atomic_write(staged, patch, tool.stat().st_mode & 0o777)
    run(["/bin/sh", "-n", str(staged)])
    state = {"version": VERSION, "build": BUILD, "active": False, "tool": str(tool),
             "backup": str(backup), "original_sha256": hashlib.sha256(original).hexdigest(),
             "patched_sha256": hashlib.sha256(patch).hexdigest(), "loader_sha256": digest(loader)}
    atomic_write(root / "state.json", (json.dumps(state, indent=2) + "\n").encode())
    if args.action == "prepare":
        print("Preparation complete. The active Steam launcher was not changed.")
        return
    activate(root)


def load_state(root):
    state = json.loads((root / "state.json").read_text())
    return state, Path(state["tool"]), Path(state["backup"])


def activate(root):
    state, tool, backup = load_state(root)
    if game_running():
        raise RuntimeError("Close AION2 before activation. Prepared files and launcher retained.")
    if state["version"] != VERSION or state["build"] != BUILD:
        raise RuntimeError("Prepared installation version differs; no changes applied.")
    if tool.is_symlink() or backup.is_symlink():
        raise RuntimeError("Refusing a symlinked launcher or backup.")
    if digest(backup) != TOOL_HASH or state["original_sha256"] != TOOL_HASH:
        raise RuntimeError("Original launcher backup differs from the supported version.")
    runtime = root / "runtime"
    for file, expected in [(runtime / "lib/wine/x86_64-unix/ntdll.so", UNIX_HASH),
                           (runtime / "lib/wine/x86_64-windows/ntdll.dll", PE_HASH),
                           (runtime / "lib/wine/x86_64-unix/wine", state["loader_sha256"])]:
        if digest(file) != expected:
            raise RuntimeError("Prepared runtime changed; no launcher changes applied.")
    if not (root / "compatdata/pfx").is_dir():
        raise RuntimeError("Prepared AION2 profile is missing.")
    patch = patched_script(backup.read_text(), root).encode("utf-8")
    if hashlib.sha256(patch).hexdigest() != state["patched_sha256"]:
        raise RuntimeError("Prepared launcher checksum differs; no changes applied.")
    actual = digest(tool)
    if actual not in (state["original_sha256"], state["patched_sha256"]):
        raise RuntimeError("Launcher changed after preparation; refusing to overwrite it.")
    if actual == state["original_sha256"]:
        atomic_write(tool, patch, tool.stat().st_mode & 0o777)
    state["active"] = True
    atomic_write(root / "state.json", (json.dumps(state, indent=2) + "\n").encode())
    print("Active for AION2 only. Open Steam for Mac, then press Play.")


def status(root):
    if not (root / "state.json").exists():
        print("Not installed by this installer.")
        return
    state, tool, backup = load_state(root)
    actual = digest(tool) if tool.is_file() else None
    if actual == state["patched_sha256"]:
        result = "Active: AION2 uses the isolated guard runtime."
    elif actual == state["original_sha256"]:
        result = "Inactive: Steam uses the original launcher."
    else:
        result = "Launcher changed after installation; automatic rollback will refuse to overwrite it."
    print(result)
    print("Version: " + state["version"] + "; pinned CrossOver: " + state["build"])
    log = root / "launcher/notproton-wine.log"
    if log.is_file():
        # Print guard messages only. Full game command lines can contain tokens.
        messages = [line for line in log.read_text(errors="replace").splitlines()
                    if line.startswith("aion2-rosetta-guard:")]
        for line in list(dict.fromkeys(messages))[-8:]:
            print(line)


def uninstall(root):
    state, tool, backup = load_state(root)
    if game_running():
        raise RuntimeError("Close AION2 before rollback.")
    if tool.is_symlink() or backup.is_symlink():
        raise RuntimeError("Refusing a symlinked launcher or backup.")
    actual = digest(tool)
    if actual not in (state["patched_sha256"], state["original_sha256"]):
        raise RuntimeError("Launcher changed after installation. Refusing to overwrite newer/user changes; original backup retained.")
    if digest(backup) != state["original_sha256"]:
        raise RuntimeError("Original backup hash does not match; no changes applied.")
    if actual == state["patched_sha256"]:
        atomic_write(tool, backup.read_bytes(), tool.stat().st_mode & 0o777)
    state["active"] = False
    atomic_write(root / "state.json", (json.dumps(state, indent=2) + "\n").encode())
    print("Original NotProton launcher restored. Isolated runtime and game profile retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "prepare", "activate", "uninstall", "status"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--tool", type=Path, default=DEFAULT_TOOL)
    parser.add_argument("--prefix", type=Path, default=DEFAULT_PREFIX)
    args = parser.parse_args()
    for name in ("root", "runtime", "tool", "prefix"):
        value = getattr(args, name).expanduser()
        setattr(args, name, value.absolute() if name == "tool" else value.resolve())
    try:
        if args.action in ("install", "prepare"):
            install(args)
        elif args.action == "status":
            status(args.root)
        elif args.action == "activate":
            activate(args.root)
        else:
            uninstall(args.root)
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
