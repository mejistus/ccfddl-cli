#!/usr/bin/env python3
"""
check_ground_truth.py — INDEPENDENT ground truth for the CCFDDL CLI rebuild.

This script is written from scratch by `source-scout` (the verifier's data
source) and is deliberately NOT derived from SPEC.md's appendix values.  It
downloads the live CCFDDL catalog and re-derives, with its own timezone
arithmetic, the set of upcoming *paper submission* deadlines (`timeline[].deadline`)
for research area `AI`.

Semantics implemented (independent of the builder's implementation):
  * Catalog: https://ccfddl.com/conference/allconf.json (a JSON list of series).
  * Selection: series with sub == "AI" (case-insensitive); every edition
    (historical editions included); every timeline entry (rounds kept separate).
  * Kind: only the `deadline` field (paper submission).  abstract/rebuttal/decision
    nodes are never treated as the paper deadline.
  * Naive datetime strings "YYYY-MM-DD HH:MM:SS" are interpreted in the edition's
    `timezone`:
        AoE          -> fixed UTC-12 (Anywhere on Earth)
        PT           -> America/Los_Angeles, DST-aware via zoneinfo
        UTC          -> fixed UTC+00:00
        UTC+N/UTC-N  -> fixed offset N hours (optionally UTC+HH:MM)
    Any other / unknown timezone value is reported and its events are skipped —
    never silently treated as local or UTC.
  * "TBD" is unknown: never parsed, never compared, never sorted.  Events whose
    deadline is "TBD" are dropped from the upcoming list (and surface in the TBD
    section only if SPEC §4.4 conditions hold).
  * Ordering: (deadline_utc, title, year) ascending.
  * Exact duplicate events (conference_key, edition id, deadline_utc, comment)
    are collapsed; distinct rounds/editions are kept.
  * TBD section (SPEC §4.4): AI series with NO upcoming dated paper deadline
    across all editions AND latest edition year >= current display year.
  * Display timezone for *_local fields: Asia/Shanghai (system tz at recon time).

Usage:
  # live network (default); writes research/expected_ai_deadlines.json
  python3 research/check_ground_truth.py

  # deterministic / offline: reuse a catalog snapshot, pin the clock
  python3 research/check_ground_truth.py --data-file research/raw/allconf.json \
      --as-of 2026-10-18T07:55:19Z

  # print a short human summary instead of writing
  python3 research/check_ground_truth.py --data-file research/raw/allconf.json --summary

Stdlib only (urllib, json, hashlib, datetime, zoneinfo, argparse).
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CATALOG_URL = "https://ccfddl.com/conference/allconf.json"
CATEGORY = "AI"
DISPLAY_TZ = "Asia/Shanghai"
DEFAULT_OUT = Path(__file__).with_name("expected_ai_deadlines.json")
USER_AGENT = "ccfddl-research/1.0 (source-scout; independent ground-truth audit)"
DEADLINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
TZ_FIXED_RE = re.compile(r"^UTC([+-])(\d{1,2})(?::(\d{2}))?$")


# --------------------------------------------------------------------------- #
# timezone semantics
# --------------------------------------------------------------------------- #
def resolve_timezone(name):
    """Return (tzinfo, description, error).

    AoE == UTC-12.  PT == America/Los_Angeles (DST-aware).  UTC == +00:00.
    UTC+N / UTC-N == fixed offset.  Anything else -> error (caller must skip).
    """
    if not isinstance(name, str) or not name.strip():
        return None, None, "missing/empty timezone"
    raw = name.strip()
    low = raw.lower()
    if low == "aoe":
        return timezone(timedelta(hours=-12)), {"tz": raw, "mode": "fixed", "utc_offset": "-12:00"}, None
    if low == "pt":
        return ZoneInfo("America/Los_Angeles"), {"tz": raw, "mode": "iana", "iana": "America/Los_Angeles"}, None
    if low == "utc":
        return timezone.utc, {"tz": raw, "mode": "fixed", "utc_offset": "+00:00"}, None
    m = TZ_FIXED_RE.match(raw)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        delta = timedelta(hours=hours, minutes=minutes)
        if sign < 0:
            delta = -delta
        if delta == timedelta(0):
            return timezone.utc, {"tz": raw, "mode": "fixed", "utc_offset": "+00:00"}, None
        return timezone(delta), {
            "tz": raw,
            "mode": "fixed",
            "utc_offset": f"{'+' if sign > 0 else '-'}{hours:02d}:{minutes:02d}",
        }, None
    return None, None, f"unknown timezone {raw!r}"


def parse_deadline(raw, tzinfo, tz_desc):
    """Parse 'YYYY-MM-DD HH:MM:SS' in tzinfo.  Return (aware_utc, warnings).

    - "TBD" or anything non-matching -> (None, ...) : unknown, never a date.
    - PT ambiguous wall time (DST fall-back): choose fold=0 (earlier UTC) and warn.
    - PT nonexistent wall time (DST spring-forward): return None + warning; the
      wall clock does not identify an instant.
    """
    if not isinstance(raw, str):
        return None, [f"non-string deadline {raw!r}"]
    if raw == "TBD":
        return None, []
    if not DEADLINE_RE.match(raw):
        return None, [f"unexpected deadline format {raw!r}"]
    try:
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None, [f"unparseable datetime {raw!r}"]
    warnings = []
    if tz_desc.get("mode") == "iana":
        # Detect ambiguous (fall-back) and nonexistent (spring-forward) wall times.
        folds = [naive.replace(tzinfo=tzinfo, fold=f) for f in (0, 1)]
        offsets = {d.utcoffset() for d in folds}
        if len(offsets) == 2:
            # Ambiguous: roundtrip both; pick fold=0 (earlier instant).
            warnings.append("PT wall time ambiguous at DST fall-back; using fold=0 (earlier UTC)")
        probe = naive.replace(tzinfo=tzinfo, fold=0)
        roundtrip = probe.astimezone(timezone.utc).astimezone(tzinfo).replace(tzinfo=None)
        if roundtrip != naive:
            return None, warnings + [
                f"PT wall time {raw} nonexistent at DST spring-forward; instant undefined"
            ]
        aware = probe
    else:
        aware = naive.replace(tzinfo=tzinfo)
    return aware.astimezone(timezone.utc), warnings


# --------------------------------------------------------------------------- #
# catalog loading
# --------------------------------------------------------------------------- #
def fetch_catalog(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    started = datetime.now(timezone.utc)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        meta = {
            "request_url": url,
            "final_url": resp.geturl(),
            "http_status": resp.status,
            "content_type": resp.headers.get("Content-Type"),
            "content_length_header": resp.headers.get("Content-Length"),
            "last_modified": resp.headers.get("Last-Modified"),
            "etag": resp.headers.get("ETag"),
            "cache_control": resp.headers.get("Cache-Control"),
            "server": resp.headers.get("Server"),
            "fetched_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    return body, meta


def load_bytes(path):
    p = Path(path)
    data = sys.stdin.buffer.read() if str(p) == "-" else p.read_bytes()
    return data, {
        "request_url": None,
        "final_url": str(p),
        "http_status": None,
        "content_type": "application/json",
        "content_length_header": None,
        "last_modified": None,
        "etag": None,
        "cache_control": None,
        "server": None,
        "fetched_at_utc": None,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "loaded_from_local_file": str(p),
    }


def iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat()


def iso_in(dt, zone):
    return dt.astimezone(zone).isoformat()


# --------------------------------------------------------------------------- #
# derivation
# --------------------------------------------------------------------------- #
def build_ground_truth(catalog, as_of, display_zone_name=DISPLAY_TZ, category=CATEGORY):
    if not isinstance(catalog, list):
        raise TypeError(f"catalog root must be a JSON list, got {type(catalog).__name__}")
    display_zone = ZoneInfo(display_zone_name)
    display_year = as_of.astimezone(display_zone).year

    series = [s for s in catalog if str(s.get("sub", "")).strip().upper() == category.upper()]
    unknown_tz = {}
    warnings = []
    events = []
    seen = set()
    deduped = 0
    tbd_series = []
    passed_series = []

    def parse_node(raw, tzinfo, tz_desc, where):
        if raw is None:
            return None
        if raw == "TBD":
            return None
        dt, warns = parse_deadline(raw, tzinfo, tz_desc)
        for w in warns:
            warnings.append(f"{where}: {w}")
        return dt

    for s in series:
        key = s.get("conference_key")
        title = s.get("title")
        rank = s.get("rank") or {}
        ccf = rank.get("ccf")
        confs = s.get("confs") or []
        latest_year = max((c.get("year") or 0) for c in confs) if confs else 0
        latest = max(confs, key=lambda x: x.get("year") or 0) if confs else None
        # (b) does the latest edition have ANY dated (non-TBD) paper deadline?
        latest_has_dated = False
        if latest is not None:
            ltzinfo, _ltzdesc, _ltzerr = resolve_timezone(latest.get("timezone"))
            if ltzinfo is not None:
                for node in latest.get("timeline") or []:
                    if parse_node(node.get("deadline"), ltzinfo, _ltzdesc, "latest") is not None:
                        latest_has_dated = True
                        break
            else:
                latest_has_dated = True  # unknown tz: do not claim TBD
        series_has_upcoming = False

        for c in confs:
            ed_year = c.get("year")
            ed_id = c.get("id")
            tz_raw = c.get("timezone")
            tzinfo, tz_desc, tz_err = resolve_timezone(tz_raw)
            if tzinfo is None:
                unknown_tz[tz_raw] = unknown_tz.get(tz_raw, 0) + 1
                warnings.append(f"{key}/{ed_id}: skipped edition — {tz_err}")
                continue
            if not isinstance(ed_year, int):
                warnings.append(f"{key}/{ed_id}: non-integer year {ed_year!r}")
                continue

            for idx, node in enumerate(c.get("timeline") or []):
                where = f"{key}/{ed_id}/timeline[{idx}]"
                comment = node.get("comment") or ""
                deadline_utc = parse_node(node.get("deadline"), tzinfo, tz_desc, where + ".deadline")
                abstract_utc = parse_node(node.get("abstract_deadline"), tzinfo, tz_desc, where + ".abstract_deadline")
                if deadline_utc is None:
                    continue
                if deadline_utc <= as_of:
                    continue
                series_has_upcoming = True
                sig = (key, ed_id, deadline_utc, comment)
                if sig in seen:
                    deduped += 1
                    continue
                seen.add(sig)
                seconds_left = int((deadline_utc - as_of).total_seconds())
                events.append(
                    {
                        "conference": title,
                        "conference_key": key,
                        "year": ed_year,
                        "edition_id": ed_id,
                        "ccf_rank": ccf,
                        "core_rank": rank.get("core"),
                        "thcpl_rank": rank.get("thcpl"),
                        "kind": "deadline",
                        "deadline_utc": iso_utc(deadline_utc),
                        "deadline_local": iso_in(deadline_utc, display_zone),
                        "deadline_source": node.get("deadline"),
                        "source_timezone": tz_raw,
                        "source_timezone_resolution": tz_desc,
                        "abstract_utc": iso_utc(abstract_utc) if abstract_utc else None,
                        "abstract_local": iso_in(abstract_utc, display_zone) if abstract_utc else None,
                        "abstract_source": node.get("abstract_deadline") if node.get("abstract_deadline") not in (None, "TBD") else None,
                        "rebuttal_source": node.get("rebuttal_deadline") if DEADLINE_RE.match(str(node.get("rebuttal_deadline", ""))) else None,
                        "decision_source": node.get("decision_deadline") if DEADLINE_RE.match(str(node.get("decision_deadline", ""))) else None,
                        "days_left": seconds_left // 86400,
                        "seconds_left": seconds_left,
                        "comment": comment,
                        "event_date": c.get("date"),
                        "place": c.get("place"),
                        "link": c.get("link"),
                    }
                )

        # SPEC §4.4 (refined): TBD requires ALL of
        #   (a) no upcoming dated paper deadline across editions,
        #   (b) latest edition has no dated paper deadline (all TBD/absent),
        #   (c) latest edition year >= current display year.
        if latest is not None and latest_year >= display_year and not series_has_upcoming and not latest_has_dated:
            tbd_series.append(
                {
                    "conference": title,
                    "conference_key": key,
                    "year": latest.get("year"),  # SPEC §4.2 tbd[] field name
                    "latest_edition_year": latest.get("year"),
                    "latest_edition_id": latest.get("id"),
                    "ccf_rank": ccf,
                    "core_rank": rank.get("core"),
                    "thcpl_rank": rank.get("thcpl"),
                    "event_date": latest.get("date"),
                    "place": latest.get("place"),
                    "link": latest.get("link"),
                    "deadline_status": "TBD",
                    "note": "latest edition announced but paper deadline not announced (TBD)",
                }
            )
        elif latest is not None and latest_year >= display_year and not series_has_upcoming and latest_has_dated:
            # Explicitly NOT TBD (refined SPEC): latest deadline already passed.
            passed_series.append(
                {
                    "conference": title,
                    "conference_key": key,
                    "latest_edition_year": latest.get("year"),
                    "ccf_rank": ccf,
                    "reason": "latest edition deadline already passed; NOT TBD per SPEC §4.4",
                }
            )

    events.sort(key=lambda e: (e["deadline_utc"], e["conference"] or "", e["year"]))
    tbd_series.sort(key=lambda e: (e["conference"] or "", e["conference_key"] or ""))

    all_years = sorted({c.get("year") for s in catalog for c in (s.get("confs") or []) if isinstance(c.get("year"), int)})
    editions_total = sum(len(s.get("confs") or []) for s in catalog)

    return {
        "events": events,
        "tbd": tbd_series,
        "non_upcoming_passed_deadline_series": passed_series,
        "tracked_series": len(series),
        "deduped": deduped,
        "unknown_tz": unknown_tz,
        "warnings": warnings,
        "catalog_stats": {
            "series_total": len(catalog),
            "editions_total": editions_total,
            "edition_years_min": all_years[0] if all_years else None,
            "edition_years_max": all_years[-1] if all_years else None,
        },
        "display_year": display_year,
    }


# --------------------------------------------------------------------------- #
# catalog audit (schema / domain / data-quality facts used by source_notes.md)
# --------------------------------------------------------------------------- #
def audit(catalog, as_of, category=CATEGORY, display_tz=DISPLAY_TZ):
    """Print a reproducible summary of the catalog schema and data-quality traps."""
    import collections

    areas = collections.Counter(s.get("sub") for s in catalog)
    tz_all = collections.Counter()
    tz_area = collections.Counter()
    ccf = collections.Counter()
    rank_shapes = collections.Counter()
    missing_rank = 0
    edition_ids = collections.Counter()
    years = []
    date_tbd = place_tbd = 0
    tbd = collections.Counter()
    nonstandard = collections.Counter()
    no_comment = 0
    abstract_gt = 0
    abstract_tbd_paper_dated = 0
    round_dist = collections.Counter()
    editions = timeline_entries = 0
    titles = collections.defaultdict(list)
    dup_events = 0
    seen = set()
    sel = str(category).upper()

    for s in catalog:
        titles[s.get("title")].append((s.get("conference_key"), s.get("sub")))
        r = s.get("rank") or {}
        rank_shapes[tuple(sorted(r.keys()))] += 1
        ccf[r.get("ccf")] += 1
        if "core" not in r or "thcpl" not in r:
            missing_rank += 1
        for c in s.get("confs") or []:
            editions += 1
            years.append(c.get("year"))
            edition_ids[c.get("id")] += 1
            tz_all[c.get("timezone")] += 1
            if str(s.get("sub", "")).upper() == sel:
                tz_area[c.get("timezone")] += 1
            if c.get("date") == "TBD":
                date_tbd += 1
            if c.get("place") == "TBD":
                place_tbd += 1
            round_dist[len(c.get("timeline") or [])] += 1
            tzinfo, tz_desc, _err = resolve_timezone(c.get("timezone"))
            for node in c.get("timeline") or []:
                timeline_entries += 1
                if not node.get("comment"):
                    no_comment += 1
                for field in ("deadline", "abstract_deadline", "rebuttal_deadline", "decision_deadline"):
                    v = node.get(field)
                    if v is None:
                        continue
                    if v == "TBD":
                        tbd[field] += 1
                    elif not DEADLINE_RE.match(str(v)):
                        nonstandard[(field, str(v))] += 1
                a, dl = node.get("abstract_deadline"), node.get("deadline")
                if DEADLINE_RE.match(str(a or "")) and DEADLINE_RE.match(str(dl or "")):
                    if datetime.strptime(a, "%Y-%m-%d %H:%M:%S") > datetime.strptime(dl, "%Y-%m-%d %H:%M:%S"):
                        abstract_gt += 1
                if a == "TBD" and DEADLINE_RE.match(str(dl or "")):
                    abstract_tbd_paper_dated += 1
                if tzinfo is not None and DEADLINE_RE.match(str(dl or "")):
                    inst = parse_deadline(dl, tzinfo, tz_desc)[0]
                    sig = (s.get("conference_key"), c.get("id"), inst, node.get("comment") or "")
                    if sig in seen:
                        dup_events += 1
                    seen.add(sig)

    gt = build_ground_truth(catalog, as_of, display_tz, category)
    dup_titles = {k: v for k, v in titles.items() if len(v) > 1}
    print("=== catalog audit ===")
    print(f"root_type                 : {type(catalog).__name__}  series={len(catalog)}  "
          f"editions={editions}  timeline_entries={timeline_entries}")
    print(f"areas (sub -> series)     : {dict(sorted(areas.items(), key=lambda x: -x[1]))}")
    print(f"edition years              : min={min(y for y in years if isinstance(y, int))} "
          f"max={max(y for y in years if isinstance(y, int))} distinct={len(set(years))}")
    print(f"duplicate edition ids      : {[k for k, v in edition_ids.items() if v > 1] or 'none'}")
    print(f"rank key shapes            : {dict(rank_shapes)}")
    print(f"ccf rank distribution      : {dict(ccf)}")
    print(f"series missing core/thcpl  : {missing_rank}")
    print(f"timezone domain (global)   : {dict(sorted(tz_all.items(), key=lambda x: -x[1]))}")
    print(f"timezone domain ({category:<2})       : {dict(sorted(tz_area.items(), key=lambda x: -x[1]))}")
    print(f"timeline len distribution  : {dict(sorted(round_dist.items()))}")
    print(f"TBD counts by field        : {dict(tbd)}")
    print(f"non-standard deadline vals : {dict(nonstandard) or 'none (only YYYY-MM-DD HH:MM:SS or TBD)'}")
    print(f"free-text TBD               : date={date_tbd} place={place_tbd}")
    print(f"timeline empty comment     : {no_comment}")
    print(f"abstract > deadline (naive): {abstract_gt}")
    print(f"abstract TBD + dated paper : {abstract_tbd_paper_dated}")
    print(f"duplicate titles           : {dup_titles}")
    print(f"exact duplicate events     : {dup_events}")
    print(f"{category} series            : {gt['tracked_series']}")
    print(f"{category} upcoming papers    : {len(gt['events'])}")
    print(f"{category} TBD series          : {[t['conference_key'] for t in gt['tbd']]}")
    print(f"{category} non-upcoming passed: {len(gt['non_upcoming_passed_deadline_series'])} "
          f"(NOT TBD per SPEC 4.4; e.g. "
          f"{[t['conference_key'] for t in gt['non_upcoming_passed_deadline_series'][:5]]} ...)")
    return {
        "series": len(catalog), "editions": editions, "timeline_entries": timeline_entries,
        "areas": dict(areas), "tbd_field_counts": dict(tbd), "duplicate_titles": dup_titles,
        "ccf": dict(ccf), "missing_core_thcpl": missing_rank,
        "upcoming": len(gt["events"]), "tbd": [t["conference_key"] for t in gt["tbd"]],
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def selftest():
    """Assert the timezone semantics that matter (sign of UTC-12, AoE, PT DST).

    These are synthetic checks of *semantics*, not catalog data.  They fail loudly
    if a UTC-12 -> +12 sign bug (the bug once present in SPEC's appendix) reappears.
    """
    sh = ZoneInfo("Asia/Shanghai")
    cases = []
    # UTC-12 / AoE: 23:59:59 on Nov 16 is 11:59:59 UTC the NEXT day.
    for tzname in ("AoE", "UTC-12"):
        tzinfo, desc, err = resolve_timezone(tzname)
        assert err is None and desc["utc_offset"] == "-12:00", (tzname, desc, err)
        utc, warns = parse_deadline("2026-11-16 23:59:59", tzinfo, desc)
        assert utc == datetime(2026, 11, 17, 11, 59, 59, tzinfo=timezone.utc), (tzname, utc)
        assert utc.astimezone(sh).isoformat() == "2026-11-17T19:59:59+08:00", (tzname, utc.astimezone(sh))
        cases.append(f"{tzname} 2026-11-16 23:59:59 -> {utc.isoformat()} -> {utc.astimezone(sh).isoformat()}")
    # UTC+8 symmetric round-trip.
    tzinfo, desc, err = resolve_timezone("UTC+8")
    utc, _ = parse_deadline("2026-11-17 19:59:59", tzinfo, desc)
    assert utc == datetime(2026, 11, 17, 11, 59, 59, tzinfo=timezone.utc), utc
    cases.append(f"UTC+8 2026-11-17 19:59:59 -> {utc.isoformat()}")
    # PT: winter standard time is UTC-8; summer daylight time is UTC-7.
    tzinfo, desc, err = resolve_timezone("PT")
    utc, _ = parse_deadline("2026-01-15 23:59:59", tzinfo, desc)
    assert utc == datetime(2026, 1, 16, 7, 59, 59, tzinfo=timezone.utc), utc
    cases.append(f"PT 2026-01-15 23:59:59 (PST) -> {utc.isoformat()}")
    utc, _ = parse_deadline("2026-07-15 23:59:59", tzinfo, desc)
    assert utc == datetime(2026, 7, 16, 6, 59, 59, tzinfo=timezone.utc), utc
    cases.append(f"PT 2026-07-15 23:59:59 (PDT) -> {utc.isoformat()}")
    # PT nonexistent wall time (spring forward 2026-03-08 02:00) -> undefined.
    utc, warns = parse_deadline("2026-03-08 02:30:00", tzinfo, desc)
    assert utc is None and warns, (utc, warns)
    cases.append("PT 2026-03-08 02:30:00 (nonexistent) -> None (correct)")
    # PT ambiguous wall time (fall back 2026-11-01 01:00..02:00) -> fold=0, earlier UTC.
    utc, warns = parse_deadline("2026-11-01 01:30:00", tzinfo, desc)
    assert utc == datetime(2026, 11, 1, 8, 30, tzinfo=timezone.utc) and warns, (utc, warns)
    cases.append(f"PT 2026-11-01 01:30:00 (ambiguous) -> {utc.isoformat()} fold=0")
    # TBD is never a date.
    for tzn in ("UTC-12", "PT", "UTC+8"):
        tzinfo, desc, _ = resolve_timezone(tzn)
        utc, warns = parse_deadline("TBD", tzinfo, desc)
        assert utc is None and not warns, (tzn, utc, warns)
    # Unknown timezone must not be silently accepted.
    tzinfo, _desc, err = resolve_timezone("Mars/Olympus")
    assert tzinfo is None and err, (tzinfo, err)
    cases.append("TBD -> None; unknown tz -> error (correct)")
    for c in cases:
        print("ok:", c)
    print(f"selftest PASSED ({len(cases)} checks, incl. UTC-12 sign regression)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Derive independent CCFDDL AI ground truth.")
    ap.add_argument("--url", default=CATALOG_URL)
    ap.add_argument("--data-file", default=None, help="local catalog JSON instead of network")
    ap.add_argument("--as-of", default=None, help="ISO-8601 UTC instant used as 'now' (default: fetch time)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--display-tz", default=DISPLAY_TZ)
    ap.add_argument("--category", default=CATEGORY)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--summary", action="store_true", help="print summary only, do not write JSON")
    ap.add_argument("--selftest", action="store_true", help="run synthetic timezone-semantics assertions and exit")
    ap.add_argument("--audit", action="store_true", help="print catalog schema/domain/data-quality audit and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.data_file:
        body, fetch_meta = load_bytes(args.data_file)
    else:
        body, fetch_meta = fetch_catalog(args.url, args.timeout)

    if args.as_of:
        raw = args.as_of.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        as_of = datetime.fromisoformat(raw)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        as_of = as_of.astimezone(timezone.utc)
        as_of_source = "cli --as-of"
    else:
        # For network runs, fetched_at is our as_of.  For local files without
        # a pinned clock, fall back to the current wall clock.
        if fetch_meta.get("fetched_at_utc"):
            as_of = datetime.fromisoformat(fetch_meta["fetched_at_utc"]).replace(tzinfo=timezone.utc)
            as_of_source = "fetch timestamp"
        else:
            as_of = datetime.now(timezone.utc).replace(microsecond=0)
            as_of_source = "current wall clock"

    try:
        catalog = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - report, exit non-zero
        print(f"error: catalog is not valid JSON: {exc}", file=sys.stderr)
        return 1

    if args.audit:
        audit(catalog, as_of, args.category, args.display_tz)
        return 0

    gt = build_ground_truth(catalog, as_of, args.display_tz, args.category)

    doc = {
        "_comment": "Independent ground truth for the CCFDDL CLI rebuild. Computed from live "
        "ccfddl.com data by research/check_ground_truth.py; do not hand-edit.",
        "source": CATALOG_URL,
        "as_of_utc": iso_utc(as_of),
        "as_of_source": as_of_source,
        "fetched_at_utc": fetch_meta.get("fetched_at_utc"),
        "fetch": fetch_meta,
        "category": args.category,
        "display_timezone": args.display_tz,
        "tracked_series": gt["tracked_series"],
        "catalog_stats": gt["catalog_stats"],
        "semantics": {
            "AoE": "fixed UTC-12",
            "PT": "America/Los_Angeles, DST-aware (zoneinfo)",
            "UTC": "fixed UTC+00:00",
            "UTC+N": "fixed offset",
            "TBD": "unknown; never parsed, compared or sorted",
            "selection": "sub=='AI', all editions, all rounds, only timeline[].deadline paper deadline, deadline_utc > as_of",
            "sort": "(deadline_utc, conference, year) ascending",
            "dedup": "exact dupes on (conference_key, edition_id, deadline_utc, comment)",
            "tbd_rule": "AI series with no upcoming dated paper deadline and latest edition year >= current display year",
        },
        "upcoming_paper_deadline_count": len(gt["events"]),
        "events": gt["events"],
        "tbd": gt["tbd"],
        "tbd_count": len(gt["tbd"]),
        "checks": {
            "deduped_exact_duplicates": gt["deduped"],
            "unknown_timezones": gt["unknown_tz"],
            "warnings": gt["warnings"],
            "display_year": gt["display_year"],
            "non_upcoming_passed_deadline_series_count": len(gt["non_upcoming_passed_deadline_series"]),
            "non_upcoming_passed_deadline_series": gt["non_upcoming_passed_deadline_series"],
            "tbd_deadline_values_seen_total": None,  # filled below
        },
    }

    # Count TBD strings across the selected category for the audit trail.
    tbd_seen = 0
    for s in catalog:
        if str(s.get("sub", "")).strip().upper() != args.category.upper():
            continue
        for c in s.get("confs") or []:
            for node in c.get("timeline") or []:
                for k in ("deadline", "abstract_deadline", "rebuttal_deadline", "decision_deadline"):
                    if node.get(k) == "TBD":
                        tbd_seen += 1
    doc["checks"]["tbd_deadline_values_seen_total"] = tbd_seen

    if args.summary:
        print(f"as_of_utc            : {doc['as_of_utc']}")
        print(f"catalog sha256       : {fetch_meta['sha256']}  ({fetch_meta['bytes']} bytes)")
        print(f"tracked AI series    : {gt['tracked_series']}")
        print(f"upcoming paper events: {len(gt['events'])}")
        for e in gt["events"][:12]:
            print(f"  {e['deadline_utc']}  {e['deadline_local']}  {e['conference']} {e['year']}  "
                  f"[{e['ccf_rank']}] {e['deadline_source']} {e['source_timezone']} "
                  f"{('// ' + e['comment']) if e['comment'] else ''}")
        if len(gt["events"]) > 12:
            print(f"  ... {len(gt['events']) - 12} more")
        print(f"TBD series ({len(gt['tbd'])}):")
        for t in gt["tbd"]:
            print(f"  {t['conference']} {t['latest_edition_year']}  ({t['conference_key']})")
        if gt["unknown_tz"]:
            print(f"unknown timezones: {gt['unknown_tz']}")
        if gt["warnings"]:
            print(f"warnings ({len(gt['warnings'])}):")
            for w in gt["warnings"][:20]:
                print("  -", w)
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({len(gt['events'])} upcoming AI paper deadlines, "
          f"{len(gt['tbd'])} TBD, as_of {doc['as_of_utc']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
