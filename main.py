#!/usr/bin/env python3
"""
UnitLang compiler front end / middle end — CLI driver.

Usage:
    python3 main.py path/to/program.ul            # run the program
    python3 main.py path/to/program.ul --ir        # also dump the IR

Pipeline: lex -> parse -> semantic analysis (dimensional checking) ->
IR generation -> interpretation. If lexing/parsing/semantic analysis
finds any errors, the pipeline stops and prints them instead of
running anything (no point generating IR for a program that doesn't
type-check).
"""

import sys

from lexer import Lexer
from parser import Parser, ParseError
from semantic import SemanticAnalyzer
from irgen import IRGen
from interpreter import Interpreter


def run_source(source: str, show_ir: bool = False) -> int:
    lexer = Lexer(source)
    tokens, lex_errors = lexer.tokenize()
    if lex_errors:
        for e in lex_errors:
            print(str(e), file=sys.stderr)
        return 1

    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(str(e), file=sys.stderr)
        return 1

    analyzer = SemanticAnalyzer()
    sem_errors = analyzer.analyze(ast)
    if sem_errors:
        for e in sem_errors:
            print(e, file=sys.stderr)
        return 1

    irgen = IRGen()
    irgen.generate(ast)
    if show_ir:
        print("---- IR ----")
        print(irgen.dump())
        print("---- output ----")

    interp = Interpreter(analyzer.sym)
    output = interp.run(ast)
    for line in output:
        print(line)
    return 0


def main():
    if len(sys.argv) < 2:
        print("usage: python3 main.py <file.ul> [--ir]", file=sys.stderr)
        return 2
    path = sys.argv[1]
    show_ir = "--ir" in sys.argv[2:]
    with open(path) as f:
        source = f.read()
    return run_source(source, show_ir=show_ir)


if __name__ == "__main__":
    sys.exit(main())
