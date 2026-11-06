from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "9e25e36e50a073a99419d406d47c13088956f48c"
IMAGE = "ghcr.io/jacoporusso-css/wangp-showrunner-runpod:latest"


class TemplateTests(unittest.TestCase):
    def test_dockerfile_is_pinned_and_authenticated(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn(f"ARG WAN2GP_COMMIT={PIN}", text)
        self.assertIn("runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404", text)
        self.assertIn('assert gradio.__version__ == "5.29.0"', text)
        self.assertNotIn('ARG WAN2GP_COMMIT="main"', text)
        self.assertNotIn("gradio==4.44.1", text)
        self.assertNotIn("JUPYTER", text)
        self.assertEqual(text.count("EXPOSE"), 1)
        self.assertIn("EXPOSE 7860", text)

    def test_entrypoint_has_security_and_persistence_controls(self):
        text = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
        for required in (
            "--auth",
            "--public-url",
            '--settings "$PROJECT_ROOT/settings"',
            '--config "$PROJECT_ROOT/config"',
            '--deepy-sessions-dir "$PROJECT_ROOT/deepy_sessions"',
            '--workspaces-dir "$PROJECT_ROOT/workspaces"',
            f'EXPECTED_COMMIT="{PIN}"',
        ):
            self.assertIn(required, text)
        self.assertNotIn("--no-auth", text)
        self.assertNotIn("--share", text)
        self.assertNotIn("8888", text)

    def test_runpod_template_matches_current_v2_shape(self):
        data = json.loads((ROOT / "runpod-template.json").read_text(encoding="utf-8"))
        self.assertEqual(data["image"], IMAGE)
        self.assertEqual(data["allowedCudaVersions"], ["12.8"])
        self.assertEqual(data["ports"], ["7860/http"])
        self.assertEqual(data["disk"], 30)
        self.assertEqual(data["mounts"]["persistent"], {"size": 300, "path": "/workspace"})
        self.assertFalse(data["startJupyter"])
        self.assertFalse(data["startSsh"])
        self.assertFalse(data["serverless"])
        self.assertFalse(data["public"])
        self.assertNotIn("registry", data)
        for key, value in data.get("env", {}).items():
            self.assertFalse(re.search(r"PASSWORD|TOKEN|SECRET|KEY", key, re.I), key)
            self.assertNotEqual(value, "[REDACTED]")

    def test_image_contains_no_project_assets(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        copied = re.findall(r"^COPY\s+([^\s]+)", dockerfile, flags=re.MULTILINE)
        self.assertEqual(copied, ["entrypoint.sh", "healthcheck.py"])


if __name__ == "__main__":
    unittest.main()
