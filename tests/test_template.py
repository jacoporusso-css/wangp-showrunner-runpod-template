from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "9e25e36e50a073a99419d406d47c13088956f48c"
IMAGE = "ghcr.io/jacoporusso-css/wangp-showrunner-runpod@sha256:61562e7f7ebcadaef831948a6f091c6e2a64b4ee0fbcc53e5ad986130d25a172"


class TemplateTests(unittest.TestCase):
    def test_dockerfile_is_pinned_and_authenticated(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn(f"ARG WAN2GP_COMMIT={PIN}", text)
        self.assertIn("runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404", text)
        self.assertIn("ghcr.io/astral-sh/uv:0.9.5", text)
        self.assertIn("sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35", text)
        self.assertIn("sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7", text)
        self.assertIn("uv python install 3.11.14", text)
        self.assertIn('assert gradio.__version__ == "5.29.0"', text)
        self.assertNotIn('ARG WAN2GP_COMMIT="main"', text)
        self.assertNotIn("gradio==4.44.1", text)
        self.assertNotIn("JUPYTER", text)
        self.assertEqual(text.count("EXPOSE"), 1)
        self.assertIn("EXPOSE 7860", text)
        self.assertIn("PUBLIC_MODEL_ROOT=/workspace/wangp-public-models", text)
        self.assertIn("PROJECT_ROOT=/runpod-private/lamba-video", text)
        self.assertIn("REQUIRE_NETWORK_VOLUME=1", text)
        self.assertIn("HF_HOME=/runpod-private/lamba-video/cache/huggingface-home", text)
        self.assertIn("HF_TOKEN_PATH=/runpod-private/lamba-video/config/huggingface/token", text)
        self.assertIn("HUGGINGFACE_HUB_CACHE=/workspace/wangp-public-models/huggingface/hub", text)
        self.assertIn("TORCH_HOME=/workspace/wangp-public-models/torch", text)
        self.assertIn("XDG_CACHE_HOME=/runpod-private/lamba-video/cache/xdg", text)
        self.assertIn("GRADIO_TEMP_DIR=/runpod-private/lamba-video/tmp/gradio", text)
        self.assertIn("TMPDIR=/runpod-private/lamba-video/tmp", text)

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
            'mountpoint -q "$WORKSPACE_ROOT"',
            '[[ "$(stat -c \'%d\' "$WORKSPACE_ROOT")" != "$(stat -c \'%d\' /)" ]]',
            'path_contains "$WORKSPACE_ROOT" "$PUBLIC_MODEL_ROOT"',
            'path_contains "$PRIVATE_BASE" "$PROJECT_ROOT"',
            '[[ "$(stat -c \'%d\' "$PROJECT_ROOT")" == "$(stat -c \'%d\' /)" ]]',
            'export HF_HOME="$PROJECT_ROOT/cache/huggingface-home"',
            'export HUGGINGFACE_HUB_CACHE="$PUBLIC_MODEL_ROOT/huggingface/hub"',
            'export TORCH_HOME="$PUBLIC_MODEL_ROOT/torch"',
            'export XDG_CACHE_HOME="$PROJECT_ROOT/cache/xdg"',
            'export TMPDIR="$PROJECT_ROOT/tmp"',
            'PUBLIC_DIRS=(ckpts loras huggingface torch compute-cache)',
            'Unexpected top-level path in PUBLIC_MODEL_ROOT',
            'route_directory ckpts "$PUBLIC_MODEL_ROOT" ckpts',
            'route_directory loras "$PUBLIC_MODEL_ROOT" loras',
            'route_directory computecache "$PUBLIC_MODEL_ROOT" compute-cache',
            'route_directory finetunes "$PROJECT_ROOT" finetunes',
            'route_directory storage "$PROJECT_ROOT" storage',
            'route_directory uploads "$PROJECT_ROOT" uploads',
            'route_directory outputs "$PROJECT_ROOT" outputs/wangp',
            'route_directory cache "$PROJECT_ROOT" cache/wangp',
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
        self.assertEqual(data["disk"], 50)
        self.assertNotIn("mounts", data)
        self.assertEqual(
            data["env"],
            {
                "WAN2GP_PORT": "7860",
                "PUBLIC_MODEL_ROOT": "/workspace/wangp-public-models",
                "PROJECT_ROOT": "/runpod-private/lamba-video",
                "REQUIRE_NETWORK_VOLUME": "1",
            },
        )
        self.assertFalse(data["startJupyter"])
        self.assertFalse(data["startSsh"])
        self.assertFalse(data["serverless"])
        self.assertFalse(data["public"])
        self.assertNotIn("registry", data)
        for key, value in data.get("env", {}).items():
            self.assertFalse(re.search(r"PASSWORD|TOKEN|SECRET|KEY", key, re.I), key)
            self.assertNotEqual(value, "[REDACTED]")

        labels = json.loads((ROOT / "runpod-port-labels.json").read_text(encoding="utf-8"))
        self.assertEqual(labels, [{"port": "7860", "name": "WanGP Web UI"}])
        helper = (ROOT / "scripts" / "create_runpod_template.py").read_text(encoding="utf-8")
        self.assertIn("portsConfig", helper)
        self.assertIn("saveTemplate", helper)
        self.assertIn("Port-label read-back mismatch", helper)
        self.assertIn('"volumeInGb": 0', helper)
        self.assertIn("Persistent template storage size was not cleared", helper)
        self.assertNotIn('(\"volumeMountPath\", \"volumeMountPath\")', helper)

    def test_image_contains_no_project_assets(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        copied = []
        for line in dockerfile.splitlines():
            if line.startswith("COPY ") and "--from=" not in line:
                copied.append(line.split()[1])
        self.assertEqual(copied, ["entrypoint.sh", "healthcheck.py", "public_cache_inventory.py"])

    def test_public_cache_inventory_reports_only_relative_regular_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ckpts").mkdir()
            payload = b"public model bytes\n"
            (root / "ckpts" / "model.bin").write_bytes(payload)
            result = subprocess.run(
                [sys.executable, str(ROOT / "public_cache_inventory.py")],
                env={**os.environ, "PUBLIC_MODEL_ROOT": str(root)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        records = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(
            records,
            [
                {
                    "path": "ckpts/model.bin",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ],
        )

    def test_public_cache_inventory_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            (root / "ckpts").mkdir()
            target = Path(outside) / "private.bin"
            target.write_bytes(b"private")
            (root / "ckpts" / "escape.bin").symlink_to(target)
            result = subprocess.run(
                [sys.executable, str(ROOT / "public_cache_inventory.py")],
                env={**os.environ, "PUBLIC_MODEL_ROOT": str(root)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("non-regular file is not allowed", result.stderr)

    def test_public_cache_inventory_rejects_unapproved_top_level_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "private-uploads").mkdir()
            (root / "private-uploads" / "reference.jpg").write_bytes(b"private")
            result = subprocess.run(
                [sys.executable, str(ROOT / "public_cache_inventory.py")],
                env={**os.environ, "PUBLIC_MODEL_ROOT": str(root)},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unexpected top-level public cache path", result.stderr)


if __name__ == "__main__":
    unittest.main()
