"""scripts/loadtest/analyze.py 통계 함수 검증 — 전후 비교 결론이 이 계산에 달려 있다."""
import math

from scripts.loadtest.analyze import bootstrap_change_ci, mann_whitney_exact, pct


def test_percentile_linear_interpolation_matches_numpy_default():
    vals = [10, 20, 30, 40, 50]
    assert pct(vals, 50) == 30
    assert pct(vals, 95) == 48          # numpy.percentile(vals, 95) == 48.0
    assert pct([7], 99) == 7
    assert math.isnan(pct([], 50))


def test_mann_whitney_fully_separated_5v5():
    # 완전히 분리된 5 대 5 → 정확 양측 p = 2/252 ≈ 0.0079 (가능한 최소값)
    u, p = mann_whitney_exact([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert u == 0
    assert abs(p - 2 / 252) < 1e-9


def test_mann_whitney_identical_groups_not_significant():
    _, p = mann_whitney_exact([5, 5, 5], [5, 5, 5])
    assert p == 1.0


def test_bootstrap_ci_contains_true_change():
    before = [100, 102, 98, 101, 99]
    after = [80, 82, 78, 81, 79]         # 약 −20%
    lo, hi = bootstrap_change_ci(before, after)
    assert lo <= -20 <= hi
    assert hi < 0
