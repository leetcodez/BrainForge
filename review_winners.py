import sqlite3
from tabulate import tabulate

def review_alphas():
    try:
        conn = sqlite3.connect("brain_memory.db")
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT expression, sharpe, turnover, ast_depth, is_tuned 
            FROM alpha_population 
            ORDER BY sharpe DESC 
            LIMIT 10
        ''')
        winners = cursor.fetchall()
        conn.close()
        
        if not winners:
            print("[-] No alphas found.")
            return

        headers = ["Expression", "Sharpe", "Turnover", "AST Depth", "Is Tuned"]
        print(f"\n[+] Top 10 Performance frontier:\n")
        print(tabulate(winners, headers=headers, tablefmt="grid"))
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    review_alphas()
