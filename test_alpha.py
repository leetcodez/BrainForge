import asyncio
from network_engine import NetworkEngine

async def test():
    network = NetworkEngine()
    payload = {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "decay": 15,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.08,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "ON",
            "language": "FASTEXPR",
            "visualization": False
        },
        "regular": "group_neutralize(ts_mean(ts_zscore(implied_volatility_put_30, 5) - ts_zscore(implied_volatility_put_60, 5), 5), bucket(rank(assets), range='0,1,0.1'))"
    }
    
    print("Submitting simulation...")
    response_data = await network.request("POST", "/simulations", json=payload)
    print("Response:", response_data)
    
    if "Location" in response_data or "url" in response_data:
        poll_url = response_data.get("Location") or response_data.get("url")
        print("Polling", poll_url)
        for _ in range(10):
            await asyncio.sleep(2)
            result = await network.request("GET", poll_url.replace("https://api.worldquantbrain.com", ""))
            status = result.get("status")
            print("Status:", status)
            if status == "ERROR":
                print("Error Details:", result)
                break
            elif status == "COMPLETE":
                print("Complete!")
                break
    await network.close()

if __name__ == "__main__":
    asyncio.run(test())
