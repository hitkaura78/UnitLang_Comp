"""
IR generator: type-checked AST -> linear three-address code (TAC).

Every instruction is a 4-tuple (op, a1, a2, result):

    ("const",    value, None, "%t0")        literal into a temporary
    (<binop>,    a, b, "%t1")               + - * / ^ < <= > >= == != && ||
    ("unary-",   a, None, "%t2")            also "unary!"
    ("decl",     a, None, "name")           create a variable
    ("=",        a, None, "name")           assign an existing variable
    ("label",    None, None, "L0")  ("goto", None, None, "L0")
    ("if_false", a, None, "L0")
    ("print",    a, None, None)
    ("return",   a|None, None, None)
    ("call",     "f", (args...), "%t3")
    ("func_begin", "f", (params...), None)  ("func_end", "f", None, None)

Temporaries are named %t0, %t1, ... - the '%' can never appear in a user
identifier, so a temporary can never collide with a variable.

For code at top level the dimension of each temporary is recorded in
`self.dims` for display. Function bodies are dimension-polymorphic (one
body, several instances), so no single dimension is recorded inside them.
"""

from ast_nodes import (
    Program, FuncDecl, UnitDecl, Block, DeclStmt, AssignStmt, IfStmt,
    WhileStmt, ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp,
    UnaryOp, Call, NumberLit, BoolLit, Identifier,
)

BINARY_OPS = {"+", "-", "*", "/", "^", "<", "<=", ">", ">=", "==", "!=", "&&", "||"}


class IRGen:
    def __init__(self):
        self.code = []
        self.dims = {}
        self._temp_n = 0
        self._label_n = 0
        self._in_func = False

    def _temp(self, dim):
        name = f"%t{self._temp_n}"
        self._temp_n += 1
        if not self._in_func and dim is not None:
            self.dims[name] = dim
        return name

    def _label(self):
        name = f"L{self._label_n}"
        self._label_n += 1
        return name

    def _emit(self, *instr):
        self.code.append(instr)

    # ------------------------------------------------------------------
    def generate(self, program: Program):
        for decl in program.decls:
            if isinstance(decl, FuncDecl):
                self._in_func = True
                self._emit("func_begin", decl.name, tuple(decl.params), None)
                for s in decl.body.stmts:
                    self._gen_stmt(s)
                self._emit("func_end", decl.name, None, None)
                self._in_func = False
            elif isinstance(decl, UnitDecl):
                continue            # compile-time only
            else:
                self._gen_stmt(decl)
        return self.code

    # ------------------------------------------------------------------
    def _gen_stmt(self, node):
        if isinstance(node, Block):
            for s in node.stmts:
                self._gen_stmt(s)
        elif isinstance(node, DeclStmt):
            val = self._gen_expr(node.expr)
            self._emit("decl", val, None, node.name)
            if not self._in_func:
                self.dims[node.name] = node.expr.dim
        elif isinstance(node, AssignStmt):
            val = self._gen_expr(node.expr)
            self._emit("=", val, None, node.name)
        elif isinstance(node, IfStmt):
            cond = self._gen_expr(node.cond)
            else_l, end_l = self._label(), self._label()
            self._emit("if_false", cond, None, else_l)
            self._gen_stmt(node.then_branch)
            self._emit("goto", None, None, end_l)
            self._emit("label", None, None, else_l)
            if node.else_branch:
                self._gen_stmt(node.else_branch)
            self._emit("label", None, None, end_l)
        elif isinstance(node, WhileStmt):
            start_l, end_l = self._label(), self._label()
            self._emit("label", None, None, start_l)
            cond = self._gen_expr(node.cond)
            self._emit("if_false", cond, None, end_l)
            self._gen_stmt(node.body)
            self._emit("goto", None, None, start_l)
            self._emit("label", None, None, end_l)
        elif isinstance(node, ForStmt):
            if node.init:
                self._gen_stmt(node.init)
            start_l, end_l = self._label(), self._label()
            self._emit("label", None, None, start_l)
            cond = self._gen_expr(node.cond)
            self._emit("if_false", cond, None, end_l)
            self._gen_stmt(node.body)
            self._gen_stmt(node.step)
            self._emit("goto", None, None, start_l)
            self._emit("label", None, None, end_l)
        elif isinstance(node, ReturnStmt):
            val = self._gen_expr(node.expr) if node.expr is not None else None
            self._emit("return", val, None, None)
        elif isinstance(node, PrintStmt):
            self._emit("print", self._gen_expr(node.expr), None, None)
        elif isinstance(node, ExprStmt):
            self._gen_expr(node.expr)
        else:
            raise ValueError(f"IRGen: unhandled statement {type(node).__name__}")

    def _gen_expr(self, node):
        if isinstance(node, NumberLit):
            t = self._temp(node.dim)
            self._emit("const", float(node.value), None, t)
            return t
        if isinstance(node, BoolLit):
            t = self._temp(node.dim)
            self._emit("const", bool(node.value), None, t)
            return t
        if isinstance(node, Identifier):
            return node.name
        if isinstance(node, UnaryOp):
            v = self._gen_expr(node.operand)
            t = self._temp(node.dim)
            self._emit(f"unary{node.op}", v, None, t)
            return t
        if isinstance(node, BinaryOp):
            l = self._gen_expr(node.left)
            r = self._gen_expr(node.right)
            t = self._temp(node.dim)
            self._emit(node.op, l, r, t)
            return t
        if isinstance(node, Call):
            args = tuple(self._gen_expr(a) for a in node.args)
            t = self._temp(node.dim)
            self._emit("call", node.callee, args, t)
            return t
        raise ValueError(f"IRGen: unhandled expression {type(node).__name__}")

    # ------------------------------------------------------------------
    def dump(self, code=None):
        code = self.code if code is None else code
        return dump_tac(code, self.dims)


def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, (tuple, list)):
        return ", ".join(_fmt(i) for i in x)
    return repr(x) if not isinstance(x, str) else x


def dump_tac(code, dims=None):
    dims = dims or {}
    lines = []
    for op, a1, a2, res in code:
        note = ""
        d = dims.get(res)
        if d is not None and not d.is_dimensionless():
            note = f"   # {d.pretty()}"
        if op == "label":
            lines.append(f"{res}:")
        elif op == "goto":
            lines.append(f"    goto {res}")
        elif op == "if_false":
            lines.append(f"    if_false {_fmt(a1)} goto {res}")
        elif op == "const":
            lines.append(f"    {res} = const {_fmt(a1)}{note}")
        elif op == "decl":
            lines.append(f"    declare {res} = {_fmt(a1)}{note}")
        elif op == "=":
            lines.append(f"    {res} = {_fmt(a1)}")
        elif op == "func_begin":
            lines.append(f"func {a1}({_fmt(a2)}):")
        elif op == "func_end":
            lines.append(f"end {a1}")
        elif op == "print":
            lines.append(f"    print {_fmt(a1)}")
        elif op == "return":
            lines.append(f"    return {_fmt(a1)}".rstrip())
        elif op == "call":
            lines.append(f"    {res} = call {a1}({_fmt(a2)})")
        elif op.startswith("unary"):
            lines.append(f"    {res} = {op[5:]}{_fmt(a1)}{note}")
        else:
            lines.append(f"    {res} = {_fmt(a1)} {op} {_fmt(a2)}{note}")
    return "\n".join(lines)
