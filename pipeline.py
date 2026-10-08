"""
The whole compiler as one function, shared by main.py and the tests.

    source -> lex -> parse -> semantic analysis -> TAC IR
           -> optimize (fold + dead code) -> bytecode (+ peephole)
           -> run on the VM   (or on the reference interpreter)
"""

from dataclasses import dataclass, field
from typing import Optional

from lexer import Lexer
from parser import Parser, ParseError
from semantic import SemanticAnalyzer
from irgen import IRGen
from optimizer import optimize_tac, OptStats
from codegen import generate, disassemble
from vm import VM
from interpreter import Interpreter
from quantity import RuntimeErr


@dataclass
class CompileResult:
    ok: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stage: str = ""                       # stage that failed, if any
    ast: object = None
    analyzer: Optional[SemanticAnalyzer] = None
    irgen: Optional[IRGen] = None
    tac: list = field(default_factory=list)
    opt_tac: list = field(default_factory=list)
    program: object = None
    stats: OptStats = field(default_factory=OptStats)


def compile_source(source: str, optimize: bool = True) -> CompileResult:
    res = CompileResult()

    tokens, lex_errors = Lexer(source).tokenize()
    if lex_errors:
        res.errors, res.stage = [str(e) for e in lex_errors], "lexical"
        return res

    try:
        res.ast = Parser(tokens).parse()
    except ParseError as e:
        res.errors, res.stage = [str(e)], "syntax"
        return res

    analyzer = SemanticAnalyzer()
    res.analyzer = analyzer
    errors = analyzer.analyze(res.ast)
    res.warnings = list(analyzer.warnings)
    if errors:
        res.errors, res.stage = list(errors), "semantic"
        return res

    gen = IRGen()
    res.irgen = gen
    res.tac = gen.generate(res.ast)
    if optimize:
        res.opt_tac, res.stats = optimize_tac(res.tac, analyzer.sym.units, res.stats)
    else:
        res.opt_tac = list(res.tac)
        res.stats.tac_before = res.stats.tac_after = len(res.tac)
    res.program = generate(res.opt_tac, optimize=optimize, stats=res.stats)
    res.ok = True
    return res


def run_vm(res: CompileResult, echo=False):
    """Returns (output lines, VM). Raises RuntimeErr on a runtime error;
    output produced before the error is kept on vm.output."""
    sym = res.analyzer.sym
    vm = VM(res.program, sym.units, sym.used_units, echo=echo)
    vm.run()
    return vm.output, vm


def run_interpreter(res: CompileResult, echo=False):
    sym = res.analyzer.sym
    it = Interpreter(sym.functions, sym.units, sym.used_units, echo=echo)
    it.run(res.ast)
    return it.output, it
