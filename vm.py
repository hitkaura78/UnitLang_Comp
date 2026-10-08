"""
Stack-based virtual machine for UnitLang bytecode.

Values on the operand stack are tagged: a Quantity (magnitude in base
units + Dimension) or a bool. Arithmetic opcodes delegate to
quantity.apply_binary, which copies/combines the tags; PRINT is the one
opcode that reads a tag in order to choose a display unit.

Frames are plain dicts. Temporaries (names starting with '%') are always
frame-local. Other names resolve frame -> globals -> unit table, so a
function can read and update top-level variables and can use any unit.
"""

from quantity import Quantity, RuntimeErr, apply_binary, apply_unary, truthy
from display import format_quantity

BINARY = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "POW": "^",
          "LT": "<", "LE": "<=", "GT": ">", "GE": ">=", "EQ": "==",
          "NE": "!=", "AND": "&&", "OR": "||"}


class VM:
    MAX_STEPS = 5_000_000
    MAX_DEPTH = 200

    def __init__(self, program, units, used_units=None, echo=False):
        self.program = program
        self.units = units
        self.used = used_units or set()
        self.unit_values = {n: Quantity(u.scale, u.dim) for n, u in units.items()}
        self.globals = {}
        self.output = []
        self.echo = echo
        self.steps = 0

    # ------------------------------------------------------------------
    def run(self):
        self._exec(self.program.main, self.globals, 0)
        return self.output

    def _lookup(self, name, frame):
        if name in frame:
            return frame[name]
        if name in self.globals:
            return self.globals[name]
        if name in self.unit_values:
            return self.unit_values[name]
        raise RuntimeErr(f"undefined name '{name}'")

    def _store(self, name, value, frame):
        if name.startswith("%") or name in frame:
            frame[name] = value
        elif name in self.globals:
            self.globals[name] = value
        else:
            frame[name] = value

    def _print(self, v):
        if isinstance(v, bool):
            line = "true" if v else "false"
        elif isinstance(v, Quantity):
            line = format_quantity(v, self.units, self.used)
        else:
            raise RuntimeErr("cannot print: a function that returns no value was used")
        self.output.append(line)
        if self.echo:
            print(line)

    # ------------------------------------------------------------------
    def _exec(self, code, frame, depth):
        stack = []
        ip = 0
        while True:
            self.steps += 1
            if self.steps > self.MAX_STEPS:
                raise RuntimeErr("step limit exceeded (possible infinite loop)")
            op, arg = code[ip]
            ip += 1

            if op == "PUSH_CONST":
                stack.append(arg)
            elif op == "LOAD":
                stack.append(self._lookup(arg, frame))
            elif op == "STORE":
                self._store(arg, stack.pop(), frame)
            elif op == "DECL":
                frame[arg] = stack.pop()
            elif op == "POP":
                stack.pop()
            elif op in BINARY:
                b = stack.pop()
                a = stack.pop()
                stack.append(apply_binary(BINARY[op], a, b))
            elif op == "NEG":
                stack.append(apply_unary("-", stack.pop()))
            elif op == "NOT":
                stack.append(apply_unary("!", stack.pop()))
            elif op == "JMP":
                ip = arg
            elif op == "JMP_IF_FALSE":
                if not truthy(stack.pop()):
                    ip = arg
            elif op == "PRINT":
                self._print(stack.pop())
            elif op == "CALL":
                name, argc = arg
                if depth + 1 > self.MAX_DEPTH:
                    raise RuntimeErr("maximum call depth exceeded (runaway recursion?)")
                params, fcode = self.program.functions[name]
                args = stack[len(stack) - argc:] if argc else []
                if argc:
                    del stack[len(stack) - argc:]
                stack.append(self._exec(fcode, dict(zip(params, args)), depth + 1))
            elif op == "RET":
                return stack.pop() if arg else None
            elif op == "HALT":
                return None
            else:
                raise RuntimeErr(f"unknown opcode {op}")
