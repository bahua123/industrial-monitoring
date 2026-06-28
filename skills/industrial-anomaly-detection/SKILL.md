---
name: industrial-anomaly-detection
description: 工业温控异常检测 — 基于 InfluxDB + Hermes Cron 的双层检测（固定阈值+3σ统计），支持 Telegram/微信告警推送
---

# 工业温控异常检测

## 适用场景
已有 InfluxDB + Grafana 温控监控栈，需要定时扫描数据并推送异常告警。

## 前置条件
- InfluxDB v1 运行中，数据库 `factory_monitoring`
- 测量表 `datacenter_cooling` 和/或 `transformer_oil`
- Hermes Agent 已配置 Telegram/微信推送

## 步骤

### 1. 创建检测脚本
脚本位于 `~/.hermes/scripts/anomaly-detector.py`

```
├── 第一层：固定阈值（冷却入风>40°C / 偏差>5°C / 油温>50°C / 负载>95%）
├── 第二层：动态 3σ 统计（7天滑动窗口，超均±3σ 告警）
└── 输出：结构化异常报告
```

### 2. 设置定时 Cron（测试用短间隔）
```bash
hermes cron create --schedule "2m" --repeat 3 \
  --name "Anomaly Detector (Test)" \
  --prompt "运行 ~/.hermes/scripts/anomaly-detector.py 进行温控异常检测，整理结果推送给我"
```

### 3. 确认正常后改长间隔
```bash
hermes cron update <job_id> --schedule "*/30 * * * *" --repeat forever
```

### 4. 定稿间隔建议
| 场景 | 推荐间隔 |
|------|---------|
| 实时温控 | 5-15 分钟 |
| 历史数据分析 | 30-60 分钟 |
| 低负载模式 | 每 2 小时 |

## 异常规则说明

### 固定阈值
| 规则 | 字段 | 阈值 | 说明 |
|------|------|------|------|
| 冷却入风超温 | `inlet_temp` | > 40°C | 服务器入风危险线 |
| 温度异常突变 | `temp_deviation` | > 5°C | 短时温度剧烈变化 |
| 变压器油温过高 | `OT` | > 50°C | 变压器警戒线 |
| 变压器油温过低 | `OT` | < -2°C | 异常低温 |
| 冷却出风超温 | `outlet_temp` | > 45°C | 制冷效果不足 |
| 服务器负载过高 | `server_workload` | > 95% | 接近满载 |

### 动态 3σ 检测
- 自动计算 7 天滑动窗口的均值与标准差
- 最新值超出 `均值 ± 3×标准差` 即告警
- 无需人工调参，自动适应季节性变化

## 验证
```bash
# 手动运行测试
python3 ~/.hermes/scripts/anomaly-detector.py

# 检查 Cron 执行状态
hermes cron list
```

## 常见问题
**Q: 测试期没有收到通知？**
A: 检查 Cron 是否用 agent 模式（非 no_agent），确保 deliver=origin。

**Q: 数据是静态的为什么还要跑检测？**
A: 脚本框架已就绪。接入 MQTT 实时数据流后自动生效，无需修改脚本。静态数据下跑检测用于验证管道完整性。

**Q: 磁盘空间够吗？**
A: InfluxDB 数据文件仅 4.7MB（139K 条记录），整栈 < 500MB 内存。