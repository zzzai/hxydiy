"""Catch report credentials omitted from the actual release container environment."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


COMPOSE = Path(__file__).resolve().parents[1] / "deploy/diy/docker-compose.hxy.yml"


class TcmDeploymentContractTests(unittest.TestCase):
    def test_api_explicitly_maps_report_settings_with_fail_closed_defaults(self):
        content = COMPOSE.read_text(encoding="utf-8")
        api = content.split("  api:", 1)[1].split("    volumes:", 1)[0]
        environment = dict(re.findall(r"^      ([A-Z_]+): (.+)$", api, re.MULTILINE))
        self.assertEqual(environment.get("TCM_REPORTS_READ_TOKEN"), "${TCM_REPORTS_READ_TOKEN:-}")
        self.assertEqual(environment.get("TCM_REPORTS_BASE_URL"), "${TCM_REPORTS_BASE_URL:-http://172.18.0.1:18090}")

    def test_compose_passes_only_configured_read_token_and_internal_default(self):
        docker = shutil.which("docker")
        if not docker:
            self.skipTest("Docker Compose unavailable; run this contract on the server")
        probe = subprocess.run([docker, "compose", "version"], capture_output=True)
        if probe.returncode:
            self.skipTest("Docker Compose plugin unavailable; run this contract on the server")
        # Never read the operator's .env or print rendered credentials.
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("TCM_REPORTS_", "COMPOSE_"))}
        environment.update(DIY_POSTGRES_PASSWORD="fixture-password", DIY_JWT_SECRET="fixture-jwt")
        with tempfile.TemporaryDirectory() as project:
            command = [docker, "compose", "--env-file", os.devnull, "--project-directory", project,
                       "-f", str(COMPOSE), "config", "--format", "json"]
            for token in (None, "isolated-read-fixture", ""):
                with self.subTest(configured=bool(token)):
                    supplied = dict(environment)
                    if token is not None:
                        supplied["TCM_REPORTS_READ_TOKEN"] = token
                    result = subprocess.run(command, env=supplied, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, "Isolated Compose configuration failed")
                    api = json.loads(result.stdout)["services"]["api"]["environment"]
                    self.assertEqual(api.get("TCM_REPORTS_READ_TOKEN"), token or "")
                    self.assertEqual(api.get("TCM_REPORTS_BASE_URL"), "http://172.18.0.1:18090")


if __name__ == "__main__":
    unittest.main()
