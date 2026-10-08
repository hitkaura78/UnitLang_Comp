import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def cli(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), *args],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout, p.stderr


def test_working_example_exit_zero_and_output():
    code, out, _ = cli("examples/02_custom_units.ul")
    assert code == 0 and out.split("\n")[:4] == ["6 N", "4.5 kN", "60 mph", "5 N"]


@pytest.mark.parametrize("name,phrase", [
    ("09_error_dimensions.ul", "different physical dimensions"),
    ("10_error_names.ul", "did you mean 'speed'"),
    ("11_error_function_context.ul", "while checking 'addOne'"),
])
def test_compile_errors_exit_one(name, phrase):
    code, out, err = cli(f"examples/{name}")
    assert code == 1 and out == "" and phrase in err


def test_runtime_error_exit_two():
    code, _, err = cli("examples/12_runtime_error.ul")
    assert code == 2 and "division by zero" in err


def test_flags_run():
    code, out, _ = cli("examples/03_polymorphic_functions.ul", "--symbols", "--ir", "--bytecode", "--stats")
    assert code == 0
    for marker in ("Function instances", "TAC (optimized)", "== main ==", "instructions executed"):
        assert marker in out


def test_check_only_does_not_run():
    code, out, _ = cli("examples/01_basics.ul", "--check")
    assert code == 0 and out.strip() == "Type check passed."


def test_interpreter_flag_matches_vm():
    _, vm_out, _ = cli("examples/06_showcase_physics.ul")
    _, it_out, _ = cli("examples/06_showcase_physics.ul", "--interp")
    assert vm_out == it_out
