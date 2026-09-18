"""
IR generator for UnitLang.

Produces linear three-address code (TAC) from a *type-checked* AST
(i.e. run this after SemanticAnalyzer.analyze() has succeeded, so
every expression node already has `.dim` filled in).

Each instruction is a simple tuple:

    ("op", arg1, arg2, result)

Temporaries are named t0, t1, ... . Every temporary's dimension is
recorded separately in `self.dims` so a later code-generation phase
(Phase 3) knows, for each TAC value, what physical dimension it
carries — the IR doesn't lose the information the semantic analyzer
worked out.

Control flow (if/while/for) lowers to labels and conditional jumps,
the standard TAC treatment, rather than staying structured.
"""

from ast_nodes import (
    Program, FuncDecl, UnitDecl, Block, DeclStmt, AssignStmt, IfStmt,
    WhileStmt, ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp,
    UnaryOp, Call, NumberLit, BoolLit, Identifier,
)


class IRGen:
    def __init__(self):
        self.code = []       # list of instruction tuples
        self.dims = {}        # temp/var name -> Dimension, for display only
        self._temp_n = 0
        self._label_n = 0

    def _temp(self, dim):
        name = f"t{self._temp_n}"
        self._temp_n += 1
        self.dims[name] = dim
        return name

    def _label(self):
        name = f"L{self._label_n}"
        self._label_n += 1
        return name

    def _emit(self, *instr):
        self.code.append(instr)

    # -- public entry point ---------------------------------------------
    def generate(self, program: Program):
        for decl in program.decls:
            if isinstance(decl, FuncDecl):
                self._emit("func_begin", decl.name, ",".join(decl.params), None)
                for s in decl.body.stmts:
                    self._gen_stmt(s)
                self._emit("func_end", decl.name, None, None)
            elif isinstance(decl, UnitDecl):
                continue  # compile-time only, nothing to emit
            else:
                self._gen_stmt(decl)
        return self.code

    # -- statements -----------------------------------------------------
    def _gen_stmt(self, node):
        if isinstance(node, Block):
            for s in node.stmts:
                self._gen_stmt(s)
        elif isinstance(node, DeclStmt):
            val = self._gen_expr(node.expr)
            self._emit("=", val, None, node.name)
            self.dims[node.name] = node.expr.dim
        elif isinstance(node, AssignStmt):
            val = self._gen_expr(node.expr)
            self._emit("=", val, None, node.name)
        elif isinstance(node, IfStmt):
            cond = self._gen_expr(node.cond)
            else_l = self._label()
            end_l = self._label()
            self._emit("if_false", cond, None, else_l)
            self._gen_stmt(node.then_branch)
            self._emit("goto", None, None, end_l)
            self._emit("label", None, None, else_l)
            if node.else_branch:
                self._gen_stmt(node.else_branch)
            self._emit("label", None, None, end_l)
        elif isinstance(node, WhileStmt):
            start_l = self._label()
            end_l = self._label()
            self._emit("label", None, None, start_l)
            cond = self._gen_expr(node.cond)
            self._emit("if_false", cond, None, end_l)
            self._gen_stmt(node.body)
            self._emit("goto", None, None, start_l)
            self._emit("label", None, None, end_l)
        elif isinstance(node, ForStmt):
            if node.init:
                self._gen_stmt(node.init)
            start_l = self._label()
            end_l = self._label()
            self._emit("label", None, None, start_l)
            cond = self._gen_expr(node.cond)
            self._emit("if_false", cond, None, end_l)
            self._gen_stmt(node.body)
            self._gen_stmt(node.step)
            self._emit("goto", None, None, start_l)
            self._emit("label", None, None, end_l)
        elif isinstance(node, ReturnStmt):
            val = self._gen_expr(node.expr) if node.expr else None
            self._emit("return", val, None, None)
        elif isinstance(node, PrintStmt):
            val = self._gen_expr(node.expr)
            self._emit("print", val, None, None)
        elif isinstance(node, ExprStmt):
            self._gen_expr(node.expr)

    # -- expressions -----------------------------------------------------
    def _gen_expr(self, node):
        if isinstance(node, NumberLit):
            t = self._temp(node.dim)
            self._emit("const", node.value, None, t)
            return t
        if isinstance(node, BoolLit):
            t = self._temp(node.dim)
            self._emit("const", node.value, None, t)
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
            arg_temps = [self._gen_expr(a) for a in node.args]
            t = self._temp(node.dim)
            self._emit("call", node.callee, ",".join(arg_temps), t)
            return t
        raise ValueError(f"IRGen: unhandled node {type(node).__name__}")

    # -- pretty printer ---------------------------------------------------
    def dump(self):
        lines = []
        for op, a1, a2, res in self.code:
            if op == "label":
                lines.append(f"{res}:")
            elif op == "goto":
                lines.append(f"    goto {res}")
            elif op == "if_false":
                lines.append(f"    if_false {a1} goto {res}")
            elif op == "const":
                dim = self.dims.get(res)
                lines.append(f"    {res} = const {a1}"
                              f"{'  # ' + dim.pretty() if dim and not dim.is_dimensionless() else ''}")
            elif op == "=":
                lines.append(f"    {res} = {a1}")
            elif op in ("func_begin",):
                lines.append(f"func {a1}({a2}):")
            elif op in ("func_end",):
                lines.append(f"end {a1}")
            elif op == "print":
                lines.append(f"    print {a1}")
            elif op == "return":
                lines.append(f"    return {a1 if a1 is not None else ''}")
            elif op == "call":
                lines.append(f"    {res} = call {a1}({a2})")
            elif op.startswith("unary"):
                lines.append(f"    {res} = {op[5:]}{a1}")
            else:
                dim = self.dims.get(res)
                suffix = f"  # {dim.pretty()}" if dim and not dim.is_dimensionless() else ""
                lines.append(f"    {res} = {a1} {op} {a2}{suffix}")
        return "\n".join(lines)
