from dimension import Dimension, LENGTH
from pipeline import compile_source
from helpers import errors_of


def dims_of(source):
    res = compile_source(source)
    assert res.ok, res.errors
    return {k: v.dim for k, v in res.analyzer.sym.scopes[0].items()}


def test_multiplication_and_division_combine_dimensions():
    d = dims_of("qty v = 10 * m / s; qty a = v / (2 * s);")
    assert d["v"] == Dimension(1, 0, -1)
    assert d["a"] == Dimension(1, 0, -2)


def test_addition_requires_equal_dimensions():
    errs = errors_of("qty a = 1 * m + 2 * s;")
    assert len(errs) == 1 and "Length" in errs[0] and "Time" in errs[0]


def test_bare_number_plus_dimension_has_helpful_message():
    assert "attach one" in errors_of("qty a = 3 * m + 5;")[0]


def test_power_scales_dimension():
    assert dims_of("qty a = (3 * m) ^ 2;")["a"] == Dimension(2, 0, 0)


def test_exponent_must_be_integer_literal():
    assert "integer literal" in errors_of("qty n = 2; qty a = (3 * m) ^ n;")[0]


def test_negative_exponent_allowed():
    assert dims_of("qty a = s ^ -1;")["a"] == Dimension(0, 0, -1)


def test_literal_zero_adapts_to_any_dimension():
    dims_of("qty d = 5 * m; qty b = d > 0; qty c = d - 0;")


def test_condition_must_be_dimensionless():
    assert "condition" in errors_of("qty d = 5 * m; if (d) { print(d); }")[0]


def test_assignment_cannot_change_dimension():
    assert "declared as" in errors_of("qty d = 5 * m; d = 3 * s;")[0]


def test_unit_name_cannot_be_a_variable():
    assert "unit name" in errors_of("qty m = 5;")[0]


def test_no_redeclaration_in_same_scope():
    assert "already declared" in errors_of("qty x = 1; qty x = 2;")[0]


def test_inner_block_variable_does_not_leak():
    assert "undeclared" in errors_of("{ qty inner = 1; } print(inner);")[0]


def test_did_you_mean_suggestion():
    assert "did you mean 'speed'" in errors_of("qty speed = 1; print(sped);")[0]


def test_one_error_does_not_cascade():
    assert len(errors_of("qty bad = 1 * m + 1 * s; print(bad);")) == 1


def test_user_unit_dimension_and_scale():
    res = compile_source("unit N = kg * m / s ^ 2; unit kN = 1000 * N;")
    u = res.analyzer.sym.units
    assert u["N"].dim == Dimension(1, 1, -2) and u["N"].scale == 1
    assert u["kN"].dim == u["N"].dim and u["kN"].scale == 1000


def test_unit_definition_with_unknown_name():
    assert "not a known unit" in errors_of("unit Q = foo * m;")[0]


def test_redefining_a_unit_is_an_error():
    assert "already defined" in errors_of("unit km = 5 * m;")[0]


# ---- dimension-polymorphic functions ------------------------------------

def test_same_function_gets_different_instances():
    res = compile_source(
        "fn twice(x) { return x * 2; } qty a = twice(3 * m); qty b = twice(4);")
    assert res.ok
    log = {(n, d): r for n, d, r in res.analyzer.instance_log}
    assert log[("twice", (LENGTH,))] == LENGTH
    assert log[("twice", (Dimension(),))] == Dimension()


def test_return_dimension_is_inferred_from_arguments():
    d = dims_of("fn speed(d, t) { return d / t; } qty v = speed(10 * m, 2 * s);")
    assert d["v"] == Dimension(1, 0, -1)


def test_error_inside_function_names_the_call():
    errs = errors_of("fn f(x) { return x + 1; } print(f(2 * m));")
    assert "while checking 'f' called with (Length)" in errs[0]


def test_function_arity_is_checked():
    assert "expects 2" in errors_of("fn f(a, b) { return a; } print(f(1));")[0]


def test_recursion_is_inferred():
    d = dims_of("fn fact(n) { if (n <= 1) { return 1; } else { return n * fact(n - 1); } } qty r = fact(4);")
    assert d["r"] == Dimension()


def test_inconsistent_return_dimensions_rejected():
    errs = errors_of("fn f(x) { if (x > 0) { return 1 * m; } return 1 * s; } print(f(1));")
    assert "different dimensions" in errs[0]


def test_uncalled_function_gets_a_warning():
    res = compile_source("fn unused(x) { return x; } qty a = 1;")
    assert res.ok and any("never called" in w for w in res.warnings)


def test_return_outside_function():
    assert "outside" in errors_of("return 1;")[0]
