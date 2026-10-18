#!/usr/bin/env python3
"""Independent oracle for the CCFDDL CLI verification.

This file is written by the verifier, intentionally WITHOUT importing or
reusing any builder code (./ccfddl) or source-scout code. It re-derives the
"expected" event set straight from the live catalog using only the Python
standard library and the rules in SPEC.md (§3 accuracy rules, §4.2 JSON
schema, §4.4 TBD section).

It is NOT a copy of the CLI: it is a deliberately simple, slow, literal
reimplementation whose only job is to disagree with the CLI when the CLI is
wrong.

Usage:
    # offline, from a previously downloaded catalog
    python3 tests/oracle_live.py --catalog tests/fixtures/allconf_live.json \
        --out tests/fixtures/expected_live.json

    # fresh network download (records provenance)
    python3 tests/oracle_live.py --fetch --out tests/fixtures/expected_live.json

    # pin the reference instant (default: now, UTC)
    python3 tests/oracle_live.py --catalog ... --now 2026-10-18T08:00:00Z

Output JSON: provenance block, reference instant, display timezone, the full
canonical event list (with audit fields) plus a compact event_set tuple list,
and the SPEC §4.4 TBD list.
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

SOURCE_URL = "https://ccfddl.com/conference/allconf.json"
USER_AGENT = "ccfddl-independent-verifier-oracle/1.0 (audit; stdlib urllib)"


# ---------------------------------------------------------------------------
# timezone handling (SPEC §3.3)
# ---------------------------------------------------------------------------

def tz_from_source(name):
    """Map a CCFDDL edition `timezone` string to a tzinfo.

    AoE == UTC-12, UTC == +00:00, UTC±N == fixed offset, PT == DST-aware
    America/Los_Angeles. Anything else is UNKNOWN and must be skipped/reported
    (never silently treated as local time).
    """
    if not isinstance(name, str):
        return None
    s = name.strip()
    if s == "AoE":
        return timezone(timedelta(hours=-12))
    if s == "PT":
        if ZoneInfo is None:  # pragma: no cover
            return None
        return ZoneInfo("America/Los_Angeles")
    if s == "UTC":
        return timezone.utc
    if s.startswith("UTC") and len(s) > 3:
        rest = s[3:]
        if rest in ("+0", "-0"):
            return timezone.utc
        sign = None
        if rest.startswith("+"):
            sign, body = 1, rest[1:]
        elif rest.startswith("-"):
            sign, body = -1, rest[1:]
        if sign is not None and body.isdigit():
            return timezone(timedelta(hours=sign * int(body)))
    return None


def parse_source_datetime(raw, tz):
    """Parse a raw source deadline string in its source timezone -> UTC.

    Returns None for absent/TBD/unparseable values. "TBD" is NEVER parsed as a
    date (SPEC §3.4).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if cleaned.upper() == "TBD":
        return None
    # Accept "YYYY-MM-DD HH:MM:SS" strictly; ISO "T" also tolerated.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.strptime(cleaned, fmt)
            break
        except ValueError:
            naive = None
    if naive is None:
        return None
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


def iso_utc(dt):
    return dt.astimezone(timezone.utc).isoformat()


def iso_local(dt, display_tz):
    return dt.astimezone(display_tz).isoformat()


# ---------------------------------------------------------------------------
# catalog parsing / selection (SPEC §3.5, §3.6, §3.8, §4.4)
# ---------------------------------------------------------------------------

