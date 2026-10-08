"""
Code generator: (optimized) TAC -> stack-machine bytecode.

Bytecode instructions are (opcode, operand) pairs:

    PUSH_CONST q     LOAD name      STORE name     DECL name     POP
    ADD SUB MUL DIV POW             LT LE GT GE EQ NE            AND OR
    NEG NOT          JMP label      JMP_IF_FALSE label
    PRINT            CALL (name, argc)       RET flag            HALT

Mapping from TAC (Review 3, section 2.2):

    %t = a op b   ->  <load a> <load b> OP  STORE %t
    declare x = a ->  <load a> DECL x         x = a -> <load a> STORE x
    if_false a L  ->  <load a> JMP_IF_FALSE L
    call f(args)  ->  <load each arg> CALL f,n  STORE %t

where <load x> is PUSH_CONST for an immediate operand and LOAD otherwise.

Temporaries live in frame slots, so STORE/LOAD pairs appear around every
sub-expression. A peephole pass removes the redundant ones: if a temporary
is stored and then loaded exactly once, immediately, the value simply stays
on the operand stack. A temporary that is never loaded (an unused call
result) becomes POP.

Labels are symbolic until `assemble` turns them into instruction indices.
"""

from collections import Counter
from dataclasses import dataclass, field

from quantity import Quantity
from optimizer import Imm, OptStats, is_temp

OPCODES = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "^": "POW",
           "<": "LT", "<=": "LE", ">": "GT", ">=": "GE", "==": "EQ",
           "!=": "NE", "&&": "AND", "||": "OR"}


@dataclass
class BytecodeProgram:
    main: list
    functions: dict = field(default_factory=dict)    # name -> (params, code)


def _const_value(v):
    if isinstance(v, (bool, Quantity)):
        return v
    return Quantity(float(v))


def _load(x):
    if isinstance(x, Imm):
        return ("PUSH_CONST", x.value)
    return ("LOAD", x)


def _translate(tac_chunk):
    code = []
    for op, a1, a2, res in tac_chunk:
        if op == "const":
            code.append(("PUSH_CONST", _const_value(a1)))
            code.append(("STORE", res))
        elif op in OPCODES:
            code += [_load(a1), _load(a2), (OPCODES[op], None), ("STORE", res)]
        elif op in ("unary-", "unary!"):
            code += [_load(a1), ("NEG" if op == "unary-" else "NOT", None),
                     ("STORE", res)]
        elif op == "=":
            code += [_load(a1), ("STORE", res)]
        elif op == "decl":
            code += [_load(a1), ("DECL", res)]
        elif op == "label":
            code.append(("LABEL", res))
        elif op == "goto":
            code.append(("JMP", res))
        elif op == "if_false":
            code += [_load(a1), ("JMP_IF_FALSE", res)]
        elif op == "print":
            code += [_load(a1), ("PRINT", None)]
        elif op == "return":
            if a1 is not None:
                code += [_load(a1), ("RET", True)]
            else:
                code.append(("RET", False))
        elif op == "call":
            for a in a2:
                code.append(_load(a))
            code += [("CALL", (a1, len(a2))), ("STORE", res)]
        else:
            raise ValueError(f"codegen: unknown TAC op {op!r}")
    return code


def peephole(code, stats: OptStats):
    loads = Counter(arg for op, arg in code if op == "LOAD" and is_temp(arg))
    out, i = [], 0
    while i < len(code):
        op, arg = code[i]
        if op == "STORE" and is_temp(arg):
            if loads[arg] == 0:
                out.append(("POP", None))
                i += 1
                continue
            if (loads[arg] == 1 and i + 1 < len(code)
                    and code[i + 1] == ("LOAD", arg)):
                stats.peephole += 1
                i += 2
                continue
        out.append(code[i])
        i += 1
    return out


def assemble(code):
    labels, flat = {}, []
    for op, arg in code:
        if op == "LABEL":
            labels[arg] = len(flat)
        else:
            flat.append((op, arg))
    return [(op, labels[arg]) if op in ("JMP", "JMP_IF_FALSE") else (op, arg)
            for op, arg in flat]


def generate(tac, optimize=True, stats: OptStats = None) -> BytecodeProgram:
    stats = stats if stats is not None else OptStats()
    chunks = {"__main__": ([], [])}
    current = "__main__"
    for ins in tac:
        op, a1, a2, _ = ins
        if op == "func_begin":
            current = a1
            chunks[current] = (list(a2), [])
        elif op == "func_end":
            current = "__main__"
        else:
            chunks[current][1].append(ins)

    def build(tac_chunk, tail):
        raw = _translate(tac_chunk) + [tail]
        stats.bc_before += len(raw)
        if optimize:
            raw = peephole(raw, stats)
        asm = assemble(raw)
        stats.bc_after += len(asm)
        return asm

    main = build(chunks["__main__"][1], ("HALT", None))
    functions = {}
    for name, (params, body) in chunks.items():
        if name != "__main__":
            functions[name] = (params, build(body, ("RET", False)))
    return BytecodeProgram(main, functions)


def _fmt_operand(op, arg):
    if arg is None:
        return ""
    if op == "CALL":
        return f"{arg[0]}, {arg[1]}"
    if op == "RET":
        return "value" if arg else "(none)"
    return repr(arg)


def disassemble(program: BytecodeProgram) -> str:
    lines = ["== main =="]
    for i, (op, arg) in enumerate(program.main):
        lines.append(f"{i:4d}  {op:<13}{_fmt_operand(op, arg)}".rstrip())
    for name, (params, code) in program.functions.items():
        lines.append(f"\n== function {name}({', '.join(params)}) ==")
        for i, (op, arg) in enumerate(code):
            lines.append(f"{i:4d}  {op:<13}{_fmt_operand(op, arg)}".rstrip())
    return "\n".join(lines)
