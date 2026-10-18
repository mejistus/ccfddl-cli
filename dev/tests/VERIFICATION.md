# Independent Verification — live CCFDDL CLI (`./ccfddl`, SPEC v2)

Verifier: `verifier` teammate (independent of `builder` and `source-scout`).
Date: 2026-10-18 (Asia/Shanghai). Authority: `SPEC.md` sha256
`8ae6869fec2f30b753a3d282d92be8a6a7b8035595f0bafa335f004bd0408385` (305 lines,
includes the 15:58 UTC-12 sign correction).

## Verdict

**PASS — all 7 SPEC §7 acceptance criteria pass.** Evidence below: 75/75 black-box
tests green; the live event set is an **exact match (0 diffs, 0 s error)** against two
independent ground truths (the verifier's own oracle and `research/expected_ai_deadlines.json`);
TBD set exactly `{COLT 2027, GECCO 2027, ICCV 2027}`; UTC-12 sign, PT DST boundaries,
TBD handling, filters, failure modes, aesthetics and no-hardcoded-data all verified.

No accuracy defects and no SPEC deviations were found. The single cosmetic README
imprecision from the first pass (`COLUMNS` lower-bound wording, §7.7) was fixed by a
docs-only README edit; re-verification of the updated tree confirms **no open nits**.

## Build under test (stable, final)

| Artifact | Bytes | sha256 | mtime |
|---|---|---|---|
| `./ccfddl` | 62 396 | `848b33e4d619bbad6c855459c7140cc5761b26b446634c1fcba539ee3f35f2b2` | 2026-10-18 16:08 |
| `README.md` | 16 969 | `9f86f8135308cdb4a45343e6ce896f3cb625b35c9f33f3dcfe870ca115e01a44` | 2026-10-18 16:15 (docs-only `COLUMNS` wording update) |
| `SPEC.md` | 17 154 | `8ae6869fec2f30b753a3d282d92be8a6a7b8035595f0bafa335f004bd0408385` | 2026-10-18 15:56 |

The CLI hash was recorded before and after the full suite and was identical
(“build stable during suite”), so all results below refer to the same artifact.
**Docs-only follow-up:** after the first verification pass the Lead reworded the README
`COLUMNS` row only; `./ccfddl` was untouched (sha256 unchanged), the README was
re-hashed above, and the full suite was re-run on the updated tree: **75/75 passed**
(26.55 s; README/contract subset 7/7).
Environment: Python 3.12.13, pytest 9.1.1, macOS; `rich` installed. Harness env has
`NO_COLOR=1`/`TERM=dumb`, so TTY/colour behaviour was additionally probed through a
real pty (below).

## Method

1. **Black box only.** Every check invokes `./ccfddl` as a subprocess (no imports of the
   implementation, no monkeypatching). Tests: `tests/test_ccfddl.py` (75 tests).
2. **Independent oracle.** `tests/oracle_live.py` (verifier code, Python stdlib only,
   does not import `./ccfddl` or `research/check_ground_truth.py`) re-implements SPEC §3
   selection/timezone/TBD rules and emits `tests/fixtures/expected_live.json` /
   `expected_verify.json`.
3. **Two external cross-checks.** (a) my oracle vs (b) source-scout's independently
   produced `research/expected_ai_deadlines.json`.
4. **Fresh data.** Catalog re-fetched at 2026-10-18T08:08:59–08:09:02Z into
   `tests/fixtures/allconf_verify.json`; bytes 777 074, sha256
   `19ad4305b5d80c5ea599d320bee33bd09b537c1000f5c8fd4d522c359ca88879` (identical to the
   pinned snapshot and to source-scout's fetch → same upstream revision).
5. **Deterministic fixtures** for timezone/DST/selection edge cases:
   `tests/fixtures/synthetic_tz.json`, `tests/fixtures/synthetic_edge.json`
   (provenance: `tests/fixtures/provenance.md`).

Commands used (all from `/Users/eculid/Desktop/CodeBase/tools`):

```sh
python3 -m pytest tests/test_ccfddl.py -q          # 75 passed (57.72 s first run, 22.10 s final re-run)
python3 tests/oracle_live.py --catalog tests/fixtures/allconf_verify.json \
    --now 2026-10-18T08:09:02Z --out tests/fixtures/expected_verify.json
./ccfddl ; ./ccfddl --json ; ./ccfddl --json --include-tbd
./ccfddl --rank A ; ./ccfddl --category CG ; ./ccfddl --days 30 ; ./ccfddl --tz UTC
./ccfddl --limit 5 ; ./ccfddl --all-kinds ; ./ccfddl --details cvpr
./ccfddl --data-file tests/fixtures/synthetic_tz.json --json --tz America/Los_Angeles
COLUMNS=80 ./ccfddl ; COLUMNS=120 ./ccfddl
env https_proxy=http://127.0.0.1:9 ./ccfddl --json   # network-failure probe
```

## Independent ground truth comparison (SPEC §7.2)

Fresh live run `./ccfddl --json --tz Asia/Shanghai` (now_utc 2026-10-18T08:10:28Z):

| Comparison | Result |
|---|---|
| CLI events vs verifier oracle events | **20 vs 20, exact ordered match, 0 diffs** |
| Per-event audit fields (`deadline_utc`, `deadline_local`, `deadline_source`, `source_timezone`, `abstract_*`, `comment`, `event_date`, `place`, `link`, `ccf_rank`) | **0 differences** |
| CLI events vs `research/expected_ai_deadlines.json` | **20 vs 20, exact set match, 0 diffs** |
| `tracked_series` | CLI 61; live catalog `sub=="AI"` count 61 (dynamic; not hardcoded) |
| Ordering | ascending `deadline_utc`; all `deadline_local` == instant converted to Asia/Shanghai (0 mismatches) |
| TBD | CLI = oracle = source-scout = `{AI/colt 2027, AI/gecco 2027, AI/iccv 2027}`; date/place/link/rank fields exact |
| JSON instants error vs oracle | **0 s** (SPEC allows ≤1 s) |
| Duplicate instants | 4 events share 2026-11-02T11:59:59Z (EuroGP/EvoApplications/EvoCOP/EvoMUSART); distinct `conference_key`s and titles → correctly not deduplicated |

The full verified event set (all 20 rows; UTC instants are what the CLI prints and what
both oracles independently compute):

| # | conference_key | yr | CCF | source (tz) | deadline_utc | Asia/Shanghai |
|---|---|---|---|---|---|---|
| 1 | AI/eurogp | 2027 | N | 2026-11-01 23:59:59 (AoE) | 2026-11-02T11:59:59Z | 2026-11-02 19:59:59 |
| 2 | AI/evoapps | 2027 | N | 2026-11-01 23:59:59 (AoE) | 2026-11-02T11:59:59Z | 2026-11-02 19:59:59 |
| 3 | AI/evocop | 2027 | N | 2026-11-01 23:59:59 (AoE) | 2026-11-02T11:59:59Z | 2026-11-02 19:59:59 |
| 4 | AI/evomusart | 2027 | N | 2026-11-01 23:59:59 (AoE) | 2026-11-02T11:59:59Z | 2026-11-02 19:59:59 |
| 5 | AI/cvpr | 2027 | A | 2026-11-16 23:59:59 (UTC-12) | 2026-11-17T11:59:59Z | 2026-11-17 19:59:59 |
| 6 | AI/esann | 2027 | N | 2026-11-18 23:59:59 (UTC-8) | 2026-11-19T07:59:59Z | 2026-11-19 15:59:59 |
| 7 | AI/rss | 2027 | N | 2026-12-04 23:59:59 (AoE) | 2026-12-05T11:59:59Z | 2026-12-05 19:59:59 |
| 8 | AI/cpal | 2027 | N | 2026-12-05 23:59:59 (AoE) | 2026-12-06T11:59:59Z | 2026-12-06 19:59:59 |
| 9 | AI/icaps | 2027 | B | 2026-12-14 23:59:59 (UTC-12) | 2026-12-15T11:59:59Z | 2026-12-15 19:59:59 |
| 10 | AI/coling | 2027 | B | 2026-12-23 23:59:59 (UTC-12) | 2026-12-24T11:59:59Z | 2026-12-24 19:59:59 |
| 11 | AI/naacl | 2027 | B | 2026-12-23 23:59:59 (UTC-12) | 2026-12-24T11:59:59Z | 2026-12-24 19:59:59 |
| 12 | AI/acl | 2027 | A | 2027-01-04 23:59:59 (UTC-12) | 2027-01-05T11:59:59Z | 2027-01-05 19:59:59 |
| 13 | AI/ijcai | 2027 | B | 2027-01-11 23:59:00 (AoE) | 2027-01-12T11:59:00Z | 2027-01-12 19:59:00 |
| 14 | AI/ijcnn | 2027 | C | 2027-01-31 23:59:59 (UTC-12) | 2027-02-01T11:59:59Z | 2027-02-01 19:59:59 |
| 15 | AI/icdar | 2027 | C | 2027-02-20 23:59:59 (AoE) | 2027-02-21T11:59:59Z | 2027-02-21 19:59:59 |
| 16 | AI/cec | 2027 | C | 2027-02-28 23:59:59 (UTC-12) | 2027-03-01T11:59:59Z | 2027-03-01 19:59:59 |
| 17 | AI/iros | 2027 | C | 2027-03-01 23:59:59 (AoE) | 2027-03-02T11:59:59Z | 2027-03-02 19:59:59 |
| 18 | AI/icpr | 2027 | C | 2027-03-08 23:59:59 (AoE) | 2027-03-09T11:59:59Z | 2027-03-09 19:59:59 |
| 19 | AI/ecai | 2027 | B | 2027-04-14 23:59:59 (AoE) | 2027-04-15T11:59:59Z | 2027-04-15 19:59:59 |
| 20 | AI/kr | 2027 | B | 2027-04-28 23:59:59 (AoE) | 2027-04-29T11:59:59Z | 2027-04-29 19:59:59 |

TBD (SPEC §4.4): COLT 2027 (`June 28 - July 2, 2027`, Tokyo, Japan, CCF B),
GECCO 2027 (`July 12-16, 2027`, Kraków, Poland, CCF C), ICCV 2027
(`October 2-8, 2027`, Hong Kong, China, CCF A) — matching both oracles exactly.
AAAI 2027 (deadline already passed 2026-07-28) is correctly **not** listed as TBD.

## SPEC §7 criterion-by-criterion

### §7.1 `./ccfddl` runs clean with no args; live AI paper deadlines; no hardcoded data — PASS

`COLUMNS=120 ./ccfddl` → exit 0, realistic 20-row table, correct local times
(programmatic check: every one of the 20 `--json` events' title+year, local date and
`HH:MM` appears in the rendered table — 0 missing fragments). Snippet:

```
Upcoming AI Conference Deadlines — live CCFDDL data

Conference            CCF  Deadline (Asia/Shanghai)  Left     Abstract          Note
────────────────────────────────────────────────────────────────────────────────────────
EuroGP 2027           –    2026-11-02 Mon 19:59      15d 3h   –                 Full papers
...
CVPR 2027             A    2026-11-17 Tue 19:59      30d 3h   2026-11-11 19:59  –
...
KR 2027               B    2027-04-29 Thu 19:59      193d 3h  2027-04-24 19:59  Main track; author response period: Jun…

────────────────────────────────────────────────────────────────
source   : https://ccfddl.com/conference/allconf.json
fetched  : 2026-10-18 16:10:19 UTC+08:00  (2026-10-18T08:10:19Z)  — live fetch
showing  : 20 paper deadlines · 61 AI series tracked · display tz Asia/Shanghai (UTC+08:00)
tbd      : 3 series have no announced deadline; use --include-tbd to list them (TBD is unknown, not a date)
caveat   : live catalog data can change; always verify the deadline on the official venue page before acting.
```

No hardcoded venue/date data — grep over the whole script returns **nothing**:

```sh
grep -nEi '\b(AAAI|AAMAS|ACL|AISTATS|CVPR|ECCV|ICCV|ICLR|ICML|IJCAI|NeurIPS|NIPS|EMNLP|NAACL|COLING|ICAPS|RSS|ESANN|KDD|SIGMOD|OSDI|SOSP|ICSE|FSE|MICCAI|BMVC|WACV|CoRL|COLM|GECCO|COLT|UAI)\b' ccfddl   # 0 matches
grep -nE '\b20[0-9]{2}-[0-9]{2}-[0-9]{2}\b' ccfddl   # 0 matches (no hardcoded ISO dates)
grep -nE '\b20(1|2)[0-9]\b' ccfddl                   # 0 matches (no hardcoded year literals)
```

`tests/test_ccfddl.py::test_no_hardcoded_venue_or_date_data` additionally does an AST
scan of every non-docstring, non-argparse-help string constant (so exceptions cannot
hide in comments/docstrings) and also finds none. `./ccfddl` is byte-different from
`legacy/ccfddl-v1-hardcoded.py`; v1's `requests`/`tabulate`/`colorama` imports are gone,
fetching uses stdlib `urllib`.

### §7.2 `--json` valid; every `deadline_utc` matches independent ground truth; ordering; dynamic `tracked_series` — PASS

* `--json` parses as a single JSON object on stdout, no ANSI, no extra text.
* Top-level keys exactly per §4.2: `source, fetched_at, display_timezone, category,
  now_utc, filters, tracked_series, events, tbd`; `filters` has
  `days/ranks/limit/all_kinds`; `source` is the catalog URL.
* Every event has all audit fields (`deadline_source`, `source_timezone`,
  `deadline_utc/local`, `abstract_*`, `days_left`, `seconds_left`, `comment`,
  `event_date`, `place`, `link`, `ccf_rank`, `kind`); `days_left == seconds_left // 86400`;
  `seconds_left` consistent with `now_utc`; ISO-8601 with explicit offsets.
* Event set/order: **exact** match to both independent ground truths (table above), 0 s
  instant error, ascending UTC.
* `tracked_series` = 61 = live count of `sub == "AI"` series (checked dynamically from the
  same catalog; 378 for `--category all`).

### §7.3 Timezone semantics (UTC-12 sign, PT DST, TBD) — PASS

CVPR 2027 concrete case (real CLI `--json` output):

```
deadline_source "2026-11-16 23:59:59"  source_timezone "UTC-12"
deadline_utc    "2026-11-17T11:59:59+00:00"
deadline_local  "2026-11-17T19:59:59+08:00"      (Asia/Shanghai)
abstract        "2026-11-10 23:59:59" UTC-12 → "2026-11-11T11:59:59Z" → "2026-11-11T19:59:59+08:00"
```

Rendered table row: `CVPR 2027  A  2026-11-17 Tue 19:59  30d 3h  2026-11-11 19:59  –`.
The independent test also asserts the value is **not** `2026-11-16T19:59:59+08:00`
(the one-day-early symptom of a `UTC-12 → +12` sign bug), using both the live catalog
and synthetic fixtures where a `+12` mapping would yield `2033-02-10T11:59:59Z` instead
of the correct `2033-02-11T11:59:59Z`.

`PT` DST via `tests/fixtures/synthetic_tz.json` (`--data-file ... --json --tz ...`):

| source (PT) | expected UTC | LA display | Shanghai display |
|---|---|---|---|
| 2033-01-15 23:59:59 (winter) | 2033-01-16T07:59:59Z | 2033-01-15T23:59:59-08:00 | 2033-01-16T15:59:59+08:00 |
| 2033-07-15 23:59:59 (summer) | 2033-07-16T06:59:59Z | 2033-07-15T23:59:59-07:00 | 2033-07-16T14:59:59+08:00 |
| 2033-03-14 00:30:00 (after spring-forward 2033-03-13) | 2033-03-14T07:30:00Z | 2033-03-14T00:30:00-07:00 | — |
| 2033-11-07 00:30:00 (after fall-back 2033-11-06) | 2033-11-07T08:30:00Z | 2033-11-07T00:30:00-08:00 | — |

All 11 synthetic tz cases (AoE, UTC-12, UTC, UTC+0, UTC±N, PT×4) match exact expected
instants. `TBD` is never parsed: `AI/tbded`/`AI/abstbd2` produce no paper row (TBD
section only); a TBD abstract yields `abstract_utc: null` while its dated paper row is
still shown (`AI/tbdabs`); dates in output are all valid ISO instants. An unknown source
timezone (`MARS`) is skipped with a stderr warning, never interpreted as local:
`ccfddl: warning: unrecognized source timezone 'MARS'; skipped its deadlines (affects: UNKNOWNTZ)`.

### §7.4 Filters (`--rank/--category/--days/--tz/--limit/--include-tbd/--data-file` + bad values) — PASS

Live run, compared event-by-event to the oracle (all `oracle match=True`):

| Command | Result |
|---|---|
| `--rank A` / `B` / `C` / `N` / `A,B` | 2 / 6 / 5 / 7 / 8 events; only requested ranks returned; exact oracle match |
| `--category CG` | 11 events, CG venues only; `tracked_series=36`; exact oracle match |
| `--category all` | 125 events, `tracked_series=378` (all catalog series); exact oracle match |
| `--category cg` (lowercase) | same 11 events as `CG` (case-insensitive per SPEC §2.1) |
| `--days 1` / `30` / `365` | 0 / 4 / 20 events; exact oracle match (boundary `now+N days`) |
| `--tz UTC` | same selection as Asia/Shanghai; local offsets `+00:00` vs `+08:00`; instants unchanged |
| `--limit 5` | 5 events = first 5 of default; `filters.limit=5`; footer: `showing : 5 of 20 …` + `limit : 15 more matching row(s) hidden by --limit 5` |
| `--include-tbd` | separate `TBD — deadline not yet announced (3 series)` section, sorted by title, labelled, no countdowns; `--json` `tbd` identical whether or not the flag is given |
| `--all-kinds` | 66 events (20 paper + 46 abstract/rebuttal/decision), adds `Kind` column; default paper rows are a subset; ordering still ascending |
| `--data-file tests/fixtures/synthetic_edge.json` | works with no network; `fetched_at` = file mtime; stdin (`--data-file -`) works; `--json` output is a strict superset of SPEC schema |
| `--details cvpr --data-file …` | full detail view with raw source + source tz + local times + link (see §7.7) |

Negative cases all exit non-zero with clear stderr and **no table on stdout**:
unknown `--tz` (rc 2, argparse usage), unknown `--category` (rc 2, `unknown category 'NOPE'; available: AI, CG (or 'all')`),
unknown `--rank` (rc 2), missing `--data-file` (rc 1, `cannot read data file …: No such file or directory`),
`/dev/null` (rc 1, `not valid JSON`), directory path (rc 1, `Is a directory`), JSON object
instead of list (rc 1, `unexpected shape: expected a JSON list`), empty list (rc 1,
`contains no conference series`).

### §7.5 Fetch failure → error, no table, no stale fallback — PASS

Guaranteed-bad proxy (`http_proxy`/`https_proxy`/`ALL_PROXY = http://127.0.0.1:9`):

```
$ env https_proxy=http://127.0.0.1:9 ./ccfddl --json
rc=1, stdout="" (0 bytes)
stderr: ccfddl: error: cannot fetch https://ccfddl.com/conference/allconf.json:
        [Errno 61] Connection refused; no data displayed
        (this tool never falls back to a stale table)
```

Default (non-JSON) run behaves identically; a second failing run fails the same way
(no in-memory/on-disk cache from the successful runs). `--data-file` runs under the same
bad proxy still succeed (offline path is genuinely local; no network touched). A run
from a pristine empty cwd leaves no cache/state files behind. `--help`/`--version`
work under the bad proxy (no network needed). Freshness is also evidenced by the live
footer fetch timestamp matching the run time.

### §7.6 Aesthetics / rendering / colour — PASS

* Piped table: no ANSI, aligned columns, full date incl. year + 24h time; header names
  the display timezone (`Deadline (Asia/Shanghai)`; at 80 cols the header cell wraps the
  tz name onto a continuation line but the date cells themselves never wrap).
* `COLUMNS=80` → max line length 80; `COLUMNS=120` → 120; zero overflow lines at either
  width; no date token wrapped mid-value; header + footer present. Long `Note` values are
  truncated with `…` at 80/120 cols (e.g. `This is a…`), and `--json` keeps the full value.
* `--no-color`, `NO_COLOR=1`, piped output and `--json`: **0 ANSI bytes**.
* On a real pty (`COLUMNS=100`): ANSI colour is present *by default* (header styled bold
  cyan, countdown colours), and `--no-color`/`NO_COLOR=1` remove all ANSI. With `rich`
  forcibly unimportable (`PYTHONPATH` shim raising `ImportError`), the built-in
  Unicode-width-aware renderer still draws the table and `--json` still works (rich is
  genuinely optional).
* Footer always contains: source URL, fetch time (local + UTC), shown count,
  tracked-series count, display timezone, TBD hint and the official-venue-page caveat.
  All counts are dynamic (20/61/3 now; derived from data, no literals in the script).
* `--limit` note (`15 more … hidden by --limit 5`) appears whenever rows are cut.

### §7.7 README accuracy — PASS (no open nits)

`README.md` (sha256 `9f86f813…`, docs-only updated) documents: live data source, no-cache/failure
behaviour, requirements (stdlib only, rich optional), default semantics, all 14 flags
plus `-h`, exit codes, JSON schema, TBD semantics/definition, timezone semantics
(AoE=UTC−12, PT DST-aware, unknown-tz skipped), rounds/duplicates/all-editions,
environment variables, and the accuracy caveat. Claims were cross-checked against real
runs:

| README claim | Verified behaviour |
|---|---|
| default = AI, all upcoming paper deadlines, local tz, footer | ✓ |
| `--days 30` sample shows the 4 EuroGP-family rows | ✓ actual `--days 30` = exactly those 4 |
| `--details cvpr` sample block | ✓ byte-for-byte same rows/values as actual output |
| `--include-tbd` sample (COLT/GECCO/ICCV 2027) | ✓ same section, label and links |
| footer sample | ✓ same fields/format |
| `--data-file` `fetched_at` = file mtime, stdin = now | ✓ (mtime → `2026-10-18T08:09:02Z`; stdin → now) |
| `--limit` caps JSON and footer says how many are hidden | ✓ |
| `--all-kinds` adds `Kind` column; JSON kinds `abstract_deadline` etc. | ✓ |
| exit codes 0/1/2 as documented | ✓ |
| `TZ` used when `--tz` omitted | ✓ (`TZ=UTC|America/New_York|Asia/Tokyo` all honoured) |
| Python 3.9+ syntax | ✓ `ast.parse(feature_version=(3,9))` succeeds |
| no required third-party deps (rich optional + fallback) | ✓ stdlib only; fallback verified |

**Documentation nit — RESOLVED (docs-only).** First pass: README said `COLUMNS` was
“clamped to 48–180”, while the table’s real minimum rendered width is 64 columns. The
updated README now reads: “Preferred table width, honoured when piped (the request is
clamped to 48–180; the rendered table cannot be narrower than its content, e.g. ~64
columns for the default view, ~71 with `--all-kinds`).” Re-measured behaviour:
`COLUMNS=48/56/60/64 → 64 chars` default minimum; `--all-kinds` minimum is 73 chars;
`72 → 72`, `80 → 80`, `500 → 180`. The default-view figure (64) is exact; the
`--all-kinds` “~71” is a rounded approximation of the measured 73 (explicitly “e.g. ~”,
non-blocking). At spec-relevant 80/120 widths behaviour remains correct. No open nit.

## Adversarial checks (real behaviour, not happy path)

| Probe | Actual behaviour | Judgement |
|---|---|---|
| `--days -5` | rc 2, argparse usage error on stderr, no table | correct (invalid value, documented) |
| `--limit -1` | rc 2, argparse usage error, no table | correct |
| `--days abc` / `--limit abc` / `--timeout -5` | rc 2, usage error, no table | correct |
| `--rank Z` | rc 2, error listing valid ranks | correct |
| `--rank a` (lowercase) | rc 0, normalised to CCF-A | lenient, harmless |
| `--category NOPE` | rc 2, `unknown category 'NOPE'; available: AI, CG (or 'all')` | correct |
| `--tz Not/AZone` / `--tz ""` | rc 2, error, no table | correct |
| `--details zzz-no-such-series` | rc 0; stderr `no series matched '…'`, stdout hint | matches SPEC §4.3 |
| `--details cvpr` | rc 0; full timeline raw source→local; no PASSED nodes (all future) | correct |
| `--details detailv` (synthetic) | rc 0; passed nodes marked `PASSED`, incl. comment labels | correct |
| `--details FSE` (duplicate title) | rc 0; 2 series printed with `SC/fse` and `SE/fse` keys | correct (SPEC §4.3) |
| `--details colt` (TBD venue) | rc 0; `PAPER TBD (not announced)`; no invented date | correct |
| `--details cvpr --category CG` | rc 0; stderr no match (category-constrained) | matches README |
| `--json --details cvpr` | rc 0; JSON object with `query`/`matches` (does not corrupt `--json` mode) | acceptable extension |
| `--data-file -` stdin | rc 0; parses catalog from stdin | correct |
| empty/malformed catalog (`[]`, `{}`, non-JSON) | rc 1 or 2 with clear stderr, no table | safe |
| catalog list but series lacks `sub` | rc 2 `unknown category 'AI'; available:  (or 'all')` | malformed upstream only; message slightly odd, not reachable with real catalog |
| unknown source tz | warning on stderr, event skipped, table still correct | correct |
| duplicate exact timeline entries (`AI/dupe`) | 1 row after dedupe (SPEC §3.8) | correct |
| abstract-only edition (`AI/abstbd2`) | no paper row; listed under TBD | correct |
| `--json` mixed with table flags | stdout stays pure JSON | correct |

## Test-suite coverage map

`tests/test_ccfddl.py` → 75 tests, all passing: `TestContract` (executable/shebang/help/
version/unknown-arg/no-hardcoded AST scan/stdlib-only/README),
`TestLiveJson` (schema, exact oracle set/order, TBD, rank/category/all/days/limit/
all-kinds/tz-selection/default-tz/filters/CVPR UTC-12),
`TestTimezoneMatrix` (AoE, UTC-12 sign trap, UTC/UTC+0/UTC±N, PT winter/summer,
spring/fall DST boundaries, tz-switch selection invariance),
`TestSelectionEdgeCases` (rounds, abstract+paper/TBD combos, TBD definition, dedupe,
duplicate titles, missing ranks, free-text date/place, unknown tz, historical editions,
custom `--days`, `--all-kinds`), `TestFiltersAndDataFile`, `TestFailureModes`,
`TestDetails`, `TestRendering` (live table/footer, 80/120 width, long-note ellipsis,
ANSI/NO_COLOR), `TestOracleSelfConsistency` (oracle self-checks + agreement with
`research/expected_ai_deadlines.json`).

## Residual risks / limitations

1. **Upstream data drift.** Live tests re-fetch on each run and compare against a
   fresh oracle; tonight the upstream `allconf.json` was unchanged (sha `19ad4305…`,
   `last-modified` 2026-10-17T03:43:17Z). Counts (20/61/3) are point-in-time; the tool
   derives them from data and README examples are marked as snapshots, so future catalog
   changes are expected and will alter output without indicating a regression.
2. **Network/certificate availability.** Live mode needs ccfddl.com + a CA bundle; the
   failure path was verified with a refused proxy, not with DNS/TLS skew.
3. **`PT`/`--tz` need the IANA tz database** (`America/Los_Angeles`, requested zones).
   On images without tzdata, PT/--tz failures are environmental (README documents this);
   fixed-offset source zones (AoE/UTC±N) do not need it.
4. **Timezone display edge cases** in tzdata future rules (e.g. 2033 synthetic PT
   dates) assume the current US DST rules continue; fixture-based tests may need
   re-baselining decades from now.
5. **Interactive/rich path** was exercised through a pty plus a forced-ImportError
   fallback; exotic terminals/unicode-width fonts were not tested beyond width math.
6. ~~`COLUMNS` lower clamp documentation imprecision~~ — **resolved** by the docs-only
   README update (§7.7); measured minima: 64 columns default, 73 with `--all-kinds`.
7. **Malformed upstream catalogs** beyond real-world shapes (series missing `sub`) produce
   a confusing category error rather than a schema-specific one; unreachable with the
   real CCFDDL feed and not a spec requirement.
8. Test suite live sections skip gracefully if ccfddl.com is unreachable; they were run
   successfully multiple times tonight (75/75; final re-run 22.10 s on the stable build hash).

## Artifacts

| Path | Purpose | sha256 |
|---|---|---|
| `tests/test_ccfddl.py` | 75 black-box pytest tests | `ca118fa298271f8b6368861a2e0851b5aa4ab6ce0fa3abf51cd0dfaefaaca32f` |
| `tests/oracle_live.py` | independent stdlib oracle | `2b1f95c8a2336e3ef12634f036a4b7cad3c87e6fd0d3f632c2e36a86f9beeb5b` |
| `tests/fixtures/allconf_verify.json` | fresh Turn-2 catalog snapshot | `19ad4305b5d80c5ea599d320bee33bd09b537c1000f5c8fd4d522c359ca88879` |
| `tests/fixtures/expected_verify.json` | oracle @ 2026-10-18T08:09:02Z | `0396a95f25779c990a05c8eddc1ad71a285d438cc390dcb49f9b71d252987935` |
| `tests/fixtures/synthetic_tz.json` | deterministic tz matrix | `e496a5505f078bc462ebc863c1f4cca346c29b0446d0504c90c95e5867c16d9b` |
| `tests/fixtures/synthetic_edge.json` | selection/schema/rendering edge cases | `2d2ca9af04cdd52ea10b6e83c50674a2e239e0d20df8cc669bbbf7c14399f7ea` |
| `tests/fixtures/provenance.md` | fetch provenance, DST calibration | `9dca34fdd8134a8b7136c1b62f8e35c015fc90da00d2adcfe2b69242ebffe787` |

Reproduce: `python3 -m pytest tests/test_ccfddl.py -q` (network required for live tests;
`-k "not live"` gives the offline subset, though class names are `TestLive*`).

**Final verdict: PASS against SPEC §7.1–§7.7.**

---

# ADDENDUM — Post-verification change: v2.1.0 quiet-by-default footer

Re-verified by `verifier` on 2026-10-18 (Asia/Shanghai) after the project was
restructured for publication and `-v/--verbose` was added. **This addendum supersedes
only the build/hash and footer/rendering specifics above; the original v2.0.0
verification remains valid for build sha256 `848b33e4…` (62,396 B).** Paths in the
sections above now live under `dev/` (e.g. `dev/tests/test_ccfddl.py`).

## Scope of change (all by Lead, docs/CLI only — no accuracy logic changed)

1. `./ccfddl` **v2.1.0** (62,786 B): default human output is now title + table only
   (**quiet by default**); new `-v/--verbose` appends the previous footer
   (source URL, fetch time, shown count, tracked series, TBD hint, caveat). JSON output
   is unchanged. `--limit`'s “N more hidden” line now appears only in the `-v` footer.
2. Layout for publication: `./ccfddl` + `README.md` at repo root; SPEC/legacy/research/
   tests/fixtures/VERIFICATION under `dev/`. README (root) and `dev/SPEC.md` §4/§4.1/§7
   updated to document quiet default + `-v`.
3. Tests updated (76 tests): `--verbose` added to help/README flag lists; old default
   footer test split into quiet-default + verbose-footer tests; limit-footer test now
   runs with `-v`; path fallbacks for the new layout.

## Build under test (independently re-hashed, stable)

| Artifact | Bytes | sha256 | mtime |
|---|---|---|---|
| `./ccfddl` (v2.1.0) | 62 786 | `a5680f2471900ddd307473feeaa28919ca2875b33a6922313cbc33e9d5e291a5` | 2026-10-18 16:36 |
| `README.md` (repo root) | 17 289 | `b2122b1b3281ab62568784d09477c864d201c646fa5c4da9e952fe0b4528b01c` | 2026-10-18 16:37 |
| `dev/SPEC.md` | 17 483 | `9db12176021f2b91308414d5876938523af971b2354ee3ef474d440f6da75ea7` | 2026-10-18 16:37 |
| `dev/tests/test_ccfddl.py` | 64 810 | `f70b8c4575bb7472d38df6587e4f552663caf773f7aef5846186de132ef75413` | 2026-10-18 16:38 |
| `dev/tests/oracle_live.py` | 15 455 | `2b1f95c8a2336e3ef12634f036a4b7cad3c87e6fd0d3f632c2e36a86f9beeb5b` | unchanged |

Fresh catalog re-fetch 2026-10-18T08:39:49Z: 777,074 B, sha256
`19ad4305b5d80c5ea599d320bee33bd09b537c1000f5c8fd4d522c359ca88879` — **identical to the
pinned snapshot**, so upstream data was unchanged between the v2.0.0 PASS and this
re-verification.

## Behaviour evidence (black-box, independent of Lead's claims)

Commands: `python3 -m pytest dev/tests/test_ccfddl.py -q`; direct `./ccfddl` /
`./ccfddl -v` / `./ccfddl --verbose` / `./ccfddl --json` from repo root, plus pty runs.

* **Full suite: `76 passed in 25.84s`** (no skips, no failures).
* **Quiet default:** `./ccfddl` prints exactly 24 lines (title + blank + header + rule +
  20 rows); contains **no** `source`, `fetched`, `showing`, `caveat`, `series tracked`,
  `official`, URL or TBD-hint text. Same under a real pty (TTY). A 0-row run
  (`--days 1`) prints title + `No upcoming AI paper deadlines match the current filters.`
  and no footer.
* **`-v` and `--verbose`:** both exit 0 and append the full footer: source URL, fetch time
  (local + UTC), `showing: 20 paper deadlines · 61 AI series tracked · display tz
  Asia/Shanghai`, TBD hint, caveat. Verified piped and on a pty. `-v` footer wraps within
  `COLUMNS` (max line = COLUMNS at 80 and 120; no overflow).
* **Only footer removal in default output:** v2.1.0 default output is **byte-identical**
  (24 table/header/title lines) to the v2.0.0 default table body captured during the
  original verification; only the 7 footer lines disappeared. JSON core tuples
  (`conference_key, year, deadline_utc, deadline_local, deadline_source,
  source_timezone, comment, ccf_rank`) and TBD list are **identical** v2.0.0 → v2.1.0;
  `--json` top-level keys/schema/filters unchanged (only time-dependent
  `now_utc`/`fetched_at`/`seconds_left` naturally differ).
* **Oracle equality unchanged:** fresh `--json --tz Asia/Shanghai` vs my independent
  oracle on the fresh catalog → 20/20 events, exact set + order, `tracked_series` 61,
  TBD `{AI/colt, AI/gecco, AI/iccv}`, audit-field diffs 0.
* **Selection/filters/tz unchanged:** `--rank A/B/C/N/A,B` → 2/6/5/7/8 events exact
  oracle match; `--category CG` 11 events/tracked 36; `--category all` 125/tracked 378;
  `--days 1/30/365` → 0/4/20; `--tz UTC` same selection with `+00:00` display.
* **CVPR case:** default table row shows `CVPR 2027 A 2026-11-17 Tue 19:59`; JSON
  `deadline_source "2026-11-16 23:59:59"` + `UTC-12` → `2026-11-17T11:59:59Z` →
  `2026-11-17T19:59:59+08:00`.
* **Unchanged features:** `--include-tbd` section still printed in quiet default (it is
  content, not footer) and gets the footer with `-v`; `--json -v` emits pure JSON with
  identical events and no footer; `--details` output unchanged (raw source + local +
  link still present); `--data-file -` stdin works; `--all-kinds` kinds unchanged;
  `--version` → `ccfddl 2.1.0`.
* **Failure/read-only/piped behaviour unchanged:** bad-proxy fetch → rc 1, empty stdout,
  clear stderr, no table/footer for default/`-v`/`--json`; run from a read-only cwd → rc 0,
  no files written; piped output ANSI-free.
* **No hardcoded data unchanged:** `grep -c` for venue acronyms = 0, ISO dates = 0,
  4-digit year literals = 0 in v2.1.0; AST scan test still passes.

## Test-edit review (looking for weakened assertions)

No weakening of the main accuracy checks: oracle/filter/tz/schema assertions are
untouched; the footer split is sound (default test asserts footer **absence** and still
checks headers/rows/local times; `test_verbose_shows_footer` asserts source URL, caveat,
tracked count and shown count); the path fallbacks (`ROOT/ccfddl` → `ROOT.parent/ccfddl`,
same for README) resolve correctly in the new layout and still work for the old one —
verified by the 76/76 pass. Flagged, non-blocking:

1. **Coverage regression (test-only):** `test_limit_zero_means_no_limit` still runs
   **without `-v`**, so its “no 'more' note” assertion is now trivially true (the count
   only exists in the `-v` footer). Behaviour itself is correct — `--limit 0` with `-v`
   prints no limit line — but the test no longer proves it. Recommend adding `-v` to that
   test.
2. **Docs-only publication nit:** `README.md` install section still says `cd tools` while
   the published repo will be `ccfddl-cli`; harmless, but a one-word fix would avoid
   confusing public readers.

## Verdict on re-verification

**PASS.** §7.1 PASS (quiet default + `-v` footer, live rows, no hardcoded data);
§7.2 PASS (JSON schema/instants/ordering/tracked unchanged, exact oracle match);
§7.3 PASS (UTC-12 sign, PT DST, TBD unchanged); §7.4 PASS (filters unchanged; limit count
now correctly in `-v` footer per updated SPEC/README); §7.5 PASS (no stale fallback);
§7.6 PASS (quiet default with no footer, complete `-v` footer, 80/120 widths, no ANSI);
§7.7 PASS (README/SPEC now consistently document quiet default + `-v`; examples and flag
table match actual output). Two non-blocking observations above; **no accuracy or
specification defect found**, no changes made outside `dev/tests/VERIFICATION.md`.

## Residual risks (v2.1.0)

1. Intentional output-contract change: scripts that parsed the footer from **default**
   stdout must now pass `-v` (JSON consumers unaffected). This is documented in README
   and SPEC; it is a deliberate user-requested change, not a defect.
2. Live data drift (same as original verification): 20/61/3 are point-in-time and derived
   dynamically; fresh fetch during this re-check was byte-identical to the pinned snapshot.
3. Dual-layout path fallbacks in the test file mean that if a stale `dev/ccfddl` (or
   `dev/README.md`) ever existed alongside the root copy, tests would silently prefer it;
   no such files exist in this repo state.
4. Network/tzdata availability, exotic terminal widths, future tzdata DST-rule changes:
   unchanged from the original verification (§7 residual risks above).
5. `test_limit_zero_means_no_limit` coverage gap is test-only; cannot mask an accuracy
   defect in the CLI (the limit count is separately exercised with `-v` in
   `test_limit_table_cuts_and_notes_more`).