def normalize_comment(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def select_events(catalog, now, display_tz, category="AI",
                  include_unknown_tz_log=None, all_kinds=False):
    """Return (events, tbd, tracked_series, unknown_tz_records, invalid_deadline_records).

    events: upcoming paper (or all-kind, when all_kinds) dated events, deduped,
            sorted by (deadline_utc, title, year) per SPEC §4.1.
    """
    unknown = []
    invalid = []
    events = []
    seen = set()
    tbd = []

    cat = (category or "").strip()
    cat_lower = cat.lower()
    all_categories = cat_lower == "all"

    tracked_series = 0
    for series in catalog:
        sub = series.get("sub")
        if not all_categories and (sub or "").lower() != cat_lower:
            continue
        tracked_series += 1

        title = series.get("title") or ""
        ckey = series.get("conference_key") or ""
        ranks = series.get("rank") or {}
        ccf = ranks.get("ccf")
        description = series.get("description") or ""
        confs = series.get("confs") or []
        has_upcoming_paper = False

        for edition in confs:
            year = edition.get("year")
            edition_id = edition.get("id") or ""
            tzone = edition.get("timezone")
            tzinfo = tz_from_source(tzone)
            if tzinfo is None and (edition.get("timeline") or []):
                unknown.append({
                    "conference_key": ckey, "edition_id": edition_id,
                    "year": year, "timezone": tzone,
                })
            timeline = edition.get("timeline") or []
            for idx, entry in enumerate(timeline):
                if not isinstance(entry, dict):
                    continue
                comment = normalize_comment(entry.get("comment"))
                for field, kind in (("deadline", "deadline"),
                                    ("abstract_deadline", "abstract"),
                                    ("rebuttal_deadline", "rebuttal"),
                                    ("decision_deadline", "decision")):
                    raw = entry.get(field)
                    if raw is None:
                        continue
                    if isinstance(raw, str) and raw.strip().upper() == "TBD":
                        continue  # unknown, never parsed as a date
                    if tzinfo is None:
                        invalid.append({
                            "conference_key": ckey, "edition_id": edition_id,
                            "year": year, "field": field, "raw": raw,
                            "reason": "unknown timezone %r" % (tzone,),
                        })
                        continue
                    utc_dt = parse_source_datetime(raw, tzinfo)
                    if utc_dt is None:
                        invalid.append({
                            "conference_key": ckey, "edition_id": edition_id,
                            "year": year, "field": field, "raw": raw,
                            "reason": "unparseable datetime",
                        })
                        continue
                    if kind == "deadline" and utc_dt > now:
                        has_upcoming_paper = True
                    if kind != "deadline" and not all_kinds:
                        continue
                    if utc_dt <= now:
                        continue
                    identity = (ckey, edition_id, iso_utc(utc_dt), comment, kind)
                    if identity in seen:
                        continue  # SPEC §3.8 exact-duplicate removal
                    seen.add(identity)

                    abstract_raw = entry.get("abstract_deadline")
                    abstract_utc = None
                    if abstract_raw is not None and tzinfo is not None:
                        abstract_utc = parse_source_datetime(abstract_raw, tzinfo)
                    events.append({
                        "conference_key": ckey,
                        "conference": title,
                        "year": year,
                        "edition_id": edition_id,
                        "ccf_rank": ccf,
                        "kind": kind,
                        "deadline_utc": iso_utc(utc_dt),
                        "deadline_local": iso_local(utc_dt, display_tz),
                        "deadline_source": raw,
                        "source_timezone": tzone,
                        "abstract_utc": iso_utc(abstract_utc) if abstract_utc else None,
                        "abstract_local": (iso_local(abstract_utc, display_tz)
                                           if abstract_utc else None),
                        "abstract_source": abstract_raw,
                        "days_left": int((utc_dt - now).total_seconds() // 86400),
                        "seconds_left": int((utc_dt - now).total_seconds()),
                        "comment": comment,
                        "event_date": edition.get("date"),
                        "place": edition.get("place"),
                        "link": edition.get("link"),
                        "timeline_index": idx,
                    })

        # SPEC §4.4 TBD section requires ALL of:
        #   (a) no upcoming dated paper deadline across all editions,
        #   (b) in the latest edition every timeline entry's `deadline` is
        #       "TBD"/absent (i.e. not announced),
        #   (c) latest edition year >= current display year.
        # A latest-edition deadline that already PASSED is NOT TBD.
        if not has_upcoming_paper and confs:
            latest = max(
                enumerate(confs),
                key=lambda pair: (pair[1].get("year") or 0, pair[0]),
            )[1]
            latest_year = latest.get("year")
            display_year = now.astimezone(display_tz).year
            latest_timeline = latest.get("timeline") or []

            def _announced(entry):
                if not isinstance(entry, dict):
                    return False
                raw = entry.get("deadline")
                if raw is None:
                    return False  # absent -> not announced
                if isinstance(raw, str) and raw.strip().upper() == "TBD":
                    return False  # explicitly TBD -> not announced
                return True

            latest_all_tbd = not any(_announced(e) for e in latest_timeline)
            if latest_all_tbd and isinstance(latest_year, int) and latest_year >= display_year:
                tbd.append({
                    "conference_key": ckey,
                    "conference": title,
                    "year": latest_year,
                    "ccf_rank": ccf,
                    "event_date": latest.get("date"),
                    "place": latest.get("place"),
                    "link": latest.get("link"),
                    "source_timezone": latest.get("timezone"),
                })

    # Sort by UTC instant, tie-break title then year (SPEC §4.1).
    events.sort(key=lambda e: (e["deadline_utc"], e["conference"], e["year"] or 0))
    tbd.sort(key=lambda t: ((t["conference"] or "").lower(), t["conference_key"]))
    return events, tbd, tracked_series, unknown, invalid


# ---------------------------------------------------------------------------
# fetch / main
# ---------------------------------------------------------------------------

def fetch_catalog(url=SOURCE_URL, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        headers = dict(resp.headers.items())
        status = resp.status
    return data, headers, status


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Independent CCFDDL oracle")
    ap.add_argument("--catalog", help="local path to allconf.json")
    ap.add_argument("--fetch", action="store_true",
                    help="download the live catalog (overrides --catalog)")
    ap.add_argument("--url", default=SOURCE_URL)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--now", help="reference instant, ISO-8601 (default: current UTC)")
    ap.add_argument("--display-tz", default="Asia/Shanghai")
    ap.add_argument("--category", default="AI")
    ap.add_argument("--all-kinds", action="store_true")
    ap.add_argument("--out", help="write oracle JSON here")
    args = ap.parse_args(argv)

    provenance = {"source": args.url, "fetched_at_utc": None, "bytes": None,
                  "sha256": None, "catalog_path": None}
    raw_bytes = None
    if args.fetch:
        raw_bytes, headers, status = fetch_catalog(args.url, args.timeout)
        provenance["fetched_at_utc"] = datetime.now(timezone.utc).isoformat()
        provenance["http_status"] = status
        provenance["content_type"] = headers.get("Content-Type")
        provenance["bytes"] = len(raw_bytes)
        provenance["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        catalog = json.loads(raw_bytes.decode("utf-8"))
    else:
        if not args.catalog:
            ap.error("either --catalog PATH or --fetch is required")
        with open(args.catalog, "rb") as fh:
            raw_bytes = fh.read()
        provenance["bytes"] = len(raw_bytes)
        provenance["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        provenance["catalog_path"] = args.catalog
        provenance["fetched_at_utc"] = datetime.fromtimestamp(
            __import__("os").path.getmtime(args.catalog), timezone.utc).isoformat()
        catalog = json.loads(raw_bytes.decode("utf-8"))

    if args.now:
        now = datetime.fromisoformat(args.now.strip().replace("Z", "+00:00"))
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
    else:
        now = datetime.now(timezone.utc)

    display_tz = ZoneInfo(args.display_tz)
    events, tbd, tracked, unknown, invalid = select_events(
        catalog, now, display_tz, category=args.category, all_kinds=args.all_kinds)

    result = {
        "source": args.url,
        "provenance": provenance,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "now_utc": now.isoformat(),
        "display_timezone": args.display_tz,
        "category": args.category,
        "tracked_series": tracked,
        "count": len(events),
        "count_tbd": len(tbd),
        "event_set": [[e["conference_key"], e["year"], e["deadline_utc"],
                       e["comment"], e["kind"]] for e in events],
        "events": events,
        "tbd": tbd,
        "unknown_timezones": unknown,
        "invalid_deadlines": invalid,
    }
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print("wrote %s: %d events, %d tbd, tracked_series=%d, now=%s"
              % (args.out, len(events), len(tbd), tracked, now.isoformat()))
    else:
        print(text)
    if unknown:
        print("WARNING: %d unknown-timezone edition(s)" % len(unknown), file=sys.stderr)
    if invalid:
        print("WARNING: %d invalid deadline(s)" % len(invalid), file=sys.stderr)


if __name__ == "__main__":
    main()
