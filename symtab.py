"""
Symbol table for UnitLang.

Two separate namespaces, because they answer two different questions:

  - `units`: "if I see the identifier `km`, what dimension and scale
    factor does it carry?"  Pre-populated with the built-ins and extended
    at compile time by `unit` declarations (novelty #1). Each entry also
    records its `origin` (builtin / user) and `system` (SI / imperial /
    user); the context-aware printer (novelty #3) uses both.

  - `scopes`: the variable table, a stack of dictionaries with proper
    lexical scoping (a new scope per block / function).

`used_units` records which unit identifiers the program actually mentions;
the printer only reaches for imperial units (mi, ft, lb) if the program
itself used one.
"""

from dimension import Dimension, LENGTH, MASS, TIME


class UnitEntry:
    __slots__ = ("name", "dim", "scale", "origin", "system")

    def __init__(self, name, dim: Dimension, scale: float,
                 origin="builtin", system="SI"):
        self.name = name
        self.dim = dim
        self.scale = scale      # value of 1 <name> in base units (m, kg, s)
        self.origin = origin    # "builtin" | "user"
        self.system = system    # "SI" | "imperial" | "user"

    def __repr__(self):
        return f"UnitEntry({self.name}, {self.dim.pretty()}, scale={self.scale})"


def _builtin_units():
    rows = [
        ("m", LENGTH, 1.0, "SI"), ("km", LENGTH, 1000.0, "SI"),
        ("cm", LENGTH, 0.01, "SI"), ("mi", LENGTH, 1609.34, "imperial"),
        ("ft", LENGTH, 0.3048, "imperial"),
        ("kg", MASS, 1.0, "SI"), ("g", MASS, 0.001, "SI"),
        ("lb", MASS, 0.453592, "imperial"),
        ("s", TIME, 1.0, "SI"), ("ms", TIME, 0.001, "SI"),
        ("min", TIME, 60.0, "SI"), ("hr", TIME, 3600.0, "SI"),
    ]
    return {n: UnitEntry(n, d, sc, "builtin", sysm) for n, d, sc, sysm in rows}


BUILTIN_UNITS = _builtin_units()


class VarEntry:
    __slots__ = ("name", "dim")

    def __init__(self, name, dim: Dimension):
        self.name = name
        self.dim = dim


class SymbolTable:
    def __init__(self):
        self.units = dict(BUILTIN_UNITS)
        self.used_units = set()
        self.scopes = [{}]          # scopes[0] is the global scope
        self.functions = {}         # name -> FuncDecl

    # -- unit namespace -----------------------------------------------
    def define_unit(self, name, dim: Dimension, scale: float):
        self.units[name] = UnitEntry(name, dim, scale, "user", "user")

    def lookup_unit(self, name):
        return self.units.get(name)

    # -- variable namespace -------------------------------------------
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

    def all_var_names(self):
        names = set()
        for scope in self.scopes:
            names.update(scope)
        return names
