#!/usr/bin/env python3
"""
Run every sample program and check it against its expected result.

    python3 run_samples.py              run everything (examples/ and samples/)
    python3 run_samples.py -v           also print each program's actual output
    python3 run_samples.py samples/B02  run only files whose path contains the text

Each program in samples/ states what it expects in comment lines at the end:

    // expect-exit: 1                   exit status (0 ok, 1 compile error, 2 runtime error)
    // expect: <line>                   one expected line of program output, in order
    // expect-stderr: <text>            text that must appear in the error output
    // expect-errors: <n>               exactly n error messages must be reported

The 12 programs in examples/ have their expectations listed in EXAMPLES below.
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

EXAMPLES = {
    "01_basics.ul": (0, ["100 m", "9.58 s", "10.4384 m/s", "2.5 hr", "49 m*kg/s^2", "1.5 km", "250 g"], [], None),
    "02_custom_units.ul": (0, ["6 N", "4.5 kN", "60 mph", "5 N"], [], None),
    "03_polymorphic_functions.ul": (0, ["10.4384 m/s", "5.81151 m/s", "9 J", "8 m", "6", "120"], [], None),
    "04_control_flow.ul": (0, ["2.5 hr", "4", "1.6 km", "2 km", "1 km", "0 m"], [], None),
    "05_optimizer_demo.ul": (0, ["5.3 km", "24", "500 km"], [], None),
    "06_showcase_physics.ul": (0, ["686.7 N", "2060.1 J", "412.02 W"], [], None),
    "07_context_aware_print.ul": (0, ["5 km", "100 m", "2.5 hr"], [], None),
    "08_imperial_context.ul": (0, ["26.2 mi", "3.10686 mi"], [], None),
    "09_error_dimensions.ul": (1, [], ["Length and Time", "a plain number", "a condition must be"], 3),
    "10_error_names.ul": (1, [], ["did you mean 'speed'?", "unit name", "undefined function 'foo'", "already declared"], 4),
    "11_error_function_context.ul": (1, [], ["while checking 'addOne' called with (Length)"], 1),
    "12_runtime_error.ul": (2, [], ["Runtime error: division by zero"], None),
}


def parse_header(path):
    code, out, err, nerr = 0, [], [], None
    for line in open(path):
        if not line.startswith("// expect"):
            continue
        key, _, val = line[3:].rstrip("\n").partition(":")
        val = val[1:] if val.startswith(" ") else val
        if key == "expect-exit":
            code = int(val)
        elif key == "expect":
            out.append(val)
        elif key == "expect-stderr":
            err.append(val)
        elif key == "expect-errors":
            nerr = int(val)
    return code, out, err, nerr


def run_one(path, expected):
    code, out, err, nerr = expected
    p = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), path],
                       capture_output=True, text=True, cwd=ROOT)
    problems = []
    if p.returncode != code:
        problems.append(f"exit status {p.returncode}, expected {code}")
    if out and p.stdout.splitlines() != out:
        problems.append(f"output {p.stdout.splitlines()} != expected {out}")
    for text in err:
        if text not in p.stderr:
            problems.append(f"stderr is missing: {text!r}")
    if nerr is not None:
        n = p.stderr.count("error at ")
        if n != nerr:
            problems.append(f"{n} error message(s), expected {nerr}")
    return problems, p


def main():
    args = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv[1:]
    cases = []
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.ul"))):
        if os.path.basename(path) in EXAMPLES:
            cases.append((path, EXAMPLES[os.path.basename(path)]))
    for path in sorted(glob.glob(os.path.join(ROOT, "samples", "*.ul"))):
        cases.append((path, parse_header(path)))
    if args:
        cases = [c for c in cases if any(a in c[0] for a in args)]
    failed = 0
    for path, expected in cases:
        problems, p = run_one(path, expected)
        name = os.path.relpath(path, ROOT)
        print(f"{'PASS' if not problems else 'FAIL'}  {name}")
        for pr in problems:
            print(f"        {pr}")
        failed += bool(problems)
        if verbose:
            for line in (p.stdout + p.stderr).rstrip("\n").splitlines():
                print(f"        | {line}")
    print(f"\n{len(cases) - failed} of {len(cases)} programs behaved as expected.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
