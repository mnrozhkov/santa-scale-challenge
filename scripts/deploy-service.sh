#!/usr/bin/env bash
# Build, push, and run santa-service on a public CPU endpoint.
# Secrets are passed as --env and never printed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IMAGE_LOCAL="${SANTA_SERVICE_IMAGE_LOCAL:-santa-service:dev}"
IMAGE_REMOTE="${SANTA_SERVICE_IMAGE:-cr.eu-north1.nebius.cloud/e00gw2b7v3pxetvpy7/santa-service:dev}"
NAME="${SANTA_SERVICE_NAME:-santa-service}"
REGISTRY_HOST="${IMAGE_REMOTE%%/*}"
DOCKERFILE="${SANTA_SERVICE_DOCKERFILE:-docker/service.Dockerfile}"

ENV_KEYS=(
  TOKEN_FACTORY_API_KEY
  IMAGE_ENDPOINT_URL
  IMAGE_ENDPOINT_TOKEN
  VIDEO_ENDPOINT_URL
  VIDEO_ENDPOINT_TOKEN
  AUDIO_ENDPOINT_URL
  AUDIO_ENDPOINT_TOKEN
  OPENAI_API_KEY
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_ENDPOINT_URL
  AWS_DEFAULT_REGION
  AWS_CA_BUNDLE
  AWS_S3_BUCKET
  NEBIUS_BUCKET_NAME
  NEBIUS_PROJECT_ID
  NEBIUS_BUCKET_ID
  NEBIUS_SUBNET_ID
  NEBIUS_IAM_TOKEN
  SANTA_FALLBACK
  SANTA_OPERATOR_TOKEN
)

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy-service.sh <build|push|up|ship|url|restart|recreate>

  build     docker build linux/amd64 → santa-service:dev
  push      tag + push cr.eu-north1.nebius.cloud/e00gw2b7v3pxetvpy7/santa-service:dev
  up        create the CPU endpoint if missing (--auth none); no-op if it exists
  restart   nebius ai endpoint restart (same HTTPS URL)
  recreate  stop/delete/create with the same --name (URL may change)
  ship      build && push && restart; recreate if restart fails
  url       print the managed https:// URL for the QR

Local Vite stays the fast UI loop. ship is only for the public QR URL.
IAM: nebius iam get-access-token is minted at up/recreate (12h). QR guests never see it.
EOF
}

load_env() {
  local env_file="$ROOT/.env"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}

refresh_iam() {
  # Stale NEBIUS_IAM_TOKEN in .env makes the CLI Unauthenticated. Drop it, then
  # mint a live token for the container (--env) and for this process.
  unset NEBIUS_IAM_TOKEN
  if ! command -v nebius >/dev/null 2>&1; then
    return 0
  fi
  local tok
  tok="$(nebius iam get-access-token 2>/dev/null || true)"
  if [[ -n "${tok}" ]]; then
    NEBIUS_IAM_TOKEN="$tok"
    export NEBIUS_IAM_TOKEN
  fi
}

require_nebius() {
  if ! command -v nebius >/dev/null 2>&1; then
    echo "nebius CLI not found" >&2
    exit 1
  fi
}

registry_login() {
  require_nebius
  echo "docker login ${REGISTRY_HOST} (iam)" >&2
  nebius iam get-access-token | docker login "$REGISTRY_HOST" --username iam --password-stdin >/dev/null
}

py_json() {
  python3 -c "$1"
}

endpoint_json() {
  require_nebius
  load_env
  refresh_iam
  local parent="${NEBIUS_PROJECT_ID:-}"
  if [[ -z "$parent" ]]; then
    echo "NEBIUS_PROJECT_ID is required to look up ${NAME}" >&2
    exit 1
  fi
  nebius ai endpoint get-by-name --name "$NAME" --parent-id "$parent" --format json
}

endpoint_id_from_json() {
  py_json 'import json,sys
d=json.load(sys.stdin)
print(d.get("metadata",{}).get("id") or d.get("id") or "")'
}

