import optuna
import asyncio
import logging
import nest_asyncio

nest_asyncio.apply()

optuna.logging.set_verbosity(optuna.logging.WARNING)

class AlphaTuner:
    def __init__(self, base_expression, simulate_func):
        self.base_expression = base_expression
        self.simulate_func = simulate_func
        
    def objective(self, trial):
        d1 = trial.suggest_int("d1", 2, 60)
        d2 = trial.suggest_int("d2", 5, 120)
        
        candidate_expr = self.base_expression.replace("{d1}", str(d1)).replace("{d2}", str(d2))
        
        loop = asyncio.get_event_loop()
        sharpe, turnover, alpha_id = loop.run_until_complete(self.simulate_func(candidate_expr))
        
        trial.set_user_attr("alpha_id", alpha_id)
        
        if turnover > 0.70:
            return -1.0 
            
        return sharpe

    def run_tuning(self, n_trials=15):
        print(f"[*] Commencing Bayesian Tuning on base structure...")
        study = optuna.create_study(direction="maximize")
        study.optimize(self.objective, n_trials=n_trials)
        
        best_params = study.best_params
        best_sharpe = study.best_value
        best_alpha_id = study.best_trial.user_attrs.get("alpha_id", "")
        
        optimal_expr = self.base_expression.replace("{d1}", str(best_params["d1"])).replace("{d2}", str(best_params["d2"]))
        
        print(f"[+] Tuning Complete! Best Sharpe: {best_sharpe} using {best_params}")
        return optimal_expr, best_sharpe, best_params, best_alpha_id
