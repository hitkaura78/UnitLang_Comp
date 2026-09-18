"""
UnitLang parser.

Straightforward recursive-descent parser, one function per grammar rule
from the Review 1 EBNF, plus `unitDecl` (the novelty rule for
user-defined units — see ast_nodes.UnitDecl).

    program    ::= { funcDecl | unitDecl | statement } ;
    unitDecl   ::= "unit" IDENT "=" expression ";" ;
    ... (rest matches the Review 1 grammar)

Each parse_X() consumes exactly the tokens for rule X and returns an
AST node. Errors raise ParseError with a line/col so the caller can
report them the same way the lexer does.
"""

from ast_nodes import (
    Program, FuncDecl, UnitDecl, Block, DeclStmt, AssignStmt, IfStmt,
    WhileStmt, ForStmt, ReturnStmt, PrintStmt, ExprStmt, BinaryOp,
    UnaryOp, Call, NumberLit, BoolLit, Identifier,
)


class ParseError(Exception):
    def __init__(self, message, tok):
        super().__init__(f"Parse error at {tok.line}:{tok.col}: {message} (got {tok.type} {tok.value!r})")
        self.line, self.col = tok.line, tok.col


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # -- token helpers -----------------------------------------------
    def _cur(self):
        return self.toks[self.i]

    def _check(self, *types):
        return self._cur().type in types

    def _advance(self):
        tok = self.toks[self.i]
        if tok.type != "EOF":
            self.i += 1
        return tok

    def _expect(self, ttype, what=None):
        if self._cur().type != ttype:
            raise ParseError(f"expected {what or ttype}", self._cur())
        return self._advance()

    # -- entry point ---------------------------------------------------
    def parse(self):
        decls = []
        while not self._check("EOF"):
            if self._check("FN"):
                decls.append(self._func_decl())
            elif self._check("UNIT"):
                decls.append(self._unit_decl())
            else:
                decls.append(self._statement())
        return Program(decls, line=1)

    def _func_decl(self):
        tok = self._expect("FN")
        name = self._expect("ID", "function name").value
        self._expect("LPAREN")
        params = []
        if not self._check("RPAREN"):
            params.append(self._expect("ID", "parameter name").value)
            while self._check("COMMA"):
                self._advance()
                params.append(self._expect("ID", "parameter name").value)
        self._expect("RPAREN")
        body = self._block()
        return FuncDecl(name, params, body, line=tok.line)

    def _unit_decl(self):
        tok = self._expect("UNIT")
        name = self._expect("ID", "unit name").value
        self._expect("ASSIGN")
        expr = self._expression()
        self._expect("SEMI")
        return UnitDecl(name, expr, line=tok.line)

    def _block(self):
        tok = self._expect("LBRACE")
        stmts = []
        while not self._check("RBRACE"):
            stmts.append(self._statement())
        self._expect("RBRACE")
        return Block(stmts, line=tok.line)

    # -- statements -----------------------------------------------------
    def _statement(self):
        if self._check("QTY"):
            return self._decl_stmt()
        if self._check("IF"):
            return self._if_stmt()
        if self._check("WHILE"):
            return self._while_stmt()
        if self._check("FOR"):
            return self._for_stmt()
        if self._check("RETURN"):
            return self._return_stmt()
        if self._check("PRINT"):
            return self._print_stmt()
        if self._check("LBRACE"):
            return self._block()
        if self._check("ID") and self.toks[self.i + 1].type == "ASSIGN":
            return self._assign_stmt()
        # bare expression statement
        tok = self._cur()
        expr = self._expression()
        self._expect("SEMI")
        return ExprStmt(expr, line=tok.line)

    def _decl_stmt(self):
        tok = self._expect("QTY")
        name = self._expect("ID", "variable name").value
        self._expect("ASSIGN")
        expr = self._expression()
        self._expect("SEMI")
        return DeclStmt(name, expr, line=tok.line)

    def _assign_stmt(self):
        tok = self._cur()
        name = self._expect("ID").value
        self._expect("ASSIGN")
        expr = self._expression()
        self._expect("SEMI")
        return AssignStmt(name, expr, line=tok.line)

    def _if_stmt(self):
        tok = self._expect("IF")
        self._expect("LPAREN")
        cond = self._expression()
        self._expect("RPAREN")
        then_b = self._statement()
        else_b = None
        if self._check("ELSE"):
            self._advance()
            else_b = self._statement()
        return IfStmt(cond, then_b, else_b, line=tok.line)

    def _while_stmt(self):
        tok = self._expect("WHILE")
        self._expect("LPAREN")
        cond = self._expression()
        self._expect("RPAREN")
        body = self._statement()
        return WhileStmt(cond, body, line=tok.line)

    def _for_stmt(self):
        tok = self._expect("FOR")
        self._expect("LPAREN")
        init = None
        if self._check("QTY"):
            init = self._decl_stmt()
        elif not self._check("SEMI"):
            n = self._expect("ID").value
            self._expect("ASSIGN")
            e = self._expression()
            init = AssignStmt(n, e, line=tok.line)
            self._expect("SEMI")
        else:
            self._expect("SEMI")
        cond = self._expression()
        self._expect("SEMI")
        name = self._expect("ID").value
        self._expect("ASSIGN")
        step_expr = self._expression()
        step = AssignStmt(name, step_expr, line=tok.line)
        self._expect("RPAREN")
        body = self._statement()
        return ForStmt(init, cond, step, body, line=tok.line)

    def _return_stmt(self):
        tok = self._expect("RETURN")
        expr = None
        if not self._check("SEMI"):
            expr = self._expression()
        self._expect("SEMI")
        return ReturnStmt(expr, line=tok.line)

    def _print_stmt(self):
        tok = self._expect("PRINT")
        self._expect("LPAREN")
        expr = self._expression()
        self._expect("RPAREN")
        self._expect("SEMI")
        return PrintStmt(expr, line=tok.line)

    # -- expressions (precedence climbing via layered rules) -----------
    def _expression(self):
        return self._logic_or()

    def _binary_level(self, next_level, ops):
        left = next_level()
        while self._cur().type in ops:
            tok = self._advance()
            right = next_level()
            left = BinaryOp(tok.value, left, right, line=tok.line)
        return left

    def _logic_or(self):
        return self._binary_level(self._logic_and, {"OR"})

    def _logic_and(self):
        return self._binary_level(self._equality, {"AND"})

    def _equality(self):
        return self._binary_level(self._relational, {"EQ", "NEQ"})

    def _relational(self):
        return self._binary_level(self._additive, {"LT", "LE", "GT", "GE"})

    def _additive(self):
        return self._binary_level(self._term, {"PLUS", "MINUS"})

    def _term(self):
        return self._binary_level(self._power, {"STAR", "SLASH"})

    def _power(self):
        base = self._unary()
        if self._check("CARET"):
            tok = self._advance()
            exp = self._unary()
            return BinaryOp("^", base, exp, line=tok.line)
        return base

    def _unary(self):
        if self._check("NOT", "MINUS"):
            tok = self._advance()
            operand = self._unary()
            return UnaryOp(tok.value, operand, line=tok.line)
        return self._call()

    def _call(self):
        node = self._primary()
        if self._check("LPAREN") and isinstance(node, Identifier):
            tok = self._advance()
            args = []
            if not self._check("RPAREN"):
                args.append(self._expression())
                while self._check("COMMA"):
                    self._advance()
                    args.append(self._expression())
            self._expect("RPAREN")
            return Call(node.name, args, line=tok.line)
        return node

    def _primary(self):
        tok = self._cur()
        if tok.type == "NUM":
            self._advance()
            return NumberLit(float(tok.value), line=tok.line)
        if tok.type == "TRUE":
            self._advance()
            return BoolLit(True, line=tok.line)
        if tok.type == "FALSE":
            self._advance()
            return BoolLit(False, line=tok.line)
        if tok.type == "ID":
            self._advance()
            return Identifier(tok.value, line=tok.line)
        if tok.type == "LPAREN":
            self._advance()
            e = self._expression()
            self._expect("RPAREN")
            return e
        raise ParseError("expected an expression", tok)
