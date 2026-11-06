#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

WAN2GP_HOME="${WAN2GP_HOME:-/opt/Wan2GP}"
PROJECT_ROOT="${PROJECT_ROOT:-/workspace/lamba-video}"
PORT="${WAN2GP_PORT:-7860}"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/wangp.log"

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "Invalid WAN2GP_PORT: $PORT" >&2
  exit 2
fi

if [[ -z "${RUNPOD_POD_ID:-}" && -z "${WANGP_PUBLIC_URL:-}" ]]; then
  echo "RUNPOD_POD_ID or WANGP_PUBLIC_URL is required." >&2
  exit 2
fi

PUBLIC_URL="${WANGP_PUBLIC_URL:-https://${RUNPOD_POD_ID}-${PORT}.proxy.runpod.net}"
python - "$PUBLIC_URL" <<'PY'
import sys
from urllib.parse import urlsplit
url = urlsplit(sys.argv[1])
assert url.scheme == "https", "public URL must use HTTPS"
assert url.netloc and not url.username and not url.password, "invalid public URL authority"
assert not url.path.strip("/") and not url.query and not url.fragment, "public URL must be an origin"
PY

mkdir -p \
  "$PROJECT_ROOT/settings" \
  "$PROJECT_ROOT/config" \
  "$PROJECT_ROOT/deepy_sessions" \
  "$PROJECT_ROOT/workspaces" \
  "$PROJECT_ROOT/logs" \
  "$PROJECT_ROOT/huggingface" \
  "$PROJECT_ROOT/torch" \
  "$PROJECT_ROOT/cache" \
  "$PROJECT_ROOT/models" \
  "$PROJECT_ROOT/outputs"
chmod 0700 "$PROJECT_ROOT" "$LOG_DIR"

persist_directory() {
  local name="$1" source="$WAN2GP_HOME/$1" target="$PROJECT_ROOT/$2"
  mkdir -p "$target"
  if [[ -L "$source" ]]; then
    [[ "$(readlink -f "$source")" == "$(readlink -f "$target")" ]] || {
      echo "Refusing unexpected symlink: $source" >&2
      exit 2
    }
    return
  fi
  if [[ -d "$source" ]]; then
    if [[ -n "$(find "$source" -mindepth 1 -maxdepth 1 -print -quit)" && -z "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      cp -a "$source"/. "$target"/
    fi
    rm -rf "$source"
  elif [[ -e "$source" ]]; then
    echo "Refusing non-directory persistent path: $source" >&2
    exit 2
  fi
  ln -s "$target" "$source"
}

persist_directory ckpts models/ckpts
persist_directory loras models/loras
persist_directory finetunes models/finetunes
persist_directory storage storage
persist_directory gradio_outputs outputs/gradio
persist_directory mask_outputs outputs/masks
persist_directory tmp tmp
persist_directory cache wangp-cache
persist_directory computecache compute-cache

cd "$WAN2GP_HOME"
EXPECTED_COMMIT="9e25e36e50a073a99419d406d47c13088956f48c"
ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$EXPECTED_COMMIT" ]] || {
  echo "WanGP commit mismatch: $ACTUAL_COMMIT" >&2
  exit 2
}

ARGS=(
  --listen
  --server-port "$PORT"
  --public-url "$PUBLIC_URL"
  --auth
  --settings "$PROJECT_ROOT/settings"
  --config "$PROJECT_ROOT/config"
  --deepy-sessions-dir "$PROJECT_ROOT/deepy_sessions"
  --workspaces-dir "$PROJECT_ROOT/workspaces"
)

if [[ -n "${WAN2GP_EXTRA_ARGS:-}" ]]; then
  echo "WAN2GP_EXTRA_ARGS is intentionally unsupported; rebuild the image for reviewed launch changes." >&2
  exit 2
fi

{
  echo "WanGP pinned commit: $ACTUAL_COMMIT"
  echo "Public URL: $PUBLIC_URL"
  echo "Persistent root: $PROJECT_ROOT"
  echo "Authentication: enabled"
} | tee "$LOG_FILE"
chmod 0600 "$LOG_FILE"

exec > >(tee -a "$LOG_FILE") 2>&1
exec python -u wgp.py "${ARGS[@]}"
