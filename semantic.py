"""
Semantic analyzer for UnitLang - the dimensional type checker.

Walks the AST and computes a Dimension for every expression bottom-up:

    literal / true / false      -> dimensionless
    identifier                  -> declared dimension, or a unit's own
    a + b, a - b                -> dims must match (a literal 0 adapts)
    a * b / a / b               -> exponents add / subtract
    a ^ n                       -> n must be an integer literal
    comparisons                 -> dims must match; result dimensionless
    conditions, && || !         -> operands must be dimensionless

Features beyond a basic checker (the project's novelty):

  1. `unit NAME = expr;` declarations are evaluated here at compile time
     (dimension AND scale factor) and registered in the symbol table.
  2. DIMENSION-POLYMORPHIC FUNCTIONS. Parameters have no declared type.
     Each distinct tuple of argument dimensions at a call site creates an
     "instance" of the function: the body is re-checked with the
     parameters bound to those dimensions, and the return dimension is
     inferred. speed(100 * m, 9.58 * s) and speed(5 * kg, 2 * kg) are both
     fine, each with its own inferred result.
  3. Diagnostics name the physical dimensions involved, suggest fixes,
     and offer "did you mean ...?" for misspelt names.

Rules that keep the language unambiguous: a unit name cannot be reused as
a variable name, and a name cannot be redeclared inside the same function
(no shadowing within a frame).
"""

import difflib

from dimension import Dimension, DIMENSIONLESS
from symtab import SymbolTable
from ast_nodes import (
    Program, FuncDecl, UnitDecl, Block, DeclStmt, AssignStmt, IfStmt,
    WhileStmt, ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp,
    UnaryOp, Call, NumberLit, BoolLit, Identifier,
)


class SemanticError(Exception):
    def __init__(self, message, line):
        super().__init__(f"Semantic error at line {line}: {message}")
        self.line = line
        self.message = message


def _const_int(node):
    """Value of an integer literal (optionally negated), else None."""
    if isinstance(node, NumberLit) and float(node.value).is_integer():
        return int(node.value)
    if (isinstance(node, UnaryOp) and node.op == "-"
            and isinstance(node.operand, NumberLit)
            and float(node.operand.value).is_integer()):
        return -int(node.operand.value)
    return None


def _is_zero(node):
    return isinstance(node, NumberLit) and node.value == 0


