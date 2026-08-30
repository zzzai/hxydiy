#!/bin/sh
# 容器启动入口：初始化数据库 -> 启动 API
set -e

if python -c "
from sqlalchemy import inspect
from app.db.session import engine
raise SystemExit(0 if inspect(engine).has_table('alembic_version') else 1)
"; then
  if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] 执行已明确授权的 Alembic 增量迁移..."
    python -m alembic upgrade head
  else
    echo "[entrypoint] 已有数据库：跳过 Alembic 迁移（RUN_MIGRATIONS=false）"
  fi
else
  # 仅首次创建空库时使用 ORM 建表，并将该完整初始结构登记为当前基线。
  echo "[entrypoint] 初始化全新数据库..."
  python -c "
from app.db.session import Base, engine
from app import models
Base.metadata.create_all(engine)
print('[entrypoint] 表结构就绪')
"
  python -m alembic stamp head
fi

# 种子数据：仅 SEED_ON_START=true 且库为空时执行（首店验证阶段可用，生产请关闭）
if [ "$SEED_ON_START" = "true" ]; then
  python -c "
from app.db.session import SessionLocal
from app.seed import seed
db = SessionLocal()
seed(db)
db.close()
print('[entrypoint] 种子数据就绪')
"
fi

# 独立 DIY 首店初始化：仅写门店、项目、券、服务位和页面配置，重复执行不会重复创建。
if [ "$DIY_BOOTSTRAP" = "true" ]; then
  PYTHONPATH=/app python scripts/bootstrap_diy_store.py
fi

echo "[entrypoint] 启动 uvicorn..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
