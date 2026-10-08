"""
Tree-walking interpreter - the REFERENCE ("oracle") implementation.

It executes the AST directly, using the same Quantity arithmetic as the
VM, but with its own scoping and control-flow code. The test-suite runs
every example program through both this interpreter and the compiled
bytecode VM (optimised and unoptimised) and requires identical output;
that is how the code generator and optimizer are validated without
hand-writing expected output for every program.
"""

from quantity import Quantity, RuntimeErr, apply_binary, apply_unary, truthy
from display import format_quantity
from ast_nodes import (
    Program, FuncDecl, UnitDecl, Block, DeclStmt, AssignStmt, IfStmt,
    WhileStmt, ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp,
    UnaryOp, Call, NumberLit, BoolLit, Identifier,
)


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class _Frame:
    def __init__(self):
        self.scopes = [{}]


class Interpreter:
    MAX_STEPS = 5_000_000
    MAX_DEPTH = 200

    def __init__(self, functions, units, used_units=None, echo=False):
        self.functions = functions
        self.units = units
        self.used = used_units or set()
        self.unit_values = {n: Quantity(u.scale, u.dim) for n, u in units.items()}
        self.globals = _Frame()
        self.output = []
        self.echo = echo
        self.steps = 0
        self.depth = 0

    def run(self, program: Program):
        for decl in program.decls:
            if isinstance(decl, (FuncDecl, UnitDecl)):
                continue
            self._exec(decl, self.globals)
        return self.output

    # -- variable access ----------------------------------------------
    def _find(self, name, frame):
        for scope in reversed(frame.scopes):
            if name in scope:
                return scope
        if frame is not self.globals:
            for scope in reversed(self.globals.scopes):
                if name in scope:
                    return scope
        return None

    def _get(self, name, frame):
        scope = self._find(name, frame)
        if scope is not None:
            return scope[name]
        if name in self.unit_values:
            return self.unit_values[name]
        raise RuntimeErr(f"undefined name '{name}'")

    # -- statements -----------------------------------------------------
    def _tick(self):
        self.steps += 1
        if self.steps > self.MAX_STEPS:
            raise RuntimeErr("step limit exceeded (possible infinite loop)")

    def _exec(self, node, frame):
        self._tick()
        if isinstance(node, Block):
            frame.scopes.append({})
            try:
                for s in node.stmts:
                    self._exec(s, frame)
            finally:
                frame.scopes.pop()
        elif isinstance(node, DeclStmt):
            frame.scopes[-1][node.name] = self._eval(node.expr, frame)
        elif isinstance(node, AssignStmt):
            value = self._eval(node.expr, frame)
            scope = self._find(node.name, frame)
            if scope is None:
                raise RuntimeErr(f"assignment to undeclared variable '{node.name}'")
            scope[node.name] = value
        elif isinstance(node, IfStmt):
            if truthy(self._eval(node.cond, frame)):
                self._exec(node.then_branch, frame)
            elif node.else_branch is not None:
                self._exec(node.else_branch, frame)
        elif isinstance(node, WhileStmt):
            while truthy(self._eval(node.cond, frame)):
                self._exec(node.body, frame)
        elif isinstance(node, ForStmt):
            frame.scopes.append({})
            try:
                if node.init is not None:
                    self._exec(node.init, frame)
                while truthy(self._eval(node.cond, frame)):
                    self._exec(node.body, frame)
                    self._exec(node.step, frame)
            finally:
                frame.scopes.pop()
        elif isinstance(node, ReturnStmt):
            raise _Return(self._eval(node.expr, frame) if node.expr is not None else None)
        elif isinstance(node, PrintStmt):
            v = self._eval(node.expr, frame)
            if isinstance(v, bool):
                line = "true" if v else "false"
            elif isinstance(v, Quantity):
                line = format_quantity(v, self.units, self.used)
            else:
                raise RuntimeErr("cannot print: a function that returns no value was used")
            self.output.append(line)
            if self.echo:
                print(line)
        elif isinstance(node, ExprStmt):
            self._eval(node.expr, frame)
        else:
            raise RuntimeErr(f"unhandled statement {type(node).__name__}")

    # -- expressions -----------------------------------------------------
    def _eval(self, node, frame):
        self._tick()
        if isinstance(node, NumberLit):
            return Quantity(float(node.value))
        if isinstance(node, BoolLit):
            return bool(node.value)
        if isinstance(node, Identifier):
            return self._get(node.name, frame)
        if isinstance(node, UnaryOp):
            return apply_unary(node.op, self._eval(node.operand, frame))
        if isinstance(node, BinaryOp):
            left = self._eval(node.left, frame)
            right = self._eval(node.right, frame)
            return apply_binary(node.op, left, right)
        if isinstance(node, Call):
            func = self.functions[node.callee]
            args = [self._eval(a, frame) for a in node.args]
            if self.depth + 1 > self.MAX_DEPTH:
                raise RuntimeErr("maximum call depth exceeded (runaway recursion?)")
            callee = _Frame()
            callee.scopes[0].update(zip(func.params, args))
            self.depth += 1
            try:
                self._exec(func.body, callee)
            except _Return as r:
                return r.value
            finally:
                self.depth -= 1
            return None
        raise RuntimeErr(f"unhandled expression {type(node).__name__}")
