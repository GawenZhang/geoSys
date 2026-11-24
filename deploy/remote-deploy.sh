#!/usr/bin/env bash
# Update dependencies, migrate, and restart geoSys. Called after git is already on origin/main.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f backend/.env ]]; then
  echo "缺少 backend/.env。请在服务器上执行: bash deploy/bootstrap.sh" >&2
  exit 1
fi

if ! python3 -m venv backend/.venv; then
  echo "创建虚拟环境失败。请先执行: sudo apt-get install -y python3-venv" >&2
  exit 1
fi

backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt

(
  cd backend
  .venv/bin/python manage.py migrate --noinput
  .venv/bin/python manage.py collectstatic --noinput
)

mkdir -p backend/media backend/staticfiles
chmod -R a+rX backend/media backend/staticfiles

if ! sudo -n true >/dev/null 2>&1; then
  echo "ubuntu 用户需要免密 sudo，才能安装并重启 systemd / nginx。" >&2
  exit 1
fi

sudo -n cp "$ROOT/deploy/geosys.service" /etc/systemd/system/geosys.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable geosys
sudo -n systemctl restart geosys

if command -v nginx >/dev/null 2>&1; then
  if [[ -d /etc/nginx/sites-available ]]; then
    sudo -n cp "$ROOT/deploy/nginx-geosys.conf" /etc/nginx/sites-available/geosys.conf
    sudo -n ln -sfn /etc/nginx/sites-available/geosys.conf /etc/nginx/sites-enabled/geosys.conf
    sudo -n rm -f /etc/nginx/sites-enabled/default
  elif [[ -d /etc/nginx/conf.d ]]; then
    sudo -n cp "$ROOT/deploy/nginx-geosys.conf" /etc/nginx/conf.d/geosys.conf
  fi
  sudo -n nginx -t
  sudo -n systemctl reload nginx
fi

ready=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done

if [[ "$ready" -ne 1 ]]; then
  echo "gunicorn 未在 127.0.0.1:8000 就绪。" >&2
  sudo -n systemctl status geosys --no-pager || true
  exit 1
fi

echo "Deploy OK: http://127.0.0.1:8000/api/health"
