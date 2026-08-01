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

## 生产部署（服务器 2核4G + Docker，推荐）

```bash
# 0. 准备：把 hxy-server 目录传到服务器（scp / git clone / 面板上传均可），
#    并在服务器上创建证书目录、放入域名证书（fullchain.pem + privkey.pem）
mkdir -p /etc/ssl/hxy
# 将证书文件放到 /etc/ssl/hxy/ 下（文件名必须与 nginx.conf 一致）

# 1. 配置生产环境变量（凭证只在这里填，绝不入库/进聊天）
cp .env.example .env
#   编辑 .env：
#   ENVIRONMENT=production
#   POSTGRES_PASSWORD=<随机强密码>
#   DATABASE_URL=postgresql+psycopg://hxy:<密码>@db:5432/hxy   # 注意主机名是 db（compose 服务名）
#   JWT_SECRET=<长随机串>
#   WX_APPSECRET=<公众平台重置后的新值>
#   WXPAY_APIV3_KEY / WXPAY_CERT_SERIAL_NO / WXPAY_PRIVATE_KEY_PATH 等支付凭证
#   SEED_ON_START=true   # 首店验证阶段开；正式运营改 false

# 2. 一键部署（构建镜像 + 启动三容器 + 健康检查）
bash deploy.sh

# 3. 常用运维命令
docker compose logs -f api     # 看 API 日志
docker compose restart api     # 重启 API
docker compose down            # 停止（数据在 pgdata 卷，不会丢）
docker compose up -d --build   # 更新代码后重新部署
```

> 备选：不用 Docker 的手动部署（PostgreSQL + systemd + Nginx）见仓库早期版本 README；Docker 方案优先。

## 微信小程序联调

- 小程序 `services/http.js` 的 `CUSTOMER_API_BASE` 指向 `https://hxyapi.hexiaoyue.com/api/v1/customer`
- 微信公众平台 → 开发管理 → 开发设置 → 服务器域名：把 `hxyapi.hexiaoyue.com` 加入 request 合法域名
- 本地联调可在开发者工具勾选"不校验合法域名"

## 约定

- 凭证只进 `.env`（已被 .gitignore 忽略），严禁入库 / 进聊天记录
- 价格只从 price_book 读，前端传价一律不信任
- 状态机只在服务端流转，前端只能请求动作
- 关键操作写 audit_logs / order_events
