# UnitLang

A small statically-checked programming language in which **every number carries a
physical unit**, with a complete compiler: lexer → parser → dimensional type
checker → IR → optimizer → bytecode generator → virtual machine.

`distance + time` is rejected at compile time, the same way `int + bool` would be in
an ordinary language — because Length and Time are different *dimensions*.

```
qty distance = 100 * m;
qty time     = 9.58 * s;
print(distance / time);        // 10.4384 m/s
print(distance + time);        // compile error: Length and Time ...
```

Pure Python 3.10+ standard library. **No installation needed.** (`pytest` is only
needed to run the tests.)

## Quick start

```bash
python3 main.py examples/01_basics.ul
python3 main.py examples/03_polymorphic_functions.ul --symbols
python3 main.py examples/05_optimizer_demo.ul --stats
python3 main.py examples/09_error_dimensions.ul
python3 -m pytest tests -q
```

| Flag | What it shows |
|---|---|
| *(none)* | compile and run on the bytecode VM |
| `--ir` | three-address code, before and after optimization |
| `--bytecode` | the generated stack-machine bytecode |
| `--symbols` | unit table, global variables, inferred function instances |
| `--stats` | optimizer counters and number of VM instructions executed |
| `--no-opt` | disable the optimizer (compare with `--stats`) |
| `--interp` | run on the reference tree-walking interpreter instead of the VM |
| `--check` | type-check only |

Exit status: `0` success, `1` compile-time error, `2` runtime error.

## Pipeline

```
source ─► lexer ─► parser ─► semantic analysis ─► IR generator ─► optimizer ─► code generator ─► VM
          tokens    AST       dimension check       TAC           fold + DCE    bytecode+peephole  run
```

| File | Role |
|---|---|
| `lexer.py` | hand-written maximal-munch scanner, multi-error recovery |
| `parser.py`, `ast_nodes.py` | recursive-descent parser, AST |
| `dimension.py` | the type system: (Length, Mass, Time) exponent vectors |
| `symtab.py` | unit table + scoped variable table |
| `semantic.py` | dimensional analysis, polymorphic function instances, diagnostics |
| `irgen.py` | AST → three-address code |
| `optimizer.py` | unit constant folding, dead-code elimination |
| `codegen.py` | TAC → stack bytecode, peephole pass, assembler, disassembler |
| `vm.py` | stack virtual machine |
| `quantity.py` | runtime tagged values and arithmetic |
| `display.py` | context-aware unit selection for `print` |
| `interpreter.py` | reference tree-walking interpreter (test oracle) |
| `pipeline.py`, `main.py` | pipeline entry point, CLI |
| `run_review2.py` | Review 2 snapshot: stops after IR generation |

## The language

```
program   ::= { funcDecl | unitDecl | statement }
unitDecl  ::= "unit" IDENT "=" expression ";"
funcDecl  ::= "fn" IDENT "(" [ IDENT { "," IDENT } ] ")" block
statement ::= "qty" IDENT "=" expr ";" | IDENT "=" expr ";" | if | while | for
            | "return" [expr] ";" | "print" "(" expr ")" ";" | block | expr ";"
```

Built-in units (scale in base units m, kg, s):
`m 1`, `km 1000`, `cm 0.01`, `mi 1609.34`, `ft 0.3048`, `kg 1`, `g 0.001`,
`lb 0.453592`, `s 1`, `ms 0.001`, `min 60`, `hr 3600`.

Rules: `+`, `-` and comparisons need equal dimensions (a literal `0` adapts to any);
`*` and `/` combine dimensions; `^` needs an integer literal exponent; conditions
and `&& || !` need plain numbers; a unit name cannot be a variable; no shadowing
inside a function; functions see top-level variables declared before the call.

## Novelty

1. **User-defined units** — `unit N = kg * m / s ^ 2;` The compiler computes the new
   unit's dimension *and* scale at compile time and registers it (`examples/02`).
2. **Dimension-polymorphic functions** — parameters carry no annotations; each call
   site creates an *instance* checked with that call's argument dimensions, and the
   return dimension is inferred. `--symbols` lists the instances (`examples/03`).
3. **Context-aware printing** — `print` picks the display unit: your own units win;
   otherwise the largest SI unit with magnitude ≥ 1; imperial units only if the
   program itself used one; derived dimensions fall back to `m/s`, `m*kg/s^2`
   (`examples/07`, `08`).
4. **Diagnostic errors** — messages name the physical dimensions, say how to fix the
   problem, suggest `did you mean ...?`, and, for errors inside a polymorphic
   function, name the call that triggered them (`examples/09`–`11`).
5. **Unit constant folding** — the optimizer treats unit identifiers as compile-time
   constants, so `5 * km + 300 * m` and `9.8 * m / s ^ 2` become single immediates
   carrying their dimension (`examples/05`, `--stats`).

## Sample programs and expected output

| Program | Shows | Expected output |
|---|---|---|
| `01_basics.ul` | normal working | `100 m`, `9.58 s`, `10.4384 m/s`, `2.5 hr`, `49 m*kg/s^2`, `1.5 km`, `250 g` |
| `02_custom_units.ul` | novelty 1 | `6 N`, `4.5 kN`, `60 mph`, `5 N` |
| `03_polymorphic_functions.ul` | novelty 2 | `10.4384 m/s`, `5.81151 m/s`, `9 J`, `8 m`, `6`, `120` |
| `04_control_flow.ul` | loops, conditions | `2.5 hr`, `4`, `1.6 km`, `2 km`, `1 km`, `0 m` |
| `05_optimizer_demo.ul` | novelty 5 | `5.3 km`, `24`, `500 km` |
| `06_showcase_physics.ul` | everything together | `686.7 N`, `2060.1 J`, `412.02 W` |
| `07_context_aware_print.ul` | novelty 3 | `5 km`, `100 m`, `2.5 hr` |
| `08_imperial_context.ul` | novelty 3 | `26.2 mi`, `3.10686 mi` |
| `09_error_dimensions.ul` | novelty 4 | 3 dimension errors, exit 1 |
| `10_error_names.ul` | novelty 4 | 4 name errors incl. `did you mean 'speed'?`, exit 1 |
| `11_error_function_context.ul` | novelty 4 | error `[while checking 'addOne' called with (Length)]`, exit 1 |
| `12_runtime_error.ul` | runtime error | `Runtime error: division by zero`, exit 2 |

## How correctness is checked

`tests/` holds 72 tests. The key idea: every working example is executed three ways —
the reference interpreter, the optimized VM, and the unoptimized VM — and all three must
print identical output. That validates the code generator and the optimizer without
hand-writing expected values for each program.

## Known limitations

- `&&` and `||` evaluate both operands (no short-circuit).
- Only three base dimensions (Length, Mass, Time); no temperature, current, etc.
- Exponents must be integer literals; functions cannot be passed as values.
- A function that is never called is not type-checked (a warning is printed).
- The display-unit rule is a simple heuristic, not a model of convention.
