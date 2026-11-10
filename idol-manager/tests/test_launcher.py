import subprocess
import sys
import unittest

from idol_manager.config import ROOT


class LauncherTests(unittest.TestCase):
    def test_checker_version_dependencies_and_missing_package(self):
        checker = str(ROOT / "tools" / "check_environment.py")
        for arguments, expected in (
            (["python-version"], 0),
            (["dependencies"], 0),
            (["invalid-mode"], 2),
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run([sys.executable, checker, *arguments], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(result.stderr, b"")
        # -S omits site-packages, reproducing an environment before PySide6 installation.
        result = subprocess.run([sys.executable, "-S", checker, "dependencies"], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b"")

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell launcher")
    def test_windows_powershell_51_bootstrap(self):
        if not (ROOT / ".venv" / "Scripts" / "python.exe").exists():
            self.skipTest("Create the project .venv and install requirements first")
        result = subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "tools" / "bootstrap.ps1"), "-CheckOnly",
        ], cwd=ROOT, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertIn(b"environment check: OK", result.stdout)
        self.assertEqual(result.stderr, b"")
