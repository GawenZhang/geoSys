#!/usr/bin/env bash
# One-time server setup. Safe to re-run. Does not overwrite an existing backend/.env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx curl

if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  python3 - <<'PY'
from pathlib import Path
import secrets

path = Path("backend/.env")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "DJANGO_SECRET_KEY=change-me-to-a-long-random-string",
    "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(48),
)
text = text.replace("DJANGO_DEBUG=true", "DJANGO_DEBUG=false")
text = text.replace(
    "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost",
    "DJANGO_ALLOWED_HOSTS=110.40.173.15,127.0.0.1,localhost",
)
needle = "# DJANGO_CSRF_TRUSTED_ORIGINS=https://your.domain.com"
origin = "DJANGO_CSRF_TRUSTED_ORIGINS=http://110.40.173.15,http://127.0.0.1:8000"
if needle in text:
    text = text.replace(needle, origin)
elif "DJANGO_CSRF_TRUSTED_ORIGINS=" not in text:
    text += "\n" + origin + "\n"
path.write_text(text, encoding="utf-8")
print("已生成 backend/.env。请填写 MYSQL_PASSWORD，并确认数据库 geo_sys 已创建。")
PY
else
  echo "保留已有 backend/.env"
fi

if ! systemctl is-active --quiet mysql && ! systemctl is-active --quiet mariadb; then
  echo "本机 MySQL/MariaDB 未在运行。建库示例："
  echo "  sudo apt-get install -y mysql-server"
  echo "  sudo mysql -e \"CREATE DATABASE IF NOT EXISTS geo_sys CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\""
fi

bash "$ROOT/deploy/remote-deploy.sh"

if [[ "${1:-}" == "--init-demo" ]]; then
  (cd "$ROOT/backend" && .venv/bin/python manage.py init_demo)
fi

echo "首次部署完成。浏览器打开 http://110.40.173.15/  （云安全组需放行 80 端口）"
