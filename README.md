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
- Current public-model-cache OCI index digest: `sha256:61562e7f7ebcadaef831948a6f091c6e2a64b4ee0fbcc53e5ad986130d25a172`
- `runpod-template.json` uses that immutable digest, not a mutable tag.

## Security and storage separation

- WanGP always starts with `--auth`.
- The exact RunPod HTTPS proxy origin is derived from `RUNPOD_POD_ID`.
- Only port `7860/http` is declared.
- Jupyter and automatic SSH are disabled in the RunPod template.
- The image rejects arbitrary extra launch arguments.
- A manually selected 200 GB RunPod network volume must be mounted at `/workspace`.
- The network volume contains public model material only, below `/workspace/wangp-public-models`.
- Protected project data is ephemeral below `/runpod-private/lamba-video` on the 50 GB container disk.
- The entrypoint fails closed unless `/workspace` is a mount point on a filesystem distinct from the container root.
- It also rejects overlapping/nested roots, a public root outside `/workspace`, or a private root outside ephemeral container storage.
- The entrypoint verifies the WanGP Git commit before launch.
- No protected project asset is built into the image.

Only these paths are routed to the public network volume:

- WanGP public checkpoints and public accelerator LoRAs (`ckpts` and `loras`);
- Hugging Face caches;
- Torch cache;
- WanGP compute cache.

Settings, config, finetune definitions, Showrunner/Deepy sessions, workspaces, uploads, logs, storage, Gradio and mask outputs, general outputs, temporary media, Hugging Face credentials/home state, WanGP cache, XDG cache, and all other project data remain below `/runpod-private/lamba-video`. Retrieve and verify protected outputs before terminating the Pod; the private tree is intentionally destroyed with the container disk.

If `WANGP_AUTH_PASSWORD` is absent, WanGP generates a passphrase and reports it in the Pod log. Store it directly in a password manager; do not put it in template environment variables, chat, repository files or shell history.

## Build and publication

GitHub Actions runs static checks and publishes the image to GHCR on `main`. Tags:

- `latest`
- `wan19.13-9e25e36`
- `sha-<commit>`

The workflow publishes SBOM and provenance attestations. The package must be public for credential-free RunPod pulls; the image contains no private project data.

Verified publication for storage-split commit `89569b05a4d52dfe3e564ffc4dec435b283de5c0`:

- GitHub Actions run `42382006291`: successful in `39m14s`;
- anonymous GHCR manifest request: HTTP 200;
- platform manifest: `linux/amd64`;
- SPDX SBOM attestation: present;
- SLSA provenance v1 attestation: present.

## RunPod template resource

`runpod-template.json` matches the RunPod v2 template schema and specifies:

- NVIDIA Pod template;
- 50 GB ephemeral container disk for private project data;
- no persistent mount declaration (network-volume selection is a manual paid deployment gate);
- storage guards requiring a separately attached volume at `/workspace`;
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
- intended region/host;
- an existing or newly created 200 GB network volume mounted at `/workspace`;
- that the network volume will contain public model weights/caches only;
- final Deploy action.

This manual confirmation is intentional because deployment starts a paid resource and determines the actual cloud tier.

## First paid run: warm the public model cache

The first Pod may be used only to populate the public model cache. Do not upload the song or protected references during this run.

1. Confirm the Pod log reports `/workspace/wangp-public-models` as the public cache and `/runpod-private/lamba-video` as the ephemeral private root. A missing or unsafe mount causes startup to stop.
2. Read the generated WanGP passphrase from RunPod logs and store it in a password manager.
3. Open the `7860` HTTP service and authenticate.
4. In **Configuration → General → Manage Models & Disk Space** (`Alt+M`), confirm the model directories resolve below the public cache and monitor disk use.
5. Configure Deepy Prime and exercise only non-sensitive smoke generations needed to load the production model families: Qwen Image 2.1 Turbo, MiniMax H3 FL2VA Pruned PDD, MiniMax H3 Ref2VA Pruned PDD, and the Ref2VA Lightx2v sound template. Use synthetic prompts and generated/non-sensitive references only.
6. Wait for every download to complete; do not stop or restart during an active model transfer.
7. Optionally run `wangp-public-cache-inventory` from the Pod console and save the JSONL inventory into the ephemeral private root before downloading it locally.
8. Terminate the Pod rather than retaining its ephemeral disk. Keep the separately managed network volume.

A later Pod in the same RunPod datacenter can attach the existing network volume and reuse the cache. It will still pull/unpack the application image, but it should not re-download model files already present and valid.

## Production run after cache warming

1. Attach the existing 200 GB network volume at `/workspace`.
2. Confirm the two storage roots in the Pod log.
3. Authenticate to WanGP.
4. Run the local supported API bootstrap from the project:

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

To inventory what is retained on the public cache, run this inside the Pod:

```bash
wangp-public-cache-inventory > /runpod-private/lamba-video/public-cache-inventory.jsonl
```

Each JSONL record contains only a path relative to `PUBLIC_MODEL_ROOT`, byte size, and SHA-256. The tool discovers actual regular files at runtime; it does not preload a model list and refuses symlinks or other non-regular files.

## Local verification

```bash
python3 -m unittest discover -s tests -v
bash -n entrypoint.sh
python3 -m py_compile healthcheck.py public_cache_inventory.py scripts/create_runpod_template.py tests/test_template.py
python3 scripts/create_runpod_template.py --check
git diff --check
```

A full runtime acceptance additionally requires the published image to start on an approved RunPod Secure Cloud GPU, pass its container health check, expose the authenticated UI, and display the required Showrunner/Qwen/MiniMax templates.
