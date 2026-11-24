#!/usr/bin/env bash
# Update dependencies, migrate, and restart geoSys. Called after git is already on origin/main.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f backend/.env ]]; then
  echo "缺少 backend/.env。请在服务器上执行: bash deploy/bootstrap.sh" >&2
  exit 1
fi

if ! sudo -n true >/dev/null 2>&1; then
  echo "ubuntu 用户需要免密 sudo，才能安装 MySQL 并重启服务。" >&2
  exit 1
fi

SQL_FILE="$(mktemp)"
chmod 600 "$SQL_FILE"
trap 'rm -f "$SQL_FILE"' EXIT
python3 - "$SQL_FILE" <<'PY'
import re
import secrets
import sys
from pathlib import Path

out = Path(sys.argv[1])
path = Path("backend/.env")
text = path.read_text(encoding="utf-8")
vals = {}
for line in text.splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    vals[key.strip()] = value.strip().strip('"').strip("'")

host = vals.get("MYSQL_HOST", "127.0.0.1")
if host not in ("127.0.0.1", "localhost"):
    print(f"MYSQL_HOST={host}，跳过本机 MySQL 安装。")
    out.write_text("", encoding="utf-8")
    raise SystemExit(0)

db = vals.get("MYSQL_DATABASE", "geo_sys")
user = vals.get("MYSQL_USER", "root")
password = vals.get("MYSQL_PASSWORD", "")
if not re.fullmatch(r"[A-Za-z0-9_]+", db) or not re.fullmatch(r"[A-Za-z0-9_]+", user):
    raise SystemExit("MYSQL_DATABASE / MYSQL_USER 只能包含字母、数字和下划线。")

if not password:
    password = secrets.token_urlsafe(24)
    replaced, count = re.subn(r"(?m)^MYSQL_PASSWORD=.*$", "MYSQL_PASSWORD=" + password, text, count=1)
    if count == 0:
        replaced = text.rstrip() + "\nMYSQL_PASSWORD=" + password + "\n"
    path.write_text(replaced, encoding="utf-8")
    print("MYSQL_PASSWORD 为空，已生成密码并写入 backend/.env。")

escaped = password.replace("\\", "\\\\").replace("'", "''")
out.write_text(
    f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
    f"CREATE USER IF NOT EXISTS '{user}'@'127.0.0.1' IDENTIFIED BY '{escaped}';\n"
    f"ALTER USER '{user}'@'127.0.0.1' IDENTIFIED BY '{escaped}';\n"
    f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'127.0.0.1';\n"
    "FLUSH PRIVILEGES;\n",
    encoding="utf-8",
)
print(f"准备连接本机 MySQL，数据库 {db}，用户 {user}。")
PY

if [[ -s "$SQL_FILE" ]]; then
  if ! dpkg -s mysql-server >/dev/null 2>&1 && ! dpkg -s mariadb-server >/dev/null 2>&1; then
    sudo -n apt-get update
    sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server
  fi
  sudo -n systemctl enable --now mysql || sudo -n systemctl enable --now mariadb
  mysql_ready=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do
    if sudo -n mysqladmin --protocol=socket ping >/dev/null 2>&1; then
      mysql_ready=1
      break
    fi
    sleep 1
  done
  if [[ "$mysql_ready" -ne 1 ]]; then
    echo "MySQL 未能在本机 3306 端口启动。" >&2
    sudo -n journalctl -u mysql -n 40 --no-pager || true
    rm -f "$SQL_FILE"
    exit 1
  fi
  sudo -n mysql < "$SQL_FILE"
fi
rm -f "$SQL_FILE"

if ! python3 -m venv backend/.venv; then
  echo "创建虚拟环境失败。请先执行: sudo apt-get install -y python3-venv" >&2
  exit 1
fi

backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt

(
  cd backend
  .venv/bin/python manage.py migrate --noinput
  .venv/bin/python manage.py init_demo
  .venv/bin/python manage.py collectstatic --noinput
)

mkdir -p backend/media backend/staticfiles
chmod -R a+rX backend/media backend/staticfiles

sudo -n cp "$ROOT/deploy/geosys.service" /etc/systemd/system/geosys.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable geosys
sudo -n systemctl restart geosys

if command -v nginx >/dev/null 2>&1; then
  sudo -n python3 "$ROOT/deploy/install-nginx-prefix.py" "$ROOT/deploy/nginx-geosys.conf"
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

if ! curl -fsS -H "Host: 110.40.173.15" "http://127.0.0.1/geo/api/health" >/dev/null; then
  echo "gunicorn 已启动，但现有站点的 /geo 没有转发成功。" >&2
  exit 1
fi

echo "Deploy OK: http://110.40.173.15/geo/"
