"""Launcher isolation, quoting, rollback, and file-preservation checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer

FIXTURE = '''#!/bin/sh
np_support="$HOME/Library/Application Support/notproton"
np_build=26.3.0.39832
CX_ROOT="$np_support/runners/crossover-$np_build/CrossOver"
export CX_ROOT
app_id="${STEAM_COMPAT_APP_ID:-0}"
loader_root="$HOME/Library/Application Support/notproton/launchers/$app_id"
printf '%s\\n' "$CX_ROOT" "$loader_root" "${STEAM_COMPAT_DATA_PATH:-}"
'''


class InstallerTests(unittest.TestCase):
    def test_other_game_keeps_original_runtime_and_prefix(self):
        script = installer.patched_script(FIXTURE, Path("/tmp/guard-test"))
        env = dict(os.environ, STEAM_COMPAT_APP_ID="123", STEAM_COMPAT_DATA_PATH="original-prefix")
        result = subprocess.run(["/bin/sh"], input=script, text=True, capture_output=True, env=env, check=True)
        values = result.stdout.splitlines()
        self.assertEqual(values[0], str(installer.SUPPORT / "notproton/runners/crossover-26.3.0.39832/CrossOver"))
        self.assertEqual(values[2], "original-prefix")

    def test_aion_routing_and_shell_quoting(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "unexpected"
            root = Path(temporary) / ("spaces ' $(touch " + str(marker) + ")")
            script = installer.patched_script(FIXTURE, root)
            env = dict(os.environ, STEAM_COMPAT_APP_ID="3393110", STEAM_COMPAT_DATA_PATH="old")
            result = subprocess.run(["/bin/sh"], input=script, text=True, capture_output=True, env=env, check=True)
            self.assertEqual(result.stdout.splitlines(), [str(root / "runtime"), str(root / "launcher"), str(root / "compatdata")])
            self.assertFalse(marker.exists())

    def test_unknown_layout_and_duplicate_patch_refused(self):
        with self.assertRaises(RuntimeError):
            installer.patched_script(FIXTURE.replace('export CX_ROOT', 'export OTHER'), Path("/tmp/test"))
        script = installer.patched_script(FIXTURE, Path("/tmp/test"))
        with self.assertRaises(RuntimeError):
            installer.patched_script(script, Path("/tmp/test"))

    def fixture_state(self, directory):
        root = Path(directory)
        original = FIXTURE.encode()
        modified = installer.patched_script(FIXTURE, root).encode()
        tool, backup = root / "run", root / "original"
        tool.write_bytes(modified)
        backup.write_bytes(original)
        state = {"tool": str(tool), "backup": str(backup), "version": "test", "build": installer.BUILD,
                 "original_sha256": hashlib.sha256(original).hexdigest(),
                 "patched_sha256": hashlib.sha256(modified).hexdigest(), "active": True}
        (root / "state.json").write_text(json.dumps(state))
        profile = root / "compatdata/pfx/save.txt"
        profile.parent.mkdir(parents=True)
        profile.write_text("retain the user's game profile")
        return root, tool, backup, profile, original

    @patch("installer.game_running", return_value=False)
    def test_rollback_restores_original_and_preserves_profile(self, unused):
        with tempfile.TemporaryDirectory() as directory:
            root, tool, backup, profile, original = self.fixture_state(directory)
            installer.uninstall(root)
            self.assertEqual(tool.read_bytes(), original)
            self.assertTrue(profile.exists())
            self.assertFalse(json.loads((root / "state.json").read_text())["active"])

    @patch("installer.game_running", return_value=False)
    def test_rollback_preserves_newer_launcher_edits(self, unused):
        with tempfile.TemporaryDirectory() as directory:
            root, tool, backup, profile, original = self.fixture_state(directory)
            tool.write_text("new user launcher")
            with self.assertRaises(RuntimeError):
                installer.uninstall(root)
            self.assertEqual(tool.read_text(), "new user launcher")

    def prepare_activation_fixture(self, directory):
        root, tool, backup, profile, original = self.fixture_state(directory)
        tool.write_bytes(original)
        files = [(root / "runtime/lib/wine/x86_64-unix/ntdll.so", b"unix ntdll"),
                 (root / "runtime/lib/wine/x86_64-windows/ntdll.dll", b"Windows ntdll"),
                 (root / "runtime/lib/wine/x86_64-unix/wine", b"compiled loader")]
        for file, content in files:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(content)
        state = json.loads((root / "state.json").read_text())
        state.update(version=installer.VERSION, loader_sha256=installer.digest(files[2][0]))
        (root / "state.json").write_text(json.dumps(state))
        return root, tool, profile, original, files

    @patch("installer.game_running", return_value=False)
    def test_reactivation_preserves_existing_profile(self, unused):
        with tempfile.TemporaryDirectory() as directory:
            root, tool, profile, original, files = self.prepare_activation_fixture(directory)
            with patch.multiple(installer, TOOL_HASH=hashlib.sha256(original).hexdigest(),
                                UNIX_HASH=installer.digest(files[0][0]), PE_HASH=installer.digest(files[1][0])):
                installer.activate(root)
            self.assertIn(installer.MARKER, tool.read_text())
            self.assertEqual(profile.read_text(), "retain the user's game profile")
            self.assertTrue(json.loads((root / "state.json").read_text())["active"])

    @patch("installer.game_running", return_value=False)
    def test_reactivation_refuses_changed_runtime(self, unused):
        with tempfile.TemporaryDirectory() as directory:
            root, tool, profile, original, files = self.prepare_activation_fixture(directory)
            expected_loader = installer.digest(files[2][0])
            files[2][0].write_bytes(b"a newer loader")
            with patch.multiple(installer, TOOL_HASH=hashlib.sha256(original).hexdigest(),
                                UNIX_HASH=installer.digest(files[0][0]), PE_HASH=installer.digest(files[1][0])):
                with self.assertRaises(RuntimeError):
                    installer.activate(root)
            self.assertEqual(tool.read_bytes(), original)
            self.assertNotEqual(installer.digest(files[2][0]), expected_loader)

    @patch("installer.game_running", return_value=True)
    def test_activation_refuses_running_game(self, unused):
        with tempfile.TemporaryDirectory() as directory:
            root, tool, profile, original, files = self.prepare_activation_fixture(directory)
            with self.assertRaises(RuntimeError):
                installer.activate(root)
            self.assertEqual(tool.read_bytes(), original)

    @patch("installer.subprocess.run")
    def test_game_detection_handles_native_and_windows_paths(self, ps):
        for command in ("C:\\games\\AION2.exe", "/games/AION2.exe"):
            ps.return_value = subprocess.CompletedProcess([], 0, stdout=command + "\n")
            self.assertTrue(installer.game_running())
        ps.return_value = subprocess.CompletedProcess([], 0, stdout="/games/not-aion2.exe\n")
        self.assertFalse(installer.game_running())

    def test_valid_bundled_loader_needs_no_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "package/bin/wine-loader"
            loader = root / "runtime/lib/wine/x86_64-unix/wine"
            bundle.parent.mkdir(parents=True)
            loader.parent.mkdir(parents=True)
            bundle.write_bytes(b"known bundled loader")
            loader.write_bytes(b"original runtime loader")
            with patch.multiple(installer, PACKAGE=bundle.parents[1], BUNDLED_LOADER_HASH=installer.digest(bundle)):
                with patch("installer.run") as command:
                    installer.build_loader(None, root / "runtime")
                    command.assert_not_called()
            self.assertEqual(loader.read_bytes(), bundle.read_bytes())
            self.assertEqual(loader.stat().st_mode & 0o777, 0o755)

    def test_modified_bundle_does_not_overwrite_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "package/bin/wine-loader"
            loader = root / "runtime/lib/wine/x86_64-unix/wine"
            bundle.parent.mkdir(parents=True)
            loader.parent.mkdir(parents=True)
            bundle.write_bytes(b"unexpected bundled loader")
            loader.write_bytes(b"keep original loader")
            with patch("installer.PACKAGE", bundle.parents[1]):
                with self.assertRaises(RuntimeError):
                    installer.build_loader(None, root / "runtime")
            self.assertEqual(loader.read_bytes(), b"keep original loader")


if __name__ == "__main__":
    unittest.main()
