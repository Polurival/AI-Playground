"""Small utility tools: safe calculator and date/time."""

import ast
import datetime as dt
import math
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {n: getattr(math, n) for n in
          ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil", "factorial")}
_FUNCS.update(abs=abs, round=round, min=min, max=max)
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        l, r = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(r) > 1000:
            raise ValueError("exponent too large")
        return _BIN[type(node.op)](l, r)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str:
    try:
        return str(_eval(ast.parse(expression.strip(), mode="eval")))
    except ZeroDivisionError:
        return "error: division by zero"
    except (ValueError, SyntaxError, TypeError, OverflowError) as exc:
        return f"error: {exc}"


def current_datetime() -> str:
    now = dt.datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z), %A")
