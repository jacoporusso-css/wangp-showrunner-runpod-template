#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

WAN2GP_HOME="${WAN2GP_HOME:-/opt/Wan2GP}"
PUBLIC_MODEL_ROOT="${PUBLIC_MODEL_ROOT:-/workspace/wangp-public-models}"
PROJECT_ROOT="${PROJECT_ROOT:-/runpod-private/lamba-video}"
REQUIRE_NETWORK_VOLUME="${REQUIRE_NETWORK_VOLUME:-1}"
PORT="${WAN2GP_PORT:-7860}"

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

normalize_path() {
  realpath -m -- "$1"
}

path_contains() {
  local parent="${1%/}" child="${2%/}"
  [[ "$child" == "$parent" || "$child" == "$parent/"* ]]
}

if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
  echo "Invalid WAN2GP_PORT: $PORT" >&2
  exit 2
fi

[[ -n "${RUNPOD_POD_ID:-}" || -n "${WANGP_PUBLIC_URL:-}" ]] || fail "RUNPOD_POD_ID or WANGP_PUBLIC_URL is required."

[[ "$REQUIRE_NETWORK_VOLUME" == "1" ]] || fail "REQUIRE_NETWORK_VOLUME must be 1."
[[ "$PUBLIC_MODEL_ROOT" == /* && "$PROJECT_ROOT" == /* ]] || fail "Storage roots must be absolute paths."

PUBLIC_MODEL_ROOT="$(normalize_path "$PUBLIC_MODEL_ROOT")"
PROJECT_ROOT="$(normalize_path "$PROJECT_ROOT")"
WORKSPACE_ROOT="$(normalize_path /workspace)"
PRIVATE_BASE="$(normalize_path /runpod-private)"

mountpoint -q "$WORKSPACE_ROOT" || fail "/workspace must be a manually attached network-volume mount."
[[ "$(stat -c '%d' "$WORKSPACE_ROOT")" != "$(stat -c '%d' /)" ]] || fail "/workspace must be a filesystem distinct from the container root."
path_contains "$WORKSPACE_ROOT" "$PUBLIC_MODEL_ROOT" || fail "PUBLIC_MODEL_ROOT must be below /workspace."
[[ "$PUBLIC_MODEL_ROOT" != "$WORKSPACE_ROOT" ]] || fail "PUBLIC_MODEL_ROOT may not be /workspace itself."
path_contains "$PRIVATE_BASE" "$PROJECT_ROOT" || fail "PROJECT_ROOT must be below /runpod-private."
if path_contains "$PUBLIC_MODEL_ROOT" "$PROJECT_ROOT" || path_contains "$PROJECT_ROOT" "$PUBLIC_MODEL_ROOT"; then
  fail "PUBLIC_MODEL_ROOT and PROJECT_ROOT must not overlap or contain one another."
fi

mkdir -p "$PUBLIC_MODEL_ROOT" "$PROJECT_ROOT"
[[ "$(readlink -f "$PUBLIC_MODEL_ROOT")" == "$PUBLIC_MODEL_ROOT" ]] || fail "PUBLIC_MODEL_ROOT may not resolve through a symlink."
[[ "$(readlink -f "$PROJECT_ROOT")" == "$PROJECT_ROOT" ]] || fail "PROJECT_ROOT may not resolve through a symlink."
[[ "$(stat -c '%d' "$PUBLIC_MODEL_ROOT")" == "$(stat -c '%d' "$WORKSPACE_ROOT")" ]] || fail "PUBLIC_MODEL_ROOT escaped the /workspace filesystem."
[[ "$(stat -c '%d' "$PROJECT_ROOT")" == "$(stat -c '%d' /)" ]] || fail "PROJECT_ROOT must remain on ephemeral container storage."

LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/wangp.log"
export HF_HOME="$PROJECT_ROOT/cache/huggingface-home"
export HF_TOKEN_PATH="$PROJECT_ROOT/config/huggingface/token"
export HF_STORED_TOKENS_PATH="$PROJECT_ROOT/config/huggingface/stored_tokens"
export HUGGINGFACE_HUB_CACHE="$PUBLIC_MODEL_ROOT/huggingface/hub"
export TRANSFORMERS_CACHE="$PUBLIC_MODEL_ROOT/huggingface/transformers"
export HF_ASSETS_CACHE="$PUBLIC_MODEL_ROOT/huggingface/assets"
export TORCH_HOME="$PUBLIC_MODEL_ROOT/torch"
export XDG_CACHE_HOME="$PROJECT_ROOT/cache/xdg"
export GRADIO_TEMP_DIR="$PROJECT_ROOT/tmp/gradio"
export TMPDIR="$PROJECT_ROOT/tmp"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"

PUBLIC_URL="${WANGP_PUBLIC_URL:-https://${RUNPOD_POD_ID}-${PORT}.proxy.runpod.net}"
python - "$PUBLIC_URL" <<'PY'
import sys
from urllib.parse import urlsplit
url = urlsplit(sys.argv[1])
assert url.scheme == "https", "public URL must use HTTPS"
assert url.netloc and not url.username and not url.password, "invalid public URL authority"
assert not url.path.strip("/") and not url.query and not url.fragment, "public URL must be an origin"
PY

PUBLIC_DIRS=(ckpts loras huggingface torch compute-cache)
for name in "${PUBLIC_DIRS[@]}"; do
  mkdir -p "$PUBLIC_MODEL_ROOT/$name"
  [[ -d "$PUBLIC_MODEL_ROOT/$name" && ! -L "$PUBLIC_MODEL_ROOT/$name" ]] || fail "Public cache path must be a real directory: $name"
  [[ "$(stat -c '%d' "$PUBLIC_MODEL_ROOT/$name")" == "$(stat -c '%d' "$WORKSPACE_ROOT")" ]] || fail "Public cache path escaped the network volume: $name"
done
while IFS= read -r -d '' entry; do
  name="${entry##*/}"
  allowed_public_dir=0
  for allowed_name in "${PUBLIC_DIRS[@]}"; do
    [[ "$name" == "$allowed_name" ]] && allowed_public_dir=1
  done
  (( allowed_public_dir == 1 )) || fail "Unexpected top-level path in PUBLIC_MODEL_ROOT: $name"
done < <(find "$PUBLIC_MODEL_ROOT" -mindepth 1 -maxdepth 1 -print0)

mkdir -p \
  "$PROJECT_ROOT/settings" \
  "$PROJECT_ROOT/config" \
  "$PROJECT_ROOT/deepy_sessions" \
  "$PROJECT_ROOT/workspaces" \
  "$PROJECT_ROOT/logs" \
  "$PROJECT_ROOT/storage" \
  "$PROJECT_ROOT/uploads" \
  "$PROJECT_ROOT/finetunes" \
  "$PROJECT_ROOT/outputs/gradio" \
  "$PROJECT_ROOT/outputs/masks" \
  "$PROJECT_ROOT/tmp/gradio" \
  "$PROJECT_ROOT/cache/xdg" \
  "$PROJECT_ROOT/cache/huggingface-home" \
  "$PROJECT_ROOT/config/huggingface" \
  "$PROJECT_ROOT/cache/wangp"
chmod 0700 "$PUBLIC_MODEL_ROOT" "$PROJECT_ROOT" "$LOG_DIR"

route_directory() {
  local name="$1" target_root="$2" target_relative="$3"
  local source="$WAN2GP_HOME/$name" target="$target_root/$target_relative"
  mkdir -p "$target"
  if [[ -L "$source" ]]; then
    [[ "$(readlink -f "$source")" == "$(readlink -f "$target")" ]] || {
      echo "Refusing unexpected symlink: $source" >&2
      exit 2
    }
    return
  fi
  if [[ -d "$source" ]]; then
    if [[ -n "$(find "$source" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      [[ -z "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]] || fail "Refusing to merge non-empty storage paths: $source and $target"
      cp -a -- "$source"/. "$target"/
    fi
    rm -rf -- "$source"
  elif [[ -e "$source" ]]; then
    fail "Refusing non-directory routed path: $source"
  fi
  ln -s -- "$target" "$source"
}

route_directory ckpts "$PUBLIC_MODEL_ROOT" ckpts
route_directory loras "$PUBLIC_MODEL_ROOT" loras
route_directory computecache "$PUBLIC_MODEL_ROOT" compute-cache

route_directory finetunes "$PROJECT_ROOT" finetunes
route_directory storage "$PROJECT_ROOT" storage
route_directory uploads "$PROJECT_ROOT" uploads
route_directory gradio_outputs "$PROJECT_ROOT" outputs/gradio
route_directory mask_outputs "$PROJECT_ROOT" outputs/masks
route_directory outputs "$PROJECT_ROOT" outputs/wangp
route_directory tmp "$PROJECT_ROOT" tmp/wan2gp
route_directory cache "$PROJECT_ROOT" cache/wangp

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
  echo "Public model cache: $PUBLIC_MODEL_ROOT"
  echo "Ephemeral private project root: $PROJECT_ROOT"
  echo "Authentication: enabled"
} | tee "$LOG_FILE"
chmod 0600 "$LOG_FILE"

exec > >(tee -a "$LOG_FILE") 2>&1
exec python -u wgp.py "${ARGS[@]}"
