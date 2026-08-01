#!/bin/sh
# 容器启动入口：初始化数据库 -> 启动 API
set -e

echo "[entrypoint] 初始化数据库..."
python -c "
from app.db.session import Base, engine
from app import models
Base.metadata.create_all(engine)
print('[entrypoint] 表结构就绪')
"

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

echo "[entrypoint] 启动 uvicorn..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
