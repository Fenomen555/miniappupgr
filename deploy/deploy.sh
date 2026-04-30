#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-miniappupgr}"
BRANCH="${DEPLOY_BRANCH:-main}"
REPO_DIR="${REPO_DIR:-/opt/miniappupgr}"
BACKEND_TARGET="${BACKEND_TARGET:-/root/botminitest}"
FRONTEND_TARGET="${FRONTEND_TARGET:-/var/www/app_devsbite_usr/data/www/app.devsbite.com}"
BACKEND_SERVICE="${BACKEND_SERVICE:-botminitest.service}"
LAST_FILE="${LAST_FILE:-$REPO_DIR/.deploy-last-sha}"
LOCK_FILE="${LOCK_FILE:-/var/lock/${APP_NAME}-deploy.lock}"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    log "Missing required command: $1"
    exit 1
  }
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Another deploy is already running"
  exit 0
fi

need_cmd git
need_cmd rsync
need_cmd python3
need_cmd systemctl
need_cmd npm

if [ ! -d "$REPO_DIR/.git" ]; then
  log "Repository checkout is missing: $REPO_DIR"
  exit 1
fi

cd "$REPO_DIR"

log "Fetching origin/$BRANCH"
git fetch --prune origin "$BRANCH"
new_sha="$(git rev-parse "origin/$BRANCH")"
last_sha=""
if [ -f "$LAST_FILE" ]; then
  last_sha="$(tr -d '[:space:]' < "$LAST_FILE")"
fi

if [ "${FORCE_DEPLOY:-0}" != "1" ] && [ -n "$last_sha" ] && [ "$last_sha" = "$new_sha" ]; then
  log "No changes to deploy ($new_sha)"
  exit 0
fi

first_deploy=0
if [ -z "$last_sha" ] || ! git cat-file -e "${last_sha}^{commit}" 2>/dev/null; then
  first_deploy=1
fi

git reset --hard "$new_sha"

backend_changed=0
frontend_changed=0

if [ "${FORCE_DEPLOY:-0}" = "1" ] || [ "$first_deploy" = "1" ]; then
  backend_changed=1
  frontend_changed=1
else
  changed_files="$(git diff --name-only "$last_sha" "$new_sha")"
  if printf '%s\n' "$changed_files" | grep -qE '^(backend/|deploy/deploy\.sh$)'; then
    backend_changed=1
  fi
  if printf '%s\n' "$changed_files" | grep -qE '^(frontend/|deploy/deploy\.sh$)'; then
    frontend_changed=1
  fi
fi

if [ "$backend_changed" = "1" ]; then
  log "Deploying backend to $BACKEND_TARGET"
  if [ ! -f "$BACKEND_TARGET/.env" ]; then
    log "Backend env file is missing: $BACKEND_TARGET/.env"
    exit 1
  fi

  mkdir -p "$BACKEND_TARGET"
  rsync -a --delete \
    --exclude='.env' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$REPO_DIR/backend/" "$BACKEND_TARGET/"

  if [ -f "$BACKEND_TARGET/requirements.txt" ]; then
    python3 -m pip install -r "$BACKEND_TARGET/requirements.txt"
  fi

  systemctl restart "$BACKEND_SERVICE"
  systemctl is-active --quiet "$BACKEND_SERVICE"
  log "Backend service restarted: $BACKEND_SERVICE"
else
  log "Backend unchanged"
fi

if [ "$frontend_changed" = "1" ]; then
  log "Building frontend"
  cd "$REPO_DIR/frontend"
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
  npm run build

  mkdir -p "$FRONTEND_TARGET/dist"
  rsync -a --delete "$REPO_DIR/frontend/dist/" "$FRONTEND_TARGET/dist/"
  if id app_devsbite_usr >/dev/null 2>&1; then
    chown -R app_devsbite_usr:app_devsbite_usr "$FRONTEND_TARGET/dist"
  fi
  log "Frontend dist deployed to $FRONTEND_TARGET/dist"
else
  log "Frontend unchanged"
fi

printf '%s\n' "$new_sha" > "$LAST_FILE"
log "Deploy complete: $new_sha"
