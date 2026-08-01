#!/bin/bash
# ===== 荷小悦后端一键部署脚本（服务器上执行）=====
# 用法：先按 README 准备代码与 .env，然后执行本脚本
set -e

echo "==> 1/4 检查 Docker"
docker --version && docker compose version

echo "==> 2/4 构建并启动（db + api + nginx）"
docker compose up -d --build

echo "==> 3/4 等待服务就绪"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8010/api/v1/health >/dev/null 2>&1; then
    echo "    API 已就绪"
    break
  fi
  echo "    等待中 ($i/30)..."
  sleep 2
done

echo "==> 4/4 验证"
curl -s http://127.0.0.1:8010/api/v1/health && echo ""
echo "部署完成。外部访问：https://miniapp.hexiaoyue.com/api/v1/health"
