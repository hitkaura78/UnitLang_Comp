from helpers import run


def test_prefers_largest_unit_with_magnitude_at_least_one():
    assert run("print(5000 * m); print(100 * m); print(0.02 * m);") == ["5 km", "100 m", "2 cm"]


def test_time_units():
    assert run("print(9000 * s); print(30 * s); print(150 * s);") == ["2.5 hr", "30 s", "2.5 min"]


def test_mass_units():
    assert run("print(1500 * g); print(0.25 * kg);") == ["1.5 kg", "250 g"]


def test_derived_dimension_falls_back_to_base_units():
    assert run("print(10 * m / (2 * s));") == ["5 m/s"]
    assert run("print(3 * kg * 2 * m / s ^ 2);") == ["6 m*kg/s^2"]


def test_user_unit_wins_over_base_string():
    assert run("unit N = kg * m / s ^ 2; print(6 * kg * m / s ^ 2);") == ["6 N"]


def test_user_unit_hierarchy_picks_kN_for_large_values():
    out = run("unit N = kg * m / s ^ 2; unit kN = 1000 * N; print(4500 * N); print(6 * N);")
    assert out == ["4.5 kN", "6 N"]


def test_imperial_only_when_the_program_uses_imperial():
    assert run("print(5000 * m);") == ["5 km"]
    assert run("print(5000 * m); print(1 * mi);") == ["3.10686 mi", "1 mi"]


def test_zero_prints_in_base_unit():
    assert run("print(0 * m);") == ["0 m"]


def test_dimensionless_numbers_and_booleans():
    assert run("print(2 * 3); print(1 < 2); print(2.5);") == ["6", "true", "2.5"]
