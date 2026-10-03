```python
from db_manager import DatabaseManager

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


def main():
    db = DatabaseManager()
    db.init_db_sync()
    rows = db.get_top_for_review_sync(20)
    db.close_sync()
    if not rows:
        print("No scored alphas yet. Run orchestrator.py first.")
        return

    headers = ["Expression", "Sharpe", "Turnover", "Fitness", "Depth", "MaxCorr", "Tuned"]
    table = []
    for expr, sharpe, turnover, fitness, depth, max_corr, is_tuned in rows:
        display_expr = (expr[:70] + "...") if expr and len(expr) > 70 else (expr or "")
        table.append([
            display_expr,
            f"{sharpe:.3f}" if sharpe is not None else "-",
            f"{turnover:.3f}" if turnover is not None else "-",
            f"{fitness:.4f}" if fitness is not None else "-",
            depth if depth is not None else "-",
            f"{max_corr:.3f}" if max_corr is not None else "-",
            "yes" if is_tuned else "no",
        ])

    if tabulate:
        print(tabulate(table, headers=headers, tablefmt="github"))
    else:
        print("\t".join(headers))
        for row in table:
            print("\t".join(str(c) for c in row))


if __name__ == "__main__":
    main()
```