"""Quantile forecaster for hourly Twitch viewer counts.

A log-space launch-comparables model with a conditional linear shape (OLS of
release-day ratios on hour-1 level), a diurnal correction from the target's own
pre-launch history, and a blended empirical-normal spread. Deterministic per case.
"""

import datetime as dt
import json
import math
import os
import statistics as st
from pathlib import Path

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = {
    0.05: -1.6448536269514722,
    0.25: -0.6744897501960817,
    0.5: 0.0,
    0.75: 0.6744897501960817,
    0.95: 1.6448536269514722,
}
WSIZE = 7
LQ = 0.4
K_TAIL = 0.45
K_MID = 0.35
CLAMP = 0.5
S_FLOOR = 0.05
S_CAP = 1.2
BETA = 0.2
WIN_DAYS = 7
HOURS = list(range(2, 25))


def parse_ts(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_day_curve(comp):
    """Release-day curve: 24 log-interpolated hourly values indexed 1..24."""
    ds = parse_ts(comp["day_start"])
    end = ds + dt.timedelta(hours=24)
    pts = {}
    for row in comp.get("hourly") or []:
        ts = parse_ts(row["from"])
        if ds <= ts < end:
            h = int((ts - ds).total_seconds() // 3600) + 1
            pts[h] = row["viewers"]
    curve = []
    for h in range(1, 25):
        v = pts.get(h)
        if v is not None:
            curve.append(float(v))
            continue
        lower = [k for k in pts if k < h]
        upper = [k for k in pts if k > h]
        if not lower or not upper:
            curve.append(None)
            continue
        lo = max(lower)
        hi = min(upper)
        w = (h - lo) / (hi - lo)
        lv_lo = math.log(max(float(pts[lo]), 1.0))
        lv_hi = math.log(max(float(pts[hi]), 1.0))
        curve.append(math.exp(lv_lo * (1 - w) + lv_hi * w))
    return curve


def diurnal_profile(hourly, cutoff):
    """Median-normalized UTC-hour-of-day ratio profile, or None if unusable."""
    rows = []
    for row in hourly or []:
        v = row.get("viewers")
        if v is None or v <= 0:
            continue
        ts = parse_ts(row["from"])
        if ts < cutoff:
            rows.append((ts, v))
    if not rows:
        return None
    start = cutoff - dt.timedelta(days=WIN_DAYS)
    window = [(t, v) for t, v in rows if t >= start]
    if len(window) < 24:
        window = rows
    med = st.median([v for _, v in window])
    if not med:
        med = 1.0
    groups = {}
    for t, v in window:
        groups.setdefault(t.hour, []).append(v)
    prof = {hod: st.median(vs) / med for hod, vs in groups.items() if len(vs) >= 2}
    if len(prof) < 12:
        return None
    return prof


def comparable_profile(case, pool_names):
    """Median across pool members of their own pre-launch diurnal profiles."""
    per_member = []
    for comp in case.get("comparables") or []:
        if comp["name"] not in pool_names:
            continue
        prof = diurnal_profile(comp.get("hourly") or [], parse_ts(comp["day_start"]))
        if prof:
            per_member.append(prof)
    if len(per_member) < 6:
        return None
    avg = {}
    for hod in range(24):
        vals = [p[hod] for p in per_member if hod in p]
        if len(vals) >= 4:
            avg[hod] = st.median(vals)
    if len(avg) < 12:
        return None
    return avg


def empirical_quantile(sorted_vals, p):
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = p * (n - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def validate_hours(case_id, rows):
    """Guard the output contract: 23 hours 2..24, each q of 5 valid numbers."""
    if len(rows) != 23:
        raise ValueError(f"case {case_id}: expected 23 hours, got {len(rows)}")
    if [row["hour"] for row in rows] != list(range(2, 25)):
        raise ValueError(f"case {case_id}: hours are not exactly 2..24 in order")
    for row in rows:
        q = row["q"]
        if len(q) != 5:
            raise ValueError(f"case {case_id}: hour {row['hour']} has {len(q)} q values")
        for value in q:
            if not math.isfinite(value):
                raise ValueError(f"case {case_id}: hour {row['hour']} has non-finite q")
            if value <= 0:
                raise ValueError(f"case {case_id}: hour {row['hour']} has q <= 0")
            if value > 1e9:
                raise ValueError(f"case {case_id}: hour {row['hour']} has q > 1e9")
        for i in range(1, len(q)):
            if q[i] < q[i - 1]:
                raise ValueError(
                    f"case {case_id}: hour {row['hour']} q values not non-decreasing"
                )


def apply_fixes(qs, floor):
    vals = [max(q, floor) for q in qs]
    vals = [min(q, 1e9) for q in vals]
    for i in range(1, len(vals)):
        if vals[i] < vals[i - 1]:
            vals[i] = vals[i - 1]
    return vals


def forecast_case(case):
    known1 = next(k for k in case["known"] if k["hour"] == 1)
    p1 = max(float(known1["viewers"]), 1.0)
    lp1 = math.log(p1)
    floor = max(p1 / 1000.0, 1.0)

    pool = []
    for comp in case.get("comparables") or []:
        name = comp.get("name") or ""
        if "Grand Theft Auto VI" in name:
            continue
        if "Tier: comparable" not in (comp.get("unlock") or ""):
            continue
        curve = build_day_curve(comp)
        if curve[0] is None or curve[0] <= 0:
            continue
        if any(v is None for v in curve):
            continue
        pool.append({"name": name, "l1": math.log(curve[0]), "curve": curve})

    if len(pool) < 8:
        rows = []
        for h in HOURS:
            qs = [
                p1 * math.exp(Z[tau] * 0.15 * math.sqrt(h - 1)) for tau in LEVELS
            ]
            rows.append({"hour": h, "q": apply_fixes(qs, floor)})
        return rows

    pool.sort(key=lambda x: x["name"])

    lmin = min(x["l1"] for x in pool)
    lmax = max(x["l1"] for x in pool)
    over = max(0.0, lp1 - lmax)
    under = max(0.0, lmin - lp1)
    lpe = lp1 - (over + under) * (1.0 - CLAMP)

    fit = {}
    for h in HOURS:
        xs = [x["l1"] for x in pool]
        ys = [math.log(x["curve"][h - 1]) - x["l1"] for x in pool]
        mx = st.mean(xs)
        my = st.mean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx == 0:
            b = 0.0
            a = my
        else:
            b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
            a = my - b * mx
        fit[h] = (a, b)

    shape = {h: fit[h][0] + fit[h][1] * lpe for h in HOURS}

    s_loc = {}
    for h in HOURS:
        a, b = fit[h]
        resid_line = [
            (math.log(x["curve"][h - 1]) - x["l1"]) - (a + b * x["l1"]) for x in pool
        ]
        mad = st.median([abs(e) for e in resid_line])
        s = 1.4826 * mad
        if s == 0:
            if len(pool) > 1:
                s = st.pstdev(resid_line)
            else:
                s = S_FLOOR
        s = min(max(s, S_FLOOR), S_CAP)
        s_loc[h] = s

    prof_t = diurnal_profile(case.get("history_hourly") or [], parse_ts(case["day_start"]))
    prof_c = comparable_profile(case, {x["name"] for x in pool})
    if prof_t and prof_c:
        base_t = prof_t.get(0, 1.0)
        base_c = prof_c.get(0, 1.0)
        for h in HOURS:
            hod = (h - 1) % 24
            pt = prof_t.get(hod)
            pc = prof_c.get(hod)
            if pt is None or pc is None:
                continue
            rel = (math.log(max(pt, 0.05)) - math.log(base_t)) - (
                math.log(max(pc, 0.05)) - math.log(base_c)
            )
            shape[h] += BETA * rel

    rows = []
    for h in HOURS:
        near = sorted(pool, key=lambda x: abs(x["l1"] - lpe))[:WSIZE]
        resid = sorted(
            math.log(x["curve"][h - 1]) - x["l1"] - shape[h] for x in near
        )
        lmed = lp1 + shape[h]
        qs = []
        for tau in LEVELS:
            emp = empirical_quantile(resid, tau)
            k = K_MID if tau in (0.25, 0.75) else K_TAIL
            dev = LQ * emp + (1 - LQ) * Z[tau] * s_loc[h] * k
            qs.append(math.exp(lmed + dev))
        rows.append({"hour": h, "q": apply_fixes(qs, floor)})
    return rows


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    for in_file in sorted(Path(input_dir).glob("*.in")):
        case = json.loads(in_file.read_text(encoding="utf-8"))
        rows = forecast_case(case)
        validate_hours(case.get("id", in_file.stem), rows)
        doc = {"hours": rows}
        target = out_path / (in_file.stem + ".out")
        target.write_text(
            json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
