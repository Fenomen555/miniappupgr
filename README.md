# miniappupgr

Production source for `app.devsbite.com`.

## Layout

- `backend/` - FastAPI backend deployed to `/root/botminitest`.
- `frontend/` - React/Vite frontend. The built `dist/` is deployed to `/var/www/app_devsbite_usr/data/www/app.devsbite.com/dist`.
- `deploy/` - server-side deploy scripts and systemd units.

Runtime secrets are not committed. The production backend keeps its environment in:

```text
/root/botminitest/.env
```

## Deploy Model

The server keeps a checkout at `/opt/miniappupgr`. GitHub Actions triggers deployment after pushes to `main` that touch `backend/`, `frontend/`, `deploy/`, or the deploy workflow.

When backend files change, deploy syncs `backend/` to `/root/botminitest`, preserves `.env`, installs Python requirements, and restarts:

```text
botminitest.service
```

When frontend files change, deploy runs `npm ci`, `npm run build`, and syncs:

```text
frontend/dist/ -> /var/www/app_devsbite_usr/data/www/app.devsbite.com/dist/
```

Manual deploy on the server:

```bash
FORCE_DEPLOY=1 /bin/bash /opt/miniappupgr/deploy/deploy.sh
```

Required GitHub Actions secrets:

- `DEPLOY_HOST` - production server IP or hostname.
- `DEPLOY_USER` - SSH user, currently `root`.
- `DEPLOY_PORT` - optional SSH port, defaults to `22`.
- `DEPLOY_SSH_KEY` - private key allowed to trigger `/opt/miniappupgr/deploy/deploy.sh`.
