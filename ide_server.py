#!/usr/bin/env python3
"""
UnitLang Web IDE Server.
A lightweight, zero-dependency local web server providing an interactive
IDE for UnitLang on localhost.
"""

import glob
import http.server
import io
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

import pipeline
import irgen
import codegen
import main as main_cli
from run_samples import EXAMPLES, parse_header, run_one
from quantity import RuntimeErr

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT_DIR, "ide_web")


def get_sample_metadata():
    """Discover all examples and sample programs with metadata and expected outputs."""
    samples = []

    # 1. Add examples/
    for path in sorted(glob.glob(os.path.join(ROOT_DIR, "examples", "*.ul"))):
        filename = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()

        title = filename.replace(".ul", "").replace("_", " ").title()
        # Clean title
        if filename in EXAMPLES:
            exp_code, exp_out, exp_err, exp_nerr = EXAMPLES[filename]
        else:
            exp_code, exp_out, exp_err, exp_nerr = 0, [], [], None

        samples.append({
            "id": f"examples/{filename}",
            "filename": filename,
            "path": f"examples/{filename}",
            "category": "Examples",
            "category_order": 0,
            "title": title,
            "description": "Standard showcase and test example program",
            "code": code,
            "expected": {
                "exit_code": exp_code,
                "stdout": exp_out,
                "stderr": exp_err,
                "n_errors": exp_nerr,
            }
        })

    # 2. Add samples/ (A to G)
    category_map = {
        "A": ("Lexer & Syntax", 1),
        "B": ("Dimensional Analysis", 2),
        "C": ("Custom Units", 3),
        "D": ("Polymorphic Functions", 4),
        "E": ("Context Display", 5),
        "F": ("Control Flow", 6),
        "G": ("Runtime Limits", 7),
    }

    for path in sorted(glob.glob(os.path.join(ROOT_DIR, "samples", "*.ul"))):
        filename = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()

        prefix = filename[0] if filename and filename[0] in category_map else "Other"
        cat_name, order = category_map.get(prefix, ("Other Samples", 8))

        # Extract title and description from comments if available
        title = filename.replace(".ul", "")
        description = ""
        for line in code.splitlines():
            line_str = line.strip()
            if line_str.startswith("// TITLE:"):
                title = line_str.replace("// TITLE:", "").strip()
            elif line_str.startswith("// TESTS:"):
                description = line_str.replace("// TESTS:", "").strip()

        exp_code, exp_out, exp_err, exp_nerr = parse_header(path)

        samples.append({
            "id": f"samples/{filename}",
            "filename": filename,
            "path": f"samples/{filename}",
            "category": cat_name,
            "category_order": order,
            "title": title,
            "description": description or f"Test sample {filename}",
            "code": code,
            "expected": {
                "exit_code": exp_code,
                "stdout": exp_out,
                "stderr": exp_err,
                "n_errors": exp_nerr,
            }
        })

    return samples


def parse_inline_expectations(code_text):
    """Parse // expect-exit, // expect:, // expect-stderr:, // expect-errors: from code."""
    code, out, err, nerr = 0, [], [], None
    has_expect = False
    for line in code_text.splitlines():
        line = line.strip()
        if not line.startswith("// expect"):
            continue
        has_expect = True
        key, _, val = line[3:].partition(":")
        val = val.strip()
        if key == "expect-exit":
            try:
                code = int(val)
            except ValueError:
                pass
        elif key == "expect":
            out.append(val)
        elif key == "expect-stderr":
            err.append(val)
        elif key == "expect-errors":
            try:
                nerr = int(val)
            except ValueError:
                pass
    return has_expect, code, out, err, nerr


