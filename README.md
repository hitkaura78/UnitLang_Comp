# UnitLang — Review 2: Semantic Analysis & IR

UnitLang is a small statically-checked language where every number carries
a physical unit, and the compiler checks at compile time that operations
on those numbers actually make physical sense — `distance + time` gets
rejected the same way `int + bool` would in an ordinary type checker,
because Length and Time aren't the same dimension.

Review 1 covered the grammar and lexer. This review is about what happens
after parsing: turning the AST into something that's actually been
*checked*, and then into a form (IR) that a later code-generation phase
could work from.

## Running it

No dependencies beyond the standard library.

```bash
python3 main.py examples/basics.ul          # run a program
python3 main.py examples/basics.ul --ir     # also dump the generated IR
python3 -m pytest tests/                    # run the test suite
```

Try `examples/error_demo.ul` too — it's deliberately broken, to show what
a dimension-mismatch error actually looks like.

## Project layout

```
lexer.py        Review 1 — tokenizer (unchanged since last review)
parser.py       Review 1 — recursive-descent parser, + the new unitDecl rule
ast_nodes.py    AST node definitions
dimension.py    the actual "type system": (L, M, T) exponent vectors + arithmetic
symtab.py       symbol table: scoped variables + a unit name table
semantic.py     the dimensional-analysis checker (this review's core deliverable)
irgen.py        AST -> linear three-address code, with dimensions preserved
interpreter.py  tree-walking evaluator + the smart-print novelty feature
main.py         ties the pipeline together (lex -> parse -> check -> IR -> run)
examples/*.ul   sample programs, including one that's meant to fail
tests/          pytest suite covering the checker, IR, and interpreter
```

## How the type checking actually works

Every quantity's "type" is a `Dimension(L, M, T)` — exponents of Length,
Mass, and Time (`dimension.py`). A plain number is `(0,0,0)`. `m` is
`(1,0,0)`. `kg * m / s^2` works out to `(1,1,-2)`.

The semantic analyzer (`semantic.py`) walks the AST bottom-up and computes
a `Dimension` for every expression node:

| Expression | Rule |
|---|---|
| number / bool literal | dimensionless |
| identifier | dimension it was declared with, or a built-in unit's own dimension if it's a unit name being used as a value |
| `a + b`, `a - b` | dimensions must be **equal**; result keeps that dimension |
| `a * b` | dimensions **add** (component-wise) |
| `a / b` | dimensions **subtract** |
| `a ^ n` | `n` must be a literal integer; dimension is **multiplied by n** |
| `<`, `<=`, `==`, ... | operands must match dimension; result is dimensionless (booleans don't carry units) |

This is the same idea as any type checker unifying `int`/`float`/`bool` —
it's just that here the "types" are physics dimensions instead of the
usual scalar types, and the composition rules come from how physical
quantities actually combine.

### Symbol table & scoping

`symtab.py` keeps two separate tables, because they answer different
questions:

- **`units`**: "what does the identifier `km` mean?" → pre-loaded with the
  built-ins from Review 1 (`m`, `km`, `kg`, `s`, `hr`, ...), and extended
  at compile time by `unit` declarations (see Novelty #1 below).
- **`scopes`**: the ordinary variable table, as a stack of dictionaries —
  push on entering a block/function, pop on leaving, so a variable
  declared inside an `if` doesn't leak into the surrounding scope.

### Error handling

Dimension mismatches don't just say "type error" — see Novelty #3 below.
A bad top-level `qty` declaration is also given a dimensionless
placeholder after it's reported, so one mistake doesn't cascade into a
wall of unrelated "undeclared identifier" errors on every later line that
uses it.

## IR design

`irgen.py` lowers a *type-checked* AST (semantic analysis must have
already succeeded) into linear three-address code:

```
op, arg1, arg2, result
```

with `if`/`while`/`for` flattened into labels and conditional jumps, the
standard TAC treatment of control flow. Each temporary's `Dimension` is
kept alongside the code in a separate table, so a later code-generation
phase still has access to the physical dimension of every value without
re-deriving it — the type information the checker worked out doesn't get
thrown away once checking is done.

Example — this UnitLang snippet:

```
qty force = mass * accel;
print(force);
```

lowers to:

```
t17 = mass * accel  # Length * Mass * Time^-2
force = t17
print force
```

(Full dumps: run any example with `--ir`.)

## Novelty

Three things here go beyond what a minimal "check that units match"
project would do:

**1. User-defined units.** A fixed built-in list (`m`, `kg`, `s`, ...) is
fine for a toy example, but it doesn't scale to a real program — you'd
want `N` (newton) or `mph` without them being hardcoded. So UnitLang adds
a declaration:

```
unit N = kg * m / s ^ 2;
unit mph = mi / hr;
```

`semantic.py`'s `_check_unit_decl` / `_eval_unit_expr` evaluate the
right-hand side purely at the dimension + scale level (reusing the exact
same `Dimension` arithmetic used for checking ordinary expressions) and
register the result in the symbol table, so `N` and `mph` behave exactly
like built-in units for the rest of the program. See
`examples/custom_units.ul`.

**2. Smart unit selection on `print`.** Internally, every quantity is
just a float in base units (metres, kilograms, seconds) — printing it
raw would mean `qty d = 5000 * m; print(d);` outputs `5000`, which
defeats the point of a unit-aware language. `interpreter.py`'s
`smart_format()` instead looks at every unit (built-in or user-defined)
that shares the value's dimension and picks whichever one puts the
displayed number closest to a magnitude of 1 (`abs(log10(value/scale))`
minimized). So that same 5000 m prints as `3.1069 mi` — not necessarily
the unit a human would reach for first, but a deterministic, explainable
rule rather than a hardcoded preference table. Swapping in a "prefer
metric" or "prefer whichever unit was used most recently in this
program" rule instead would be a natural follow-up (see Known
Limitations).

**3. Diagnostic error messages.** Instead of a bare "dimension
mismatch," a failed check names the actual physical dimensions involved
and suggests what to do about it:

```
Semantic error at line 6: cannot use '+' between Length and Time —
they aren't the same physical dimension. If this is intentional,
convert one side to match the other's unit first.
```

## Known limitations / honest scope notes

These are the corners we deliberately cut for this review, rather than
bugs we missed:

- **Function parameters are treated as dimensionless.** Proper
  dimension-polymorphic functions (a `speed(dist, time)` that works for
  *any* matching pair of Length/Time) would need something like
  Hindley-Milner-style inference over dimension variables. Right now
  `fact(n)` works fine because it never mixes dimensions, but a generic
  `speed()` called with dimensioned arguments would need its parameters
  declared dimensionless-compatible or the checker extended — flagged
  here rather than silently wrong.
- **`smart_format`'s unit choice is a simple heuristic**, not a model of
  what a person would conventionally pick (it doesn't know "km" is more
  idiomatic than "mi" for everyday distances) — see Novelty #2.
- **No array/struct types**, matching the scope fixed in Review 1.

## What's next (Phase 3 / Review 3)

The IR above is designed to hand off cleanly to code generation: each
instruction is already in a flat, one-operation-at-a-time form, and every
temporary's dimension is still attached. Phase 3's job is to turn this
into target code (or a small stack-based VM, still undecided) — the
dimension annotations either get used for a final safety pass or erased
entirely once checking is done, depending on which approach we pick.

## Git repo note

This directory is a self-contained git repo (`git log` has the commit
history). To push it to GitHub under your own account:

```bash
git remote add origin <your-empty-repo-url>
git branch -M main
git push -u origin main
```
