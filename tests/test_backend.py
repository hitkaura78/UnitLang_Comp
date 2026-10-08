"""Optimizer, code generator and VM tests, including the oracle check:
every working example must produce identical output on
  (a) the reference tree-walking interpreter,
  (b) the bytecode VM with optimizations on,
  (c) the bytecode VM with optimizations off."""

import os

import pytest

from pipeline import compile_source, run_vm, run_interpreter
from quantity import RuntimeErr, Quantity, apply_binary
from dimension import LENGTH, TIME
from helpers import example_files, run

WORKING = example_files({"01", "02", "03", "04", "05", "06", "07", "08"})


@pytest.mark.parametrize("path", WORKING, ids=[os.path.basename(p) for p in WORKING])
def test_vm_matches_reference_interpreter(path):
    src = open(path).read()
    res = compile_source(src, optimize=True)
    assert res.ok, res.errors
    expected, _ = run_interpreter(res)
    optimized, _ = run_vm(res)
    unoptimized, _ = run_vm(compile_source(src, optimize=False))
    assert optimized == expected
    assert unoptimized == expected
    assert expected, "example should print something"


def test_unit_constant_folding_folds_whole_expression():
    res = compile_source("qty a = 5 * km + 300 * m;")
    assert res.stats.folded >= 3 and res.stats.unit_folds >= 3
    decl = [i for i in res.opt_tac if i[0] == "decl"][0]
    assert repr(decl[1]) == "5300<Length>"


def test_dead_code_is_removed():
    res = compile_source("qty a = 1; 2 * 3 * 4; 5 * m;")
    assert [i[0] for i in res.opt_tac] == ["decl"] and res.stats.dead > 0


def test_folding_does_not_touch_variables():
    res = compile_source("qty x = 3 * m; qty y = x * 2;")
    assert any(i[0] == "*" for i in res.opt_tac)


def test_division_by_zero_is_not_folded_but_fails_at_runtime():
    res = compile_source("print(1 / 0);")
    assert res.ok
    with pytest.raises(RuntimeErr, match="division by zero"):
        run_vm(res)


def test_optimizer_reduces_instructions_executed():
    src = open(example_files({"05"})[0]).read()
    opt, raw = compile_source(src, True), compile_source(src, False)
    _, vm_opt = run_vm(opt)
    _, vm_raw = run_vm(raw)
    assert vm_opt.steps < vm_raw.steps / 2
    assert opt.stats.bc_after < raw.stats.bc_after


def test_peephole_removes_redundant_store_load_pairs():
    res = compile_source("qty a = 1; qty b = a + 2;")
    assert res.stats.peephole >= 1
    for chunk in [res.program.main]:
        assert not any(op == "LOAD" and str(arg).startswith("%t") for op, arg in chunk)


def test_globals_are_visible_and_assignable_in_functions():
    src = """
    qty total = 0 * m;
    fn addTo(x) { total = total + x; return total; }
    addTo(2 * km);
    addTo(300 * m);
    print(total);
    """
    assert run(src) == ["2.3 km"]


def test_function_locals_do_not_leak_and_return_works():
    assert run("fn f() { qty hidden = 1; return hidden; } print(f());") == ["1"]


def test_temporaries_cannot_collide_with_user_variables():
    assert run("qty t0 = 5; qty t1 = t0 + 1; print(t1);") == ["6"]


def test_recursion_fibonacci():
    src = "fn fib(n) { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); } print(fib(10));"
    assert run(src) == ["55"]


def test_runaway_recursion_is_caught():
    res = compile_source("fn f(n) { return f(n + 1); } print(f(0));")
    assert res.ok
    with pytest.raises(RuntimeErr, match="call depth"):
        run_vm(res)


def test_infinite_loop_is_caught():
    res = compile_source("qty i = 0; while (true) { i = i + 1; }")
    with pytest.raises(RuntimeErr, match="step limit"):
        run_vm(res)


def test_runtime_dimension_safety_net():
    with pytest.raises(RuntimeErr, match="dimension mismatch"):
        apply_binary("+", Quantity(1, LENGTH), Quantity(1, TIME))


def test_booleans_and_logic():
    assert run("print(1 < 2 && 2 < 3); print(!(1 < 2)); print(1 > 2 || 3 > 2);") == [
        "true", "false", "true"]


def test_for_loop_scope():
    src = "for (qty i = 0; i < 3; i = i + 1) { print(i); } for (qty i = 5; i < 7; i = i + 1) { print(i); }"
    assert run(src) == ["0", "1", "2", "5", "6"]
