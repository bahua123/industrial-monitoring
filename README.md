# 工业温控时序监控系统

基于 InfluxDB v1 + Grafana + Mosquitto（TIG 栈）的工业温度监控方案，
支持实时异常检测与多渠道告警推送。

## 架构

```
传感器 / 模拟数据
    │
    ▼
Mosquitto (MQTT Broker) :1883
    │
    ▼
InfluxDB v1 (时序数据库) :8086
    │
    ├── factory_monitoring
    │     ├── datacenter_cooling    ← 数据中心冷却（5种策略）
    │     └── transformer_oil       ← 电力变压器油温（m1/m2双区域）
    │
    ├── Grafana (可视化) :3001       ← grafana.bahua.de
    │
    └── Hermes Anomaly Detector (Cron)
          └── 异常推送 → Telegram / 微信
```

## 数据集

| 测量表 | 来源 | 记录数 | 时间范围 | 温度范围 |
|--------|------|-------|---------|---------|
| `datacenter_cooling` | 模拟生成（5种冷却策略） | 3,498 | 2025-05 | 15~28°C |
| `transformer_oil` | ETDataset（真实电网数据） | 139,360 | 2016-07~2018-06 | -4.2~58.9°C |

## 仪表盘

**数据中心冷源监控大屏**
访问：http://grafana.bahua.de （admin/admin）

包含面板：
- 4 统计卡片（平均/最高/最低温度、数据总量）
- 温度趋势曲线（入风/出风/环境）
- 能耗成本趋势
- 服务器负载与冷却功率
- 温度偏差监控（含异常标记红线）
- 异常事件表
- 5 种冷却策略对比（温度/能耗/功率）
- 变压器油温趋势（m1 / m2 双线对比）
- 油温与负载关系
- 各区域平均油温对比

## 异常检测

由 Hermes Cron 驱动，支持双检测层：

### 第一层：固定阈值
| 规则 | 条件 | 级别 |
|------|------|------|
| 冷却入风超温 | inlet_temp > 40°C | HIGH |
| 温度异常突变 | temp_deviation > 5°C | HIGH |
| 变压器油温过高 | OT > 50°C | HIGH |
| 服务器负载过高 | server_workload > 95% | MEDIUM |

### 第二层：动态 3σ 统计
取历史数据计算均值 ± 3×标准差，超出范围即告警。
自动适应季节变化，无需人工调参。

### 告警推送
Hermes Cron 定时扫描 → Telegram/微信即时推送。

## 部署

```bash
# 1. 启动 TIG 栈
docker compose up -d influxdb grafana mosquitto

# 2. 创建数据库
curl -X POST http://127.0.0.1:8086/query?db= --data-urlencode "q=CREATE DATABASE factory_monitoring"

# 3. 导入模拟数据
python3 scripts/import_cooling_data.py

# 4. 导入变压器数据
python3 scripts/import_ett.py

# 5. 配置 Grafana → 导入仪表盘 JSON
# 6. 设置异常检测 Cron
hermes cron create "*/30 * * * *" "运行异常检测并报告结果"
```

## 资源占用

| 组件 | 内存 | 磁盘 |
|------|------|------|
| InfluxDB v1 | ~60 MB | ~15 MB |
| Grafana | ~384 MB | ~51 MB |
| Mosquitto | ~2.5 MB | ~0 MB |
| **合计** | **~447 MB** | **~66 MB** |