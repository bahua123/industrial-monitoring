#!/usr/bin/env python3
"""
工业温控异常检测脚本
定时扫描 InfluxDB，检测冷却系统 + 变压器油温异常
支持固定阈值 + 动态 3σ 统计检测
"""

import json
import urllib.request
import urllib.parse
import datetime
import sys
import os

INFLUX_URL = "http://127.0.0.1:8086/query?db=factory_monitoring"

FIXED_RULES = {
    "datacenter_cooling": [
        {"name": "冷却入风超温", "field": "inlet_temp", "op": ">", "value": 40, "unit": "°C",
         "desc": "服务器入风温度超过 40°C"},
        {"name": "温度异常突变", "field": "temp_deviation", "op": ">", "value": 5, "unit": "°C",
         "desc": "温度偏差超过 5°C，可能存在设备故障"},
        {"name": "冷却出风超温", "field": "outlet_temp", "op": ">", "value": 45, "unit": "°C"},
        {"name": "服务器负载过高", "field": "server_workload", "op": ">", "value": 95, "unit": "%"},
        {"name": "能耗异常高", "field": "energy_cost", "op": ">", "value": 0.15, "unit": "$"},
    ],
    "transformer_oil": [
        {"name": "变压器油温过高", "field": "OT", "op": ">", "value": 50, "unit": "°C"},
        {"name": "变压器油温过低", "field": "OT", "op": "<", "value": -2, "unit": "°C"},
    ]
}

SIGMA_RULES = {
    "datacenter_cooling": {"fields": ["inlet_temp", "outlet_temp", "ambient_temp", "temp_deviation", "server_workload"], "lookback_hours": 168, "sigma": 3},
    "transformer_oil": {"fields": ["OT"], "lookback_hours": 168, "sigma": 3}
}


def query_influx(query):
    url = f"{INFLUX_URL}&q={urllib.parse.quote(query)}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def get_latest_values():
    result = {}
    r = query_influx("SELECT last(*) FROM datacenter_cooling")
    series = r.get("results", [{}])[0].get("series", [])
    if series:
        cols = series[0]["columns"]
        vals = series[0]["values"][0]
        result["datacenter_cooling"] = {c.replace("last_", ""): vals[i] for i, c in enumerate(cols) if vals[i] is not None and c != "time"}

    r = query_influx("SELECT last(*) FROM transformer_oil GROUP BY region")
    for s in r.get("results", [{}])[0].get("series", []):
        region = s.get("tags", {}).get("region", "unknown")
        cols = s["columns"]
        vals = s["values"][0]
        key = f"transformer_oil_{region}"
        result[key] = {c.replace("last_", ""): vals[i] for i, c in enumerate(cols) if vals[i] is not None and c != "time"}
    return result


def check_fixed_rules(data):
    alerts = []
    for key, rules in FIXED_RULES.items():
        values = data.get(key, {})
        if not values:
            continue
        for rule in rules:
            val = values.get(rule["field"])
            if val is None:
                continue
            triggered = val > rule["value"] if rule["op"] == ">" else val < rule["value"]
            if triggered:
                alerts.append({"source": key, "type": rule["name"], "value": f"{val:.2f}{rule['unit']}", "threshold": f"{rule['op']} {rule['value']}{rule['unit']}", "desc": rule.get("desc",""), "level": "HIGH" if "超温" in rule["name"] or "过高" in rule["name"] else "MEDIUM"})
    return alerts


def check_sigma_rules(data):
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
            start_str = (now - datetime.timedelta(hours=cfg["lookback_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
            r = query_influx(f"SELECT MEAN({field}), STDDEV({field}) FROM {source} WHERE time >= '{start_str}'")
            try:
                s = r["results"][0]["series"][0]["values"][0]
                mean, stddev = s[1] or 0, s[2] or 0
            except (KeyError, IndexError):
                continue
            if stddev == 0:
                continue
            upper, lower = mean + cfg["sigma"] * stddev, mean - cfg["sigma"] * stddev
            if val > upper:
                alerts.append({"source": source, "type": f"{field} 高温异常", "value": f"{val:.2f}", "threshold": f"上限{upper:.2f}", "desc": f"当前{val:.2f} > 正常上界{upper:.2f}", "level": "WARNING"})
            elif val < lower:
                alerts.append({"source": source, "type": f"{field} 低温异常", "value": f"{val:.2f}", "threshold": f"下限{lower:.2f}", "desc": f"当前{val:.2f} < 正常下界{lower:.2f}", "level": "WARNING"})
    return alerts


def run():
    print(f"🔍 温控异常检测 - {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 50)
    data = get_latest_values()
    if "error" in data:
        print(f"❌ 失败: {data['error']}")
        return 1
    for key in sorted(data.keys()):
        v = data[key]
        if "inlet_temp" in v:
            print(f"\n📊 {key}: 入风{v.get('inlet_temp',0):.1f}°C, 出风{v.get('outlet_temp',0):.1f}°C, 偏差{v.get('temp_deviation',0):.1f}°C")
        if "OT" in v:
            print(f"\n📊 {key}: 油温{v['OT']:.1f}°C")
    fixed = check_fixed_rules(data)
    print("\n--- 固定阈值 ---")
    print(f"  {'✅ 全部正常' if not fixed else ''}")
    for a in fixed:
        print(f"  {'🔴' if a['level']=='HIGH' else '🟡'} [{a['level']}] {a['type']}: {a['value']}")
    sigma = check_sigma_rules(data)
    print("\n--- 动态 3σ ---")
    print(f"  {'✅ 全部正常' if not sigma else ''}")
    for a in sigma:
        print(f"  ⚠️  {a['type']}: {a['value']} ({a['desc']})")
    total = len(fixed) + len(sigma)
    print(f"\n{'='*50}")
    print(f"{'✅ 全部正常，无异常' if total==0 else f'⚠️ 检测到 {total} 条异常'}")
    return 0 if total == 0 else 1

if __name__ == "__main__":
    sys.exit(run())