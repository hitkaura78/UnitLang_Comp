"""
Basic pipeline tests: lex -> parse -> semantic -> interpret.

Run with: pytest tests/  (from the project root, or add root to PYTHONPATH)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lexer import Lexer
from parser import Parser
from semantic import SemanticAnalyzer
from interpreter import Interpreter


def run(source):
    tokens, lex_errors = Lexer(source).tokenize()
    assert not lex_errors, lex_errors
    ast = Parser(tokens).parse()
    analyzer = SemanticAnalyzer()
    errors = analyzer.analyze(ast)
    return ast, analyzer, errors


def run_ok(source):
    ast, analyzer, errors = run(source)
    assert not errors, errors
    return Interpreter(analyzer.sym).run(ast)


def test_valid_addition_same_dimension():
    out = run_ok("qty a = 2 * m; qty b = 3 * m; qty c = a + b; print(c);")
    assert out == ["5 m"]


def test_mismatched_addition_is_rejected():
    _, _, errors = run("qty a = 2 * m; qty b = 3 * s; qty c = a + b;")
    assert len(errors) == 1
    assert "Length" in errors[0] and "Time" in errors[0]


def test_multiplication_combines_dimensions():
    out = run_ok("qty f = (5 * kg) * (2 * m / s ^ 2); print(f);")
    assert out == ["10 (base units: Length * Mass * Time^-2)"]


def test_custom_unit_declaration():
    out = run_ok(
        "unit N = kg * m / s ^ 2; "
        "qty f = (5 * kg) * (2 * m / s ^ 2); "
        "print(f);"
    )
    assert out == ["10 N"]


def test_smart_print_picks_the_unit_closest_to_magnitude_one():
    # 5000 m: candidates are m(5000), km(5), mi(~3.11), ft(~16404).
    # log10-distance-from-1 heuristic picks mi here (~3.11 is closer to 1
    # than km's 5) — see interpreter.smart_format's docstring/README notes.
    out = run_ok("qty d = 5000 * m; print(d);")
    assert out == ["3.1069 mi"]


def test_functions_and_recursion():
    src = """
    fn fact(n) {
        if (n <= 1) { return 1; } else { return n * fact(n - 1); }
    }
    print(fact(5));
    """
    out = run_ok(src)
    assert out == ["120"]


def test_undeclared_variable_is_rejected():
    _, _, errors = run("qty a = b + 1;")
    assert len(errors) == 1
    assert "undeclared" in errors[0]


def test_while_loop_and_smart_time_units():
    src = """
    qty total = 0 * s;
    qty i = 0;
    while (i < 3) {
        total = total + 1 * hr;
        i = i + 1;
    }
    print(total);
    """
    out = run_ok(src)
    assert out == ["3 hr"]