class SemanticAnalyzer:
    def __init__(self):
        self.sym = SymbolTable()
        self.errors = []
        self.warnings = []
        self.instances = {}        # (func name, arg dims) -> state dict
        self.instance_log = []     # (name, arg dims, return dim) in order
        self.called = set()
        self._ret_stack = []
        self._ctx_stack = []
        self._frame_base = 0

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def analyze(self, program: Program):
        for decl in program.decls:
            if isinstance(decl, FuncDecl):
                if decl.name in self.sym.functions:
                    self._report(SemanticError(
                        f"function '{decl.name}' is already defined", decl.line))
                else:
                    self.sym.functions[decl.name] = decl

        for decl in program.decls:
            if isinstance(decl, FuncDecl):
                continue            # bodies are checked per call site
            try:
                if isinstance(decl, UnitDecl):
                    self._check_unit_decl(decl)
                else:
                    self._check_stmt(decl)
            except SemanticError as e:
                self._report(e)
                self._recover(decl)

        for name in self.sym.functions:
            if name not in self.called:
                self.warnings.append(
                    f"warning: function '{name}' is never called, so its body was not type-checked")
        return self.errors

    # ------------------------------------------------------------------
    # error helpers
    # ------------------------------------------------------------------
    def _report(self, err: SemanticError):
        msg = str(err)
        if self._ctx_stack:
            msg += f"   [while checking {self._ctx_stack[-1]}]"
        self.errors.append(msg)

    def _recover(self, decl):
        """After a failed declaration, still register the name (as a plain
        number) so later uses don't produce a cascade of follow-up errors."""
        if (isinstance(decl, DeclStmt)
                and self.sym.lookup_var(decl.name) is None
                and decl.name not in self.sym.units):
            self.sym.declare_var(decl.name, DIMENSIONLESS)

    def _suggest(self, name):
        pool = (self.sym.all_var_names() | set(self.sym.units)
                | set(self.sym.functions))
        m = difflib.get_close_matches(name, pool, n=1, cutoff=0.6)
        return f" - did you mean '{m[0]}'?" if m else ""

    @staticmethod
    def _describe(dim: Dimension) -> str:
        return "a plain number" if dim.is_dimensionless() else dim.pretty()

    def _mismatch(self, left, right, op):
        a, b = self._describe(left), self._describe(right)
        verb = "compare" if op in ("<", "<=", ">", ">=", "==", "!=") else f"use '{op}' on"
        if left.is_dimensionless() or right.is_dimensionless():
            return (f"cannot {verb} {a} and {b}. A bare number has no unit - "
                    f"attach one (for example 5 * m) or fix the other operand.")
        return (f"cannot {verb} {a} and {b}: they are different physical "
                f"dimensions, so no unit conversion can reconcile them.")

    # ------------------------------------------------------------------
    # declarations
    # ------------------------------------------------------------------
    def _declare(self, name, dim, line):
        if name in self.sym.units:
            raise SemanticError(
                f"'{name}' is a unit name and cannot be used as a variable name", line)
        for scope in self.sym.scopes[self._frame_base:]:
            if name in scope:
                raise SemanticError(
                    f"'{name}' is already declared in this scope "
                    f"(UnitLang does not allow shadowing)", line)
        self.sym.declare_var(name, dim)

    def _use_unit(self, name):
        self.sym.used_units.add(name)
        return self.sym.units[name]

    def _check_unit_decl(self, decl: UnitDecl):
        if decl.name in self.sym.units:
            raise SemanticError(f"unit '{decl.name}' is already defined", decl.line)
        if self.sym.lookup_var(decl.name) is not None:
            raise SemanticError(
                f"'{decl.name}' is already a variable and cannot also be a unit", decl.line)
        dim, scale = self._eval_unit_expr(decl.expr)
        if scale <= 0:
            raise SemanticError("a unit's scale factor must be positive", decl.line)
        self.sym.define_unit(decl.name, dim, scale)

    def _eval_unit_expr(self, node):
        """(Dimension, scale-in-base-units) of a unit-defining expression."""
        if isinstance(node, NumberLit):
            return DIMENSIONLESS, node.value
        if isinstance(node, Identifier):
            if node.name not in self.sym.units:
                raise SemanticError(
                    f"'{node.name}' is not a known unit{self._suggest(node.name)}", node.line)
            u = self._use_unit(node.name)
            return u.dim, u.scale
        if isinstance(node, BinaryOp):
            ld, ls = self._eval_unit_expr(node.left)
            if node.op == "^":
                n = _const_int(node.right)
                if n is None:
                    raise SemanticError("unit exponent must be an integer literal", node.line)
                return ld.pow(n), ls ** n
            rd, rs = self._eval_unit_expr(node.right)
            if node.op == "*":
                return ld * rd, ls * rs
            if node.op == "/":
                if rs == 0:
                    raise SemanticError("division by zero in unit definition", node.line)
                return ld / rd, ls / rs
            if node.op in ("+", "-"):
                if ld != rd:
                    raise SemanticError(
                        f"cannot combine {self._describe(ld)} and {self._describe(rd)} "
                        f"with '{node.op}' inside a unit definition", node.line)
                return ld, (ls + rs if node.op == "+" else ls - rs)
        raise SemanticError("invalid unit expression", getattr(node, "line", 0))

    # ------------------------------------------------------------------
    # statements
    # ------------------------------------------------------------------
    def _check_stmt(self, node):
        if isinstance(node, Block):
            self._check_block(node)
        elif isinstance(node, DeclStmt):
            dim = self._check_expr(node.expr)
            self._declare(node.name, dim, node.line)
        elif isinstance(node, AssignStmt):
            entry = self.sym.lookup_var(node.name)
            if entry is None:
                if node.name in self.sym.units:
                    raise SemanticError(f"cannot assign to unit '{node.name}'", node.line)
                raise SemanticError(
                    f"assignment to undeclared variable '{node.name}'{self._suggest(node.name)}",
                    node.line)
            dim = self._check_expr(node.expr)
            if dim != entry.dim and not (_is_zero(node.expr)):
                raise SemanticError(
                    f"cannot assign {self._describe(dim)} to '{node.name}', "
                    f"which was declared as {self._describe(entry.dim)}", node.line)
        elif isinstance(node, IfStmt):
            self._check_cond(node.cond, node.line)
            self._check_stmt(node.then_branch)
            if node.else_branch:
                self._check_stmt(node.else_branch)
        elif isinstance(node, WhileStmt):
            self._check_cond(node.cond, node.line)
            self._check_stmt(node.body)
        elif isinstance(node, ForStmt):
            self.sym.push_scope()
            try:
                if node.init:
                    self._check_stmt(node.init)
                self._check_cond(node.cond, node.line)
                self._check_stmt(node.step)
                self._check_stmt(node.body)
            finally:
                self.sym.pop_scope()
        elif isinstance(node, ReturnStmt):
            if not self._ret_stack:
                raise SemanticError("'return' outside of a function", node.line)
            if node.expr is not None:
                self._ret_stack[-1].append(self._check_expr(node.expr))
        elif isinstance(node, PrintStmt):
            self._check_expr(node.expr)
        elif isinstance(node, ExprStmt):
            self._check_expr(node.expr)
        else:
            raise SemanticError(
                f"unhandled statement {type(node).__name__}", getattr(node, "line", 0))

    def _check_block(self, block: Block):
        """Check each statement independently so one bad statement does not
        hide the errors after it."""
        self.sym.push_scope()
        try:
            for s in block.stmts:
                try:
                    self._check_stmt(s)
                except SemanticError as e:
                    self._report(e)
                    self._recover(s)
        finally:
            self.sym.pop_scope()

    def _check_cond(self, expr, line):
        dim = self._check_expr(expr)
        if not dim.is_dimensionless():
            raise SemanticError(
                f"a condition must be a plain number or boolean, but this is {dim.pretty()}. "
                f"Compare it with something (e.g. x > 0 * {self._unit_hint(dim)}).", line)

    def _unit_hint(self, dim):
        for u in self.sym.units.values():
            if u.dim == dim and u.scale == 1.0:
                return u.name
        return "unit"

    # ------------------------------------------------------------------
    # expressions
    # ------------------------------------------------------------------
    def _check_expr(self, node) -> Dimension:
        if isinstance(node, (NumberLit, BoolLit)):
            node.dim = DIMENSIONLESS
            return node.dim
        if isinstance(node, Identifier):
            var = self.sym.lookup_var(node.name)
            if var is not None:
                node.dim = var.dim
            elif node.name in self.sym.units:
                node.dim = self._use_unit(node.name).dim
            else:
                raise SemanticError(
                    f"undeclared identifier '{node.name}'{self._suggest(node.name)}", node.line)
            return node.dim
        if isinstance(node, UnaryOp):
            dim = self._check_expr(node.operand)
            if node.op == "!" and not dim.is_dimensionless():
                raise SemanticError(
                    f"'!' needs a plain number or boolean, got {dim.pretty()}", node.line)
            node.dim = dim if node.op == "-" else DIMENSIONLESS
            return node.dim
        if isinstance(node, BinaryOp):
            return self._check_binary(node)
        if isinstance(node, Call):
            return self._check_call(node)
        raise SemanticError(
            f"unhandled expression {type(node).__name__}", getattr(node, "line", 0))

    def _check_binary(self, node: BinaryOp) -> Dimension:
        left = self._check_expr(node.left)
        right = self._check_expr(node.right)
        op = node.op

        if op in ("+", "-"):
            if left == right:
                node.dim = left
            elif _is_zero(node.left):
                node.dim = right
            elif _is_zero(node.right):
                node.dim = left
            else:
                raise SemanticError(self._mismatch(left, right, op), node.line)
        elif op == "*":
            node.dim = left * right
        elif op == "/":
            node.dim = left / right
        elif op == "^":
            n = _const_int(node.right)
            if n is None:
                raise SemanticError(
                    "an exponent must be an integer literal (for example s ^ 2)", node.line)
            node.dim = left.pow(n)
        elif op in ("<", "<=", ">", ">=", "==", "!="):
            if left != right and not (_is_zero(node.left) or _is_zero(node.right)):
                raise SemanticError(self._mismatch(left, right, op), node.line)
            node.dim = DIMENSIONLESS
        elif op in ("&&", "||"):
            for d in (left, right):
                if not d.is_dimensionless():
                    raise SemanticError(
                        f"'{op}' needs plain numbers or booleans, got {d.pretty()}", node.line)
            node.dim = DIMENSIONLESS
        else:
            raise SemanticError(f"unknown operator '{op}'", node.line)
        return node.dim

    # ------------------------------------------------------------------
    # calls: dimension-polymorphic instantiation
    # ------------------------------------------------------------------
    def _check_call(self, node: Call) -> Dimension:
        func = self.sym.functions.get(node.callee)
        if func is None:
            raise SemanticError(
                f"call to undefined function '{node.callee}'{self._suggest(node.callee)}",
                node.line)
        if len(node.args) != len(func.params):
            raise SemanticError(
                f"'{node.callee}' expects {len(func.params)} argument(s), got {len(node.args)}",
                node.line)
        arg_dims = tuple(self._check_expr(a) for a in node.args)
        node.dim = self._instantiate(func, arg_dims)
        return node.dim

    def _instantiate(self, func: FuncDecl, arg_dims):
        self.called.add(func.name)
        key = (func.name, arg_dims)
        inst = self.instances.get(key)
        if inst is not None:
            if inst["state"] == "done":
                return inst["ret"]
            # recursive call while this instance is still being checked:
            # use the first return dimension seen so far
            return inst["rets"][0] if inst["rets"] else DIMENSIONLESS

        inst = {"state": "active", "rets": [], "ret": DIMENSIONLESS}
        self.instances[key] = inst
        shown = ", ".join("number" if d.is_dimensionless() else d.pretty() for d in arg_dims)
        ctx = f"'{func.name}' called with ({shown})"

        saved_scopes, saved_base = self.sym.scopes, self._frame_base
        self.sym.scopes = [saved_scopes[0], {}]      # globals + fresh frame
        self._frame_base = 1
        self._ret_stack.append(inst["rets"])
        self._ctx_stack.append(ctx)
        try:
            try:
                for p, d in zip(func.params, arg_dims):
                    self._declare(p, d, func.line)
                self._check_block(func.body)
            finally:
                self.sym.scopes, self._frame_base = saved_scopes, saved_base
                self._ret_stack.pop()
                self._ctx_stack.pop()
        except SemanticError:
            inst["state"] = "done"
            raise

        rets = inst["rets"]
        ret = rets[0] if rets else DIMENSIONLESS
        inst["ret"], inst["state"] = ret, "done"
        self.instance_log.append((func.name, arg_dims, ret))
        if len(set(rets)) > 1:
            kinds = " vs ".join(sorted({self._describe(r) for r in rets}))
            raise SemanticError(
                f"'{func.name}' returns different dimensions on different paths ({kinds})",
                func.line)
        return ret