https_url_from_json() {
  py_json 'import json,sys
d=json.load(sys.stdin)
eps=d.get("status",{}).get("public_endpoints") or []
for e in eps:
    if isinstance(e, str):
        s=e
    elif isinstance(e, dict):
        s=e.get("url") or e.get("address") or e.get("endpoint") or ""
    else:
        s=""
    if str(s).startswith("https://"):
        print(s)
        break
'
}

cmd_build() {
  echo "building ${IMAGE_LOCAL} from ${DOCKERFILE}" >&2
  docker build --platform linux/amd64 -f "$DOCKERFILE" -t "$IMAGE_LOCAL" .
}

cmd_push() {
  registry_login
  echo "pushing ${IMAGE_REMOTE}" >&2
  docker tag "$IMAGE_LOCAL" "$IMAGE_REMOTE"
  docker push "$IMAGE_REMOTE"
}

collect_env_args() {
  # Prints --env KEY=VALUE lines to stdout (values not echoed elsewhere).
  local key val
  for key in "${ENV_KEYS[@]}"; do
    val="${!key-}"
    if [[ -n "${val}" ]]; then
      printf -- '--env\n%s=%s\n' "$key" "$val"
      echo "  env ${key} (set)" >&2
    fi
  done
}

cmd_create() {
  require_nebius
  load_env
  refresh_iam
  local parent="${NEBIUS_PROJECT_ID:-}"
  local -a args=(
    ai endpoint create
    --name "$NAME"
    --image "$IMAGE_REMOTE"
    --platform cpu-e2
    --preset 4vcpu-16gb
    --container-port 8000
    --auth none
  )
  if [[ -n "$parent" ]]; then
    args+=(--parent-id "$parent")
  fi
  local -a env_args=()
  while IFS= read -r line; do
    env_args+=("$line")
  done < <(collect_env_args)
  echo "creating endpoint ${NAME} (auth none, cpu-e2 4vcpu-16gb, port 8000)" >&2
  nebius "${args[@]}" "${env_args[@]}"
}

cmd_up() {
  load_env
  if endpoint_json >/dev/null 2>&1; then
    echo "endpoint ${NAME} already exists (no-op)" >&2
    cmd_url
    return 0
  fi
  cmd_create
  cmd_url
}

cmd_restart() {
  local raw id
  if ! raw="$(endpoint_json)"; then
    echo "endpoint ${NAME} not found" >&2
    return 1
  fi
  id="$(printf '%s' "$raw" | endpoint_id_from_json || true)"
  if [[ -z "$id" ]]; then
    echo "could not resolve id for ${NAME}" >&2
    return 1
  fi
  echo "restarting ${NAME} (${id})" >&2
  nebius ai endpoint restart --id "$id"
}

cmd_recreate() {
  require_nebius
  load_env
  local raw id
  if raw="$(endpoint_json 2>/dev/null)"; then
    id="$(printf '%s' "$raw" | endpoint_id_from_json)"
    if [[ -n "$id" ]]; then
      echo "stopping/deleting ${NAME} (${id})" >&2
      nebius ai endpoint stop --id "$id" || true
      nebius ai endpoint delete --id "$id"
    fi
  fi
  cmd_create
  cmd_url
}

cmd_ship() {
  cmd_build
  cmd_push
  if cmd_restart; then
    cmd_url
    return 0
  fi
  echo "restart failed; recreating ${NAME} with the same name" >&2
  cmd_recreate
}

cmd_url() {
  local raw url
  raw="$(endpoint_json)"
  url="$(printf '%s' "$raw" | https_url_from_json)"
  if [[ -z "$url" ]]; then
    echo "no https:// URL yet for ${NAME} (still provisioning?)" >&2
    exit 1
  fi
  printf '%s\n' "$url"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    build) cmd_build ;;
    push) cmd_push ;;
    up) cmd_up ;;
    restart) cmd_restart ;;
    recreate) cmd_recreate ;;
    ship) cmd_ship ;;
    url) cmd_url ;;
    -h|--help|help|"") usage ;;
    *)
      echo "unknown command: ${cmd}" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
