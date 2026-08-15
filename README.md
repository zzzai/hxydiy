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

### DIY 选单闭环发布门禁

`diy.hexiaoyue.com` 是独立 H5，不创建线上支付订单。顾客提交的选单、前台确认、服务中加选和实际服务项均由 API 服务端保存。

开发区完成构建后，先运行只读发布一致性检查，确认后端、顾客端 H5 与管理后台没有只发布一侧：

```bash
python scripts/check_release_consistency.py
```

该检查只读取 `/root/hxy-workspace` 和 `/root/hxy-diy-20260811` 的源码/构建产物，不启动服务、不连接数据库、不修改文件。生产版本缺少 P0 路由或 H5 调用时会以非零状态退出。

发布前必须按以下顺序在**生产备份恢复库**演练，不能直接在生产库试迁移：

```bash
# 1. 先恢复生产备份到隔离数据库，并指向该隔离库。
export DATABASE_URL='postgresql+psycopg://.../hxy_restore_rehearsal'

# 2. 升级，再执行只读结构和遗留选单可读性验证。
alembic upgrade head
python -m scripts.verify_selection_closure_upgrade
```

验证项：
- `selection_revisions`、`selection_change_requests`、`service_lines` 三张表存在；
- `addons` 已包含收费、会员价、独立售卖、挂靠、图文和排序字段；
- 原有 `selection_sessions` 可读取；
- 使用测试账号现场走通：扫码、匿名提交、登录领券、前台确认、服务中加选审批、技师开始/完成、线下收款、离位释放、评价。

**回退策略：** V2 表中存在记录时，迁移会拒绝降级，以免删除已产生的服务事实。生产回退必须停止写入并恢复已验证备份，不能执行 `alembic downgrade`。

在满足以上门禁前，不得将新迁移应用到生产库；同时必须配置短信通道、第三方会员同步鉴权和真实项目/券数据。

## 微信小程序联调

- 小程序 `services/http.js` 的 `CUSTOMER_API_BASE` 指向 `https://miniapp.hexiaoyue.com/api/v1/customer`
- 微信公众平台 → 开发管理 → 开发设置 → 服务器域名：把 `miniapp.hexiaoyue.com` 加入 request 合法域名
- 本地联调可在开发者工具勾选"不校验合法域名"

## 约定

- 凭证只进 `.env`（已被 .gitignore 忽略），严禁入库 / 进聊天记录
- 价格只从 price_book 读，前端传价一律不信任
- 状态机只在服务端流转，前端只能请求动作
- 关键操作写 audit_logs / order_events
