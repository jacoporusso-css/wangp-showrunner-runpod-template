# WanGP Showrunner H3 — RunPod one-click image

A security-focused RunPod image for the `Lavoro senza riposo` S013–S017 prototype.

It packages the exact WanGP revision and launch policy. It contains no song, lyrics, character images, project assets, credentials, model weights, or generated outputs.

## Pinned stack

- WanGP commit: `9e25e36e50a073a99419d406d47c13088956f48c`
- WanGP version at that revision: `19.13`
- Base: official RunPod `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`
- Base and uv installer images are pinned by OCI digest, not tag alone.
- Application environment: uv-managed Python 3.11.14, Torch 2.10.0 with CUDA 12.8 wheels
- Required Gradio: `5.29.0`
- Image: `ghcr.io/jacoporusso-css/wangp-showrunner-runpod:latest`
- Immutable release tag: `ghcr.io/jacoporusso-css/wangp-showrunner-runpod:wan19.13-9e25e36`
- Published OCI index digest: `sha256:d4406549bddb9978475a4f9d327e48417f33a307cd96d823431377b14f20a62e`
- The RunPod template uses the digest reference, not a mutable tag.

## Security and persistence

- WanGP always starts with `--auth`.
- The exact RunPod HTTPS proxy origin is derived from `RUNPOD_POD_ID`.
- Only port `7860/http` is declared.
- Jupyter and automatic SSH are disabled in the RunPod template.
- The image rejects arbitrary extra launch arguments.
- Showrunner settings and productions persist under `/workspace/lamba-video/settings`.
- Deepy sessions, workspaces, model caches and outputs persist below `/workspace/lamba-video`.
- The entrypoint verifies the WanGP Git commit before launch.
- No protected project asset is built into the image.

If `WANGP_AUTH_PASSWORD` is absent, WanGP generates a passphrase and reports it in the Pod log. Store it directly in a password manager; do not put it in template environment variables, chat, repository files or shell history.

## Build and publication

GitHub Actions runs static checks and publishes the image to GHCR on `main`. Tags:

- `latest`
- `wan19.13-9e25e36`
- `sha-<commit>`

The workflow publishes SBOM and provenance attestations. The package must be public for credential-free RunPod pulls; the image contains no private project data.

Verified publication for commit `a90202216324f19663e55a1ddd2aaa6f31de7316`:

- GitHub Actions run `42265611385`: successful;
- anonymous GHCR manifest request: HTTP 200;
- platform manifest: `linux/amd64`;
- SPDX SBOM attestation: present;
- SLSA provenance v1 attestation: present.

## RunPod template resource

`runpod-template.json` matches the RunPod v2 template schema and specifies:

- NVIDIA Pod template;
- 30 GB ephemeral container disk;
- 300 GB persistent mount at `/workspace`;
- `7860/http` only;
- dashboard port label `WanGP Web UI` for port 7860;
- Jupyter off;
- automatic SSH off;
- no secret environment variables;
- no automatic Pod creation.

Creating the template does not provision a Pod or incur GPU charges:

```bash
python3 scripts/create_runpod_template.py --check

# RUNPOD_API_KEY must come from a secret manager or masked shell input.
python3 scripts/create_runpod_template.py
```

The helper is idempotent by exact template name and verifies the resource after create/update. RunPod REST v2 does not expose dashboard port labels, so the helper performs the same follow-up GraphQL `saveTemplate` operation used by the official `runpodctl` client, then reads back both the label and all security-critical REST fields. It never calls a Pod creation or state-transition endpoint.

## Deployment boundary

The resulting RunPod template is the one-click deployment preset. The user must still manually select and confirm:

- Secure Cloud, never Community Cloud for protected assets;
- On-Demand rather than Spot;
- an approved 48 GB GPU;
- current price and budget;
- intended region/host and storage policy;
- final Deploy action.

This manual confirmation is intentional because deployment starts a paid resource and determines the actual cloud tier.

## After the Pod is ready

1. Read the generated WanGP passphrase from RunPod logs and store it in a password manager.
2. Open the `7860` HTTP service and authenticate.
3. Run the local supported API bootstrap from the project:

```bash
cd /home/jacopo/ai-music-video-wangp

TOOL=tools/runpod_wangp/bin/wangp-toolkit
CFG=tools/runpod_wangp/config/prototype_s013_s017.json
STAGE=tools/runpod_wangp/staging/prototype
POD_URL=https://POD_ID-7860.proxy.runpod.net

$TOOL showrunner \
  --config "$CFG" \
  --stage-dir "$STAGE" \
  --base-url "$POD_URL" \
  --apply
```

The bootstrap prompts for the passphrase without echo and uploads only SHA-256-verified working copies.

## Local verification

```bash
python3 -m unittest discover -s tests -v
bash -n entrypoint.sh
python3 -m py_compile healthcheck.py scripts/create_runpod_template.py tests/test_template.py
python3 scripts/create_runpod_template.py --check
```

A full runtime acceptance additionally requires the published image to start on an approved RunPod Secure Cloud GPU, pass its container health check, expose the authenticated UI, and display the required Showrunner/Qwen/MiniMax templates.
