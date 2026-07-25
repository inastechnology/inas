import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stage_appliance_bundle.py"


class StageBundleTest(unittest.TestCase):
    def test_stages_gateway_and_runtime_without_local_environments(self):
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "bundle"
            first = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((output / "edge-gateway" / "uv.lock").is_file())
            self.assertTrue((output / "shared" / "edge-runtime" / "pyproject.toml").is_file())
            self.assertTrue((output / "MANIFEST.sha256").is_file())
            self.assertFalse((output / "edge-gateway" / ".venv").exists())
            self.assertFalse((output / "edge-gateway" / "dist").exists())

            second = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(second.returncode, 0)


if __name__ == "__main__":
    unittest.main()
