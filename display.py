"""
Context-aware unit selection for `print` (novelty #3).

A quantity is stored in base units, so printing the raw float would throw
away the whole point of a unit-aware language. `format_quantity` chooses
a display unit with a small, deterministic, explainable rule:

  1. Candidates are every unit whose dimension equals the value's.
  2. If the PROGRAM DEFINED a unit of that dimension (e.g. `unit N = ...`)
     only those user-defined units are candidates - the programmer's own
     vocabulary wins.
  3. Otherwise candidates are the built-in SI units, plus imperial units
     (mi, ft, lb) ONLY if the program itself mentioned an imperial unit.
  4. Among candidates choose the largest unit in which the magnitude is
     still >= 1 (engineering-style: 5000 m -> 5 km, 100 m -> 100 m,
     9000 s -> 2.5 hr); if the value is smaller than every candidate,
     use the smallest one.
  5. A derived dimension with no candidate (e.g. speed) falls back to a
     composed base-unit string such as m/s or kg*m/s^2.
"""

from dimension import Dimension

_EPS = 1e-9


def format_number(x: float) -> str:
    if abs(x) < 1e15 and abs(x - round(x)) <= _EPS * max(1.0, abs(x)):
        return str(int(round(x)))
    s = f"{x:.6g}"
    return s


def base_unit_string(dim: Dimension) -> str:
    num, den = [], []
    for sym, e in (("m", dim.L), ("kg", dim.M), ("s", dim.T)):
        if e > 0:
            num.append(sym if e == 1 else f"{sym}^{e}")
        elif e < 0:
            den.append(sym if e == -1 else f"{sym}^{-e}")
    top = "*".join(num) if num else "1"
    if not den:
        return top
    bottom = den[0] if len(den) == 1 else "(" + "*".join(den) + ")"
    return f"{top}/{bottom}"


def pick_unit(value: float, dim: Dimension, units: dict, used: set):
    """Return (unit_name, scale)."""
    matches = [u for u in units.values() if u.dim == dim]
    user = [u for u in matches if u.origin == "user"]
    if user:
        pool = user
    else:
        pool = [u for u in matches if u.system == "SI" or u.name in used]
    if not pool:
        return base_unit_string(dim), 1.0

    if value == 0:
        base = [u for u in pool if u.scale == 1.0]
        u = base[0] if base else min(pool, key=lambda x: x.scale)
        return u.name, u.scale

    ordered = sorted(pool, key=lambda u: u.scale, reverse=True)
    for u in ordered:
        if abs(value) / u.scale >= 1 - _EPS:
            return u.name, u.scale
    u = ordered[-1]
    return u.name, u.scale


def format_quantity(q, units: dict, used: set) -> str:
    if q.dim.is_dimensionless():
        return format_number(q.value)
    name, scale = pick_unit(q.value, q.dim, units, used)
    return f"{format_number(q.value / scale)} {name}"
