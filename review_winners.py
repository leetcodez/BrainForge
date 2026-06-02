import sqlite3
from tabulate import tabulate

def review_alphas():
    try:
        conn = sqlite3.connect("brain_memory.db")
        cursor = conn.cursor()
        
        # Fetch top winners for review
        cursor.execute('''
            SELECT expression, sharpe, turnover, ast_depth, is_tuned 
            FROM alpha_population 
            WHERE sharpe >= 1.25 AND turnover <= 0.70
            ORDER BY sharpe DESC
        ''')
        winners = cursor.fetchall()
        conn.close()
        
        if not winners:
            print("[-] No high-performance alphas found in the database yet.")
            return

        headers = ["Expression", "Sharpe", "Turnover", "AST Depth", "Is Tuned"]
        print(f"\n[+] Found {len(winners)} potential candidates for submission:\n")
        print(tabulate(winners, headers=headers, tablefmt="grid"))
        print("\n[?] Review the expressions above. If happy, run: python3 submit_to_worldquant.py\n")
    except Exception as e:
        print(f"[-] Error reviewing winners: {e}")

if __name__ == "__main__":
    # Check if tabulate is installed
    try:
        from tabulate import tabulate
    except ImportError:
        print("[-] Please install tabulate: pip install tabulate")
    
    review_alphas()
