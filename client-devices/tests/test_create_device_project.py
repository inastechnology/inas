import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_device_project.py"
SPEC = importlib.util.spec_from_file_location("create_device_project", SCRIPT_PATH)
create_device_project = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = create_device_project
SPEC.loader.exec_module(create_device_project)


class CreateDeviceProjectTest(unittest.TestCase):
    def test_create_device_project_generates_platformio_project_with_common_library_link(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            (repo_root / "client-devices" / "common" / "lib" / "ina-client-common").mkdir(parents=True)
            spec = create_device_project.build_spec(
                project_slug="soil-device",
                device_kind="SOI",
                display_name="INA Soil Sensor",
                board="seeed_xiao_esp32s3",
                env_name=None,
                firmware_version="0.1.0",
                firmware_build_id="test-build",
                setup_ap_ssid=None,
                repo_root=repo_root,
            )

            project_root = create_device_project.create_device_project(spec, repo_root)

            self.assertEqual(project_root, repo_root / "client-devices" / "soil-device")
            self.assertTrue((project_root / "platformio.ini").is_file())
            self.assertTrue((project_root / "Makefile").is_file())
            self.assertTrue((project_root / "src" / "app" / "src" / "app.cpp").is_file())
            self.assertTrue((project_root / "src" / "app" / "src" / "app_resource.cpp").is_file())
            self.assertTrue((project_root / "lib" / "ina-client-common").is_symlink())
            self.assertEqual(
                (project_root / "lib" / "ina-client-common").readlink(),
                Path("../../common/lib/ina-client-common"),
            )
            platformio = (project_root / "platformio.ini").read_text(encoding="utf-8")
            self.assertIn('-D APP_DEVICE_KIND=\\"SOI\\"', platformio)
            self.assertIn('-D APP_FIRMWARE_PROJECT=\\"soil-device\\"', platformio)
            self.assertIn("-Wl,-u,INAS_FIRMWARE_MANIFEST", platformio)
            makefile = (project_root / "Makefile").read_text(encoding="utf-8")
            self.assertIn("RELEASE_MODULE_ID := soil-device", makefile)
            self.assertIn("RELEASE_MODULE_DEVICE_KIND := SOI", makefile)
            self.assertIn(
                "include ../common/make/esp32s3-release-module.mk",
                makefile,
            )
            app_cpp = (project_root / "src" / "app" / "src" / "app.cpp").read_text(encoding="utf-8")
            self.assertIn("class SoilDevice : public AppDevice", app_cpp)
            self.assertIn('return "INA Soil Sensor";', app_cpp)
            app_resource_cpp = (project_root / "src" / "app" / "src" / "app_resource.cpp").read_text(encoding="utf-8")
            self.assertIn("AppConfig appConfig = AppConfig();", app_resource_cpp)

    def test_create_device_project_rejects_invalid_device_kind(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)

            with self.assertRaisesRegex(ValueError, "device_kind"):
                create_device_project.build_spec(
                    project_slug="soil-device",
                    device_kind="soil",
                    display_name=None,
                    board="seeed_xiao_esp32s3",
                    env_name=None,
                    firmware_version="0.1.0",
                    firmware_build_id="test-build",
                    setup_ap_ssid=None,
                    repo_root=repo_root,
                )

    def test_create_device_project_does_not_overwrite_existing_project(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            (repo_root / "client-devices" / "common" / "lib" / "ina-client-common").mkdir(parents=True)
            (repo_root / "client-devices" / "soil-device").mkdir(parents=True)
            spec = create_device_project.build_spec(
                project_slug="soil-device",
                device_kind="SOI",
                display_name=None,
                board="seeed_xiao_esp32s3",
                env_name=None,
                firmware_version="0.1.0",
                firmware_build_id="test-build",
                setup_ap_ssid=None,
                repo_root=repo_root,
            )

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                create_device_project.create_device_project(spec, repo_root)


if __name__ == "__main__":
    unittest.main()
