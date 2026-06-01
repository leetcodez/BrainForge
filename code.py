from curl_cffi import requests
import time
import random

# --- 1. CONFIGURATION & AUTH ---
BROWSER_COOKIE = "cookieyes-consent=consentid:MnNBbnljSThGUWJQRkFSaE5SNXd1WmdJZXpTY1c0RG4,consent:yes,action:yes,necessary:yes,functional:yes,analytics:yes,performance:yes,advertisement:yes,other:yes; __zlcmid=1XjoXQxrdKEmm6w; t=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJKbkdGdERhZ2tDQ2RveTE4SVZJMkZUMUV4eUdHdDVmcyIsImV4cCI6MTc4MDMwNzgwMSwiYW1yIjpbInB3ZCIsImZhY2UiXX0.FAecRUqtjY5zVevTJs6KlvfktSnjFejAFpvrobx2tMA"

session = requests.Session(impersonate="chrome120")
session.headers.update({
    "Cookie": BROWSER_COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json"
})

# --- 2. LOCAL DATA DICTIONARY ---
# A mix of price, volume, and fundamental metrics to hot-swap into the LLM template
DATA_FIELDS = [
    "volume",
    "close",
    "returns",
    "vwap",
    "adv20",               # 20-day average daily volume
    "fra_sales",           # Fundamental: Sales
    "fra_ebitda",          # Fundamental: EBITDA
    "fra_net_income"       # Fundamental: Net Income
]

# --- 3. CORE SIMULATION FUNCTIONS ---
def run_simulation(expression):
    url = "https://api.worldquantbrain.com/simulations"
    
    payload = {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "decay": 0,
            "neutralization": "SUBINDUSTRY", 
            "truncation": 0.08, 
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "OFF",
            "language": "FASTEXPR",
            "visualization": False
        },
        "regular": expression
    }

    response = session.post(url, json=payload)
    
    if response.status_code == 201:
        return response.headers.get("Location")
    elif response.status_code == 401:
        print("❌ Authentication failed. Cookie expired.")
        return None
    else:
        print(f"❌ Simulation rejected: {response.status_code} - {response.text}")
        return None

def poll_results(sim_location):
    while True:
        response = session.get(sim_location)
        
        if response.status_code == 429:
            backoff = int(response.headers.get("Retry-After", 15))
            print(f"⚠️ RATE LIMIT! Backing off for {backoff}s...")
            time.sleep(backoff)
            continue
            
        data = response.json()
        status = data.get("status")
        
        if status == "COMPLETE":
            alpha_id = data.get("alpha")
            alpha_response = session.get(f"https://api.worldquantbrain.com/alphas/{alpha_id}")
            
            if alpha_response.status_code == 200:
                is_metrics = alpha_response.json().get("is", {})
                sharpe = is_metrics.get("sharpe", 0)
                turnover = is_metrics.get("turnover", 0)
                
                print(f"   | Sharpe: {sharpe} | Turnover: {turnover * 100:.2f}%")
                if sharpe >= 1.25 and turnover <= 0.70:
                    print("   🌟 WINNER: Metrics passed!")
                else:
                    print("   🗑️ Failed minimum metrics.")
            break
        elif status == "ERROR":
            print(f"   ❌ Error: {data.get('error')}")
            break
        else:
            jitter_delay = max(3.0, abs(random.gauss(5.5, 1.2))) 
            time.sleep(jitter_delay)

# --- 4. THE TEMPLATE INJECTOR ---
def execute_mutation_batch(template_expression, max_tests=3):
    """Takes a template string, swaps {FIELD} with real data, and simulates."""
    print(f"\n🧬 INITIATING BATCH. Seed Template: {template_expression}")
    
    # Grab a random sample from our dictionary to test
    test_batch = random.sample(DATA_FIELDS, min(max_tests, len(DATA_FIELDS)))
    
    for i, field in enumerate(test_batch):
        # 1. Hot-swap the placeholder with the actual data token
        mutated_alpha = template_expression.replace("{FIELD}", field)
        print(f"\n🧪 Test {i+1}/{max_tests} -> Executing: {mutated_alpha}")
        
        # 2. Run the simulation
        queue_url = run_simulation(mutated_alpha)
        if queue_url:
            poll_results(queue_url)
            
        # 3. Stealth delay between different alpha submissions
        inter_submission_delay = max(5.0, abs(random.gauss(8.0, 2.5)))
        print(f"⏸️ Resting {inter_submission_delay:.2f}s before next mutation to evade telemetry...")
        time.sleep(inter_submission_delay)


# --- 5. MAIN EXECUTION ---
if __name__ == "__main__":
    
    # Imagine Gemini generated this structure for us. 
    # It contains the {FIELD} placeholder instead of a hardcoded metric.
    gemini_generated_seed = "group_neutralize(rank(-1 * returns) * ts_rank({FIELD}, 10), subindustry)"
    
    # Run a batch test on 4 different fundamental/price fields
    execute_mutation_batch(gemini_generated_seed, max_tests=4)