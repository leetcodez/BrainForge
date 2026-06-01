import asyncio
import json
from network_engine import NetworkEngine
import config

async def probe():
    net = NetworkEngine()
    
    endpoints = [
        "/data-fields?instrumentType=EQUITY&region=USA&delay=1&universe=TOP3000&limit=50",
        "/operators",
        "/simulations"
    ]
    
    for ep in endpoints:
        print(f"Probing {ep} ...")
        try:
            res = await net.request("GET", ep)
            print(f"SUCCESS {ep}")
            if "data-fields" in ep:
                fields = [f["id"] for f in res.get("results", [])]
                print(f"Sample fields: {fields[:10]}")
                with open("fields.json", "w") as f:
                    json.dump(fields, f)
            elif "operators" in ep:
                # Assuming operators return list or dict with results
                ops = [o["name"] if "name" in o else o["id"] for o in res] if isinstance(res, list) else res
                print(f"Sample operators: {str(ops)[:100]}")
                with open("operators.json", "w") as f:
                    json.dump(res, f)
        except Exception as e:
            print(f"FAILED {ep}: {e}")
            
    await net.close()

if __name__ == "__main__":
    asyncio.run(probe())