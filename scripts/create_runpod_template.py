#!/usr/bin/env python3
"""Create or update the non-billing RunPod template resource.

Requires RUNPOD_API_KEY in the process environment. This creates a template only;
it never creates, starts, stops, or terminates a Pod.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.runpod.io/v2"
ROOT = Path(__file__).resolve().parents[1]


def request(method: str, path: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"RunPod API {method} {path} failed: HTTP {error.code}: {detail[:2000]}") from None
    return json.loads(data) if data else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runpod-template.json")
    parser.add_argument("--check", action="store_true", help="validate locally without calling RunPod")
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    required = {"name", "image", "disk", "ports", "mounts"}
    missing = sorted(required - payload.keys())
    if missing:
        raise SystemExit("Missing template fields: " + ", ".join(missing))
    if payload["ports"] != ["7860/http"] or payload.get("startJupyter") or payload.get("startSsh"):
        raise SystemExit("Template must expose only 7860/http with Jupyter and automatic SSH disabled.")
    image = payload.get("image", "")
    if "@sha256:" not in image or image.endswith("@sha256:"):
        raise SystemExit("Template image must use an immutable sha256 digest reference.")
    if payload.get("public") is not False or payload.get("serverless") is not False:
        raise SystemExit("Template must remain private and Pod-only (serverless=false).")
    if payload.get("allowedCudaVersions") != ["12.8"]:
        raise SystemExit("Template must remain pinned to CUDA 12.8 compatibility.")
    if args.check:
        print(json.dumps({"valid": True, "name": payload["name"], "image": payload["image"]}, indent=2))
        return 0
    token = os.environ.get("RUNPOD_API_KEY")
    if not token:
        raise SystemExit("RUNPOD_API_KEY is not set. Use a secret manager or masked shell input; never save it in this repository.")
    catalog = request("GET", "/templates", token)
    items = catalog if isinstance(catalog, list) else catalog.get("items", catalog.get("data", []))
    matches = [item for item in items if item.get("name") == payload["name"]]
    if len(matches) > 1:
        raise SystemExit(f"Found {len(matches)} same-name templates; refusing ambiguous update.")
    if matches:
        template_id = matches[0]["id"]
        result = request("PATCH", f"/templates/{template_id}", token, payload)
        action = "updated"
    else:
        result = request("POST", "/templates", token, payload)
        template_id = result["id"]
        action = "created"
    verified = request("GET", f"/templates/{template_id}", token)
    for key in ("name", "image", "ports", "disk"):
        if verified.get(key) != payload.get(key):
            raise RuntimeError(f"Template read-back mismatch for {key}: {verified.get(key)!r}")
    print(json.dumps({"action": action, "id": template_id, "name": verified["name"], "image": verified["image"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
