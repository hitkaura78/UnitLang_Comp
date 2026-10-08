from lexer import Lexer
from parser import Parser
from pipeline import compile_source


def kinds(src):
    toks, errs = Lexer(src).tokenize()
    assert not errs
    return [t.type for t in toks]


def test_maximal_munch_two_char_operators():
    assert kinds("a <= b == c != d >= e && f || g")[:-1] == [
        "ID", "LE", "ID", "EQ", "ID", "NEQ", "ID", "GE", "ID", "AND", "ID", "OR", "ID"]


def test_units_lex_as_plain_identifiers():
    assert kinds("5 * km")[:-1] == ["NUM", "STAR", "ID"]


def test_comments_and_whitespace_are_skipped():
    assert kinds("1 // line\n /* block */ 2")[:-1] == ["NUM", "NUM"]


def test_lexer_reports_several_errors_in_one_pass():
    _, errs = Lexer("qty a = 1 @ 2 $ 3;").tokenize()
    assert len(errs) == 2


def test_unterminated_block_comment_is_an_error():
    _, errs = Lexer("/* never closed").tokenize()
    assert len(errs) == 1


def test_parse_error_has_position():
    res = compile_source("qty x = ;")
    assert not res.ok and res.stage == "syntax"
    assert "1:9" in res.errors[0]


def test_power_binds_tighter_than_division():
    toks, _ = Lexer("qty a = m / s ^ 2;").tokenize()
    ast = Parser(toks).parse()
    expr = ast.decls[0].expr
    assert expr.op == "/" and expr.right.op == "^"
