"""k6 raw 결과(JSON) 분석 — docs/performance.md §2.6

Grafana/InfluxDB 의 윈도우 percentile 은 평균 낼 수 없으므로(수학적으로 틀림)
최종 수치는 여기서 raw 샘플로 다시 계산한다. 표준 라이브러리만 사용.

사용법:
    python3 scripts/loadtest/analyze.py run <RUN_DIR>              # 1회 실행 분석
    python3 scripts/loadtest/analyze.py label <LABEL_DIR> [PROFILE]  # 같은 설정의 여러 회 집계
    python3 scripts/loadtest/analyze.py compare <BEFORE_DIR> <AFTER_DIR> [PROFILE]

규칙:
  - percentile: 선형 보간(numpy 기본과 동일)
  - load: 앞 120초(램프 60초 + 안정화 60초) 제외한 steady 구간만
  - stress: 단계(180초)마다 앞 30초 제외
  - breakpoint: 60초 구간별 — SLO(API p95<500ms, 에러<1%)를 지킨 마지막 구간의 달성 RPS 가 용량
  - 여러 회 집계: 실행별 값의 중앙값 [최소–최대] (percentile 끼리 평균 내지 않음)
  - 전후 비교: 실행 단위 Mann-Whitney U (정확 분포, 양측) + 중앙값 변화율의 부트스트랩 95% CI
"""
from __future__ import annotations

import gzip
import itertools
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

WARMUP = {"smoke": 0, "load": 120}
STAGE_SECS, STAGE_SKIP = 180, 30
SLO_API_P95, SLO_ERR = 500.0, 0.01


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _ts(t: str) -> float:
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()


def load_points(run_dir: Path):
    """(시각, 메트릭, 값, 태그) 목록."""
    pts = []
    with gzip.open(run_dir / "raw.json.gz", "rt") as f:
        for line in f:
            o = json.loads(line)
            if o.get("type") != "Point":
                continue
            m = o["metric"]
            if m in ("http_req_duration", "http_req_failed", "dropped_iterations", "iterations"):
                d = o["data"]
                pts.append((_ts(d["time"]), m, d["value"], d.get("tags") or {}))
    return pts


def window_stats(pts, t0: float, t1: float) -> dict:
    dur = [(v, tg) for t, m, v, tg in pts if m == "http_req_duration" and t0 <= t < t1]
    fail = [v for t, m, v, _ in pts if m == "http_req_failed" and t0 <= t < t1]
    dropped = sum(v for t, m, v, _ in pts if m == "dropped_iterations" and t0 <= t < t1)
    secs = max(t1 - t0, 1e-9)

    def summarize(vals: list[float]) -> dict:
        return {"n": len(vals), "rps": round(len(vals) / secs, 2),
                "p50": pct(vals, 50), "p90": pct(vals, 90), "p95": pct(vals, 95),
                "p99": pct(vals, 99), "max": max(vals) if vals else float("nan")}

    out = {"all": summarize([v for v, _ in dur]),
           "api": summarize([v for v, tg in dur if tg.get("kind") == "api"]),
           "page": summarize([v for v, tg in dur if tg.get("kind") == "page"])}
    by_name = defaultdict(list)
    for v, tg in dur:
        by_name[tg.get("name", "?")].append(v)
    out["by_name"] = {k: summarize(v) for k, v in sorted(by_name.items())}
    out["error_rate"] = (sum(fail) / len(fail)) if fail else float("nan")
    out["dropped_iterations"] = int(dropped)
    return out


def profile_of(run_dir: Path) -> str:
    for line in (run_dir / "conditions.txt").read_text().splitlines():
        if line.startswith("run_id="):
            return line.split("profile=")[1].split()[0]
    raise ValueError("profile 을 알 수 없음")


def analyze_run(run_dir: Path) -> dict:
    pts = load_points(run_dir)
    prof = profile_of(run_dir)
    start = min(t for t, *_ in pts)
    end = max(t for t, *_ in pts)
    res = {"run": run_dir.name, "profile": prof, "duration_s": round(end - start)}
    if prof in WARMUP:
        res["window"] = window_stats(pts, start + WARMUP[prof], end + 1e-6)
    elif prof == "stress":
        res["stages"] = []
        t = start
        while t < end:
            res["stages"].append(window_stats(pts, t + STAGE_SKIP, min(t + STAGE_SECS, end + 1e-6)))
            t += STAGE_SECS
    elif prof == "breakpoint":
        buckets, t = [], start
        while t < end:
            buckets.append(window_stats(pts, t, min(t + 60, end + 1e-6)))
            t += 60
        res["buckets"] = buckets
        ok = [b for b in buckets if b["api"]["p95"] < SLO_API_P95 and b["error_rate"] < SLO_ERR]
        res["capacity_rps"] = max((b["all"]["rps"] for b in ok), default=0.0)
    return res


def fmt(x: float, unit: str = "ms") -> str:
    return "—" if x != x else (f"{x:.0f}{unit}" if unit == "ms" else f"{x:.2f}")


