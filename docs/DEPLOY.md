# geoSys 部署说明（Django + MySQL）

本文记录默认配置与服务器部署步骤，方便按环境修改变量后上线。

## 默认配置

| 项 | 默认值 |
| --- | --- |
| 数据库名 | `geo_sys` |
| 数据库用户 | `root` |
| 数据库密码 | 空 |
| 数据库 Host | `127.0.0.1` |
| 数据库 Port | `3306` |
| Django 端口 | `8000` |
| 演示账号 | `demo` / `demo123` |
| AI 模式 | `stub`（未接真实模型） |

配置文件：复制 [`backend/.env.example`](../backend/.env.example) 为 `backend/.env` 后修改。

```env
DJANGO_SECRET_KEY=请改成足够长的随机字符串
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=你的域名,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://你的域名

DB_ENGINE=mysql
MYSQL_DATABASE=geo_sys
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306

AI_MODE=stub
```

本机若暂时没有 MySQL，可把 `DB_ENGINE=sqlite` 用于联调；**服务器请使用 MySQL**。

## 1. 准备 MySQL

```sql
CREATE DATABASE geo_sys CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 如需独立账号：
-- CREATE USER 'geo'@'%' IDENTIFIED BY '强密码';
-- GRANT ALL PRIVILEGES ON geo_sys.* TO 'geo'@'%';
-- FLUSH PRIVILEGES;
```

## 2. 安装依赖

```bash
cd backend
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env   # 再按上表改 .env
```

## 3. 前端构建（可选）

若改了 `app/` 下的前端源文件，先构建静态产物：

```bash
cd app
npm install
npm run build
```

Django 会直接托管 `app/dist/`。

## 4. 数据库迁移与演示账号

```bash
cd backend
python manage.py migrate
python manage.py init_demo
```

`init_demo` 会创建/更新：

- 用户 `demo` / `demo123`
- 示例关键词、问答词、文章分类、文章

## 5. 本地启动

```bash
cd backend
python manage.py runserver 0.0.0.0:8000
```

浏览器打开：

- 登录页：http://127.0.0.1:8000/
- 健康检查：http://127.0.0.1:8000/api/health
- Django Admin：http://127.0.0.1:8000/admin/（同 demo 账号）

> 旧的 `node app/tools/serve.mjs`（4173）仅静态预览，**没有登录与 API**。正式联调请用 Django `:8000`。

## 6. 生产部署（gunicorn + nginx 示例）

