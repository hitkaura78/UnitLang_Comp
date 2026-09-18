"""
AST node types for UnitLang.

Plain dataclasses, one per grammar rule that actually needs to survive
into semantic analysis. Every expression node has a `dim` slot that
starts as None and gets filled in by the semantic analyzer (Section
"Semantic Analysis" in the README) — that's the dimension vector, not
a language keyword, so it lives on the node rather than in the grammar.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any


@dataclass
class Node:
    line: int = field(default=0, kw_only=True)


# ---- top level -------------------------------------------------------

@dataclass
class Program(Node):
    decls: List[Any]


@dataclass
class FuncDecl(Node):
    name: str
    params: List[str]
    body: "Block"


@dataclass
class UnitDecl(Node):
    """Novelty feature: user-defined derived units, e.g.
    unit N = kg * m / s ^ 2;
    The right-hand side is an expression built purely out of other
    unit identifiers/numbers; it is evaluated at compile time by the
    semantic analyzer to get a dimension vector + scale factor, which
    is then registered in the symbol table under `name`.
    """
    name: str
    expr: Any


# ---- statements --------------------------------------------------------

@dataclass
class Block(Node):
    stmts: List[Any]


@dataclass
class DeclStmt(Node):
    name: str
    expr: Any


@dataclass
class AssignStmt(Node):
    name: str
    expr: Any


@dataclass
class IfStmt(Node):
    cond: Any
    then_branch: Any
    else_branch: Optional[Any]


@dataclass
class WhileStmt(Node):
    cond: Any
    body: Any


@dataclass
class ForStmt(Node):
    init: Optional[Any]
    cond: Any
    step: Any
    body: Any


@dataclass
class ReturnStmt(Node):
    expr: Optional[Any]


@dataclass
class PrintStmt(Node):
    expr: Any


@dataclass
class ExprStmt(Node):
    expr: Any


# ---- expressions --------------------------------------------------------

@dataclass
class BinaryOp(Node):
    op: str
    left: Any
    right: Any
    dim: Any = None


@dataclass
class UnaryOp(Node):
    op: str
    operand: Any
    dim: Any = None


@dataclass
class Call(Node):
    callee: str
    args: List[Any]
    dim: Any = None


@dataclass
class NumberLit(Node):
    value: float
    dim: Any = None


@dataclass
class BoolLit(Node):
    value: bool
    dim: Any = None


@dataclass
class Identifier(Node):
    name: str
    dim: Any = None
