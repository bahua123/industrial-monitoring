#!/usr/bin/env python3
"""
模拟数据中心冷却传感器数据生成器
生成 5 种冷却策略下 7 天的连续时序数据，写入 InfluxDB v1
"""

import time
import random
import math
import sys
import os

INFLUX_URL = os.environ.get(
    "INFLUX_URL",
    "http://127.0.0.1:8086/write?db=factory_monitoring"
)

STRATEGIES = [
    "free_cooling",      # 自然冷却（低温季节利用室外空气）
    "chilled_water",     # 冷水机组（传统空调）
    "evaporative",       # 蒸发冷却（高湿度地区效率略低）
    "crac_cfd",          # 精密空调+CFD优化（气流组织优化）
    "liquid_cooling",    # 液冷（高密度场景，能耗最低）
]

# 各策略的基础参数（温度范围、功率、能耗系数）
STRATEGY_PARAMS = {
    "free_cooling":    {"inlet": (14, 24), "power": (10, 30), "cost_factor": 0.02},
    "chilled_water":   {"inlet": (16, 20), "power": (40, 80), "cost_factor": 0.08},
    "evaporative":     {"inlet": (17, 23), "power": (25, 50), "cost_factor": 0.05},
    "crac_cfd":        {"inlet": (15, 19), "power": (30, 60), "cost_factor": 0.06},
    "liquid_cooling":  {"inlet": (18, 22), "power": (5, 15),  "cost_factor": 0.015},
}


def generate_hourly(base_inlet, strategy, hour_of_day, noise=0):
    """生成一条传感器样本"""
    # 昼夜温差：白天热一点，晚上凉一点
    diurnal = 3 * math.sin((hour_of_day - 14) * math.pi / 12)

    params = STRATEGY_PARAMS[strategy]
    inlet_low, inlet_high = params["inlet"]

    inlet_temp = base_inlet + diurnal + random.gauss(0, 0.8) + noise
    inlet_temp = max(inlet_low, min(inlet_high, inlet_temp))

    # 出风 = 入风 + 冷却设备温升
    outlet_temp = inlet_temp + random.uniform(4, 10)

    # 环境温度比入风略高
    ambient_temp = inlet_temp + random.uniform(1, 4)

    # 温度偏差
    temp_deviation = outlet_temp - inlet_temp + random.gauss(0, 0.5)

    # 服务器负载 (30-95%)
    server_workload = 50 + 30 * math.sin(hour_of_day / 24 * math.pi) + random.gauss(0, 8)
    server_workload = max(30, min(95, server_workload))

    # 冷却功率
    power_low, power_high = params["power"]
    cooling_power = power_low + (power_high - power_low) * (server_workload / 100)
    cooling_power += random.gauss(0, 3)

    # 能耗成本
    cost_factor = params["cost_factor"]
    energy_cost = cooling_power * cost_factor * random.uniform(0.9, 1.1)

    return {
        "inlet_temp": round(inlet_temp, 2),
        "outlet_temp": round(outlet_temp, 2),
        "ambient_temp": round(ambient_temp, 2),
        "temp_deviation": round(temp_deviation, 2),
        "server_workload": round(server_workload, 1),
        "cooling_power_kw": round(cooling_power, 2),
        "energy_cost": round(energy_cost, 4),
    }


def main():
    import urllib.request as req

    print(f"🚀 生成模拟传感器数据并写入 {INFLUX_URL}")
    print(f"   策略: {', '.join(STRATEGIES)}")
    print(f"   生成周期: 7 天, 5 分钟间隔")

    total = 0
    batch = []
    BATCH_SIZE = 500

    # 7 天，5 分钟间隔
    start_ts = int(time.time()) - 7 * 86400
    end_ts = start_ts + 7 * 86400

    for ts in range(start_ts, end_ts, 300):  # 300s = 5min
        hour = datetime.datetime.fromtimestamp(ts).hour
        strategy = random.choice(STRATEGIES)

        base_inlet = STRATEGY_PARAMS[strategy]["inlet"][0] + 2
        noise = random.gauss(0, 1.5) if random.random() < 0.02 else 0

        data = generate_hourly(base_inlet, strategy, hour, noise)
        ns = ts * 1_000_000_000

        line = (
            f"datacenter_cooling,strategy={strategy} "
            f"inlet_temp={data['inlet_temp']},"
            f"outlet_temp={data['outlet_temp']},"
            f"ambient_temp={data['ambient_temp']},"
            f"temp_deviation={data['temp_deviation']},"
            f"server_workload={data['server_workload']},"
            f"cooling_power_kw={data['cooling_power_kw']},"
            f"energy_cost={data['energy_cost']} "
            f"{ns}"
        )
        batch.append(line)
        total += 1

        if len(batch) >= BATCH_SIZE:
            payload = "\n".join(batch).encode()
            r = req.urlopen(INFLUX_URL, data=payload)
            if r.status != 204:
                print(f"  ❌ 写入失败: HTTP {r.status}")
                sys.exit(1)
            batch = []
            print(f"  ✓ {total} 条...", end="\r")

    # 最后一批
    if batch:
        payload = "\n".join(batch).encode()
        r = req.urlopen(INFLUX_URL, data=payload)
        if r.status != 204:
            print(f"  ❌ 写入失败: HTTP {r.status}")
            sys.exit(1)

    print(f"\n✅ 完成！共生成 {total} 条温度记录")
    return total


if __name__ == "__main__":
    import datetime
    main()