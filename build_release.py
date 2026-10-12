#!/usr/bin/env python3
"""Package tracked source and the tested LGPL loader, never a runtime/profile."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile
import installer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if installer.digest(args.loader) != installer.BUNDLED_LOADER_HASH:
        parser.error("Use the tested loader matching installer.BUNDLED_LOADER_HASH.")
    package = Path(__file__).resolve().parent
    files = subprocess.run(["git", "ls-files", "-z"], cwd=package,
                           capture_output=True, check=True).stdout.decode().split("\0")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    name = f"AION2-CrossOver-Logo-Fix-v{installer.VERSION}-macos"
    archive = args.output_dir / (name + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative in filter(None, files):
            file = package / relative
            if file.is_symlink() or not file.is_file():
                parser.error("Refusing non-file tracked entry: " + relative)
            bundle.write(file, name + "/" + relative)
        bundle.write(args.loader, name + "/bin/wine-loader")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n")
    print(archive)
    print("SHA-256: " + checksum)


if __name__ == "__main__":
    main()
