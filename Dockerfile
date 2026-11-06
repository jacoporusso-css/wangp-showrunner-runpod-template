# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.9.5@sha256:f459f6f73a8c4ef5d69f4e6fbbdb8af751d6fa40ec34b39a1ab469acd6e289b7 AS uv

FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404@sha256:0a360022e8de4375af99430f84e8b38951acc397252163a37ceac7204d01be35

ARG WAN2GP_REPOSITORY=https://github.com/deepbeepmeep/Wan2GP.git
ARG WAN2GP_COMMIT=9e25e36e50a073a99419d406d47c13088956f48c

LABEL org.opencontainers.image.title="WanGP Showrunner for RunPod" \
      org.opencontainers.image.description="Pinned authenticated WanGP Showrunner image for the Lamba S013-S017 prototype" \
      org.opencontainers.image.source="https://github.com/jacoporusso-css/wangp-showrunner-runpod-template" \
      org.opencontainers.image.revision="${WAN2GP_COMMIT}"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    WAN2GP_HOME=/opt/Wan2GP \
    WAN2GP_PORT=7860 \
    PROJECT_ROOT=/workspace/lamba-video \
    VIRTUAL_ENV=/opt/wan-venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    HF_HOME=/workspace/lamba-video/huggingface \
    HUGGINGFACE_HUB_CACHE=/workspace/lamba-video/huggingface/hub \
    TRANSFORMERS_CACHE=/workspace/lamba-video/huggingface/transformers \
    TORCH_HOME=/workspace/lamba-video/torch \
    XDG_CACHE_HOME=/workspace/lamba-video/cache \
    GRADIO_ANALYTICS_ENABLED=False \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl ffmpeg git git-lfs jq libgl1 libglib2.0-0 \
      libsm6 libxext6 libxrender1 ninja-build pkg-config python3-dev tini \
 && git lfs install --system \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none "${WAN2GP_REPOSITORY}" "${WAN2GP_HOME}" \
 && git -C "${WAN2GP_HOME}" fetch --depth=1 origin "${WAN2GP_COMMIT}" \
 && git -C "${WAN2GP_HOME}" checkout --detach "${WAN2GP_COMMIT}" \
 && test "$(git -C "${WAN2GP_HOME}" rev-parse HEAD)" = "${WAN2GP_COMMIT}"

WORKDIR ${WAN2GP_HOME}

COPY --from=uv /uv /uvx /usr/local/bin/

# WanGP's pinned requirements own application versions such as Gradio 5.29.0.
# Keep the official RunPod CUDA 12.8 runtime, but upgrade the isolated app
# environment to the Torch 2.10 family validated with this WanGP revision.
RUN uv python install 3.11.14 \
 && uv venv --seed --python 3.11.14 "${VIRTUAL_ENV}" \
 && "${VIRTUAL_ENV}/bin/python" - <<'PY'
import sys
assert sys.version_info[:2] == (3, 11), sys.version
PY
RUN "${VIRTUAL_ENV}/bin/python" -m pip install --upgrade pip setuptools wheel \
 && "${VIRTUAL_ENV}/bin/python" -m pip install \
      torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 \
      --index-url https://download.pytorch.org/whl/cu128 \
 && "${VIRTUAL_ENV}/bin/python" -m pip install -r requirements.txt \
 && "${VIRTUAL_ENV}/bin/python" - <<'PY'
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pip", "check"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
# Upstream decord 0.6.0 marks Python 3.11 unsupported even though its
# manylinux extension imports and is the revision-pinned WanGP dependency.
allowed = {"decord 0.6.0 is not supported on this platform"}
unexpected = [line for line in lines if line not in allowed]
if unexpected or (result.returncode and not lines):
    print(result.stdout, end="")
    raise SystemExit(result.returncode or 1)
if lines:
    print("pip check allowlisted:", *lines, sep="\n")

import decord
import gradio
import torch
assert decord.__version__ == "0.6.0", decord.__version__
assert gradio.__version__ == "5.29.0", gradio.__version__
assert torch.__version__.startswith("2.10.0"), torch.__version__
print("torch", torch.__version__, "gradio", gradio.__version__, "decord", decord.__version__)
PY

ENV PATH="/opt/wan-venv/bin:${PATH}"

COPY entrypoint.sh /usr/local/bin/wangp-entrypoint
COPY healthcheck.py /usr/local/bin/wangp-healthcheck
RUN chmod 0755 /usr/local/bin/wangp-entrypoint /usr/local/bin/wangp-healthcheck \
 && mkdir -p /workspace/lamba-video

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=10 \
  CMD ["python", "/usr/local/bin/wangp-healthcheck"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/wangp-entrypoint"]
