"""
Dimension vectors — the actual "type system" of UnitLang.

Every quantity's dimension is (L, M, T): exponents of Length, Mass,
and Time. Dimensionless values (plain numbers, booleans) are (0,0,0).

Arithmetic on dimensions mirrors arithmetic on the values themselves:
  - a + b, a - b  -> dimensions must be EQUAL, result keeps that dimension
  - a * b         -> dimensions ADD component-wise
  - a / b         -> dimensions SUBTRACT component-wise
  - a ^ n         -> dimension is MULTIPLIED by integer n

This is standard dimensional analysis (the same idea SI unit checking,
Frink, and F#'s units-of-measure use) — just implemented directly as a
small immutable vector class instead of pulled in from a library.
"""

from dataclasses import dataclass

_NAMES = ("L", "M", "T")


@dataclass(frozen=True)
class Dimension:
    L: int = 0
    M: int = 0
    T: int = 0

    def __add__(self, other):
        if self != other:
            raise DimensionError(self, other, "+")
        return self

    def __sub__(self, other):
        if self != other:
            raise DimensionError(self, other, "-")
        return self

    def __mul__(self, other):
        return Dimension(self.L + other.L, self.M + other.M, self.T + other.T)

    def __truediv__(self, other):
        return Dimension(self.L - other.L, self.M - other.M, self.T - other.T)

    def pow(self, n: int):
        return Dimension(self.L * n, self.M * n, self.T * n)

    def is_dimensionless(self):
        return self.L == 0 and self.M == 0 and self.T == 0

    def pretty(self):
        if self.is_dimensionless():
            return "dimensionless"
        labels = {"L": "Length", "M": "Mass", "T": "Time"}
        parts = []
        for name, exp in zip(_NAMES, (self.L, self.M, self.T)):
            if exp == 0:
                continue
            label = labels[name]
            parts.append(label if exp == 1 else f"{label}^{exp}")
        return " * ".join(parts)


DIMENSIONLESS = Dimension(0, 0, 0)
LENGTH = Dimension(1, 0, 0)
MASS = Dimension(0, 1, 0)
TIME = Dimension(0, 0, 1)


class DimensionError(Exception):
    """Raised internally by Dimension arithmetic; the semantic analyzer
    catches this and turns it into a friendly diagnostic (see
    semantic.py: `_binary_error_message`)."""

    def __init__(self, left, right, op):
        self.left, self.right, self.op = left, right, op
        super().__init__(
            f"dimension mismatch: {left.pretty()} {op} {right.pretty()}"
        )
