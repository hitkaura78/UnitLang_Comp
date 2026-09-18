"""
Symbol table for UnitLang.

Two separate namespaces live here, because they answer two different
questions:

  - `units`: "if I see the identifier `km`, what dimension and scale
    factor does it carry?" Pre-populated with the built-ins from the
    Review 1 spec, and extended at compile time whenever the semantic
    analyzer processes a `unit` declaration (the novelty feature).

  - `scopes`: the normal variable/function symbol table, with proper
    lexical scoping (a new scope per block/function) so a variable
    declared inside an `if` doesn't leak out of it.
"""

from dimension import Dimension, LENGTH, MASS, TIME, DIMENSIONLESS


class UnitEntry:
    __slots__ = ("name", "dim", "scale")

    def __init__(self, name, dim: Dimension, scale: float):
        self.name = name
        self.dim = dim
        self.scale = scale  # value of 1 <name> expressed in base units

    def __repr__(self):
        return f"UnitEntry({self.name}, {self.dim.pretty()}, scale={self.scale})"


# built-in unit table, values in base units (m, kg, s) — see Review 1, Sec 3.1
BUILTIN_UNITS = {
    "m":   UnitEntry("m", LENGTH, 1.0),
    "km":  UnitEntry("km", LENGTH, 1000.0),
    "cm":  UnitEntry("cm", LENGTH, 0.01),
    "mi":  UnitEntry("mi", LENGTH, 1609.34),
    "ft":  UnitEntry("ft", LENGTH, 0.3048),
    "kg":  UnitEntry("kg", MASS, 1.0),
    "g":   UnitEntry("g", MASS, 0.001),
    "lb":  UnitEntry("lb", MASS, 0.453592),
    "s":   UnitEntry("s", TIME, 1.0),
    "ms":  UnitEntry("ms", TIME, 0.001),
    "min": UnitEntry("min", TIME, 60.0),
    "hr":  UnitEntry("hr", TIME, 3600.0),
}


class VarEntry:
    __slots__ = ("name", "dim")

    def __init__(self, name, dim: Dimension):
        self.name = name
        self.dim = dim


class SymbolTable:
    def __init__(self):
        # unit namespace: starts with the built-ins, user `unit` decls add more
        self.units = dict(BUILTIN_UNITS)
        # variable namespace: stack of scopes, innermost last
        self.scopes = [{}]
        # function namespace: name -> (param names, body) filled by the analyzer
        self.functions = {}

    # -- unit namespace ---------------------------------------------------
    def define_unit(self, name, dim: Dimension, scale: float):
        self.units[name] = UnitEntry(name, dim, scale)

    def lookup_unit(self, name):
        return self.units.get(name)

    # -- variable namespace, with scoping -----------------------------------
    def push_scope(self):
        self.scopes.append({})

    def pop_scope(self):
        self.scopes.pop()

    def declare_var(self, name, dim: Dimension):
        self.scopes[-1][name] = VarEntry(name, dim)

    def lookup_var(self, name):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

    def assign_ok(self, name):
        """True if `name` already exists in some enclosing scope."""
        return self.lookup_var(name) is not None
