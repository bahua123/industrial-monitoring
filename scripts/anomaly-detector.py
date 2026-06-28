#!/usr/bin/env python3
"""
工业温控异常检测脚本
定时扫描 InfluxDB，检测冷却系统 + 变压器油温异常
支持固定阈值 + 动态 3σ 统计检测
"""

import json
import urllib.request
import datetime
import sys
import os

INFLUX_HOST = os.environ.get("INFLUX_HOST", "127.0.0.1:8086")
INFLUX_URL = f"http://{INFLUX_HOST}/query?db=factory_monitoring"

# ============================================================
# 第一层：固定阈值规则
# ============================================================
FIXED_RULES = {
    "datacenter_cooling": [
        {"name": "冷却入风超温", "field": "inlet_temp", "op": ">", "value": 40, "unit": "°C",
         "desc": "服务器入风温度超过 40°C（危险线）"},
        {"name": "温度异常突变", "field": "temp_deviation", "op": ">", "value": 5, "unit": "°C",
         "desc": "温度偏差超过 5°C，可能存在设备故障"},
        {"name": "冷却出风超温", "field": "outlet_temp", "op": ">", "value": 45, "unit": "°C",
         "desc": "出风温度超过 45°C"},
        {"name": "服务器负载过高", "field": "server_workload", "op": ">", "value": 95, "unit": "%",
         "desc": "服务器负载超过 95%"},
        {"name": "能耗异常高", "field": "energy_cost", "op": ">", "value": 0.15, "unit": "$",
         "desc": "能耗成本超过 $0.15"},
    ],
    "transformer_oil": [
        {"name": "变压器油温过高", "field": "OT", "op": ">", "value": 50, "unit": "°C",
         "desc": "变压器油温超过 50°C（警戒线）"},
        {"name": "变压器油温过低", "field": "OT", "op": "<", "value": -2, "unit": "°C",
         "desc": "变压器油温低于 -2°C（异常低温）"},
    ]
}

# ============================================================
# 第二层：动态 3σ 统计检测
# ============================================================
SIGMA_RULES = {
    "datacenter_cooling": {
        "fields": ["inlet_temp", "outlet_temp", "ambient_temp", "temp_deviation", "server_workload"],
        "lookback_hours": 168,  # 7天
        "sigma": 3
    },
    "transformer_oil": {
        "fields": ["OT"],
        "lookback_hours": 168,
        "sigma": 3
    }
}


def query_influx(query):
    """执行 InfluxDB 查询"""
    url = f"{INFLUX_URL}&q={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_latest_values():
    """获取所有测量表的最新数据"""
    result = {}

    # datacenter_cooling
    r = query_influx("SELECT last(*) FROM datacenter_cooling")
    if "error" in r:
        return {"error": r["error"]}
    series = r.get("results", [{}])[0].get("series", [])
    if series:
        cols = series[0]["columns"]
        vals = series[0]["values"][0]
        result["datacenter_cooling"] = {
            c.replace("last_", ""): vals[i]
            for i, c in enumerate(cols) if vals[i] is not None and c != "time"
        }

    # transformer_oil (按 region 取)
    r = query_influx("SELECT last(*) FROM transformer_oil GROUP BY region")
    if "error" not in r:
        series_list = r.get("results", [{}])[0].get("series", [])
        for s in series_list:
            region = s.get("tags", {}).get("region", "unknown")
            cols = s["columns"]
            vals = s["values"][0]
            key = f"transformer_oil_{region}"
            result[key] = {
                c.replace("last_", ""): vals[i]
                for i, c in enumerate(cols) if vals[i] is not None and c != "time"
            }

    return result


def check_fixed_rules(data):
    """第一层：固定阈值检测"""
    alerts = []
    for key, rules in FIXED_RULES.items():
        values = data.get(key, {})
        if not values:
            continue
        for rule in rules:
            val = values.get(rule["field"])
            if val is None:
                continue
            triggered = False
            if rule["op"] == ">":
                triggered = val > rule["value"]
            elif rule["op"] == "<":
                triggered = val < rule["value"]
            if triggered:
                alerts.append({
                    "source": key,
                    "type": rule["name"],
                    "value": f"{val:.2f}{rule['unit']}",
                    "threshold": f"{rule['op']} {rule['value']}{rule['unit']}",
                    "desc": rule["desc"],
                    "level": "HIGH" if "超温" in rule["name"] or "过高" in rule["name"] else "MEDIUM"
                })
    return alerts


