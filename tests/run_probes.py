#!/usr/bin/env python3
"""Run standalone checks in a temporary Wine prefix, never the game's prefix.

SPDX-License-Identifier: LGPL-2.1-or-later
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.expanduser().resolve()
    compiler = shutil.which("x86_64-w64-mingw32-gcc")
    if sys.platform != "darwin" or not compiler:
        parser.error("Requires macOS and x86_64-w64-mingw32-gcc (developer probes only).")
    wine = runtime / "lib/wine/x86_64-unix/wine"
    server = runtime / "bin/wineserver"
    if not wine.is_file() or not server.is_file():
        parser.error("Prepared runtime is missing its loader or wineserver.")
    with tempfile.TemporaryDirectory(prefix="aion2-guard-probes-") as temporary:
        scratch = Path(temporary)
        executable = scratch / "probe.exe"
        subprocess.run([compiler, "-O2", "-Wall", "-Wextra", "-o", str(executable),
                        str(Path(__file__).with_name("cpuid_probe.c"))], check=True)
        prefix = scratch / "prefix"
        prefix.mkdir()
        env = dict(os.environ, CX_ROOT=str(runtime),
                   CX_HOME=str(Path.home() / "Library/Application Support/CrossOver"),
                   WINEPREFIX=str(prefix), WINELOADER=str(wine), WINESERVER=str(server),
                   WINEDLLPATH=str(runtime / "lib/wine/x86_64-windows") + ":" + str(runtime / "lib/wine/x86_64-unix"),
                   CX_APPLEGPTK_LIBD3DSHARED_PATH=str(runtime / "lib64/apple_gptk/external/libd3dshared.dylib"),
                   ROSETTA_ADVERTISE_AVX="1", WINEMSYNC="1", WINEDLLOVERRIDES="mscoree,mshtml=",
                   WINEDEBUG="-all", AION2_GUARD_TEST="1")
        try:
            for mode, expected in [("baseline", 0), ("int3", 0), ("guard-contract", 0), ("wrap-iret", 78)]:
                try:
                    result = subprocess.run([str(wine), str(executable), mode], env=env,
                                            capture_output=True, text=True, timeout=60)
                except subprocess.TimeoutExpired as error:
                    print(f"{mode}: timed out; stopping the temporary probe prefix", flush=True)
                    print((error.stdout or b"").decode(errors="replace") if isinstance(error.stdout, bytes)
                          else error.stdout or "", flush=True)
                    print((error.stderr or b"").decode(errors="replace") if isinstance(error.stderr, bytes)
                          else error.stderr or "", flush=True)
                    raise
                print(f"[{mode}] exit={result.returncode}; expected={expected}")
                print(result.stdout.strip())
                messages = [line for line in result.stderr.splitlines()
                            if line.startswith("aion2-rosetta-guard:")]
                print("\n".join(dict.fromkeys(messages)))
                if result.returncode != expected or not any("workaround active" in line for line in messages):
                    raise RuntimeError(f"{mode}: expected result or active guard message missing")
                if mode in ("guard-contract", "wrap-iret"):
                    if "error=487" not in result.stdout or not any("declined fixed" in line for line in messages):
                        raise RuntimeError(f"{mode}: targeted allocation refusal missing")
        finally:
            subprocess.run([str(server), "-k"], env=env, capture_output=True, timeout=10)
            subprocess.run([str(server), "-w"], env=env, capture_output=True, timeout=10)
    print("All standalone checks passed. This does not verify an AION2 game session.")


if __name__ == "__main__":
    main()
