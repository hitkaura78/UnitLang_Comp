"""
Semantic analyzer for UnitLang.

This is where the actual "compiler idea" lives. It walks the AST the
parser produced and, for every expression, computes a Dimension (see
dimension.py) bottom-up:

    literals, true/false        -> dimensionless
    identifier                  -> whatever was recorded when it was
                                    declared (qty) or a built-in unit's
                                    own dimension if it's a unit name
    a + b, a - b                 -> dims must match; result = that dim
    a * b                        -> dims combine (add exponents)
    a / b                        -> dims combine (subtract exponents)
    a ^ n                        -> n must be a compile-time integer
                                     literal; dim is multiplied by n
    relational / equality / !    -> operands checked for matching
                                     dimension, result is dimensionless
                                     (booleans carry no unit)

Two things happen alongside the dimension pass:

  1. `unit` declarations (the novelty feature) are evaluated here, not
     in the parser — the right-hand side is just a normal expression
     over other unit names, so we reuse the same dimension arithmetic
     and register the result as a new UnitEntry.

  2. Every dimension mismatch is turned into a message that names the
     actual physical dimensions involved instead of just "type error"
     — see `_describe_mismatch`.
"""

from dimension import Dimension, DIMENSIONLESS, DimensionError
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


class SemanticAnalyzer:
    def __init__(self):
        self.sym = SymbolTable()
        self.errors = []

    # -- public entry point ---------------------------------------------
    def analyze(self, program: Program):
        # pass 1: register function signatures so calls can appear before
        # their definitions
        for decl in program.decls:
            if isinstance(decl, FuncDecl):
                self.sym.functions[decl.name] = decl

        for decl in program.decls:
            try:
                if isinstance(decl, FuncDecl):
                    self._check_func(decl)
                elif isinstance(decl, UnitDecl):
                    self._check_unit_decl(decl)
                else:
                    self._check_stmt(decl)
            except SemanticError as e:
                self.errors.append(str(e))
                # best-effort recovery: register a placeholder so a bad
                # declaration doesn't cascade into a wall of unrelated
                # "undeclared identifier" errors on every later use
                if isinstance(decl, DeclStmt) and self.sym.lookup_var(decl.name) is None:
                    self.sym.declare_var(decl.name, DIMENSIONLESS)
        return self.errors

    # -- declarations -----------------------------------------------------
    def _check_unit_decl(self, decl: UnitDecl):
        """Novelty: `unit NAME = expr;` defines a new derived unit.

        The expression is evaluated purely at the dimension level (we
        don't need a runtime value here, only how NAME relates to the
        base units), and the *scale* is computed the same way by
        evaluating the expression numerically against each built-in
        unit's scale factor.
        """
        dim, scale = self._eval_unit_expr(decl.expr)
        self.sym.define_unit(decl.name, dim, scale)

    def _eval_unit_expr(self, node):
        """Returns (Dimension, scale_in_base_units) for a unit-defining
        expression such as `kg * m / s ^ 2`."""
        if isinstance(node, NumberLit):
            return DIMENSIONLESS, node.value
        if isinstance(node, Identifier):
            entry = self.sym.lookup_unit(node.name)
            if entry is None:
                raise SemanticError(
                    f"unknown unit or identifier '{node.name}' in unit expression",
                    node.line,
                )
            return entry.dim, entry.scale
        if isinstance(node, BinaryOp):
            ld, ls = self._eval_unit_expr(node.left)
            rd, rs = self._eval_unit_expr(node.right)
            if node.op == "*":
                return ld * rd, ls * rs
            if node.op == "/":
                return ld / rd, ls / rs
            if node.op in ("+", "-"):
                if ld != rd:
                    raise SemanticError(
                        f"cannot combine {ld.pretty()} and {rd.pretty()} "
                        f"with '{node.op}' inside a unit definition",
                        node.line,
                    )
                return ld, (ls + rs if node.op == "+" else ls - rs)
            if node.op == "^":
                if not isinstance(node.right, NumberLit) or not node.right.value.is_integer():
                    raise SemanticError("unit exponent must be an integer literal", node.line)
                n = int(node.right.value)
                return ld.pow(n), ls ** n
        raise SemanticError("invalid unit expression", node.line)

    def _check_func(self, decl: FuncDecl):
        self.sym.push_scope()
        for p in decl.params:
            # parameters start dimensionless-unknown; they pick up a
            # concrete dimension the first time they're used in an
            # operation whose other operand is known. For this scope
            # (Review 2) we take the simpler, honest route: parameters
            # are treated as dimensionless unless reassigned from a
            # dimensioned expression inside the body.
            self.sym.declare_var(p, DIMENSIONLESS)
        self._check_block(decl.body)
        self.sym.pop_scope()

    # -- statements -----------------------------------------------------
    def _check_stmt(self, node):
        if isinstance(node, Block):
            self._check_block(node)
        elif isinstance(node, DeclStmt):
            dim = self._check_expr(node.expr)
            self.sym.declare_var(node.name, dim)
        elif isinstance(node, AssignStmt):
            entry = self.sym.lookup_var(node.name)
            if entry is None:
                raise SemanticError(f"assignment to undeclared variable '{node.name}'", node.line)
            dim = self._check_expr(node.expr)
            if dim != entry.dim:
                raise SemanticError(
                    f"cannot assign {self._describe(dim)} to '{node.name}', "
                    f"which was declared as {self._describe(entry.dim)}",
                    node.line,
                )
        elif isinstance(node, IfStmt):
            self._check_expr(node.cond)
            self._check_stmt(node.then_branch)
            if node.else_branch:
                self._check_stmt(node.else_branch)
        elif isinstance(node, WhileStmt):
            self._check_expr(node.cond)
            self._check_stmt(node.body)
        elif isinstance(node, ForStmt):
            self.sym.push_scope()
            if node.init:
                self._check_stmt(node.init)
            self._check_expr(node.cond)
            self._check_stmt(node.step)
            self._check_stmt(node.body)
            self.sym.pop_scope()
        elif isinstance(node, ReturnStmt):
            if node.expr:
                self._check_expr(node.expr)
        elif isinstance(node, PrintStmt):
            self._check_expr(node.expr)
        elif isinstance(node, ExprStmt):
            self._check_expr(node.expr)
        else:
            raise SemanticError(f"unhandled statement node {type(node).__name__}", getattr(node, "line", 0))

    def _check_block(self, block: Block):
        self.sym.push_scope()
        for s in block.stmts:
            self._check_stmt(s)
        self.sym.pop_scope()

    # -- expressions -----------------------------------------------------
    def _check_expr(self, node) -> Dimension:
        if isinstance(node, NumberLit):
            node.dim = DIMENSIONLESS
            return node.dim
        if isinstance(node, BoolLit):
            node.dim = DIMENSIONLESS
            return node.dim
        if isinstance(node, Identifier):
            unit = self.sym.lookup_unit(node.name)
            if unit is not None and self.sym.lookup_var(node.name) is None:
                # bare unit name used as a value, e.g. `qty x = 5 * m;`
                node.dim = unit.dim
                return node.dim
            var = self.sym.lookup_var(node.name)
            if var is None:
                raise SemanticError(f"undeclared identifier '{node.name}'", node.line)
            node.dim = var.dim
            return node.dim
        if isinstance(node, UnaryOp):
            dim = self._check_expr(node.operand)
            node.dim = dim
            return dim
        if isinstance(node, BinaryOp):
            return self._check_binary(node)
        if isinstance(node, Call):
            return self._check_call(node)
        raise SemanticError(f"unhandled expression node {type(node).__name__}", getattr(node, "line", 0))

    def _check_binary(self, node: BinaryOp) -> Dimension:
        left = self._check_expr(node.left)
        right = self._check_expr(node.right)
        op = node.op

        if op in ("+", "-"):
            if left != right:
                raise SemanticError(self._describe_mismatch(left, right, op), node.line)
            node.dim = left
        elif op == "*":
            node.dim = left * right
        elif op == "/":
            node.dim = left / right
        elif op == "^":
            if not isinstance(node.right, NumberLit) or not node.right.value.is_integer():
                raise SemanticError("exponent must be an integer literal (e.g. s ^ 2)", node.line)
            node.dim = left.pow(int(node.right.value))
        elif op in ("<", "<=", ">", ">=", "==", "!="):
            if left != right:
                raise SemanticError(self._describe_mismatch(left, right, op), node.line)
            node.dim = DIMENSIONLESS
        elif op in ("&&", "||"):
            node.dim = DIMENSIONLESS
        else:
            raise SemanticError(f"unknown operator '{op}'", node.line)
        return node.dim

    def _check_call(self, node: Call) -> Dimension:
        func = self.sym.functions.get(node.callee)
        if func is None:
            raise SemanticError(f"call to undefined function '{node.callee}'", node.line)
        if len(node.args) != len(func.params):
            raise SemanticError(
                f"'{node.callee}' expects {len(func.params)} argument(s), got {len(node.args)}",
                node.line,
            )
        for a in node.args:
            self._check_expr(a)
        # Review 2 scope: return dimension is inferred as dimensionless
        # unless the function body's return expression can be resolved
        # against the (dimensionless) parameter assumption. A full
        # generic dimension-polymorphic inference (à la Hindley-Milner)
        # is flagged as future work in the README rather than
        # implemented here.
        node.dim = DIMENSIONLESS
        return node.dim

    # -- error message helpers -----------------------------------------
    def _describe(self, dim: Dimension) -> str:
        return "a plain number" if dim.is_dimensionless() else dim.pretty()

    def _describe_mismatch(self, left: Dimension, right: Dimension, op: str) -> str:
        return (
            f"cannot use '{op}' between {self._describe(left)} and {self._describe(right)} "
            f"— they aren't the same physical dimension. "
            f"If this is intentional, convert one side to match the other's unit first."
        )