def check_sigma_rules(data):
    """第二层：动态 3σ 统计检测"""
    alerts = []
    now = datetime.datetime.utcnow()

    for source, cfg in SIGMA_RULES.items():
        values = data.get(source, {})
        if not values:
            continue

        for field in cfg["fields"]:
            val = values.get(field)
            if val is None:
                continue

            # 取历史数据计算统计基线
            lookback_start = now - datetime.timedelta(hours=cfg["lookback_hours"])
            start_str = lookback_start.strftime("%Y-%m-%dT%H:%M:%SZ")

            q = (f"SELECT MEAN({field}), STDDEV({field}) FROM {source} "
                 f"WHERE time >= '{start_str}'")
            r = query_influx(q)
            try:
                s = r["results"][0]["series"][0]["values"][0]
                mean = s[1] if s[1] is not None else 0
                stddev = s[2] if s[2] is not None else 0
            except (KeyError, IndexError):
                continue

            if stddev == 0:
                continue

            upper = mean + cfg["sigma"] * stddev
            lower = mean - cfg["sigma"] * stddev

            if val > upper:
                alerts.append({
                    "source": source,
                    "type": f"{field} 动态高温异常",
                    "value": f"{val:.2f}",
                    "threshold": f"均值{mean:.2f}+{cfg['sigma']}σ={upper:.2f}",
                    "desc": f"当前 {val:.2f} > 正常上界 {upper:.2f}（{field}）",
                    "level": "WARNING"
                })
            elif val < lower:
                alerts.append({
                    "source": source,
                    "type": f"{field} 动态低温异常",
                    "value": f"{val:.2f}",
                    "threshold": f"均值{mean:.2f}-{cfg['sigma']}σ={lower:.2f}",
                    "desc": f"当前 {val:.2f} < 正常下界 {lower:.2f}（{field}）",
                    "level": "WARNING"
                })

    return alerts


def run():
    """主流程"""
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"🔍 工业温控异常检测 - {now_str}")
    print("=" * 50)

    # 获取数据
    data = get_latest_values()
    if "error" in data:
        print(f"❌ 数据获取失败: {data['error']}")
        return

    # 显示最新数据概览
    for key in sorted(data.keys()):
        vals = data[key]
        if "inlet_temp" in vals:
            print(f"\n📊 {key}: 入风{vals.get('inlet_temp',0):.1f}°C, "
                  f"出风{vals.get('outlet_temp',0):.1f}°C, "
                  f"偏差{vals.get('temp_deviation',0):.1f}°C")
        if "OT" in vals:
            print(f"\n📊 {key}: 油温{vals['OT']:.1f}°C")
        if "energy_cost" in vals:
            print(f"   能耗${vals.get('energy_cost',0):.3f}, "
                  f"负载{vals.get('server_workload',0):.0f}%")

    # 阈值检测
    print("\n--- 第一层：固定阈值检测 ---")
    fixed = check_fixed_rules(data)
    if fixed:
        for a in fixed:
            icon = "🔴" if a["level"] == "HIGH" else "🟡"
            print(f"  {icon} [{a['level']}] {a['type']}: {a['value']} ({a['threshold']})")
            print(f"     {a['desc']}")
    else:
        print("  ✅ 所有固定阈值正常")

    # 3σ 检测
    print("\n--- 第二层：动态 3σ 统计检测 ---")
    sigma = check_sigma_rules(data)
    if sigma:
        for a in sigma:
            print(f"  ⚠️  [{a['level']}] {a['type']}: {a['value']}")
            print(f"     {a['desc']}")
    else:
        print("  ✅ 所有 3σ 统计范围内")

    # 汇总
    total = len(fixed) + len(sigma)
    print(f"\n{'=' * 50}")
    if total == 0:
        print("✅ 全部正常，无异常")
    else:
        print(f"⚠️ 共检测到 {total} 条异常")

    # 输出摘要
    return total


if __name__ == "__main__":
    import urllib.parse  # noqa: F811 - reimport for script use
    exit_code = run()
    sys.exit(0 if exit_code == 0 else 1)