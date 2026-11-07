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
GRAPHQL_API = "https://api.runpod.io/graphql"
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


def graphql_request(token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_API,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "wangp-showrunner-runpod-template/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"RunPod GraphQL failed: HTTP {error.code}: {detail[:2000]}") from None
    if result.get("errors"):
        raise RuntimeError(f"RunPod GraphQL failed: {result['errors'][0].get('message', result['errors'][0])}")
    return result


TEMPLATE_GRAPHQL_FIELDS = """
id name imageName dockerArgs env { key value } ports volumeMountPath volumeInGb
containerDiskInGb containerRegistryAuthId startJupyter startSsh startScript
isServerless isPublic readme advancedStart category portsConfig { port name }
"""


def graphql_template_state(token: str, template_id: str) -> dict[str, Any]:
    result = graphql_request(
        token,
        f"query GetTemplateForPortLabels {{ myself {{ podTemplates {{ {TEMPLATE_GRAPHQL_FIELDS} }} }} }}",
    )
    items = result["data"]["myself"]["podTemplates"]
    matches = [item for item in items if item.get("id") == template_id]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one GraphQL template {template_id}, found {len(matches)}")
    return matches[0]


def update_port_labels(token: str, template_id: str, labels: list[dict[str, str]]) -> None:
    state = graphql_template_state(token, template_id)
    available = {
        str(item).split("/", 1)[0].strip()
        for item in (state.get("ports") if isinstance(state.get("ports"), list) else str(state.get("ports", "")).split(","))
        if str(item).strip()
    }
    normalized: list[dict[str, str]] = []
    for label in labels:
        port = str(label.get("port", "")).split("/", 1)[0].strip()
        name = str(label.get("name", "")).strip()
        if not port.isdigit() or not name:
            raise RuntimeError(f"Invalid port label: {label!r}")
        if port not in available:
            raise RuntimeError(f"Port label {port!r} does not match template ports {sorted(available)!r}")
        normalized.append({"port": port, "name": name})

    env = state.get("env") or []
    ports = state.get("ports") or []
    if isinstance(ports, list):
        ports = ",".join(ports)
    mutation_input: dict[str, Any] = {
        "id": state["id"],
        "name": state["name"],
        "imageName": state["imageName"],
        "containerDiskInGb": state["containerDiskInGb"],
        "containerRegistryAuthId": state.get("containerRegistryAuthId") or "",
        "dockerArgs": state.get("dockerArgs") or "",
        "env": env,
        "ports": ports,
        "portsConfig": normalized,
        "volumeInGb": state.get("volumeInGb") or 0,
        "isPublic": bool(state.get("isPublic")),
        "isServerless": bool(state.get("isServerless")),
        "startJupyter": bool(state.get("startJupyter")),
        "startSsh": bool(state.get("startSsh")),
        "advancedStart": bool(state.get("advancedStart")),
        "readme": state.get("readme") or "",
    }
    for source, target in (
        ("volumeMountPath", "volumeMountPath"),
        ("startScript", "startScript"),
        ("category", "category"),
    ):
        if state.get(source):
            mutation_input[target] = state[source]

    result = graphql_request(
        token,
        "mutation UpdateTemplatePortLabels($input: SaveTemplateInput) { saveTemplate(input: $input) { id } }",
        {"input": mutation_input},
    )
    if result.get("data", {}).get("saveTemplate", {}).get("id") != template_id:
        raise RuntimeError("RunPod port-label update returned an unexpected template ID")
    updated = graphql_template_state(token, template_id)
    if updated.get("portsConfig") != normalized:
        raise RuntimeError(f"Port-label read-back mismatch: {updated.get('portsConfig')!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "runpod-template.json")
    parser.add_argument("--port-labels", type=Path, default=ROOT / "runpod-port-labels.json")
    parser.add_argument("--check", action="store_true", help="validate locally without calling RunPod")
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    port_labels = json.loads(args.port_labels.read_text(encoding="utf-8"))
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
    if port_labels != [{"port": "7860", "name": "WanGP Web UI"}]:
        raise SystemExit("Port labels must name port 7860 as 'WanGP Web UI'.")
    if args.check:
        print(json.dumps({"valid": True, "name": payload["name"], "image": payload["image"]}, indent=2))
        return 0
    token = os.environ.get("RUNPOD_API_KEY")
    if not token:
        raise SystemExit("RUNPOD_API_KEY is not set. Use a secret manager or masked shell input; never save it in this repository.")
    catalog = request("GET", "/templates", token)
    items = catalog if isinstance(catalog, list) else catalog.get("templates", catalog.get("items", catalog.get("data", [])))
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
    update_port_labels(token, template_id, port_labels)
    verified_after_labels = request("GET", f"/templates/{template_id}", token)
    for key in ("name", "image", "ports", "disk", "allowedCudaVersions", "mounts", "public", "serverless", "startJupyter", "startSsh"):
        if verified_after_labels.get(key) != payload.get(key):
            raise RuntimeError(f"Template changed during port-label update for {key}: {verified_after_labels.get(key)!r}")
    print(json.dumps({"action": action, "id": template_id, "name": verified["name"], "image": verified["image"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