```bash
cd backend
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

nginx 示例：

```nginx
server {
    listen 80;
    server_name your.domain.com;

    client_max_body_size 20m;

    location /static/ {
        alias /path/to/geoSys/backend/staticfiles/;
    }

    location /media/ {
        alias /path/to/geoSys/backend/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

HTTPS 时请把 `DJANGO_CSRF_TRUSTED_ORIGINS` 写成 `https://你的域名`，并将 `DJANGO_DEBUG=false`。

## 7. API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/auth/csrf` | 获取 CSRF |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户 |
| PUT | `/api/auth/profile` | 改昵称/头像/密码 |
| POST | `/api/auth/wallet` | 演示充值/点数调整（非真实支付） |
| GET | `/api/dashboard` | 首页余额/点数/近 7 日统计 |
| POST | `/api/upload` | 通用文件上传 → `/media/...` |
| * | `/api/ueditor` | UEditor 配置/插图上传 |
| * | `/api/keywords/` | 关键词 CRUD；`?id=` 单条；`/options` 下拉 |
| * | `/api/questions/` | 问答词 CRUD |
| * | `/api/article-types/` | 文章分类 CRUD；`/options` 下拉 |
| * | `/api/articles/` | 文章 CRUD |
| GET | `/api/modules/` | 业务模块清单 |
| GET | `/api/modules/resolve?page=` | pageKey → 模块映射 |
| GET | `/api/modules/<module>/options` | 模块下拉选项 |
| * | `/api/modules/<module>/` | 通用业务 CRUD（JSON `data`）；`?id=` 单条 |
| POST | `/api/ai` | AI 代理（`AI_MODE=stub|demo|proxy`） |

列表查询支持：`?page=1&page_size=20&q=关键词&subtype=1&id=123`  
删除：`DELETE` + JSON `{ "ids": [1,2] }`  
鉴权：Session Cookie；写操作需请求头 `X-CSRFToken`。

通用模块覆盖：诊断、图库、知识库、写作指令、AI 任务/生图、爆文、B2B、联系人、网媒/自媒体、收藏、草稿、站点/TDK、视频、统计、收录、Agent、指数/蒸馏/拓展、点数/资金、实名、权益等。

## 8. 接入真实 AI

1. `.env` 设置：

```env
AI_MODE=proxy
AI_UPSTREAM_URL=https://api.openai.com/v1/chat/completions
AI_UPSTREAM_KEY=sk-...
AI_UPSTREAM_MODEL=gpt-4o-mini
```

2. 本地无密钥联调可用 `AI_MODE=demo`（返回演示文案）。
3. 前端保持 `app/ai-config.js` 的 `mode: 'proxy'` 指向 `/api/ai`。

## 9. 功能范围说明

- 登录、资料、关键词/问答词/文章：专用表结构
- 其余后台菜单：`BizRecord` 通用表持久化；列表/新增/编辑回填/删除/搜索/批量状态已对接
- 上传、UEditor 插图、仪表盘真实余额/点数/近 7 日图表已对接
- AI：`demo` 可联调；`proxy` 接 OpenAI 兼容上游
- 钱包：`/api/auth/wallet` 为演示记账（落 `user_money_log` / `user_score_log`），**不是**微信/支付宝真实支付
- 媒体投稿/B2B 选站等仍以表单落库为主，未接第三方发布平台

## 10. 推送到 GitHub 后自动部署

`main` 分支每次 push 会触发 [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)：Actions 用 SSH 登录 `ubuntu@110.40.173.15:22`，在 `~/geoSys/geoSys` 执行 `git reset --hard origin/main`，再跑 [`deploy/remote-deploy.sh`](../deploy/remote-deploy.sh)（安装依赖、迁移、收集静态文件、重启 gunicorn，并重载 nginx）。

密钥只放在 GitHub，不进仓库。Repository secrets 里只需要 `DEPLOY_SSH_KEY`。

### 服务器首次准备（SSH 登录后执行一次）

```bash
cd ~/geoSys/geoSys
git pull --ff-only origin main
bash deploy/bootstrap.sh
```

`bootstrap.sh` 会安装 Python 虚拟环境依赖和 nginx。若还没有 `backend/.env`，会从示例生成一份（`DJANGO_DEBUG=false`，允许主机包含 `110.40.173.15`）。已有 `.env` 不会被覆盖。

部署脚本会在本机安装并启动 MySQL，按 `backend/.env` 创建数据库和账号。`MYSQL_PASSWORD` 为空时会生成一个密码写回 `.env`，不会打印出来。需要演示账号时再执行：

```bash
bash deploy/bootstrap.sh --init-demo
```

云安全组放行 **80**。站点入口：`http://110.40.173.15/` ，健康检查：`http://110.40.173.15/api/health`。gunicorn 只监听本机 `127.0.0.1:8000`。

### 允许 GitHub Actions 登录这台服务器

在服务器上生成一把专用密钥，公钥留在本机，私钥交给 GitHub：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/geosys_deploy -N ""
cat ~/.ssh/geosys_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
cat ~/.ssh/geosys_deploy
```

把 `cat` 打印出的整段私钥（含 `BEGIN` / `END` 行）存为仓库 Secret，名称必须是 **`DEPLOY_SSH_KEY`**：

`https://github.com/GawenZhang/geoSys/settings/secrets/actions`

保存后，再推一次 `main`，或在 Actions 页面手动重跑 Deploy。之后每次推送到 `main` 都会自动部署。`backend/.env`、上传的 `media/` 和虚拟环境不会被 git 覆盖。