def execute_unitlang(code: str, optimize: bool = True, engine: str = "vm", sample_id: str = None):
    """
    Compile and run UnitLang source code, returning detailed pipeline results,
    terminal simulation, compiler inspection artifacts, and comparison with expectations.
    """
    t0 = time.perf_counter()

    # Determine expectations
    expected_info = None
    if sample_id:
        for s in get_sample_metadata():
            if s["id"] == sample_id:
                expected_info = s["expected"]
                break

    has_inline, in_code, in_out, in_err, in_nerr = parse_inline_expectations(code)
    if has_inline:
        expected_info = {
            "exit_code": in_code,
            "stdout": in_out,
            "stderr": in_err,
            "n_errors": in_nerr,
        }

    # Execute via subprocess for authentic CLI output & exit status
    temp_file = os.path.join(ROOT_DIR, ".ide_temp.ul")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(code)

        cli_args = [sys.executable, os.path.join(ROOT_DIR, "main.py"), temp_file]
        if not optimize:
            cli_args.append("--no-opt")
        if engine == "interp":
            cli_args.append("--interp")

        proc = subprocess.run(cli_args, capture_output=True, text=True, cwd=ROOT_DIR)
        cli_exit_code = proc.returncode
        cli_stdout = proc.stdout.splitlines()
        cli_stderr = proc.stderr.splitlines()
    finally:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except OSError:
                pass

    # Detailed pipeline compilation for TAC, Bytecode, Symbols, Stats
    res = pipeline.compile_source(code, optimize=optimize)

    # Format symbols
    symbols_data = {"units": [], "globals": [], "functions": []}
    if res.analyzer and res.analyzer.sym:
        sym = res.analyzer.sym
        for u in sym.units.values():
            symbols_data["units"].append({
                "name": u.name,
                "dimension": u.dim.pretty(),
                "scale": u.scale,
                "origin": u.origin,
            })
        if sym.scopes and sym.scopes[0]:
            for name, entry in sym.scopes[0].items():
                symbols_data["globals"].append({
                    "name": name,
                    "dimension": entry.dim.pretty(),
                })
        if res.analyzer.instance_log:
            for name, dims, ret in res.analyzer.instance_log:
                args_str = ", ".join("number" if d.is_dimensionless() else d.pretty() for d in dims)
                ret_str = "number" if ret.is_dimensionless() else ret.pretty()
                symbols_data["functions"].append({
                    "name": name,
                    "args": args_str,
                    "return": ret_str,
                })

    # Format TAC
    tac_unopt = ""
    tac_opt = ""
    if res.irgen and res.tac:
        tac_unopt = irgen.dump_tac(res.tac, res.irgen.dims)
        tac_opt = irgen.dump_tac(res.opt_tac, res.irgen.dims) if res.opt_tac else tac_unopt

    # Format Bytecode
    bytecode_str = ""
    if res.program:
        bytecode_str = codegen.disassemble(res.program)

    # Optimizer stats
    stats_data = {}
    if res.stats:
        s = res.stats
        stats_data = {
            "tac_before": s.tac_before,
            "tac_after": s.tac_after,
            "folded": s.folded,
            "unit_folds": s.unit_folds,
            "unit_inlines": s.unit_inlines,
            "propagated": s.propagated,
            "dead": s.dead,
            "bc_before": s.bc_before,
            "bc_after": s.bc_after,
            "peephole": s.peephole,
        }

    # VM steps if executed
    vm_steps = None
    if res.ok and engine == "vm":
        try:
            _, vm_inst = pipeline.run_vm(res)
            vm_steps = vm_inst.steps
            stats_data["vm_steps"] = vm_steps
        except Exception:
            pass

    t1 = time.perf_counter()
    execution_time_ms = round((t1 - t0) * 1000, 2)

    # Terminal output reconstruction
    term_lines = []
    term_lines.append(f"$ unitlang run {'--no-opt ' if not optimize else ''}{'--interp ' if engine == 'interp' else ''}program.ul")
    for w in res.warnings:
        term_lines.append(f"\033[33mwarning: {w}\033[0m")
    if cli_stdout:
        term_lines.extend(cli_stdout)
    if cli_stderr:
        for err_line in cli_stderr:
            term_lines.append(f"\033[31m{err_line}\033[0m")
    term_lines.append(f"\n[Process exited with status {cli_exit_code} in {execution_time_ms}ms]")

    # Check comparison with expectation
    comparison = {
        "has_expected": expected_info is not None,
        "status": "PASS" if expected_info else "CUSTOM",
        "problems": [],
    }

    if expected_info:
        exp_code = expected_info.get("exit_code", 0)
        exp_out = expected_info.get("stdout", [])
        exp_err = expected_info.get("stderr", [])
        exp_nerr = expected_info.get("n_errors", None)

        if cli_exit_code != exp_code:
            comparison["problems"].append(f"Exit status {cli_exit_code}, expected {exp_code}")
        if exp_out and cli_stdout != exp_out:
            comparison["problems"].append(f"Output mismatch: expected {exp_out}, got {cli_stdout}")
        for text in exp_err:
            full_stderr = "\n".join(cli_stderr)
            if text not in full_stderr:
                comparison["problems"].append(f"Stderr missing required text: {text!r}")
        if exp_nerr is not None:
            full_stderr = "\n".join(cli_stderr)
            n = full_stderr.count("error at ")
            if n != exp_nerr:
                comparison["problems"].append(f"{n} error message(s) reported, expected {exp_nerr}")

        comparison["status"] = "PASS" if not comparison["problems"] else "FAIL"

    return {
        "ok": res.ok,
        "stage": res.stage,
        "exit_code": cli_exit_code,
        "stdout": cli_stdout,
        "stderr": cli_stderr,
        "terminal": "\n".join(term_lines),
        "execution_time_ms": execution_time_ms,
        "errors": res.errors,
        "warnings": res.warnings,
        "tac_unoptimized": tac_unopt,
        "tac_optimized": tac_opt,
        "bytecode": bytecode_str,
        "symbols": symbols_data,
        "stats": stats_data,
        "expected": expected_info,
        "comparison": comparison,
    }


