"""
TAC optimizer (Review 3 plan, implemented).

Pass 1 - constant folding with UNIT CONSTANT FOLDING (novelty #5)
    A unit identifier (m, km, hr, or a user-defined N) is a compile-time
    constant: its value in base units is already in the symbol table. So
    `5 * km`, `9.8 * m / s ^ 2` or `2 * hr + 30 * min` are evaluated by the
    compiler - dimension tag included - and replaced by a single immediate
    constant. Generic constant folding (`2 * 3 * 4`) falls out of the same
    mechanism. Constants are also propagated into the instructions that use
    them.

Pass 2 - dead-code elimination
    Pure instructions (constants, arithmetic, comparisons) whose result
    temporary is never read are deleted. Calls, prints and variable
    stores are never removed.

Temporaries are written exactly once (the IR generator guarantees this),
so a temporary that holds a constant holds it everywhere it is used.
"""

from dataclasses import dataclass, field

from quantity import Quantity, RuntimeErr, apply_binary, apply_unary
from irgen import BINARY_OPS


@dataclass(frozen=True)
class Imm:
    """An immediate (compile-time constant) operand."""
    value: object          # Quantity or bool

    def __repr__(self):
        v = self.value
        if isinstance(v, bool):
            return "true" if v else "false"
        return repr(v)


@dataclass
class OptStats:
    folded: int = 0            # operations evaluated at compile time
    unit_folds: int = 0        # ...of which involved a unit identifier
    unit_inlines: int = 0      # unit names replaced by their constant value
    propagated: int = 0        # constant temporaries substituted into uses
    dead: int = 0              # dead instructions removed
    tac_before: int = 0
    tac_after: int = 0
    peephole: int = 0          # STORE/LOAD pairs removed (set by codegen)
    bc_before: int = 0
    bc_after: int = 0


PURE_OPS = BINARY_OPS | {"const", "unary-", "unary!"}


def is_temp(x):
    return isinstance(x, str) and x.startswith("%t")


def uses(op, a1, a2):
    if op == "const":
        return []
    if op in BINARY_OPS:
        return [a1, a2]
    if op.startswith("unary"):
        return [a1]
    if op in ("=", "decl", "print", "return", "if_false"):
        return [a1] if a1 is not None else []
    if op == "call":
        return list(a2)
    return []


def _normalize_const(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, Quantity):
        return v
    return Quantity(float(v))


def fold_constants(tac, units, stats: OptStats):
    consts = {}                      # temp -> (value, derived_from_unit)
    out = []

    def resolve(x):
        """-> (Imm | None, came_from_unit)"""
        if isinstance(x, Imm):
            return x, False
        if is_temp(x):
            if x in consts:
                v, fu = consts[x]
                return Imm(v), fu
            return None, False
        if isinstance(x, str) and x in units:
            u = units[x]
            return Imm(Quantity(u.scale, u.dim)), True
        return None, False

    def subst(x):
        imm, from_unit = resolve(x)
        if imm is None:
            return x
        if from_unit and not is_temp(x):
            stats.unit_inlines += 1
        elif is_temp(x):
            stats.propagated += 1
        return imm

    for op, a1, a2, res in tac:
        if op == "const":
            v = _normalize_const(a1)
            consts[res] = (v, False)
            out.append(("const", v, None, res))
            continue

        if op in BINARY_OPS:
            ia, fa = resolve(a1)
            ib, fb = resolve(a2)
            if ia is not None and ib is not None:
                try:
                    v = apply_binary(op, ia.value, ib.value)
                except RuntimeErr:
                    v = None         # e.g. 1/0 - leave for run time
                if v is not None:
                    stats.folded += 1
                    if fa or fb:
                        stats.unit_folds += 1
                    consts[res] = (v, fa or fb)
                    out.append(("const", v, None, res))
                    continue
            out.append((op, subst(a1), subst(a2), res))
            continue

        if op in ("unary-", "unary!"):
            ia, fa = resolve(a1)
            if ia is not None:
                try:
                    v = apply_unary(op[5:], ia.value)
                except RuntimeErr:
                    v = None
                if v is not None:
                    stats.folded += 1
                    if fa:
                        stats.unit_folds += 1
                    consts[res] = (v, fa)
                    out.append(("const", v, None, res))
                    continue
            out.append((op, subst(a1), None, res))
            continue

        if op in ("=", "decl", "print", "return", "if_false"):
            out.append((op, subst(a1) if a1 is not None else None, a2, res))
            continue

        if op == "call":
            out.append((op, a1, tuple(subst(a) for a in a2), res))
            continue

        out.append((op, a1, a2, res))      # labels, goto, func_begin/end
    return out


def eliminate_dead(tac, stats: OptStats):
    while True:
        used = set()
        for op, a1, a2, _ in tac:
            for u in uses(op, a1, a2):
                if is_temp(u):
                    used.add(u)
        kept = []
        for ins in tac:
            op, _, _, res = ins
            if op in PURE_OPS and is_temp(res) and res not in used:
                stats.dead += 1
                continue
            kept.append(ins)
        if len(kept) == len(tac):
            return kept
        tac = kept


def optimize_tac(tac, units, stats: OptStats = None):
    stats = stats if stats is not None else OptStats()
    stats.tac_before = len(tac)
    tac = fold_constants(tac, units, stats)
    tac = eliminate_dead(tac, stats)
    stats.tac_after = len(tac)
    return tac, stats
