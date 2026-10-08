import glob
import os

from pipeline import compile_source, run_vm, run_interpreter

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")


def example_files(prefixes=None):
    files = sorted(glob.glob(os.path.join(EXAMPLES, "*.ul")))
    if prefixes:
        files = [f for f in files if os.path.basename(f)[:2] in prefixes]
    return files


def run(source, optimize=True):
    res = compile_source(source, optimize=optimize)
    assert res.ok, res.errors
    out, _ = run_vm(res)
    return out


def errors_of(source):
    res = compile_source(source)
    assert not res.ok
    return res.errors