def print_run(r: dict) -> None:
    print(f"\n## {r['run']}  ({r['profile']}, {r['duration_s']}s)")
    if "window" in r:
        w = r["window"]
        print(f"error_rate={w['error_rate']:.4f}  dropped_iterations={w['dropped_iterations']}")
        print(f"{'구분':<20} {'n':>6} {'rps':>7} {'p50':>7} {'p90':>7} {'p95':>7} {'p99':>7} {'max':>7}")
        rows = [("ALL", w["all"]), ("api", w["api"]), ("page", w["page"])] + list(w["by_name"].items())
        for k, s in rows:
            print(f"{k:<20} {s['n']:>6} {s['rps']:>7} {fmt(s['p50']):>7} {fmt(s['p90']):>7} "
                  f"{fmt(s['p95']):>7} {fmt(s['p99']):>7} {fmt(s['max']):>7}")
    for key, title in (("stages", "단계"), ("buckets", "분")):
        if key in r:
            print(f"{title:<6} {'rps':>7} {'api p95':>8} {'api p99':>8} {'err':>7} {'dropped':>8}")
            for i, s in enumerate(r[key], 1):
                print(f"{i:<6} {s['all']['rps']:>7} {fmt(s['api']['p95']):>8} {fmt(s['api']['p99']):>8} "
                      f"{s['error_rate']:>7.3f} {s['dropped_iterations']:>8}")
    if "capacity_rps" in r:
        print(f"SLO 만족 최대 처리량: {r['capacity_rps']} RPS")


def run_dirs(label_dir: Path, profile: str | None) -> list[Path]:
    dirs = sorted(p for p in label_dir.iterdir() if (p / "raw.json.gz").exists())
    return [d for d in dirs if profile is None or profile_of(d) == profile]


def key_metrics(r: dict) -> dict:
    if "window" in r:
        w = r["window"]
        return {"api_p95": w["api"]["p95"], "api_p99": w["api"]["p99"], "page_p95": w["page"]["p95"],
                "rps": w["all"]["rps"], "error_rate": w["error_rate"]}
    if "capacity_rps" in r:
        return {"capacity_rps": r["capacity_rps"]}
    return {}


def aggregate(label_dir: Path, profile: str | None) -> dict[str, list[float]]:
    vals = defaultdict(list)
    for d in run_dirs(label_dir, profile):
        for k, v in key_metrics(analyze_run(d)).items():
            vals[k].append(v)
    return vals


def mann_whitney_exact(a: list[float], b: list[float]) -> tuple[float, float]:
    """U 통계량과 정확 양측 p값 (소표본용 — 모든 배치 열거)."""
    def u_of(x, y):
        return sum(1.0 if xi > yi else 0.5 if xi == yi else 0.0 for xi in x for yi in y)
    u = u_of(a, b)
    pooled, n = a + b, len(a)
    us = [u_of([pooled[i] for i in idx], [pooled[j] for j in range(len(pooled)) if j not in idx])
          for idx in itertools.combinations(range(len(pooled)), n)]
    center = len(a) * len(b) / 2
    p = sum(1 for x in us if abs(x - center) >= abs(u - center) - 1e-12) / len(us)
    return u, p


def bootstrap_change_ci(a: list[float], b: list[float], iters: int = 10000, seed: int = 7):
    rng = random.Random(seed)
    ch = sorted((statistics.median(rng.choices(b, k=len(b))) / statistics.median(rng.choices(a, k=len(a))) - 1) * 100
                for _ in range(iters))
    return ch[int(0.025 * iters)], ch[int(0.975 * iters)]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "run":
        print_run(analyze_run(Path(sys.argv[2])))
    elif mode == "label":
        label_dir, prof = Path(sys.argv[2]), (sys.argv[3] if len(sys.argv) > 3 else None)
        for d in run_dirs(label_dir, prof):
            print_run(analyze_run(d))
        print(f"\n## 집계 {label_dir.name} ({prof or '전체'}) — 중앙값 [최소–최대]")
        for k, v in aggregate(label_dir, prof).items():
            unit = "" if k in ("rps", "error_rate", "capacity_rps") else "ms"
            print(f"{k:<12} n={len(v)}  {fmt(statistics.median(v), unit)} [{fmt(min(v), unit)}–{fmt(max(v), unit)}]")
    elif mode == "compare":
        before, after = Path(sys.argv[2]), Path(sys.argv[3])
        prof = sys.argv[4] if len(sys.argv) > 4 else "load"
        va, vb = aggregate(before, prof), aggregate(after, prof)
        print(f"## {before.name} → {after.name} ({prof})")
        for k in va.keys() & vb.keys():
            a, b = va[k], vb[k]
            change = (statistics.median(b) / statistics.median(a) - 1) * 100
            lo, hi = bootstrap_change_ci(a, b)
            u, p = mann_whitney_exact(a, b) if len(a) + len(b) <= 16 else (float("nan"), float("nan"))
            print(f"{k:<12} {statistics.median(a):.1f} → {statistics.median(b):.1f}  "
                  f"변화 {change:+.1f}% (95% CI {lo:+.1f}~{hi:+.1f}%)  Mann-Whitney U={u:.1f} p={p:.3f}  "
                  f"(n={len(a)} vs {len(b)})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
