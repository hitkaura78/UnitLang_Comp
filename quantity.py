"""
Runtime values for UnitLang.

Every number at runtime is a Quantity: a float magnitude in BASE units
(metres, kilograms, seconds) plus the Dimension it carries. Booleans are
plain Python bools. This is the "tagged value" design chosen in Review 3:
arithmetic copies/combines dimension tags, and PRINT reads the tag to
choose a display unit.

Both execution engines (the tree-walking interpreter and the bytecode VM)
use the functions in this file, so they can never disagree about what
`a + b` or `a ^ 2` means - they can only disagree about control flow,
scoping or code generation, which is exactly what the test-suite checks.
"""

from dataclasses import dataclass

from dimension import Dimension, DIMENSIONLESS


class RuntimeErr(Exception):
    """Raised for errors that can only be detected while running
    (division by zero, call-depth overflow, step limit...)."""


@dataclass(frozen=True)
class Quantity:
    value: float
    dim: Dimension = DIMENSIONLESS

    def __repr__(self):
        v = f"{self.value:g}"
        if self.dim.is_dimensionless():
            return v
        return f"{v}<{self.dim.pretty()}>"


def as_q(v):
    """Coerce a runtime value to a Quantity (bools become 1.0 / 0.0)."""
    if isinstance(v, Quantity):
        return v
    if isinstance(v, bool):
        return Quantity(1.0 if v else 0.0)
    if v is None:
        raise RuntimeErr("a function that returns no value was used in an expression")
    raise RuntimeErr(f"unusable runtime value {v!r}")


def truthy(v):
    if isinstance(v, bool):
        return v
    return as_q(v).value != 0


def _match_dims(a: Quantity, b: Quantity, op: str):
    """Return (a, b) with equal dimensions, or raise.

    A dimensionless zero is compatible with every dimension (0 m == 0 s
    physically), which is what lets `while (distance > 0)` work."""
    if a.dim == b.dim:
        return a, b
    if a.dim.is_dimensionless() and a.value == 0:
        return Quantity(0.0, b.dim), b
    if b.dim.is_dimensionless() and b.value == 0:
        return a, Quantity(0.0, a.dim)
    raise RuntimeErr(
        f"dimension mismatch at runtime: {a.dim.pretty()} {op} {b.dim.pretty()}"
    )


def apply_binary(op: str, a, b):
    if op in ("&&", "||"):
        return (truthy(a) and truthy(b)) if op == "&&" else (truthy(a) or truthy(b))

    a, b = as_q(a), as_q(b)

    if op in ("+", "-"):
        a, b = _match_dims(a, b, op)
        return Quantity(a.value + b.value if op == "+" else a.value - b.value, a.dim)
    if op == "*":
        return Quantity(a.value * b.value, a.dim * b.dim)
    if op == "/":
        if b.value == 0:
            raise RuntimeErr("division by zero")
        return Quantity(a.value / b.value, a.dim / b.dim)
    if op == "^":
        if not b.dim.is_dimensionless() or not float(b.value).is_integer():
            raise RuntimeErr("exponent must be a dimensionless integer")
        n = int(b.value)
        try:
            return Quantity(a.value ** n, a.dim.pow(n))
        except ZeroDivisionError:
            raise RuntimeErr("zero raised to a negative power")
        except OverflowError:
            raise RuntimeErr("numeric overflow in exponentiation")
    if op in ("<", "<=", ">", ">=", "==", "!="):
        a, b = _match_dims(a, b, op)
        x, y = a.value, b.value
        return {"<": x < y, "<=": x <= y, ">": x > y,
                ">=": x >= y, "==": x == y, "!=": x != y}[op]
    raise RuntimeErr(f"unknown operator '{op}'")


def apply_unary(op: str, a):
    if op == "-":
        a = as_q(a)
        return Quantity(-a.value, a.dim)
    if op == "!":
        return not truthy(a)
    raise RuntimeErr(f"unknown unary operator '{op}'")
