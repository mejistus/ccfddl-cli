#!/usr/bin/env python3
"""Independent black-box verification suite for the rebuilt `./ccfddl` CLI.

Author: verifier teammate.  Everything here is written from SPEC.md, never from
the builder's implementation.  The suite:

  * invokes `./ccfddl` as a subprocess exactly like a user would (no imports of
    the implementation, no monkeypatching, no builder code reuse);
  * compares live runs against `tests/oracle_live.py`, the verifier's own
    reimplementation of SPEC §3/§4 selection + timezone rules;
  * uses deterministic synthetic catalogs (`tests/fixtures/synthetic_*.json`)
    for timezone/DST/edge-case math;
  * skips live-network tests gracefully when ccfddl.com is unreachable, but
    fails loudly on implementation defects.

Run:
    python3 -m pytest tests/ -v
    python3 -m pytest tests/ -v -k "not live"      # offline subset
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parent.parent
# The CLI lives one level above the archived dev/ tree (tools/ccfddl), while
# README/legacy/research/fixtures stay inside dev/. Support both layouts.
CLI = ROOT / "ccfddl"
if not CLI.exists():
    CLI = ROOT.parent / "ccfddl"
README = ROOT / "README.md"
if not README.exists():
    README = ROOT.parent / "README.md"
FIX = Path(__file__).resolve().parent / "fixtures"
LIVE_FIXTURE = FIX / "allconf_live.json"
TZ_FIX = FIX / "synthetic_tz.json"
EDGE_FIX = FIX / "synthetic_edge.json"
SOURCE_URL = "https://ccfddl.com/conference/allconf.json"
LEGACY = ROOT / "legacy" / "ccfddl-v1-hardcoded.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle_live  # noqa: E402  (verifier's own oracle, stdlib only)

ANSI = re.compile(r"\x1b\[")
DATE_TOKEN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

BAD_PROXY = {
    "http_proxy": "http://127.0.0.1:9",
    "https_proxy": "http://127.0.0.1:9",
    "HTTP_PROXY": "http://127.0.0.1:9",
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9",
    "all_proxy": "http://127.0.0.1:9",
    "NO_PROXY": None,
    "no_proxy": None,
}

REQUIRED_TOP_KEYS = ["source", "fetched_at", "display_timezone", "category",
                     "now_utc", "filters", "tracked_series", "events", "tbd"]
REQUIRED_EVENT_FIELDS = [
    "conference_key", "conference", "year", "ccf_rank", "kind",
    "deadline_utc", "deadline_local", "deadline_source", "source_timezone",
    "abstract_utc", "abstract_local", "abstract_source",
    "days_left", "seconds_left", "comment", "event_date", "place", "link",
]

VENUE_ACRONYMS = [
    "AAAI", "AAMAS", "ACCV", "ACL", "ACML", "AISTATS", "ALT", "ASE", "BMVC",
    "CCS", "CEC", "CICAI", "COLM", "COLING", "COLT", "CoNLL", "CoRL", "CPAL",
    "CVPR", "ECAI", "ECCV", "EMNLP", "ESANN", "EuroGP", "EvoApplications",
    "EvoCOP", "EvoMUSART", "FG", "FSE", "GECCO", "ICANN", "ICAPS", "ICCBR",
    "ICCV", "ICDAR", "ICLR", "ICML", "ICMLA", "ICONIP", "ICPR", "ICRA",
    "ICSE", "ICTAI", "IJCAI", "IJCB", "IJCNN", "IJCNLP", "IROS", "ISSTA",
    "KDD", "KR", "KSEM", "LOG", "MICCAI", "NAACL", "NeurIPS", "NIPS",
    "NLPCC", "OSDI", "PPSN", "PRICAI", "ProbML", "RSS", "SEC", "SIGIR",
    "SIGKDD", "SIGMOD", "SOSP", "UAI", "USENIX", "WACV",
]


# ---------------------------------------------------------------------------
# subprocess helpers
# ---------------------------------------------------------------------------

def _cli_argv(args):
    if not CLI.exists():
        pytest.fail("FAIL: ./ccfddl does not exist at %s" % CLI)
    if not os.access(str(CLI), os.X_OK):
        pytest.fail("FAIL: ./ccfddl is not executable (chmod +x / shebang missing)")
    return [str(CLI)] + [str(a) for a in args]


def run(args=(), env=None, stdin_text=None, timeout=240):
    """Run ./ccfddl as a black box; return CompletedProcess."""
    e = dict(os.environ)
    if env:
        for key, value in env.items():
            if value is None:
                e.pop(key, None)
            else:
                e[key] = value
    return subprocess.run(
        _cli_argv(args), input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=e, timeout=timeout,
    )


def run_ok(args=(), env=None, stdin_text=None, timeout=240):
    p = run(args, env=env, stdin_text=stdin_text, timeout=timeout)
    assert p.returncode == 0, (
        "FAIL: ./ccfddl %s exited %d\n--- stderr ---\n%s\n--- stdout ---\n%s"
        % (" ".join(map(str, args)), p.returncode, p.stderr[-4000:], p.stdout[-4000:])
    )
    return p


def get_json(args=(), env=None, stdin_text=None, timeout=240):
    """Run `ccfddl --json ...` and parse it; asserts exit 0 and ANSI-free output."""
    p = run(["--json"] + list(args), env=env, stdin_text=stdin_text, timeout=timeout)
    assert p.returncode == 0, (
        "FAIL: ./ccfddl --json %s exited %d\n--- stderr ---\n%s\n--- stdout ---\n%s"
        % (" ".join(map(str, args)), p.returncode, p.stderr[-4000:], p.stdout[-4000:])
    )
    assert not ANSI.search(p.stdout), "FAIL: ANSI escape sequence in --json output"
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail("FAIL: --json stdout is not valid JSON: %s\nfirst 1500 chars:\n%s"
                    % (exc, p.stdout[:1500]))
    assert isinstance(data, dict), "FAIL: --json top-level must be an object"
    return data


# ---------------------------------------------------------------------------
# datetime / oracle helpers
# ---------------------------------------------------------------------------

def dt(value):
    """Parse an ISO-8601 string that MUST carry an explicit offset."""
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, "FAIL: datetime %r has no explicit UTC offset" % value
    return parsed


def norm_comment(value):
    return "" if value is None else str(value)


def event_tuple(event):
    return (
        event["conference_key"],
        int(event["year"]),
        dt(event["deadline_utc"]),
        norm_comment(event.get("comment")),
        event.get("kind", "deadline"),
    )


def oracle_select(catalog, now, display_tz="Asia/Shanghai", category="AI",
                  all_kinds=False):
    return oracle_live.select_events(
        catalog, now, ZoneInfo(display_tz), category=category, all_kinds=all_kinds)


def assert_event_sets_equal(cli_events, expected_events, context=""):
    """Exact event-set + ordering comparison against the independent oracle."""
    got = [event_tuple(e) for e in cli_events]
    exp = [event_tuple(e) for e in expected_events]
    if got == exp:
        return
    got_set, exp_set = set(got), set(exp)
    missing = sorted(exp_set - got_set, key=repr)
    extra = sorted(got_set - exp_set, key=repr)
    lines = ["FAIL: event set/order mismatch%s" % (" (%s)" % context if context else "")]
    if missing:
        lines.append("  missing from CLI (%d):" % len(missing))
        lines += ["    expected %r" % (m,) for m in missing[:25]]
    if extra:
        lines.append("  unexpected in CLI (%d):" % len(extra))
        lines += ["    got %r" % (x,) for x in extra[:25]]
    if got_set == exp_set and got != exp:
        # Same members, different order: show the first divergence.
        for idx, (g, x) in enumerate(zip(got, exp)):
            if g != x:
                lines.append("  ordering diverges at index %d:\n    CLI  %r\n    want %r"
                             % (idx, g, x))
                break
        lines.append("  (select the same events; SPEC §4.1 tie-break is UTC instant, "
                     "then title, then year)")
    pytest.fail("\n".join(lines))


def fetch_live_catalog_bytes():
    try:
        data, _headers, _status = oracle_live.fetch_catalog(timeout=30)
    except Exception as exc:  # noqa: BLE001 - any network failure -> graceful skip
        pytest.skip("live ccfddl.com catalog unreachable: %r" % (exc,))
    return data


@pytest.fixture(scope="session")
def live_catalog():
    return json.loads(fetch_live_catalog_bytes().decode("utf-8"))


def _catalog_series(catalog):
    return {s.get("conference_key"): s for s in catalog}


def _series_count(catalog, category):
    if category == "all":
        return len(catalog)
    return sum(1 for s in catalog if (s.get("sub") or "").lower() == category.lower())


# ---------------------------------------------------------------------------
# SPEC §7.1 / §3.1: contract, executable, no hardcoded data
# ---------------------------------------------------------------------------

class TestContract:
    def test_cli_exists_is_executable_and_has_shebang(self):
        assert CLI.exists(), "FAIL: ./ccfddl missing"
        assert os.access(str(CLI), os.X_OK), "FAIL: ./ccfddl is not executable"
        first = CLI.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        assert first.strip() == "#!/usr/bin/env python3", (
            "FAIL: shebang must be '#!/usr/bin/env python3', got %r" % first)

    def test_help_exits_zero_and_documents_flags(self):
        p = run(["--help"], env=BAD_PROXY)  # must not need network
        assert p.returncode == 0, "FAIL: --help exited %d: %s" % (p.returncode, p.stderr[:2000])
        out = p.stdout.lower()
        assert "usage" in out
        for flag in ("--json", "--data-file", "--details", "--include-tbd", "--tz",
                     "--rank", "--category", "--days", "--limit", "--all-kinds",
                     "--no-color", "--verbose", "--version", "--timeout"):
            assert flag in out, "FAIL: --help does not document %s" % flag

    def test_version_exits_zero_without_network(self):
        p = run(["--version"], env=BAD_PROXY)
        assert p.returncode == 0, "FAIL: --version exited %d: %s" % (p.returncode, p.stderr[:1000])
        assert re.search(r"\d+\.\d+", p.stdout), (
            "FAIL: --version output lacks a version number: %r" % p.stdout[:500])

    def test_unknown_argument_exits_2(self):
        p = run(["--definitely-not-a-real-option"], env=BAD_PROXY)
        assert p.returncode == 2, (
            "FAIL: unknown arg must exit 2 (argparse), got %d" % p.returncode)
        assert p.stderr.strip(), "FAIL: unknown arg produced no stderr message"

    def test_no_hardcoded_venue_or_date_data(self):
        """SPEC §3.1/§7.1: only URL/tz/format/help literals allowed as data.

        Docstrings and argparse `help=` strings are explicitly permitted by the
        spec (CLI examples), so they are excluded from the scan.  Any other
        venue acronym or hardcoded ISO date constant is a failure.
        """
        src = CLI.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            pytest.fail("FAIL: ./ccfddl is not valid Python: %s" % exc)

        docstrings, help_strings = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    docstrings.add(doc)
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    # SPEC §3.1 allows argparse help/description/usage/epilog
                    # strings (UI text, not data).
                    if kw.arg in ("help", "description", "epilog", "usage",
                                  "metavar", "prog", "title", "caption"):
                        if isinstance(kw.value, ast.Constant) and \
                                isinstance(kw.value.value, str):
                            help_strings.add(kw.value.value)

        hits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if value in docstrings or value in help_strings:
                continue
            upper = value.upper()
            for acronym in VENUE_ACRONYMS:
                if re.search(r"(?<![A-Za-z0-9])" + re.escape(acronym.upper())
                             + r"(?![A-Za-z0-9])", upper):
                    hits.append((node.lineno, "venue", acronym, value[:100]))
            if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", value):
                hits.append((node.lineno, "date", "", value[:100]))
        assert not hits, (
            "FAIL: hardcoded venue/date data found in ./ccfddl (outside docstrings/"
            "argparse help):\n" + "\n".join("  line %s: %s %s %r" % h for h in hits))

    def test_stdlib_only_required_deps(self):
        src = CLI.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        third_party = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            third_party.update(names)
        forbidden = third_party & {"requests", "tabulate", "colorama", "numpy", "pandas"}
        assert not forbidden, (
            "FAIL: v1 third-party deps still imported: %s" % sorted(forbidden))
        assert "urllib" in src, (
            "FAIL: SPEC §4.5 requires stdlib urllib.request for fetching; not found")
        if LEGACY.exists():
            assert CLI.read_text(encoding="utf-8", errors="replace") != \
                LEGACY.read_text(encoding="utf-8", errors="replace"), (
                "FAIL: ./ccfddl is byte-identical to the archived v1 hardcoded script")

    def test_readme_documents_contract(self):
        assert README.exists(), "FAIL: README.md missing (SPEC §7.7)"
        text = README.read_text(encoding="utf-8", errors="replace")
        low = text.lower()
        assert SOURCE_URL in text or "ccfddl.com" in text, \
            "FAIL: README does not name the live data source"
        for flag in ("--json", "--data-file", "--details", "--include-tbd", "--tz",
                     "--rank", "--category", "--days", "--limit", "--all-kinds",
                     "--no-color", "--verbose", "--version", "--timeout"):
            assert flag in text, "FAIL: README does not document %s" % flag
        for term in ("tbd", "official", "timezone"):
            assert term in low, "FAIL: README lacks required accuracy term %r" % term
        assert ("check" in low or "verify" in low), \
            "FAIL: README lacks the 'verify against official venue page' caveat"
        assert ("accuracy" in low or "unknown" in low or "not announced" in low), \
            "FAIL: README lacks the TBD-is-unknown accuracy caveat"
        assert "ccfddl" in low and ("ai" in low), \
            "FAIL: README lacks basic usage/default-category description"


# ---------------------------------------------------------------------------
# SPEC §7.2/§4.2: JSON schema + oracle comparison, live network
# ---------------------------------------------------------------------------

def _check_event_schema(events, display_tz, now=None):
    if isinstance(now, str):
        now = dt(now)
    tzinfo = ZoneInfo(display_tz)
    for ev in events:
        missing = [f for f in REQUIRED_EVENT_FIELDS if f not in ev]
        assert not missing, "FAIL: event missing fields %s: %r" % (missing, ev)
        utc = dt(ev["deadline_utc"])
        local = dt(ev["deadline_local"])
        assert utc.utcoffset() == timedelta(0), \
            "FAIL: deadline_utc %r is not UTC" % ev["deadline_utc"]
        assert local.utcoffset() == tzinfo.utcoffset(local), (
            "FAIL: deadline_local %r offset %s != display tz %s offset %s"
            % (ev["deadline_local"], local.utcoffset(), display_tz,
               tzinfo.utcoffset(local)))
        kind_norm = norm_comment(ev.get("kind")).replace("_deadline", "")
        assert kind_norm in ("deadline", "abstract", "rebuttal", "decision"), \
            "FAIL: unexpected kind %r" % ev.get("kind")
        assert isinstance(ev["year"], int), "FAIL: year must be int"
        assert isinstance(ev["days_left"], int) and isinstance(ev["seconds_left"], int), \
            "FAIL: days_left/seconds_left must be ints"
        assert ev["days_left"] == ev["seconds_left"] // 86400, \
            "FAIL: days_left must equal floor(seconds_left / 86400)"
        if now is not None:
            assert abs((utc - now).total_seconds() - ev["seconds_left"]) <= 2, \
                "FAIL: seconds_left inconsistent with now_utc/deadline_utc"
        assert isinstance(ev["comment"], str), "FAIL: comment must be a string"
        assert ev["source_timezone"] is not None, "FAIL: source_timezone missing/null"
        assert ev["deadline_source"] is not None, "FAIL: deadline_source missing/null"
        abstract_source = ev.get("abstract_source")
        if abstract_source is not None:
            if str(abstract_source).strip().upper() == "TBD":
                assert ev["abstract_utc"] is None and ev["abstract_local"] is None, \
                    "FAIL: 'TBD' abstract must never be parsed as a date"
            else:
                assert ev["abstract_utc"] is not None
                assert dt(ev["abstract_utc"]).utcoffset() == timedelta(0)
                assert dt(ev["abstract_local"]).utcoffset() == tzinfo.utcoffset(
                    dt(ev["abstract_local"]))
    return now


class TestLiveJson:
    def test_live_json_schema_and_defaults(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai"])
        for key in REQUIRED_TOP_KEYS:
            assert key in data, "FAIL: --json missing top-level key %r (SPEC §4.2)" % key
        assert data["source"] == SOURCE_URL, (
            "FAIL: source must be %s, got %r" % (SOURCE_URL, data.get("source")))
        assert data["display_timezone"] == "Asia/Shanghai"
        assert data["category"] == "AI"
        filters = data["filters"]
        assert isinstance(filters, dict)
        for key in ("days", "ranks", "limit", "all_kinds"):
            assert key in filters, "FAIL: filters.%s missing" % key
        assert filters["days"] == 0 and filters["limit"] == 0
        assert filters["all_kinds"] is False
        assert filters["ranks"] in (None, [], "")
        assert isinstance(data["events"], list)
        assert data["tracked_series"] == _series_count(live_catalog, "AI"), (
            "FAIL: tracked_series %r != live count of sub==AI series %d"
            % (data["tracked_series"], _series_count(live_catalog, "AI")))
        fetched = dt(data["fetched_at"])
        now = dt(data["now_utc"])
        wall = datetime.now(timezone.utc)
        assert abs((now - wall).total_seconds()) < 600, \
            "FAIL: now_utc is more than 10 minutes from wall clock"
        assert abs((fetched - wall).total_seconds()) < 600, \
            "FAIL: fetched_at is more than 10 minutes from wall clock"
        assert now.tzinfo is not None and fetched.tzinfo is not None
        _check_event_schema(data["events"], "Asia/Shanghai", now=data["now_utc"])
        # ordering ascending by UTC instant
        instants = [dt(e["deadline_utc"]) for e in data["events"]]
        assert instants == sorted(instants), "FAIL: events not sorted ascending by deadline_utc"
        assert all(e["kind"] == "deadline" for e in data["events"]), \
            "FAIL: default --json must contain paper deadlines only"
        assert not ANSI.search(json.dumps(data))
        assert isinstance(data["tbd"], list)

    def test_live_event_set_matches_independent_oracle_exactly(self):
        """SPEC §7.2: exact set + ordering from the same live catalog."""
        for attempt in range(3):
            before = fetch_live_catalog_bytes()
            p = run(["--json", "--tz", "Asia/Shanghai"])
            after = fetch_live_catalog_bytes()
            if before == after:
                break
        else:
            pytest.fail("FAIL: live catalog changed repeatedly during the test; retry later")
        assert p.returncode == 0, "FAIL: exit %d: %s" % (p.returncode, p.stderr[-3000:])
        data = json.loads(p.stdout)
        catalog = json.loads(before.decode("utf-8"))
        now = dt(data["now_utc"])
        expected, expected_tbd, tracked, _u, _i = oracle_select(
            catalog, now, "Asia/Shanghai", "AI")
        assert data["tracked_series"] == tracked
        assert_event_sets_equal(data["events"], expected, "live AI paper deadlines")
        got_keys = {(e["conference_key"], int(e["year"]), dt(e["deadline_utc"]))
                    for e in data["events"]}
        exp_keys = {(e["conference_key"], int(e["year"]), dt(e["deadline_utc"]))
                    for e in expected}
        assert got_keys == exp_keys

    def test_live_tbd_matches_oracle(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai", "--include-tbd"])
        now = dt(data["now_utc"])
        _events, expected_tbd, _tracked, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "AI")
        assert isinstance(data["tbd"], list)
        # tolerate schema without year by comparing keys only where possible
        got_keys = {t["conference_key"] for t in data["tbd"]}
        exp_keys = {t["conference_key"] for t in expected_tbd}
        assert got_keys == exp_keys, (
            "FAIL: --include-tbd JSON set mismatch\n  missing: %s\n  extra: %s"
            % (sorted(exp_keys - got_keys), sorted(got_keys - exp_keys)))
        for entry in data["tbd"]:
            assert entry.get("event_date"), "FAIL: tbd entry lacks event_date"
            assert entry.get("place") is not None, "FAIL: tbd entry lacks place"
            assert "link" in entry, "FAIL: tbd entry lacks link"
            assert entry.get("ccf_rank") is not None, "FAIL: tbd entry lacks ccf_rank"

    def test_live_include_tbd_table(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai", "--include-tbd"])
        now = dt(data["now_utc"])
        _ev, expected_tbd, _tr, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "AI")
        assert expected_tbd, "FAIL: oracle found no TBD series on current data"
        assert data["tbd"], "FAIL: --include-tbd JSON tbd list is empty"
        out = run_ok(["--tz", "Asia/Shanghai", "--include-tbd"]).stdout
        assert not ANSI.search(out)
        for entry in expected_tbd:
            assert entry["conference"] in out, (
                "FAIL: --include-tbd table missing TBD series %r"
                % entry["conference"])
            if entry.get("event_date") and entry["event_date"] != "TBD":
                assert entry["event_date"] in out, (
                    "FAIL: --include-tbd table missing event date for %r"
                    % entry["conference"])
        assert "not announced" in out.lower() or "tbd" in out.lower(), \
            "FAIL: TBD section lacks an explicit 'deadline not announced (TBD)' label"
        plain = run_ok(["--tz", "Asia/Shanghai"]).stdout
        assert "not announced" not in plain.lower(), \
            "FAIL: TBD section rendered without --include-tbd"

    def test_live_rank_filter(self, live_catalog):
        data_all = get_json(["--tz", "Asia/Shanghai"])
        now = dt(data_all["now_utc"])
        expected, _tbd, _tr, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "AI")
        for ranks in ("A", "B", "C", "N", "A,B"):
            wanted = set(ranks.split(","))
            exp = [e for e in expected if (e.get("ccf_rank") or "") in wanted]
            data = get_json(["--tz", "Asia/Shanghai", "--rank", ranks])
            assert {norm_comment(e.get("ccf_rank")) for e in data["events"]} <= wanted, \
                "FAIL: --rank %s returned other ranks" % ranks
            assert_event_sets_equal(data["events"], exp, "--rank %s" % ranks)

    def test_live_category_filter(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai", "--category", "CG"])
        now = dt(data["now_utc"])
        expected, _tbd, tracked, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "CG")
        assert data["tracked_series"] == tracked
        assert data["category"].lower() == "cg"
        assert_event_sets_equal(data["events"], expected, "--category CG")
        lower = get_json(["--tz", "Asia/Shanghai", "--category", "cg"])
        assert {e["conference_key"] for e in lower["events"]} == \
            {e["conference_key"] for e in data["events"]}, \
            "FAIL: --category matching must be case-insensitive (SPEC §2.1)"

    def test_live_category_all(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai", "--category", "all"])
        now = dt(data["now_utc"])
        expected, _tbd, tracked, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "all")
        assert data["tracked_series"] == tracked == len(live_catalog)
        assert_event_sets_equal(data["events"], expected, "--category all")

    def test_live_days_filter(self, live_catalog):
        base = get_json(["--tz", "Asia/Shanghai"])
        now = dt(base["now_utc"])
        expected, _tbd, _tr, _u, _i = oracle_select(
            live_catalog, now, "Asia/Shanghai", "AI")
        for days in (1, 30, 365):
            cutoff = now + timedelta(days=days)
            exp = [e for e in expected if dt(e["deadline_utc"]) <= cutoff]
            data = get_json(["--tz", "Asia/Shanghai", "--days", str(days)])
            assert data["filters"]["days"] == days
            assert_event_sets_equal(data["events"], exp, "--days %d" % days)

    def test_live_limit_filter(self, live_catalog):
        base = get_json(["--tz", "Asia/Shanghai"])
        data = get_json(["--tz", "Asia/Shanghai", "--limit", "3"])
        assert data["filters"]["limit"] == 3
        assert len(data["events"]) <= 3, "FAIL: --limit 3 returned more than 3 events"
        assert event_tuple(data["events"][0]) == event_tuple(base["events"][0])
        limit_big = get_json(["--tz", "Asia/Shanghai", "--limit", "100000"])
        assert len(limit_big["events"]) == len(base["events"])

    def test_live_all_kinds(self, live_catalog):
        paper = get_json(["--tz", "Asia/Shanghai"])
        everything = get_json(["--tz", "Asia/Shanghai", "--all-kinds"])
        assert everything["filters"]["all_kinds"] is True
        kinds = {norm_comment(e["kind"]).replace("_deadline", "")
                 for e in everything["events"]}
        assert {"abstract", "rebuttal", "decision"} & kinds, \
            "FAIL: --all-kinds added no non-paper nodes (kinds=%r)" % kinds
        # default paper rows must be a subset of all-kinds paper rows
        paper_keys = {event_tuple(e) for e in paper["events"]}
        all_keys = {event_tuple(e) for e in everything["events"]}
        assert paper_keys <= all_keys, "FAIL: --all-kinds lost default paper events"
        instants = [dt(e["deadline_utc"]) for e in everything["events"]]
        assert instants == sorted(instants)

    def test_live_cvpr_utc12_sign_regression(self, live_catalog):
        """SPEC §7.3 concrete case; catches a UTC-12 -> +12 sign error."""
        data = get_json(["--data-file", str(LIVE_FIXTURE), "--tz", "Asia/Shanghai"])
        cvpr = [e for e in data["events"] if e["conference_key"] == "AI/cvpr"]
        if not cvpr:
            pytest.skip("CVPR 2027 deadline no longer upcoming in the pinned fixture")
        ev = cvpr[0]
        assert ev["deadline_source"] == "2026-11-16 23:59:59"
        assert ev["source_timezone"] == "UTC-12"
        assert dt(ev["deadline_utc"]) == dt("2026-11-17T11:59:59+00:00"), (
            "FAIL: UTC-12 must be -12h: 2026-11-16 23:59:59 UTC-12 == "
            "2026-11-17T11:59:59Z, got %r" % ev["deadline_utc"])
        assert dt(ev["deadline_local"]) == dt("2026-11-17T19:59:59+08:00"), (
            "FAIL: CVPR local deadline must be 2026-11-17T19:59:59+08:00, got %r"
            % ev["deadline_local"])
        assert dt(ev["deadline_local"]) != dt("2026-11-16T19:59:59+08:00"), (
            "FAIL: UTC-12 sign bug detected (one day too early)")
        assert dt(ev["abstract_utc"]) == dt("2026-11-11T11:59:59+00:00")
        assert dt(ev["abstract_local"]) == dt("2026-11-11T19:59:59+08:00")

    def test_live_json_tz_changes_display_not_selection(self):
        utc = get_json(["--tz", "UTC"])
        sh = get_json(["--tz", "Asia/Shanghai"])
        assert {(e["conference_key"], e["year"], dt(e["deadline_utc"]))
                for e in utc["events"]} == \
            {(e["conference_key"], e["year"], dt(e["deadline_utc"]))
             for e in sh["events"]}, "FAIL: --tz changed the selected event set"
        for ev in utc["events"]:
            assert dt(ev["deadline_local"]).utcoffset() == timedelta(0)
        assert utc["display_timezone"] == "UTC"
        for ev in sh["events"]:
            assert dt(ev["deadline_local"]).utcoffset() == timedelta(hours=8)

    def test_live_default_display_timezone_is_system_local(self):
        data = get_json([])
        tzname = data["display_timezone"]
        assert isinstance(tzname, str) and tzname, "FAIL: empty display_timezone"
        try:
            tz = ZoneInfo(tzname)
        except Exception:
            pytest.fail("FAIL: default display_timezone %r is not an IANA zone" % tzname)
        system_offset = datetime.now().astimezone().utcoffset()
        now = dt(data["now_utc"]).astimezone(tz)
        assert now.utcoffset() == system_offset, (
            "FAIL: default display timezone %r (offset %s) != system local offset %s"
            % (tzname, now.utcoffset(), system_offset))

    def test_live_filters_field_reflects_arguments(self):
        data = get_json(["--tz", "Asia/Shanghai", "--days", "120", "--rank", "A",
                         "--limit", "7", "--all-kinds"])
        filters = data["filters"]
        assert filters["days"] == 120
        assert filters["limit"] == 7
        assert filters["all_kinds"] is True
        ranks = filters["ranks"]
        if isinstance(ranks, str):
            ranks = ranks.split(",")
        assert "A" in ranks, "FAIL: filters.ranks must record the --rank value"


# ---------------------------------------------------------------------------
# SPEC §7.3 / §3.3: timezone matrix on deterministic synthetic fixture
# ---------------------------------------------------------------------------

# (conference_key, expected deadline_utc, expected Asia/Shanghai local)
TZ_EXPECTED = {
    "AI/tz-aoe":        ("2033-01-11T11:59:59+00:00", "2033-01-11T19:59:59+08:00"),
    "AI/tz-utcm12":     ("2033-02-11T11:59:59+00:00", "2033-02-11T19:59:59+08:00"),
    "AI/tz-utc":        ("2033-03-10T12:00:00+00:00", "2033-03-10T20:00:00+08:00"),
    "AI/tz-utc0":       ("2033-03-10T12:00:00+00:00", "2033-03-10T20:00:00+08:00"),
    "AI/tz-utcp10":     ("2033-03-10T12:00:00+00:00", "2033-03-10T20:00:00+08:00"),
    "AI/tz-utcp8":      ("2033-03-10T12:00:00+00:00", "2033-03-10T20:00:00+08:00"),
    "AI/tz-utcm5":      ("2033-03-10T12:00:00+00:00", "2033-03-10T20:00:00+08:00"),
    "AI/tz-pt-winter":  ("2033-01-16T07:59:59+00:00", "2033-01-16T15:59:59+08:00"),
    "AI/tz-pt-summer":  ("2033-07-16T06:59:59+00:00", "2033-07-16T14:59:59+08:00"),
    "AI/tz-pt-spring":  ("2033-03-14T07:30:00+00:00", "2033-03-14T15:30:00+08:00"),
    "AI/tz-pt-fall":    ("2033-11-07T08:30:00+00:00", "2033-11-07T16:30:00+08:00"),
}


class TestTimezoneMatrix:
    def _run_fixture(self, tz="Asia/Shanghai"):
        return get_json(["--data-file", str(TZ_FIX), "--tz", tz])

    def test_tz_matrix_utc_and_local_instants(self):
        data = self._run_fixture("Asia/Shanghai")
        got = {e["conference_key"]: e for e in data["events"]}
        assert set(got) == set(TZ_EXPECTED), (
            "FAIL: synthetic tz fixture event set mismatch\n  missing: %s\n  extra: %s"
            % (sorted(set(TZ_EXPECTED) - set(got)), sorted(set(got) - set(TZ_EXPECTED))))
        failures = []
        for key, (utc_s, local_s) in TZ_EXPECTED.items():
            ev = got[key]
            if dt(ev["deadline_utc"]) != dt(utc_s):
                failures.append("%s: deadline_utc %r != %r" % (key, ev["deadline_utc"], utc_s))
            if dt(ev["deadline_local"]) != dt(local_s):
                failures.append("%s: deadline_local %r != %r"
                                % (key, ev["deadline_local"], local_s))
        assert not failures, "FAIL: timezone conversion matrix:\n  " + "\n  ".join(failures)

    def test_utc_minus_12_sign_trap(self):
        data = get_json(["--data-file", str(TZ_FIX), "--tz", "UTC"])
        got = {e["conference_key"]: e for e in data["events"]}
        correct = dt("2033-02-11T11:59:59+00:00")
        wrong_plus12 = dt("2033-02-10T11:59:59+00:00")  # exactly what a +12 bug yields
        assert dt(got["AI/tz-utcm12"]["deadline_utc"]) == correct, (
            "FAIL: UTC-12 sign error: expected 2033-02-11T11:59:59Z, got %r"
            % got["AI/tz-utcm12"]["deadline_utc"])
        assert dt(got["AI/tz-utcm12"]["deadline_utc"]) != wrong_plus12, \
            "FAIL: UTC-12 was mapped to +12 (one day early)"
        assert dt(got["AI/tz-aoe"]["deadline_utc"]) == \
            dt("2033-01-11T11:59:59+00:00"), (
            "FAIL: AoE (UTC-12) 2033-01-10 23:59:59 must be 2033-01-11T11:59:59Z, got %r"
            % got["AI/tz-aoe"]["deadline_utc"])
        assert dt(got["AI/tz-aoe"]["deadline_utc"]) != dt("2033-01-09T11:59:59+00:00"), \
            "FAIL: AoE was mapped to +12 (one day early)"

    def test_pt_dst_winter_vs_summer_offsets(self):
        data = get_json(["--data-file", str(TZ_FIX), "--tz", "America/Los_Angeles"])
        got = {e["conference_key"]: e for e in data["events"]}
        assert dt(got["AI/tz-pt-winter"]["deadline_local"]) == \
            dt("2033-01-15T23:59:59-08:00"), "FAIL: PT winter must be PST (-08:00)"
        assert dt(got["AI/tz-pt-summer"]["deadline_local"]) == \
            dt("2033-07-15T23:59:59-07:00"), "FAIL: PT summer must be PDT (-07:00)"

    def test_pt_dst_boundaries(self):
        data = get_json(["--data-file", str(TZ_FIX), "--tz", "UTC"])
        got = {e["conference_key"]: e for e in data["events"]}
        # spring-forward 2033-03-13: 2033-03-14 00:30 is already PDT (-07:00)
        assert dt(got["AI/tz-pt-spring"]["deadline_utc"]) == \
            dt("2033-03-14T07:30:00+00:00"), "FAIL: PT spring-DST boundary wrong"
        assert dt(got["AI/tz-pt-spring"]["deadline_local"]) == \
            dt("2033-03-14T00:30:00-07:00")
        # fall-back 2033-11-06: 2033-11-07 00:30 is already PST (-08:00)
        assert dt(got["AI/tz-pt-fall"]["deadline_utc"]) == \
            dt("2033-11-07T08:30:00+00:00"), "FAIL: PT fall-DST boundary wrong"
        assert dt(got["AI/tz-pt-fall"]["deadline_local"]) == \
            dt("2033-11-07T00:30:00-08:00")

    def test_tz_switch_changes_display_not_selection(self):
        utc = get_json(["--data-file", str(TZ_FIX), "--tz", "UTC"])
        sh = get_json(["--data-file", str(TZ_FIX), "--tz", "Asia/Shanghai"])
        utc_keys = {(e["conference_key"], e["year"], dt(e["deadline_utc"]))
                    for e in utc["events"]}
        sh_keys = {(e["conference_key"], e["year"], dt(e["deadline_utc"]))
                   for e in sh["events"]}
        assert utc_keys == sh_keys, "FAIL: --tz changed the selected events"
        for ev in utc["events"]:
            assert dt(ev["deadline_local"]).utcoffset() == timedelta(0)
        for ev in sh["events"]:
            assert dt(ev["deadline_local"]).utcoffset() == timedelta(hours=8)


# ---------------------------------------------------------------------------
# SPEC §7.3/§3.4/§3.5/§3.8: selection, TBD, dedupe, ranks on synthetic edge fixture
# ---------------------------------------------------------------------------

class TestSelectionEdgeCases:
    def _edge(self, extra=()):
        return get_json(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai", *extra])

    def test_edge_event_set_and_schema(self):
        data = self._edge()
        now = dt(data["now_utc"])
        catalog = json.loads(EDGE_FIX.read_text(encoding="utf-8"))
        expected, _tbd, tracked, _u, _i = oracle_select(
            catalog, now, "Asia/Shanghai", "AI")
        assert data["tracked_series"] == tracked == 17
        assert_event_sets_equal(data["events"], expected, "synthetic edge AI")
        _check_event_schema(data["events"], "Asia/Shanghai", now=data["now_utc"])

    def test_multiple_rounds_preserved(self):
        data = self._edge()
        rounds = [e for e in data["events"] if e["conference_key"] == "AI/rounds"]
        assert len(rounds) == 2, "FAIL: distinct rounds must not be merged (SPEC §3.5)"
        assert sorted(norm_comment(e["comment"]) for e in rounds) == ["Round 1", "Round 2"]

    def test_abstract_and_paper_deadlines(self):
        data = self._edge()
        got = {e["conference_key"]: e for e in data["events"]}
        duo = got["AI/absduo"]
        assert dt(duo["deadline_utc"]) == dt("2033-05-26T11:59:59+00:00")
        assert dt(duo["abstract_utc"]) == dt("2033-05-21T11:59:59+00:00")
        assert dt(duo["abstract_local"]) == dt("2033-05-21T19:59:59+08:00")
        assert duo["abstract_source"] == "2033-05-20 23:59:59"
        tbdabs = got["AI/tbdabs"]
        assert tbdabs["abstract_utc"] is None, \
            "FAIL: 'TBD' abstract must never be parsed as a date (SPEC §3.4)"
        assert tbdabs["abstract_source"] in ("TBD", None)

    def test_tbd_never_parsed_as_date(self):
        data = self._edge()
        for ev in data["events"]:
            assert str(ev["deadline_utc"]).upper() != "TBD"
            dt(ev["deadline_utc"])  # parses; raises on TBD
            assert str(ev["deadline_source"]).upper() != "TBD"
        keys = {e["conference_key"] for e in data["events"]}
        assert "AI/tbded" not in keys and "AI/abstbd2" not in keys, (
            "FAIL: TBD-only series must not produce paper-deadline rows")

    def test_tbd_section_offline(self):
        data = self._edge(["--include-tbd"])
        titles = sorted(t["conference"] for t in data["tbd"])
        assert titles == ["ABSTBD2", "TBDED"], (
            "FAIL: SPEC §4.4 TBD set mismatch: %r" % titles)
        keys = {t["conference_key"] for t in data["tbd"]}
        assert keys == {"AI/abstbd2", "AI/tbded"}
        for key in ("AI/passed", "AI/oldtbd", "AI/detailv", "AI/unknown-tz"):
            assert key not in keys, (
                "FAIL: %s listed as TBD; SPEC §4.4 excludes passed/announced/"
                "below-current-year/undated latest editions" % key)
        # sorted by title
        assert titles == sorted(titles, key=str.lower)

    def test_include_tbd_table_section(self):
        out = run_ok(["--data-file", str(EDGE_FIX), "--include-tbd",
                      "--tz", "Asia/Shanghai"]).stdout
        assert "TBDED" in out and "ABSTBD2" in out, \
            "FAIL: --include-tbd table does not list the TBD series"
        assert "not announced" in out.lower() or "tbd" in out.lower()
        without = run_ok(["--data-file", str(EDGE_FIX),
                          "--tz", "Asia/Shanghai"]).stdout
        assert "ABSTBD2" not in without, \
            "FAIL: TBD series must not appear without --include-tbd"

    def test_duplicate_events_deduplicated(self):
        data = self._edge()
        dupe = [e for e in data["events"] if e["conference_key"] == "AI/dupe"]
        assert len(dupe) == 1, "FAIL: exact duplicate events must be deduplicated (SPEC §3.8)"

    def test_duplicate_titles_distinguished_by_key(self):
        data = self._edge(["--category", "all"])
        same = [e for e in data["events"] if e["conference"] == "SAMENAME"]
        assert {e["conference_key"] for e in same} == \
            {"AI/same-name-ai", "CG/same-name-cg"}, \
            "FAIL: duplicate titles across areas must stay distinguishable by conference_key"

    def test_missing_rank_fields_tolerated(self):
        data = self._edge()
        got = {e["conference_key"]: e for e in data["events"]}
        assert got["AI/missingranks"]["ccf_rank"] == "B"
        norank = got["AI/norank"]["ccf_rank"]
        assert norank in (None, "", "–", "-"), (
            "FAIL: missing CCF rank must be absent/–, not invented (got %r)" % norank)
        out = run_ok(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai"]).stdout
        assert "MISSINGRANKS" in out and "NORANK" in out

    def test_free_text_date_place_and_missing_link(self):
        data = self._edge()
        got = {e["conference_key"]: e for e in data["events"]}
        ev = got["AI/freetext"]
        assert ev["event_date"] == "TBD", "FAIL: free-text event_date not passed through"
        assert ev["place"] == "TBD", "FAIL: free-text place not passed through"
        assert ev["link"] in (None, ""), \
            "FAIL: absent source link must be null/empty, not invented"

    def test_unknown_timezone_skipped_not_reinterpreted(self):
        data = self._edge()
        assert "AI/unknown-tz" not in {e["conference_key"] for e in data["events"]}, (
            "FAIL: unknown source timezone must be skipped, never treated as local time")
        assert data["events"], "FAIL: unknown tz skipped everything (selection broken)"

    def test_historical_edition_not_selected(self):
        data = self._edge()
        multi = [e for e in data["events"] if e["conference_key"] == "AI/multi"]
        assert len(multi) == 1 and int(multi[0]["year"]) == 2033, (
            "FAIL: only the future edition should be selected, got %r" % multi)

    def test_custom_days_filter_deterministic(self, tmp_path):
        now = datetime.now(timezone.utc)
        catalog = [
            {"title": "NEAR", "description": "d", "sub": "AI",
             "rank": {"ccf": "A"}, "dblp": "near", "conference_key": "AI/near",
             "confs": [{"year": 2033, "id": "near1", "timezone": "UTC",
                        "date": "TBD", "place": "TBD",
                        "timeline": [{"deadline": (now + timedelta(days=10)).strftime(
                            "%Y-%m-%d %H:%M:%S")}]}]},
            {"title": "MID", "description": "d", "sub": "AI",
             "rank": {"ccf": "A"}, "dblp": "mid", "conference_key": "AI/mid",
             "confs": [{"year": 2033, "id": "mid1", "timezone": "UTC",
                        "date": "TBD", "place": "TBD",
                        "timeline": [{"deadline": (now + timedelta(days=40)).strftime(
                            "%Y-%m-%d %H:%M:%S")}]}]},
            {"title": "FAR", "description": "d", "sub": "AI",
             "rank": {"ccf": "A"}, "dblp": "far", "conference_key": "AI/far",
             "confs": [{"year": 2033, "id": "far1", "timezone": "UTC",
                        "date": "TBD", "place": "TBD",
                        "timeline": [{"deadline": (now + timedelta(days=200)).strftime(
                            "%Y-%m-%d %H:%M:%S")}]}]},
        ]
        path = tmp_path / "days.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        data30 = get_json(["--data-file", str(path), "--tz", "UTC", "--days", "30"])
        assert {e["conference_key"] for e in data30["events"]} == {"AI/near"}, \
            "FAIL: --days 30 should keep only the 10-day event"
        data45 = get_json(["--data-file", str(path), "--tz", "UTC", "--days", "45"])
        assert {e["conference_key"] for e in data45["events"]} == {"AI/near", "AI/mid"}
        data_all = get_json(["--data-file", str(path), "--tz", "UTC"])
        assert len(data_all["events"]) == 3, "FAIL: default must not truncate by days"

    def test_all_kinds_offline(self):
        paper = self._edge()
        allkinds = self._edge(["--all-kinds"])
        assert all(e["kind"] == "deadline" for e in paper["events"])
        kinds = {norm_comment(e["kind"]).replace("_deadline", "")
                 for e in allkinds["events"]}
        assert {"abstract", "rebuttal", "decision"} <= kinds, \
            "FAIL: --all-kinds missing non-paper nodes: %r" % kinds
        got = {(e["conference_key"],
                norm_comment(e["kind"]).replace("_deadline", ""),
                dt(e["deadline_utc"])) for e in allkinds["events"]}
        assert ("AI/allkinds", "abstract", dt("2033-06-01T23:59:59+00:00")) in got
        assert ("AI/allkinds", "rebuttal", dt("2033-08-01T23:59:59+00:00")) in got
        assert ("AI/allkinds", "decision", dt("2033-09-01T23:59:59+00:00")) in got


# ---------------------------------------------------------------------------
# SPEC §7.4: filters, validation, data-file / offline determinism
# ---------------------------------------------------------------------------

class TestFiltersAndDataFile:
    def test_data_file_offline_with_bad_proxy(self):
        p = run(["--json", "--data-file", str(EDGE_FIX)], env=BAD_PROXY)
        assert p.returncode == 0, (
            "FAIL: --data-file must work offline (bad proxy); exited %d: %s"
            % (p.returncode, p.stderr[:2000]))
        json.loads(p.stdout)

    def test_data_file_stdin_dash(self):
        catalog_text = EDGE_FIX.read_text(encoding="utf-8")
        data = get_json(["--data-file", "-", "--tz", "Asia/Shanghai"],
                        stdin_text=catalog_text)
        assert data["tracked_series"] == 17
        assert data["events"]

    def test_data_file_live_snapshot_matches_oracle(self):
        data = get_json(["--data-file", str(LIVE_FIXTURE), "--tz", "Asia/Shanghai"])
        catalog = json.loads(LIVE_FIXTURE.read_text(encoding="utf-8"))
        now = dt(data["now_utc"])
        expected, _tbd, tracked, _u, _i = oracle_select(
            catalog, now, "Asia/Shanghai", "AI")
        assert data["tracked_series"] == tracked == _series_count(catalog, "AI")
        assert_event_sets_equal(data["events"], expected, "pinned live snapshot AI")

    def test_data_file_missing_exits_nonzero(self):
        p = run(["--data-file", "/nonexistent/definitely-missing.json"])
        assert p.returncode != 0, "FAIL: missing --data-file must exit non-zero"
        assert p.stderr.strip(), "FAIL: missing --data-file produced no stderr message"
        assert "Conference" not in p.stdout, "FAIL: printed a table after data-file error"

    def test_data_file_empty_exits_nonzero(self):
        p = run(["--data-file", "/dev/null"])
        assert p.returncode != 0, "FAIL: empty/invalid --data-file must exit non-zero"
        assert p.stderr.strip()
        assert "Conference" not in p.stdout

    def test_invalid_category_exits_nonzero(self):
        p = run(["--data-file", str(EDGE_FIX), "--category", "NOPE"])
        assert p.returncode != 0, "FAIL: unknown --category must exit non-zero (SPEC §3.7)"
        assert p.stderr.strip(), "FAIL: unknown --category produced no stderr message"

    def test_invalid_rank_exits_nonzero(self):
        p = run(["--data-file", str(EDGE_FIX), "--rank", "Z"])
        assert p.returncode != 0, "FAIL: unknown --rank must exit non-zero (SPEC §3.7)"
        assert p.stderr.strip()

    def test_valid_rank_filter_offline(self):
        data = get_json(["--data-file", str(EDGE_FIX), "--rank", "A"])
        assert {e["ccf_rank"] for e in data["events"]} == {"A"}
        assert {e["conference_key"] for e in data["events"]} == {"AI/same-name-ai"}

    def test_valid_category_filter_offline(self):
        data = get_json(["--data-file", str(EDGE_FIX), "--category", "CG"])
        assert {e["conference_key"] for e in data["events"]} == {"CG/same-name-cg"}
        assert data["tracked_series"] == 1

    def test_invalid_tz_exits_nonzero(self):
        p = run(["--data-file", str(EDGE_FIX), "--tz", "Not/AZone"])
        assert p.returncode != 0, "FAIL: unknown --tz must exit non-zero with no table"
        assert p.stderr.strip()
        assert "Conference" not in p.stdout

    def test_limit_table_cuts_and_notes_more(self):
        full = get_json(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai"])
        assert len(full["events"]) == 12
        p = run_ok(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai",
                    "--limit", "3", "-v"])  # the hidden-row count lives in the -v footer
        out = p.stdout
        for ev in full["events"][:3]:
            title = ev["conference"]
            assert title in out, "FAIL: --limit 3 dropped row %r" % title
        fourth = full["events"][3]["conference"]
        assert fourth not in out, "FAIL: --limit 3 did not cut row %r" % fourth
        assert re.search(r"(?is)\b9\b[^\n]{0,30}more|more[^\n]{0,30}\b9\b", out), \
            "FAIL: --limit 3 must show a '9 more' note (SPEC §4.1)"

    def test_limit_zero_means_no_limit(self):
        p = run_ok(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai",
                    "--limit", "0", "-v"])  # -v: inspect the footer too
        assert "9 more" not in p.stdout and "more" not in p.stdout.lower()

    def test_rank_n_and_unknown_ranks_offline(self):
        data = get_json(["--data-file", str(EDGE_FIX), "--rank", "N"])
        assert {e["ccf_rank"] for e in data["events"]} == {"N"}

    def test_negative_days_does_not_widen_silently(self):
        base = get_json(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai"])
        p = run(["--json", "--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai",
                 "--days", "-5"])
        assert p.returncode in (0, 1, 2), "FAIL: --days -5 crashed: %r" % p.returncode
        if p.returncode == 0:
            data = json.loads(p.stdout)
            assert {event_tuple(e) for e in data["events"]} == \
                {event_tuple(e) for e in base["events"]}, (
                "FAIL: negative --days silently changed the selection")

    def test_negative_limit_does_not_crash(self):
        p = run(["--json", "--data-file", str(EDGE_FIX), "--limit", "-1"])
        assert p.returncode in (0, 1, 2), "FAIL: --limit -1 crashed: %r" % p.returncode
        if p.returncode == 0:
            data = json.loads(p.stdout)
            assert isinstance(data["events"], list)


# ---------------------------------------------------------------------------
# SPEC §7.5: fetch failure, no stale fallback, freshness
# ---------------------------------------------------------------------------

class TestFailureModes:
    def test_fetch_failure_no_table_no_cache_fallback(self):
        p = run(["--json"], env=BAD_PROXY)
        if p.returncode == 0:
            pytest.skip("CLI does not honour proxy env vars; cannot inject a network "
                        "failure this way (documented residual risk)")
        assert p.returncode != 0, "FAIL: fetch failure must exit non-zero"
        assert p.stderr.strip(), "FAIL: fetch failure must print a clear stderr message"
        assert "Conference" not in p.stdout, "FAIL: printed a table after fetch failure"
        assert not DATE_TOKEN.search(p.stdout), \
            "FAIL: fetch failure printed deadline-looking output (stale fallback?)"
        # A second failing run must fail too: no silently cached previous fetch.
        p2 = run(["--json"], env=BAD_PROXY)
        assert p2.returncode != 0, "FAIL: second fetch failure succeeded (stale cache?)"

    def test_fetch_failure_default_run(self):
        p = run([], env=BAD_PROXY)
        if p.returncode == 0:
            pytest.skip("CLI does not honour proxy env vars; cannot inject a network "
                        "failure this way (documented residual risk)")
        assert p.returncode != 0
        assert "Conference" not in p.stdout
        assert p.stderr.strip()

    def test_no_stale_cache_file_in_cwd(self, tmp_path):
        # Run from a pristine cwd; a cache-prone CLI would leave or reuse state.
        p = subprocess.run(
            _cli_argv(["--json", "--data-file", str(EDGE_FIX)]),
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert p.returncode == 0, "FAIL: --data-file run from clean cwd failed: %s" % p.stderr
        leftovers = [f for f in tmp_path.iterdir()]
        assert not leftovers, "FAIL: CLI wrote cache/state files: %r" % leftovers


# ---------------------------------------------------------------------------
# SPEC §7.3/§4.3: --details
# ---------------------------------------------------------------------------

class TestDetails:
    def test_details_live_snapshot_cvpr(self):
        catalog = json.loads(LIVE_FIXTURE.read_text(encoding="utf-8"))
        cvpr = next((s for s in catalog if s["conference_key"] == "AI/cvpr"), None)
        if cvpr is None:
            pytest.skip("AI/cvpr absent from pinned catalog")
        latest = max(cvpr["confs"], key=lambda c: c["year"])
        p = run_ok(["--data-file", str(LIVE_FIXTURE), "--details", "cvpr",
                    "--tz", "Asia/Shanghai"])
        out = p.stdout
        assert "AI/cvpr" in out, "FAIL: --details must distinguish by conference_key"
        assert cvpr["description"] in out, "FAIL: --details missing full description"
        assert "UTC-12" in out, "FAIL: --details missing source timezone"
        assert "CCF" in out.upper() and "CORE" in out.upper() and "THCPL" in out.upper(), \
            "FAIL: --details missing CCF/CORE/THCPL ranks"
        assert latest.get("link") and latest["link"] in out, "FAIL: --details missing link"
        assert "2026-11-16 23:59:59" in out, \
            "FAIL: --details missing raw source datetime (auditability, SPEC §3.9)"
        assert "2026-11-17" in out and "19:59" in out, \
            "FAIL: --details missing local (Asia/Shanghai) deadline"
        for field_value in ("2026-11-10 23:59:59", "2027-02-01 23:59:59",
                            "2027-02-25 23:59:59"):
            if any(field_value in json.dumps(entry) for entry in latest["timeline"]):
                assert field_value in out, (
                    "FAIL: --details must show the full latest-edition timeline (%r)"
                    % field_value)

    def test_details_multiple_matches_offline(self):
        p = run_ok(["--data-file", str(EDGE_FIX), "--details", "samename"])
        out = p.stdout
        assert "AI/same-name-ai" in out and "CG/same-name-cg" in out, (
            "FAIL: --details must print every matching series with its conference_key")

    def test_details_no_match_exits_zero_with_message(self):
        p = run(["--data-file", str(EDGE_FIX), "--details",
                 "zzz-no-such-series-zzz"])
        assert p.returncode == 0, (
            "FAIL: SPEC §4.3 says no matches -> message + exit 0 (got %d)"
            % p.returncode)
        combined = p.stdout + "\n" + p.stderr
        assert re.search(r"(?i)no match|not found|nothing|no series", combined), \
            "FAIL: --details no-match printed no clear message"

    def test_details_marks_passed_nodes(self):
        p = run_ok(["--data-file", str(EDGE_FIX), "--details", "detailv",
                    "--tz", "Asia/Shanghai"])
        out = p.stdout
        assert "PASSED" in out.upper(), \
            "FAIL: --details must mark passed timeline nodes PASSED (SPEC §4.3)"
        assert "2020-01-01 23:59:59" in out, \
            "FAIL: --details must show raw source datetime for passed nodes"
        assert "2033-06-15 23:59:59" in out, \
            "FAIL: --details must show the full latest-edition timeline (rebuttal)"


# ---------------------------------------------------------------------------
# SPEC §7.1/§7.6: default table, rendering, aesthetics, colors
# ---------------------------------------------------------------------------

def _table_run(args=(), columns=None):
    env = {"COLUMNS": str(columns)} if columns else None
    return run_ok(list(args), env=env)


class TestRendering:
    def test_live_default_table_shows_live_rows(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai"])
        p = _table_run(["--tz", "Asia/Shanghai"])
        out = p.stdout
        assert not ANSI.search(out), "FAIL: ANSI escapes in piped (non-TTY) table output"
        assert "Conference" in out and "Deadline" in out, \
            "FAIL: default table missing Conference/Deadline headers"
        assert "Asia/Shanghai" in out, \
            "FAIL: deadline column/header must name the display timezone"
        # Quiet by default: source/fetch/counts/caveat footer is opt-in via -v.
        low = out.lower()
        assert "series tracked" not in low and "caveat" not in low and \
            "fetched" not in low, (
            "FAIL: default output must be quiet (footer belongs to -v/--verbose)")
        assert SOURCE_URL not in out, \
            "FAIL: default output must not print the footer source URL"
        events = data["events"]
        assert len(events) >= 10, "FAIL: suspiciously few upcoming AI deadlines"
        for ev in events[:3] + events[-2:]:
            assert ev["conference"] in out, (
                "FAIL: default table missing row for %r" % ev["conference"])
            local = dt(ev["deadline_local"])
            assert local.strftime("%Y-%m-%d") in out and \
                local.strftime("%H:%M") in out, (
                "FAIL: default table missing correct local time for %r" % ev["conference"])

    def test_verbose_shows_footer(self, live_catalog):
        data = get_json(["--tz", "Asia/Shanghai"])
        p = _table_run(["--tz", "Asia/Shanghai", "--verbose"])
        out = p.stdout
        assert not ANSI.search(out), "FAIL: ANSI escapes in piped (non-TTY) output"
        assert SOURCE_URL in out, "FAIL: -v footer missing data source URL"
        assert "official" in out.lower(), \
            "FAIL: -v footer missing 'verify against official venue page' caveat"
        assert str(data["tracked_series"]) in out, \
            "FAIL: -v footer missing tracked-series count"
        assert re.search(r"\b%d\b" % len(data["events"]), out), \
            "FAIL: -v footer does not report the shown-event count"

    @pytest.mark.parametrize("columns", [80, 120])
    def test_live_table_respects_terminal_width(self, columns):
        p = _table_run([], columns=columns)
        lines = p.stdout.splitlines()
        too_wide = [line for line in lines if len(line) > columns]
        assert not too_wide, (
            "FAIL: table exceeds COLUMNS=%d:\n%s" % (columns, "\n".join(too_wide[:5])))
        assert "Conference" in p.stdout and "Deadline" in p.stdout
        assert not re.search(r"\b\d{4}-\d{2}-$", p.stdout), \
            "FAIL: date token wrapped mid-value at width %d" % columns
        assert not re.search(r"\b\d{4}-$", p.stdout)

    @pytest.mark.parametrize("columns", [80, 120])
    def test_offline_table_truncates_long_note(self, columns):
        p = _table_run(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai"],
                       columns=columns)
        out = p.stdout
        assert len(max(out.splitlines(), key=len)) <= columns, \
            "FAIL: table exceeds COLUMNS=%d" % columns
        assert "LONGNOTE" in out
        assert "…" in out or "..." in out, (
            "FAIL: long Note value must be truncated with an ellipsis (SPEC §4.5)")

    def test_no_ansi_when_piped_no_color_flag_and_env(self):
        for args, env in (
            (["--data-file", str(EDGE_FIX)], None),
            (["--data-file", str(EDGE_FIX), "--no-color"], None),
            (["--data-file", str(EDGE_FIX)], {"NO_COLOR": "1"}),
            (["--json", "--data-file", str(EDGE_FIX)], None),
            (["--json", "--data-file", str(EDGE_FIX)], {"NO_COLOR": "1"}),
        ):
            p = run(args, env=env)
            assert p.returncode == 0, "FAIL: %r exited %d" % (args, p.returncode)
            assert not ANSI.search(p.stdout), (
                "FAIL: ANSI escape in output for args=%r env=%r" % (args, env))

    def test_header_names_timezone(self):
        p = _table_run(["--data-file", str(EDGE_FIX), "--tz", "America/Los_Angeles"])
        lines = p.stdout.splitlines()
        deadline_idx = next((i for i, ln in enumerate(lines)
                             if "Deadline" in ln and "Left" in ln), None)
        assert deadline_idx is not None, "FAIL: no Deadline header line"
        # The header cell may wrap at narrow widths; the tz name must still appear
        # inside the header block (SPEC §3.9: header must name the display tz).
        header_block = lines[deadline_idx:deadline_idx + 3]
        assert any("America/Los_Angeles" in ln for ln in header_block), (
            "FAIL: deadline column header must name the display timezone; header=%r"
            % header_block)

    def test_empty_result_still_clean(self):
        # --days 1 against 2033-only fixture yields zero rows; must not crash.
        p = run(["--data-file", str(EDGE_FIX), "--tz", "Asia/Shanghai", "--days", "1"])
        assert p.returncode == 0, "FAIL: empty result exited %d: %s" % (
            p.returncode, p.stderr[:1500])
        assert not ANSI.search(p.stdout)
        assert "Conference" in p.stdout or "no upcoming" in p.stdout.lower(), \
            "FAIL: empty result printed neither a table header nor a clear message"


# ---------------------------------------------------------------------------
# Cross-check: independent ground truth from the verifier oracle definitions
# ---------------------------------------------------------------------------

class TestOracleSelfConsistency:
    def test_oracle_utc_minus_12_semantics(self):
        tz = oracle_live.tz_from_source("UTC-12")
        parsed = oracle_live.parse_source_datetime("2026-11-16 23:59:59", tz)
        assert parsed == dt("2026-11-17T11:59:59+00:00")
        assert oracle_live.tz_from_source("UTC-12") == \
            oracle_live.tz_from_source("AoE")
        assert oracle_live.tz_from_source("UTC-12").utcoffset(None) == \
            timedelta(hours=-12)

    def test_oracle_never_parses_tbd(self):
        assert oracle_live.parse_source_datetime("TBD", timezone.utc) is None
        assert oracle_live.parse_source_datetime("tbd", timezone.utc) is None
        assert oracle_live.parse_source_datetime(None, timezone.utc) is None

    def test_oracle_pt_dst(self):
        pt = oracle_live.tz_from_source("PT")
        winter = oracle_live.parse_source_datetime("2033-01-15 23:59:59", pt)
        summer = oracle_live.parse_source_datetime("2033-07-15 23:59:59", pt)
        assert winter == dt("2033-01-16T07:59:59+00:00")
        assert summer == dt("2033-07-16T06:59:59+00:00")

    def test_expected_live_fixture_consistency(self):
        path = FIX / "expected_live.json"
        assert path.exists(), \
            "FAIL: tests/fixtures/expected_live.json (oracle snapshot) missing"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["count"] == len(data["events"]) == 20
        assert data["tracked_series"] == 61
        keys = {e["conference_key"] for e in data["events"]}
        assert "AI/cvpr" in keys
        assert {t["conference_key"] for t in data["tbd"]} == \
            {"AI/colt", "AI/gecco", "AI/iccv"}

    def test_oracle_agrees_with_source_scout_ground_truth(self):
        """Cross-check the verifier oracle against source-scout's independent truth.

        Two independently written parsers/selectors must agree on the full
        upcoming AI paper-deadline set and the TBD set.  (Reference instants
        differ by a few minutes; no deadline falls in that gap on this data.)
        """
        scout_path = ROOT / "research" / "expected_ai_deadlines.json"
        if not scout_path.exists():
            pytest.skip("research/expected_ai_deadlines.json not present yet")
        scout = json.loads(scout_path.read_text(encoding="utf-8"))
        mine = json.loads((FIX / "expected_live.json").read_text(encoding="utf-8"))

        def tuples(events):
            return {(e["conference_key"], int(e["year"]), dt(e["deadline_utc"]),
                     norm_comment(e.get("comment"))) for e in events}

        scout_events = tuples(scout.get("events") or [])
        my_events = tuples(mine["events"])
        assert scout_events == my_events, (
            "FAIL: verifier oracle disagrees with source-scout ground truth\n"
            "  only-scout: %s\n  only-oracle: %s"
            % (sorted(scout_events - my_events, key=repr)[:10],
               sorted(my_events - scout_events, key=repr)[:10]))
        scout_tbd = {t["conference_key"] for t in (scout.get("tbd") or [])}
        my_tbd = {t["conference_key"] for t in mine["tbd"]}
        assert scout_tbd == my_tbd, (
            "FAIL: TBD set disagrees with source-scout: only-scout=%s only-oracle=%s"
            % (sorted(scout_tbd - my_tbd), sorted(my_tbd - scout_tbd)))
        assert len(scout_events) == 20 and len(scout_tbd) == 3
