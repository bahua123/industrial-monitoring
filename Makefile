# 工业温控监控 - Makefile
.PHONY: up down restart logs ps seed import stop clean

up:           ## 启动全部服务
	docker compose up -d

down:         ## 停止全部服务
	docker compose down

restart:      ## 重启全部服务
	docker compose restart

logs:         ## 查看日志
	docker compose logs -f

ps:           ## 查看运行状态
	docker compose ps

seed:         ## 导入模拟传感器数据
	python3 scripts/seed-data.py

import:       ## 导入变压器油温真实数据集
	python3 scripts/import_transformer_oil.py

stop:         ## 停止并删除容器
	docker compose down -v

status:       ## 查看各服务健康状态
	@echo "=== InfluxDB ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:${INFLUXDB_PORT:-8086}/ping || echo "OFFLINE"
	@echo "=== Grafana ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:${GRAFANA_PORT:-3000}/api/health || echo "OFFLINE"
	@echo "=== Mosquitto ==="
	@nc -z 127.0.0.1 ${MQTT_PORT:-1883} && echo "UP" || echo "OFFLINE"

setup:        ## 一键部署
	bash scripts/setup.sh

help:         ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' Makefile | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'