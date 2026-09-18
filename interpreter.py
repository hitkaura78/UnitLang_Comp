"""
Tree-walking interpreter for UnitLang.

Runs *after* semantic analysis has already approved the program, so
this file does zero dimension checking — it just computes numbers.
Every quantity is stored internally as a plain float in BASE units
(meters, kilograms, seconds); unit identifiers used as values (e.g.
the `m` in `5 * m`) evaluate to their scale factor from the symbol
table, which is exactly what makes `5 * m` come out to `5.0` base
meters and `5 * km` come out to `5000.0` base meters for free — no
special-casing needed in the arithmetic.

Novelty feature #2 lives here: `print` doesn't dump the raw base-unit
float. `smart_format()` looks at the value's dimension, finds every
built-in/user-defined unit that shares that dimension, and picks
whichever one displays the value with a magnitude closest to a
comfortable 1–1000 range (falling back to base units if nothing
fits nicely). So printing 5000 (base meters, dimension Length) shows
"5 km" instead of "5000 m".
"""

import math

from ast_nodes import (
    Program, FuncDecl, Block, DeclStmt, AssignStmt, IfStmt, WhileStmt,
    ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp, UnaryOp, Call,
    NumberLit, BoolLit, Identifier,
)
from dimension import Dimension


class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


class Env:
    def __init__(self):
        self.scopes = [{}]

    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def declare(self, name, value):
        self.scopes[-1][name] = value

    def set(self, name, value):
        for scope in reversed(self.scopes):
            if name in scope:
                scope[name] = value
                return
        self.scopes[0][name] = value

    def get(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        raise NameError(name)


def smart_format(value: float, dim: Dimension, sym) -> str:
    """Novelty: pick the nicest built-in/user unit for display."""
    if dim.is_dimensionless():
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.4g}"

    candidates = [u for u in sym.units.values() if u.dim == dim]
    if not candidates:
        return f"{value:.4g} (base units: {dim.pretty()})"

    best = None
    best_score = None
    for u in candidates:
        scaled = value / u.scale
        if scaled == 0:
            score = 0
        else:
            # distance from log10(scaled) to 0 == how close scaled is to 1.
            # This is the whole heuristic: "which unit makes this number
            # closest to a single-digit magnitude" — simple, deterministic,
            # and easy to explain, even if a human might sometimes prefer
            # a different 'conventional' unit (see README, Known Limitations).
            score = abs(math.log10(abs(scaled)))
        if best_score is None or score < best_score:
            best, best_score = u, score

    scaled = value / best.scale
    shown = int(scaled) if float(scaled).is_integer() else round(scaled, 4)
    return f"{shown} {best.name}"


class Interpreter:
    def __init__(self, sym, output=None):
        self.sym = sym  # SymbolTable from the semantic analyzer (has units + functions)
        self.env = Env()
        self.output = output if output is not None else []

    def run(self, program: Program):
        for decl in program.decls:
            if isinstance(decl, FuncDecl) or decl.__class__.__name__ == "UnitDecl":
                continue
            self._exec_stmt(decl)
        return self.output

    # -- statements -----------------------------------------------------
    def _exec_stmt(self, node):
        if isinstance(node, Block):
            self.env.push()
            for s in node.stmts:
                self._exec_stmt(s)
            self.env.pop()
        elif isinstance(node, DeclStmt):
            self.env.declare(node.name, self._eval(node.expr))
        elif isinstance(node, AssignStmt):
            self.env.set(node.name, self._eval(node.expr))
        elif isinstance(node, IfStmt):
            if self._eval(node.cond):
                self._exec_stmt(node.then_branch)
            elif node.else_branch:
                self._exec_stmt(node.else_branch)
        elif isinstance(node, WhileStmt):
            while self._eval(node.cond):
                self._exec_stmt(node.body)
        elif isinstance(node, ForStmt):
            self.env.push()
            if node.init:
                self._exec_stmt(node.init)
            while self._eval(node.cond):
                self._exec_stmt(node.body)
                self._exec_stmt(node.step)
            self.env.pop()
        elif isinstance(node, ReturnStmt):
            raise ReturnSignal(self._eval(node.expr) if node.expr else None)
        elif isinstance(node, PrintStmt):
            val = self._eval(node.expr)
            dim = node.expr.dim
            if isinstance(val, bool):
                self.output.append("true" if val else "false")
            else:
                self.output.append(smart_format(val, dim, self.sym))
        elif isinstance(node, ExprStmt):
            self._eval(node.expr)

    # -- expressions -----------------------------------------------------
    def _eval(self, node):
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, BoolLit):
            return node.value
        if isinstance(node, Identifier):
            unit = self.sym.lookup_unit(node.name)
            try:
                return self.env.get(node.name)
            except NameError:
                if unit is not None:
                    return unit.scale
                raise
        if isinstance(node, UnaryOp):
            v = self._eval(node.operand)
            return -v if node.op == "-" else (not v)
        if isinstance(node, BinaryOp):
            l = self._eval(node.left)
            r = self._eval(node.right)
            op = node.op
            if op == "+": return l + r
            if op == "-": return l - r
            if op == "*": return l * r
            if op == "/": return l / r
            if op == "^": return l ** r
            if op == "<": return l < r
            if op == "<=": return l <= r
            if op == ">": return l > r
            if op == ">=": return l >= r
            if op == "==": return l == r
            if op == "!=": return l != r
            if op == "&&": return bool(l) and bool(r)
            if op == "||": return bool(l) or bool(r)
            raise ValueError(f"unknown operator {op}")
        if isinstance(node, Call):
            func = self.sym.functions[node.callee]
            args = [self._eval(a) for a in node.args]
            self.env.push()
            for name, val in zip(func.params, args):
                self.env.declare(name, val)
            result = None
            try:
                for s in func.body.stmts:
                    self._exec_stmt(s)
            except ReturnSignal as r:
                result = r.value
            self.env.pop()
            return result
        raise ValueError(f"Interpreter: unhandled node {type(node).__name__}")
