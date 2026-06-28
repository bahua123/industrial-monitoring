#!/usr/bin/env bash
# ============================================================
# 工业温控时序监控 - 一键部署脚本
# 启动 Docker 容器 + 初始化数据库 + 导入示例数据
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 工业温控时序监控系统 - 一键部署"
echo "========================================"

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "❌ 请先安装 Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# 加载 .env（如果存在）
if [ -f .env ]; then
    echo "📋 加载配置 .env"
    set -a; source .env; set +a
fi

# 启动容器
echo ""
echo "📦 启动 TIG 栈（InfluxDB + Grafana + Mosquitto）..."
docker compose up -d
echo ""

# 等待 InfluxDB 就绪
echo "⏳ 等待 InfluxDB 就绪..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${INFLUXDB_PORT:-8086}/ping 2>/dev/null | grep -q "204"; then
        echo "   InfluxDB 已就绪"
        break
    fi
    sleep 2
done

# 等待 Grafana 就绪
echo "⏳ 等待 Grafana 就绪..."
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${GRAFANA_PORT:-3000}/api/health 2>/dev/null | grep -q "200"; then
        echo "   Grafana 已就绪"
        break
    fi
    sleep 2
done

# 确保数据库存在
echo ""
echo "🗄️  确保数据库 factory_monitoring 存在..."
curl -s -X POST "http://127.0.0.1:${INFLUXDB_PORT:-8086}/query" \
    --data-urlencode "q=CREATE DATABASE factory_monitoring WITH DURATION 90d" > /dev/null

# 导入模拟数据
echo ""
echo "📊 导入模拟传感器数据..."
python3 scripts/seed-data.py

echo ""
echo "========================================"
echo "✅ 部署完成！"
echo ""
echo "    Grafana:     http://127.0.0.1:${GRAFANA_PORT:-3000}"
echo "    默认账号:    ${GRAFANA_USER:-admin} / ${GRAFANA_PASSWORD:-admin}"
echo ""
echo "    InfluxDB:    http://127.0.0.1:${INFLUXDB_PORT:-8086}"
echo "    数据量:      约 2,000 条模拟温度记录"
echo ""
echo "    MQTT Broker: 127.0.0.1:${MQTT_PORT:-1883}"
echo ""
echo "    后续操作:"
echo "      make seed    - 重新导入模拟数据"
echo "      make import  - 导入变压器油温真实数据集"
echo "      make logs    - 查看运行日志"
echo "      make status  - 查看服务健康状态"
echo "========================================"