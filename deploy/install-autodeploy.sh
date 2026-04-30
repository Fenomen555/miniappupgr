#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/Fenomen555/miniappupgr.git}"
BRANCH="${DEPLOY_BRANCH:-main}"
REPO_DIR="${REPO_DIR:-/opt/miniappupgr}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root" >&2
  exit 1
fi

command -v git >/dev/null 2>&1 || {
  echo "git is required" >&2
  exit 1
}

if [ ! -d "$REPO_DIR/.git" ]; then
  mkdir -p "$(dirname "$REPO_DIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
else
  git -C "$REPO_DIR" fetch --prune origin "$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
fi

install -m 0644 "$REPO_DIR/deploy/systemd/miniappupgr-deploy.service" /etc/systemd/system/miniappupgr-deploy.service

systemctl daemon-reload

FORCE_DEPLOY=1 /bin/bash "$REPO_DIR/deploy/deploy.sh"

systemctl status miniappupgr-deploy.service --no-pager || true
