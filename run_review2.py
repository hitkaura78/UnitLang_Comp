#!/usr/bin/env python3
"""
Review 2 snapshot driver: lex -> parse -> semantic check -> IR dump.
It stops before optimization, code generation and execution, so it shows
only the Review 2 deliverables (symbol table, dimensional type checking, IR).

    python3 run_review2.py examples/06_showcase_physics.ul
"""
import sys

from lexer import Lexer
from parser import Parser, ParseError
from semantic import SemanticAnalyzer
from irgen import IRGen


def main():
    if len(sys.argv) != 2:
        print("usage: python3 run_review2.py <file.ul>", file=sys.stderr)
        return 2
    source = open(sys.argv[1]).read()
    tokens, lex_errors = Lexer(source).tokenize()
    if lex_errors:
        for e in lex_errors:
            print(e, file=sys.stderr)
        return 1
    print(f"Lexed {len(tokens)} tokens OK.")
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(e, file=sys.stderr)
        return 1
    print("Parsed AST OK.")
    analyzer = SemanticAnalyzer()
    errors = analyzer.analyze(ast)
    if errors:
        print("\nSemantic errors found:")
        for e in errors:
            print(" ", e)
        return 1
    print("Semantic analysis passed: all dimensions check out.")
    gen = IRGen()
    gen.generate(ast)
    print("\n---- Generated IR ----")
    print(gen.dump())
    return 0


if __name__ == "__main__":
    sys.exit(main())
