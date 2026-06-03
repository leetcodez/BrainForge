import ast
import re
import logging

logger = logging.getLogger(__name__)

class AlphaSyntaxValidator(ast.NodeVisitor):
    def __init__(self):
        self.allowed_nodes = {
            ast.Module, ast.Expression, ast.Expr, ast.Call, ast.Name, ast.Load,
            ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
            ast.USub, ast.UAdd, ast.Constant, ast.Attribute, ast.List
        }
        
        self.allowed_operators = {
            'add', 'sqrt', 'log', 'subtract', 'signed_power', 'sign', 'reverse', 'power', 
            'multiply', 'min', 'max', 'inverse', 'densify', 'abs', 'divide', 'and', 'equal', 
            'or', 'not_equal', 'not', 'greater', 'greater_equal', 'less_equal', 'is_nan', 
            'if_else', 'less', 'ts_sum', 'ts_zscore', 'ts_std_dev', 'ts_mean', 'ts_scale', 
            'ts_rank', 'ts_quantile', 'ts_arg_min', 'ts_regression', 'kth_element', 'ts_corr', 
            'ts_count_nans', 'ts_covariance', 'ts_decay_linear', 'ts_product', 'ts_delay', 
            'ts_backfill', 'ts_av_diff', 'hump', 'ts_arg_max', 'last_diff_value', 'ts_step', 
            'ts_delta', 'days_from_last_change', 'winsorize', 'normalize', 'quantile', 'rank', 
            'scale', 'zscore', 'vec_sum', 'vec_avg', 'bucket', 'trade_when', 'group_scale', 
            'group_neutralize', 'group_zscore', 'group_backfill', 'group_mean', 'group_rank'
        }

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise ValueError(f"Forbidden AST node type: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id.lower()
            if func_name not in self.allowed_operators:
                raise ValueError(f"Forbidden function call: {func_name}")
        self.generic_visit(node)

class SyntaxValidator:
    @staticmethod
    def is_tautology(expression: str) -> bool:
        try:
            tree = ast.parse(expression, mode='eval')
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and type(node.op) in (ast.Div, ast.Sub):
                    if ast.unparse(node.left) == ast.unparse(node.right):
                        return True
            return False
        except Exception:
            return True

    @staticmethod
    def parse_and_validate(expression: str) -> bool:
        try:
            expression = SyntaxValidator._rectify_syntax(expression)
            tree = ast.parse(expression, mode='eval')
            validator = AlphaSyntaxValidator()
            validator.visit(tree)
            return True, expression
        except Exception as e:
            logger.error(f"Syntax validation failed for '{expression}': {e}")
            return False, expression

    @staticmethod
    def _rectify_syntax(expression: str) -> str:
        expression = re.sub(r'ts_mean\(\s*([a-zA-Z_0-9]+)\s*\)', r'ts_mean(\1, 20)', expression, flags=re.IGNORECASE)
        expression = re.sub(r'([a-zA-Z_0-9]+)\s+(\d+)', r'\1, \2', expression)
        return expression.strip()