def run_all_samples():
    """Run all samples against their expectations and return a full test report."""
    samples = get_sample_metadata()
    results = []
    passed = 0
    failed = 0

    for s in samples:
        exp = s["expected"]
        expected_tuple = (exp["exit_code"], exp["stdout"], exp["stderr"], exp["n_errors"])
        full_path = os.path.join(ROOT_DIR, s["path"])
        problems, p = run_one(full_path, expected_tuple)

        is_pass = len(problems) == 0
        if is_pass:
            passed += 1
        else:
            failed += 1

        results.append({
            "id": s["id"],
            "title": s["title"],
            "path": s["path"],
            "category": s["category"],
            "status": "PASS" if is_pass else "FAIL",
            "exit_code": p.returncode,
            "expected_exit_code": exp["exit_code"],
            "stdout": p.stdout.splitlines(),
            "stderr": p.stderr.splitlines(),
            "problems": problems,
        })

    return {
        "total": len(samples),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


class UnitLangRequestHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS and disable aggressive caching for dev server
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/samples":
            samples = get_sample_metadata()
            self._send_json(samples)
            return

        # Serve static web files
        if path == "/" or path == "/index.html":
            file_path = os.path.join(WEB_DIR, "index.html")
            mime = "text/html; charset=utf-8"
        elif path.endswith(".css"):
            file_path = os.path.join(WEB_DIR, os.path.basename(path))
            mime = "text/css; charset=utf-8"
        elif path.endswith(".js"):
            file_path = os.path.join(WEB_DIR, os.path.basename(path))
            mime = "application/javascript; charset=utf-8"
        elif path.endswith(".svg"):
            file_path = os.path.join(WEB_DIR, os.path.basename(path))
            mime = "image/svg+xml"
        else:
            file_path = os.path.join(WEB_DIR, os.path.basename(path))
            mime = "text/plain"

        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, f"File Not Found: {path}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        try:
            req_json = json.loads(post_data.decode("utf-8")) if post_data else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        if path == "/api/run":
            code = req_json.get("code", "")
            optimize = req_json.get("optimize", True)
            engine = req_json.get("engine", "vm")
            sample_id = req_json.get("sample_id", None)
            res = execute_unitlang(code, optimize=optimize, engine=engine, sample_id=sample_id)
            self._send_json(res)
        elif path == "/api/run_all":
            res = run_all_samples()
            self._send_json(res)
        elif path == "/api/save_sample":
            rel_path = req_json.get("path")
            code = req_json.get("code", "")
            if rel_path and not (".." in rel_path):
                full_path = os.path.join(ROOT_DIR, rel_path)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(code)
                self._send_json({"ok": True, "message": f"Saved {rel_path}"})
            else:
                self.send_error(400, "Invalid path")
        else:
            self.send_error(404, "Unknown API endpoint")

    def _send_json(self, data):
        content = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Clean console log for server requests
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_server(port=8080, open_browser=True):
    # Ensure stdout/stderr don't crash on Windows cp1252 consoles
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Try preferred port, or fall back to consecutive ports
    server = None
    actual_port = port
    for p in range(port, port + 20):
        try:
            server = ThreadedHTTPServer(("127.0.0.1", p), UnitLangRequestHandler)
            actual_port = p
            break
        except OSError:
            continue

    if not server:
        print(f"Error: Could not bind to any port in range {port}-{port+20}")
        sys.exit(1)

    url = f"http://127.0.0.1:{actual_port}"
    print("=" * 64)
    print("  * UnitLang Interactive Web IDE")
    print(f"  * Running at: {url}")
    print("  * Features: Code Editor, Pipeline Explorer, Output & Diff, Test Suite")
    print("  * Press Ctrl+C to stop the server")
    print("=" * 64)

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping UnitLang IDE server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="UnitLang Web IDE Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open web browser automatically")
    args = parser.parse_args()

    start_server(port=args.port, open_browser=not args.no_browser)
