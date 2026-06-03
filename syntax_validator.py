import ast
import logging
import re

import config

logger = logging.getLogger(__name__)


class AlphaSyntaxValidator(ast.NodeVisitor):
    def __init__(self):
        self.allowed_nodes = {
            ast.Module,
            ast.Expression,
            ast.Expr,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.BinOp,
            ast.UnaryOp,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.USub,
            ast.UAdd,
            ast.Constant,
            ast.List,
            ast.keyword,
            ast.Compare,
            ast.Gt,
            ast.GtE,
            ast.Lt,
            ast.LtE,
            ast.Eq,
            ast.NotEq,
        }
        self.allowed_operators = set(config.ALLOWED_OPERATORS)

    def generic_visit(self, node):
        if type(node) not in self.allowed_nodes:
            raise ValueError(f"Forbidden AST node type: {type(node).__name__}")
        super().generic_visit(node)

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct FastExpr function calls are allowed")

        func_name = node.func.id.lower()
        if func_name not in self.allowed_operators:
            raise ValueError(f"Forbidden function call: {func_name}")

        arg_count = len(node.args) + len(node.keywords)
        if not SyntaxValidator.operator_accepts_arity(func_name, arg_count):
            min_args, max_args = config.OPERATOR_ARITY.get(func_name, (0, None))
            expected = f"{min_args}+" if max_args is None else f"{min_args}-{max_args}"
            raise ValueError(f"Invalid arity for {func_name}: got {arg_count}, expected {expected}")

        self.generic_visit(node)


class SyntaxValidator:
    COMMUTATIVE_BINOPS = (ast.Add, ast.Mult)
    COMMUTATIVE_FUNCTIONS = {"add", "multiply", "min", "max", "equal", "not_equal"}

    @staticmethod
    def operator_accepts_arity(operator_name: str, arg_count: int) -> bool:
        min_args, max_args = config.OPERATOR_ARITY.get(operator_name, (0, None))
        if arg_count < min_args:
            return False
        if max_args is not None and arg_count > max_args:
            return False
        return True

    @staticmethod
    def canonicalize(expression: str) -> str:
        tree = ast.parse(expression, mode="eval")

        class CanonicalTransformer(ast.NodeTransformer):
            def visit_BinOp(self, node):
                node = self.generic_visit(node)
                if isinstance(node.op, SyntaxValidator.COMMUTATIVE_BINOPS):
                    operands = self._flatten_binop(node, type(node.op))
                    operands.sort(key=ast.unparse)
                    return self._build_binop(operands, type(node.op))
                return node

            def visit_Call(self, node):
                node = self.generic_visit(node)
                if isinstance(node.func, ast.Name) and node.func.id.lower() in SyntaxValidator.COMMUTATIVE_FUNCTIONS:
                    node.args = sorted(node.args, key=ast.unparse)
                return node

            def _flatten_binop(self, node, op_type):
                if isinstance(node, ast.BinOp) and isinstance(node.op, op_type):
                    return self._flatten_binop(node.left, op_type) + self._flatten_binop(node.right, op_type)
                return [node]

            def _build_binop(self, operands, op_type):
                current = operands[0]
                for operand in operands[1:]:
                    current = ast.BinOp(left=current, op=op_type(), right=operand)
                return current

        new_tree = CanonicalTransformer().visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)

    @staticmethod
    def is_tautology(expression: str) -> bool:
        try:
            tree = ast.parse(expression, mode="eval")
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and type(node.op) in (ast.Div, ast.Sub):
                    left = SyntaxValidator.canonicalize(ast.unparse(node.left))
                    right = SyntaxValidator.canonicalize(ast.unparse(node.right))
                    if left == right:
                        return True
            return False
        except Exception:
            return True

    @staticmethod
    def parse_and_validate(expression: str):
        try:
            expression = SyntaxValidator._rectify_syntax(expression)
            tree = ast.parse(expression, mode="eval")
            validator = AlphaSyntaxValidator()
            validator.visit(tree)
            return True, SyntaxValidator.canonicalize(expression)
        except Exception as e:
            logger.error(f"Syntax validation failed for '{expression}': {e}")
            return False, expression

    @staticmethod
    def _rectify_syntax(expression: str) -> str:
        expression = re.sub(r"ts_mean\(\s*([a-zA-Z_0-9]+)\s*\)", r"ts_mean(\1, 20)", expression, flags=re.IGNORECASE)
        expression = re.sub(r"([a-zA-Z_0-9]+)\s+(\d+)", r"\1, \2", expression)
        return expression.strip()
