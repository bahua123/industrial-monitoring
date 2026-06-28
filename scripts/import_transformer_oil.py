import csv
import requests
import time

INFLUX_URL = "http://127.0.0.1:8086/write?db=factory_monitoring"
BATCH_SIZE = 5000

def parse_and_import(filename, region_tag):
    total = 0
    batch = []
    with open(filename) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert timestamp: "2016-07-01 00:00:00" -> epoch in seconds
            ts = int(time.mktime(time.strptime(row['date'], '%Y-%m-%d %H:%M:%S')))
            
            # Build line protocol entry
            line = (f'transformer_oil,region={region_tag} '
                    f'HUFL={row["HUFL"]},HULL={row["HULL"]},'
                    f'MUFL={row["MUFL"]},MULL={row["MULL"]},'
                    f'LUFL={row["LUFL"]},LULL={row["LULL"]},'
                    f'OT={row["OT"]} '
                    f'{ts}000000000')  # append 9 zeros for nanosecond precision
            batch.append(line)
            total += 1

            if len(batch) >= BATCH_SIZE:
                data = '\n'.join(batch)
                resp = requests.post(INFLUX_URL, data=data)
                if resp.status_code != 204:
                    print(f'  ❌ Error at row {total}: {resp.status_code} {resp.text[:200]}')
                    return 0
                batch = []
                print(f'  ✓ {total} rows imported...', end='\r')
    
    # Final batch
    if batch:
        data = '\n'.join(batch)
        resp = requests.post(INFLUX_URL, data=data)
        if resp.status_code != 204:
            print(f'  ❌ Final error: {resp.status_code} {resp.text[:200]}')
            return 0
        print(f'  ✓ {total} rows imported...', end='\r')
    
    return total

print("🚀 导入 ETTm1 (region=m1)...")
t1 = parse_and_import('/tmp/ETTm1.csv', 'm1')

print()
print("🚀 导入 ETTm2 (region=m2)...")
t2 = parse_and_import('/tmp/ETTm2.csv', 'm2')

print(f"\n✅ 完成！共导入 {t1 + t2} 条记录")
