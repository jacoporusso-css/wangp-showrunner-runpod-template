# syntax=docker/dockerfile:1.7
FROM pytorch/pytorch:2.10.0-cuda13.0-cudnn9-runtime

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

# WanGP's pinned requirements own application versions such as Gradio 5.29.0.
# Torch already comes from the CUDA 13 / Torch 2.10 base and is not replaced.
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install -r requirements.txt \
 && python -m pip check \
 && python - <<'PY'
import gradio, torch
assert gradio.__version__ == "5.29.0", gradio.__version__
assert torch.__version__.startswith("2.10.0"), torch.__version__
print("torch", torch.__version__, "gradio", gradio.__version__)
PY

COPY entrypoint.sh /usr/local/bin/wangp-entrypoint
COPY healthcheck.py /usr/local/bin/wangp-healthcheck
RUN chmod 0755 /usr/local/bin/wangp-entrypoint /usr/local/bin/wangp-healthcheck \
 && mkdir -p /workspace/lamba-video

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=10 \
  CMD ["python", "/usr/local/bin/wangp-healthcheck"]

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/usr/local/bin/wangp-entrypoint"]
