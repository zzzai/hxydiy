import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[2]
CREATE = REPO_ROOT / "deploy/diy/create-release.sh"
ACTIVATE = REPO_ROOT / "deploy/diy/activate-release.sh"
BASH = shutil.which("bash")


def is_windows_wsl_launcher(executable: str) -> bool:
    if os.name != "nt":
        return False
    normalized = Path(executable).resolve().as_posix().lower()
    return normalized.endswith("/windows/system32/bash.exe")


def shell_command(script: Path, *args: str) -> list[str]:
    if os.name == "nt":
        if BASH is None:
            raise unittest.SkipTest("Windows 发布脚本测试需要 Git Bash")
        if is_windows_wsl_launcher(BASH):
            raise unittest.SkipTest("Windows 发布脚本测试需要 Git Bash，不能使用 WSL 启动器")
        return [BASH, script.as_posix(), *args]
    return [str(script), *args]


class ReleaseScriptTests(unittest.TestCase):
    def test_container_entrypoint_uses_unix_line_endings(self):
        entrypoint = (REPO_ROOT / "hxy-server/entrypoint.sh").read_bytes()

        self.assertTrue(entrypoint.startswith(b"#!/bin/sh\n"))
        self.assertNotIn(b"\r\n", entrypoint)

    def test_existing_database_migrations_require_explicit_opt_in(self):
        entrypoint = (REPO_ROOT / "hxy-server/entrypoint.sh").read_text(encoding="utf-8")
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        self.assertIn('if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then', entrypoint)
        self.assertIn('RUN_MIGRATIONS: "false"', compose)

    def test_backend_deploy_health_check_matches_compose_host_port(self):
        deploy = (REPO_ROOT / "hxy-server/deploy.sh").read_text(encoding="utf-8")
        compose = (REPO_ROOT / "hxy-server/docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn('API_HEALTH_URL=${API_HEALTH_URL:-http://127.0.0.1:18086/api/v1/health}', deploy)
        self.assertIn('"18086:8010"', compose)
        self.assertIn('curl -sf "$API_HEALTH_URL"', deploy)
        self.assertIn('curl -fsS "$API_HEALTH_URL"', deploy)

    def test_self_signed_sms_configuration_is_forwarded_to_api_container(self):
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        for variable in (
            "ALIYUN_SMS_ACCESS_KEY_ID",
            "ALIYUN_SMS_ACCESS_KEY_SECRET",
            "ALIYUN_SMS_SIGN_NAME",
            "ALIYUN_SMS_TEMPLATE_CODE",
            "ALIYUN_PNVS_ACCESS_KEY_ID",
            "ALIYUN_PNVS_ACCESS_KEY_SECRET",
            "ALIYUN_PNVS_SCHEME_NAME",
        ):
            self.assertIn(f"{variable}: ${{{variable}:-}}", compose)

    def test_wechat_payment_configuration_is_forwarded_to_api_container(self):
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        for variable in (
            "WX_APPID",
            "WX_APPSECRET",
            "WXPAY_MCHID",
            "WXPAY_APPID",
            "WXPAY_APIV3_KEY",
            "WXPAY_CERT_SERIAL_NO",
            "WXPAY_PRIVATE_KEY_PATH",
            "WXPAY_PUBLIC_KEY_ID",
            "WXPAY_PUBLIC_KEY_PATH",
            "WXPAY_PLATFORM_CERT_PATH",
            "WXPAY_NOTIFY_URL",
        ):
            self.assertIn(f"{variable}: ${{{variable}:-}}", compose)
        self.assertIn(
            "${WXPAY_CERTS_DIR:-/root/hxy-diy-20260811/certs}:/etc/hxy/certs:ro",
            compose,
        )

    def test_release_dockerfile_copies_built_customer_and_admin_static_files(self):
        dockerfile = (REPO_ROOT / "deploy/diy/Dockerfile.release").read_text(encoding="utf-8")

        self.assertIn("COPY diy-web/dist/ ./diy-web/dist/", dockerfile)
        self.assertIn("COPY admin-react/dist/ ./admin-react/dist/", dockerfile)

    def test_release_compose_build_context_points_to_release_root(self):
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")
        self.assertIn("context: ${HXY_DIY_CURRENT:-../../current}", compose)

    def test_release_creation_excludes_local_runtime_and_secret_files(self):
        create = (REPO_ROOT / "deploy/diy/create-release.sh").read_text(encoding="utf-8")

        for excluded in (".venv", "*.pyc", "*.db", ".env", "__pycache__"):
            self.assertIn(f"--exclude='{excluded}'", create)

    def test_creates_complete_release_and_switches_current(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            release_root = root / "production"
            shutil.copytree(REPO_ROOT / "hxy-server", workspace / "hxy-server", ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
            shutil.copytree(REPO_ROOT / "deploy", workspace / "deploy")
            (workspace / "diy-web/dist").mkdir(parents=True)
            (workspace / "admin-react/dist").mkdir(parents=True)
            (workspace / "diy-web/dist/index.html").write_text("customer", encoding="utf-8")
            (workspace / "admin-react/dist/index.html").write_text("staff", encoding="utf-8")
            (workspace / "hxy-server/.venv").mkdir()
            (workspace / "hxy-server/.venv/marker").write_text("runtime", encoding="utf-8")
            (workspace / "hxy-server/local.db").write_text("database", encoding="utf-8")
            (workspace / "hxy-server/.env").write_text("SECRET=do-not-package", encoding="utf-8")
            (workspace / "hxy-server/app/__pycache__").mkdir(parents=True)
            (workspace / "hxy-server/app/__pycache__/module.pyc").write_bytes(b"bytecode")
            environment = {**os.environ, "HXY_DIY_RELEASE_ROOT": str(release_root)}

            copied_create = workspace / "deploy/diy/create-release.sh"
            copied_activate = workspace / "deploy/diy/activate-release.sh"
            created = subprocess.run(
                shell_command(copied_create, "p0-test"), cwd=workspace, env=environment,
                capture_output=True, text=True, check=True,
            )
            activated = subprocess.run(
                shell_command(copied_activate, "p0-test"), cwd=workspace, env=environment,
                capture_output=True, text=True, check=True,
            )

            release = release_root / "releases/p0-test"
            self.assertEqual(Path(created.stdout.strip()), release)
            self.assertEqual(Path(activated.stdout.strip()), release)
            if os.name == "posix":
                self.assertEqual((release_root / "current").resolve(), release)
            self.assertTrue((release / "MANIFEST.sha256").is_file())
            self.assertFalse((release / "hxy-server/.venv").exists())
            self.assertFalse((release / "hxy-server/local.db").exists())
            self.assertFalse((release / "hxy-server/.env").exists())
            self.assertFalse((release / "hxy-server/app/__pycache__").exists())

    def test_can_atomically_roll_back_current_to_previous_release(self):
        if os.name != "posix":
            self.skipTest("current 符号链接回滚契约需要 POSIX mv -Tf 语义")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            release_root = root / "production"
            shutil.copytree(REPO_ROOT / "hxy-server", workspace / "hxy-server", ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
            shutil.copytree(REPO_ROOT / "deploy", workspace / "deploy")
            (workspace / "diy-web/dist").mkdir(parents=True)
            (workspace / "admin-react/dist").mkdir(parents=True)
            (workspace / "diy-web/dist/index.html").write_text("customer-v1", encoding="utf-8")
            (workspace / "admin-react/dist/index.html").write_text("staff-v1", encoding="utf-8")
            environment = {**os.environ, "HXY_DIY_RELEASE_ROOT": str(release_root)}
            copied_create = workspace / "deploy/diy/create-release.sh"
            copied_activate = workspace / "deploy/diy/activate-release.sh"

            subprocess.run(shell_command(copied_create, "release-v1"), cwd=workspace / "deploy/diy", env=environment, capture_output=True, text=True, check=True)
            subprocess.run(shell_command(copied_activate, "release-v1"), cwd=workspace / "deploy/diy", env=environment, capture_output=True, text=True, check=True)
            (workspace / "diy-web/dist/index.html").write_text("customer-v2", encoding="utf-8")
            (workspace / "admin-react/dist/index.html").write_text("staff-v2", encoding="utf-8")
            subprocess.run(shell_command(copied_create, "release-v2"), cwd=workspace / "deploy/diy", env=environment, capture_output=True, text=True, check=True)
            subprocess.run(shell_command(copied_activate, "release-v2"), cwd=workspace / "deploy/diy", env=environment, capture_output=True, text=True, check=True)
            rolled_back = subprocess.run(shell_command(copied_activate, "release-v1"), cwd=workspace / "deploy/diy", env=environment, capture_output=True, text=True, check=True)

            self.assertEqual(Path(rolled_back.stdout.strip()), release_root / "releases/release-v1")
            if os.name == "posix":
                self.assertEqual((release_root / "current").resolve(), release_root / "releases/release-v1")

    def test_refuses_to_activate_an_incomplete_release(self):
        with TemporaryDirectory() as directory:
            release_root = Path(directory)
            (release_root / "releases/broken").mkdir(parents=True)
            environment = {**os.environ, "HXY_DIY_RELEASE_ROOT": str(release_root)}

            result = subprocess.run(
                shell_command(ACTIVATE, "broken"), env=environment, capture_output=True, text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((release_root / "current").exists())


if __name__ == "__main__":
    unittest.main()
