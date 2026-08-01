# 荷小悦顾客端 API（hxy-server）

荷小悦微信小程序后端：FastAPI + PostgreSQL + SQLAlchemy + Alembic。

## 当前状态（2026-08-01 骨架 v0.1）

已完成：
- ✅ FastAPI 模块化结构（identity / catalog / orders / payments / audit 雏形）
- ✅ 数据模型：users / stores / projects / price_book / addons / orders / order_events / carts / coupons / user_coupons / member_plans / recharges / audit_logs
- ✅ JWT 登录（wx.login code2Session 换 openid，首次自动注册；未配 AppSecret 时 dev 模式可用）
- ✅ 门店 / 项目 / 价格 API（只返回 published 数据，价格从 price_book 读）
- ✅ 订单计价 + 状态机（服务端计价、加项、券锁定、30 分钟过期、事件审计）
- ⏳ 微信支付 v3（stub 占位，Task: payments 模块）
- ⏳ 手机号绑定（stub）

## 本地运行

```bash
# 1. 安装依赖（首次）
.venv/Scripts/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 配置环境变量（复制模板并填写，.env 不入库）
cp .env.example .env

# 3. 初始化数据库（开发环境 SQLite，直接建表 + 种子数据）
.venv/Scripts/python.exe -c "from app.db.session import Base, engine, SessionLocal; from app import models; Base.metadata.create_all(engine); from app.seed import seed; seed(SessionLocal())"

# 4. 启动
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8010 --reload
```

## 接口一览（smoke test 已通过）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/health | 健康检查 |
| GET | /api/v1/stores | 门店列表 |
| GET | /api/v1/stores/{id} | 门店详情 |
| GET | /api/v1/projects?store_id=1&category=bath | 已发布项目 + 三档价格 |
| POST | /api/v1/auth/login | wx.login 登录（body: {code}） |
| POST | /api/v1/orders | 下单（Bearer token，服务端计价） |
| GET | /api/v1/orders | 我的订单 |
| GET | /api/v1/orders/{id} | 订单详情 |

## 生产部署（服务器，Linux）

```bash
# 1. 安装 PostgreSQL
sudo apt update && sudo apt install -y postgresql postgresql-contrib nginx
sudo -u postgres createuser hxy --pwprompt   # 设密码
sudo -u postgres createdb -O hxy hxy

# 2. 上传代码并安装依赖（服务器 Python 3.11+）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3. 配置 .env（生产）——凭证从服务器安全位置读取，绝不在仓库/聊天中
cp .env.example .env
# DATABASE_URL=postgresql+psycopg://hxy:密码@localhost:5432/hxy
# 填入 WX_APPSECRET / WXPAY_APIV3_KEY / 证书路径等

# 4. 执行迁移（生产用 Alembic）
.venv/bin/alembic upgrade head

# 5. 用 systemd 托管（示例见下）+ Nginx 反代 + HTTPS
```

systemd 服务（/etc/systemd/system/hxy-api.service）：
```ini
[Unit]
Description=HXY Customer API
After=network.target postgresql.service

[Service]
WorkingDirectory=/srv/hxy-server
ExecStart=/srv/hxy-server/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
Restart=always
User=hxy

[Install]
WantedBy=multi-user.target
```

Nginx（server 块内）：
```nginx
server {
    listen 443 ssl;
    server_name api.hexiaoyue.com;
    ssl_certificate /etc/ssl/hxy/fullchain.pem;
    ssl_certificate_key /etc/ssl/hxy/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 微信小程序联调

- 小程序 `services/http.js` 的 `CUSTOMER_API_BASE` 指向 `https://api.hexiaoyue.com/api/v1/customer`
- 微信公众平台 → 开发管理 → 开发设置 → 服务器域名：把 `api.hexiaoyue.com` 加入 request 合法域名
- 本地联调可在开发者工具勾选"不校验合法域名"

## 约定

- 凭证只进 `.env`（已被 .gitignore 忽略），严禁入库 / 进聊天记录
- 价格只从 price_book 读，前端传价一律不信任
- 状态机只在服务端流转，前端只能请求动作
- 关键操作写 audit_logs / order_events
