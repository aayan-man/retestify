import ast

_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
    ast.comprehension,
)


def cyclomatic_complexity(node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, _DECISION_NODES) or isinstance(child, ast.ExceptHandler):
            complexity += 1
    return complexity


def nesting_depth(node: ast.AST) -> int:
    branch_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)

    def _depth(n: ast.AST, current: int) -> int:
        deepest = current
        for child in ast.iter_child_nodes(n):
            next_depth = current + 1 if isinstance(child, branch_types) else current
            deepest = max(deepest, _depth(child, next_depth))
        return deepest

    return _depth(node, 0)


def loc(node: ast.AST) -> int:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return 0
    return end - start + 1


def num_params(node: ast.AST) -> int:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return 0
    args = node.args
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg:
        count += 1
    if args.kwarg:
        count += 1
    return count
