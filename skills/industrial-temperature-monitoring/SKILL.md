---
name: industrial-temperature-monitoring
description: 从零部署工业温控时序监控栈 — Docker 部署 InfluxDB v1 + Grafana + Mosquitto，导入真实/模拟数据集，配置 Grafana 仪表盘，设置 Hermes Cron 异常检测
---

# 工业温控时序监控部署

从零开始，在一台 Linux VPS 上部署完整的工业温控监控系统。

## 适用场景
- 工业物联网（IIoT）温度监控演示
- 面试/展示用 AI Agent + 监控工具链能力
- 学习和实验时序数据库 + 可视化

## 前置条件
- Linux VPS（推荐 1C/1G 以上）
- Docker + Docker Compose
- Hermes Agent 已安装（配置推送通道如 Telegram/微信）
- 磁盘剩余 > 1GB

## 第一步：启动 TIG 栈

```bash
# 创建网络
docker network create monitoring

# 启动 InfluxDB v1
docker run -d --name influxdb --network monitoring \
  -v influxdb_data:/var/lib/influxdb \
  -p 8086:8086 \
  influxdb:1.11

# 启动 Mosquitto (MQTT Broker)
docker run -d --name mqtt --network monitoring \
  -p 1883:1883 -p 9001:9001 \
  eclipse-mosquitto:2

# 启动 Grafana
docker run -d --name grafana --network monitoring \
  -v grafana_data:/var/lib/grafana \
  -p 3001:3000 \
  -e "GF_SERVER_ENABLE_GZIP=true" \
  grafana/grafana:latest
```

## 第二步：创建数据库

```bash
curl -X POST "http://127.0.0.1:8086/query" \
  --data-urlencode "q=CREATE DATABASE factory_monitoring"
```

## 第三步：导入数据集

### 变压器油温数据（ETDataset）
真实的中国电网变压器数据，2年分钟级记录，139,360条。
使用仓库中的 `scripts/import_transformer_oil.py`。

### 数据中心冷却模拟数据
5种冷却策略的模拟数据，3,498条。

## 第四步：导入 Grafana 仪表盘

1. 登录 Grafana http://IP:3001 (admin/admin)
2. 添加 InfluxDB 数据源 → URL: http://influxdb:8086, database: factory_monitoring
3. 导入仪表盘 JSON（仓库 dashboards/datacenter-monitoring.json）

仪表盘包含 20+ 面板：温度趋势、能耗分析、策略对比、变压器油温监控等。

## 第五步：部署异常检测（Hermes Cron）

```bash
# 1. 安装检测脚本
cp scripts/anomaly-detector.py ~/.hermes/scripts/

# 2. 设置定时检测
hermes cron create --schedule "*/30 * * * *" \
  --name "Anomaly Detector" \
  --prompt "运行 ~/.hermes/scripts/anomaly-detector.py 进行温控异常检测，整理结果推送给我"
```

### 异常规则
- **固定阈值**：入风>40°C / 偏差>5°C / 油温>50°C / 负载>95%
- **动态 3σ**：7天滑动窗口，超均值±3σ 告警，自动适应季节

## 资源占用
整栈 ~447MB 内存，~66MB 磁盘。139K 条数据仅 15MB。

## 验证
```bash
docker ps
python3 ~/.hermes/scripts/anomaly-detector.py
curl -G "http://127.0.0.1:8086/query?db=factory_monitoring" \
  --data-urlencode "q=SELECT count(OT), MEAN(OT) FROM transformer_oil GROUP BY region"
```