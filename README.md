# ccfddl — live CCF conference deadline CLI

`./ccfddl` is a small terminal tool for CCF conference paper deadlines. Every run it
downloads the public **CCFDDL** catalog and prints the upcoming paper-submission
deadlines, sorted by the real UTC instant and converted into your local timezone.

Nothing about the conferences is hardcoded: no venue names, no years, no dates. The
tool is data-driven and replaces the old hardcoded v1 (archived in
`dev/legacy/ccfddl-v1-hardcoded.py`).

```
Upcoming AI Conference Deadlines — live CCFDDL data

Conference            CCF  Deadline              Left     Abstract          Note                    
                           (Asia/Shanghai)                                                          
────────────────────────────────────────────────────────────────────────────────────────────────────
EuroGP 2027           –    2026-11-02 Mon 19:59  15d 3h   –                 Full papers             
EvoApplications 2027  –    2026-11-02 Mon 19:59  15d 3h   –                 Full papers             
EvoCOP 2027           –    2026-11-02 Mon 19:59  15d 3h   –                 Full papers             
EvoMUSART 2027        –    2026-11-02 Mon 19:59  15d 3h   –                 Full papers             
CVPR 2027             A    2026-11-17 Tue 19:59  30d 3h   2026-11-11 19:59  –                       
ESANN 2027            –    2026-11-19 Thu 15:59  31d 23h  –                 –                       
RSS 2027              –    2026-12-05 Sat 19:59  48d 3h   –                 Stage 1: initial 6-page…
CPAL 2027             –    2026-12-06 Sun 19:59  49d 3h   2026-11-24 19:59  –                       
ICAPS 2027            B    2026-12-15 Tue 19:59  58d 3h   2026-12-08 19:59  –                       
COLING 2027           B    2026-12-24 Thu 19:59  67d 3h   –                 COLING commitment after…
NAACL 2027            B    2026-12-24 Thu 19:59  67d 3h   –                 NAACL commitment after …
ACL 2027              A    2027-01-05 Tue 19:59  79d 3h   –                 ARR Submission          
IJCAI 2027            B    2027-01-12 Tue 19:59  86d 3h   2027-01-05 19:59  Separate satellite even…
IJCNN 2027            C    2027-02-01 Mon 19:59  106d 3h  –                 –                       
ICDAR 2027            C    2027-02-21 Sun 19:59  126d 3h  2027-02-01 19:59  –                       
IEEE CEC 2027         C    2027-03-01 Mon 19:59  134d 3h  –                 –                       
IROS 2027             C    2027-03-02 Tue 19:59  135d 3h  –                 Paper submission deadli…
ICPR 2027             C    2027-03-09 Tue 19:59  142d 3h  2027-03-02 19:59  All dates tentative; Ma…
ECAI 2027             B    2027-04-15 Thu 19:59  179d 3h  –                 –                       
KR 2027               B    2027-04-29 Thu 19:59  193d 3h  2027-04-24 19:59  Main track; author resp…
```

The default run lists **all** upcoming paper deadlines for the default area — there is no
10-row or 90-day cap. Output shown above is a 2026-10-18 snapshot captured at 100 columns;
values change as the upstream catalog changes.

## Data source

| | |
|---|---|
| Catalog (fetched on every run) | <https://ccfddl.com/conference/allconf.json> (JSON list of ~378 conference series) |
| Website / docs | <https://ccfddl.com/> · <https://ccfddl.com/llms.txt> |
| Upstream repo | <https://github.com/ccfddl/ccf-deadlines> |
| Alternative feeds (not used by this tool) | RSS `…/deadlines/deadlines_en.xml`, ICS `…/deadlines/deadlines_en.ics` |

The catalog is downloaded with `urllib.request` on **every invocation** and is never
cached. There is no stale fallback: if the network fetch or JSON parse fails, the tool
prints an error to stderr, exits non-zero and prints **no table**. For offline or
deterministic runs, pass a local snapshot explicitly with `--data-file` (see below).

## Requirements and install

* Python **3.9+** (stdlib only: `urllib`, `json`, `argparse`, `zoneinfo`, `datetime`).
* **Zero required third-party packages.** `rich` is optional sugar: when present *and*
  stdout is an interactive terminal, it renders the table; when output is piped, or
  `rich` is unavailable, a built-in Unicode-width-aware renderer is used instead, so
  captured output is deterministic and honours `COLUMNS`.

```sh
# from the repository root (or after copying ccfddl anywhere on your PATH)
./ccfddl              # executable, shebang #!/usr/bin/env python3
# or: python3 ./ccfddl
```

Optional, if your OS does not ship an IANA tz database (some minimal Linux images):
install `tzdata`. `PT` source-timezone handling requires the `America/Los_Angeles`
zone, and `--tz` needs whatever zone you ask for.

## Repository layout

```
ccfddl            # the only file you need to copy into your PATH
README.md         # this document
dev/              # optional development & verification material (not needed at runtime)
├── SPEC.md       # rebuild specification / accuracy contract
├── legacy/       # archived hardcoded v1, for comparison only
├── research/     # data-source dossier + independent ground-truth snapshots
└── tests/        # black-box regression suite + independent VERIFICATION.md
```

Run the regression suite with `python3 -m pytest dev/tests/test_ccfddl.py -q`.

## Usage

```
./ccfddl [options]
```

Default: research area `AI`, **all** upcoming paper-submission deadlines from every
edition and every round, sorted ascending by UTC instant, displayed in the system
timezone (this machine: `Asia/Shanghai`). Output is **quiet by default**: just the
title and the table. Add `-v` / `--verbose` to append a footer with the source URL,
fetch time, counts, display timezone and the accuracy caveat.

### Real examples (captured 2026-10-18; counts/dates move as the catalog changes)

| Command | What it shows |
|---|---|
| `./ccfddl` | all upcoming AI paper deadlines (20 rows on 2026-10-18) |
| `./ccfddl -v` | same table plus the metadata footer (source, fetch time, counts, caveat) |
| `./ccfddl --days 30` | only deadlines in the next 30 days |
| `./ccfddl --rank A` | CCF-A only |
| `./ccfddl --category CG` | another research area (any `sub` value in the catalog, case-insensitive; `all` = every area) |
| `./ccfddl --tz UTC` | same rows, instants displayed in UTC |
| `./ccfddl --details cvpr` | full timeline for matching series |
| `./ccfddl --include-tbd` | also list series whose deadline is not announced yet |
| `./ccfddl --json` | machine-readable output with audit fields |

`--days 30` (first rows):

```
Upcoming AI Conference Deadlines — live CCFDDL data (next 30 days)

Conference            CCF  Deadline              Left    Abstract     Note
                           (Asia/Shanghai)
────────────────────────────────────────────────────────────────────────────────────
EuroGP 2027           –    2026-11-02 Mon 19:59  15d 3h  –            Full papers
EvoApplications 2027  –    2026-11-02 Mon 19:59  15d 3h  –            Full papers
EvoCOP 2027           –    2026-11-02 Mon 19:59  15d 3h  –            Full papers
EvoMUSART 2027        –    2026-11-02 Mon 19:59  15d 3h  –            Full papers
```

`--details cvpr`:

```
CCFDDL details for 'cvpr' — 1 matching series
CVPR
  conference_key : AI/cvpr
  description    : IEEE/CVF Conference on Computer Vision and Pattern Recognition
  area           : AI
  ranks          : CCF A · CORE A* · THCPL A
  edition        : 2027 (cvpr27) · source tz UTC-12
  event date     : June 20-25, 2027
  place          : Seattle, WA, United States
  official link  : https://cvpr.thecvf.com/Conferences/2027

  latest-edition timeline (source → Asia/Shanghai); PASSED = already past
    PAPER     2026-11-16 23:59:59 UTC-12  →  2026-11-17 19:59:59 UTC+08:00
    ABSTRACT  2026-11-10 23:59:59 UTC-12  →  2026-11-11 19:59:59 UTC+08:00
    REBUTTAL  2027-02-01 23:59:59 UTC-12  →  2027-02-02 19:59:59 UTC+08:00
    DECISION  2027-02-25 23:59:59 UTC-12  →  2027-02-26 19:59:59 UTC+08:00
```

`--include-tbd` appends a clearly separate section (not table rows, no countdowns):

```
TBD — deadline not yet announced (3 series)
  COLT 2027  ·  CCF B  ·  June 28 - July 2, 2027  ·  Tokyo, Japan
      deadline not announced (TBD) — https://learningtheory.org/colt2027/
  GECCO 2027  ·  CCF C  ·  July 12-16, 2027  ·  Kraków, Poland
      deadline not announced (TBD) — https://gecco-2027.sigevo.org/HomePage
  ICCV 2027  ·  CCF A  ·  October 2-8, 2027  ·  Hong Kong, China
      deadline not announced (TBD) — https://iccv.thecvf.com/Conferences/2027
```

`-v` / `--verbose` appends a footer (the default output above has none):

```

────────────────────────────────────────────────────────────────
source   : https://ccfddl.com/conference/allconf.json
fetched  : 2026-10-18 16:07:46 UTC+08:00  (2026-10-18T08:07:46Z)  — live fetch
showing  : 20 paper deadlines · 61 AI series tracked · display tz Asia/Shanghai (UTC+08:00)
tbd      : 3 series have no announced deadline; use --include-tbd to list them (TBD is unknown, not
           a date)
caveat   : live catalog data can change; always verify the deadline on the official venue page
           before acting.
```

### Flags

| Option | Meaning |
|---|---|
| `-d, --days N` | Only show deadlines within the next `N` days (`0`, the default, = all upcoming). |
| `-r, --rank LIST` | CCF rank filter, comma-separated subset of `A,B,C,N` (default: all). Matches the catalog's `rank.ccf` value; unranked series display `–`. |
| `-c, --category CODE` | Research area from the catalog's `sub` field, case-insensitive (default `AI`; `all` = every area). Invalid values are rejected with the list of areas actually present in the data. |
| `--tz TZ` | Display timezone: an IANA name (`Asia/Shanghai`, `America/Los_Angeles`, `UTC`, …). Default: the system timezone. Unknown names are a usage error and no table is printed. |
| `-i, --details QUERY` | Case-insensitive substring match on series title, `conference_key` or description. Prints a per-series detail view (all areas by default; constrained if `--category` is also given). No match → message on stderr, exit 0. |
| `-j, --json` | Machine-readable JSON on stdout (see schema below). Never contains ANSI escapes. |
| `--limit N` | Maximum number of table rows (default `0` = no limit). When rows are hidden the count is reported in the `-v` footer, and `--json` events are capped the same way. |
| `--include-tbd` | Append the "TBD / not yet announced" section. Does not turn TBD into dates. |
| `--all-kinds` | Also show abstract / rebuttal / decision timeline entries (adds a `Kind` column; JSON `kind` becomes `abstract_deadline`, `rebuttal_deadline`, `decision_deadline`). Default: paper `deadline` only. |
| `--data-file PATH` | Read catalog JSON from a local file instead of the network (`-` = stdin). `fetched_at` is then the file's mtime (or "now" for stdin). Useful for offline runs and tests. |
| `--timeout SECS` | Network timeout in seconds (default `20`). |
| `--no-color` | Disable ANSI colour. Colour is also disabled automatically when stdout is not a TTY or `NO_COLOR` is set. |
| `-v, --verbose` | Append the footer: data source, fetch time, counts, display timezone and the accuracy caveat. Quiet by default. |
| `--version` | Print version and exit 0. |
| `-h, --help` | Full help, including examples. |

Exit codes: `0` success (including "no matching deadlines" and "no details match"),
`1` network / JSON / data-file read errors, `2` usage errors (bad flag, invalid rank,
category, timezone, negative `--days`, …). Errors and warnings go to stderr only.

## Accuracy and semantics

* **Timezone-correct instants.** Each catalog edition has a `timezone`; the naive
  `YYYY-MM-DD HH:MM:SS` values are interpreted in that zone and converted to UTC for
  ordering/filtering, then to the display zone for rendering.
  * `AoE` = Anywhere on Earth = **UTC−12**, a fixed offset. AoE `2026-11-16 23:59:59`
    is `2026-11-17T11:59:59Z` = `2026-11-17 19:59:59` in `Asia/Shanghai`.
  * `PT` = `America/Los_Angeles`, DST-aware (winter −08:00, summer −07:00) — it is
    never approximated with a fixed −8.
  * `UTC±N` = fixed offsets, `UTC`/`UTC+0` = +00:00.
  * Any unrecognized timezone is reported on stderr and its deadlines are skipped —
    it is never silently treated as local time.
* **TBD is unknown, not a date.** Deadline values equal to the literal `"TBD"` (or
  missing) are never parsed, sorted, compared or estimated. They are shown only in
  the `--include-tbd` section (and the JSON `tbd` array) and never get a countdown.
* **Paper vs. abstract.** The main table is paper submission (`deadline`) only.
  Abstract/rebuttal/decision nodes appear in `--details`, in JSON when
  `--all-kinds` is used, and in the table only with `--all-kinds`. The `Abstract`
  column shows the abstract deadline of the *same* timeline entry.
* **Rounds are preserved.** `timeline` is a list; every round is a separate row,
  labelled by its `comment` (`Round 1`, `ARR Submission`, `Main track`, …). Distinct
  rounds/editions are never merged. Exact duplicate events (same series, edition,
  kind, UTC instant and comment) are de-duplicated.
* **All editions are considered**, including historical ones; only deadlines strictly
  after "now" are shown. There is no 10-row or 90-day default cap.
* **Filters are data-driven.** Categories are whatever `sub` values exist in the
  catalog; ranks come from `rank.ccf`. Missing ranks and `N` ("not ranked in CCF")
  are displayed as `–`, never invented.
* **Live, not cached.** The table you see comes from a fetch made by that run. With
  `-v` / `--verbose`, the footer records the fetch time (local and UTC) and the
  catalog URL.

The `--include-tbd` section lists a series only when (a) it has no upcoming dated
paper deadline in any edition, (b) every `deadline` in its **latest** edition is
`TBD`/absent, and (c) the latest edition year is not in the past. A series whose
latest deadline merely passed (e.g. AAAI 2027 on 2026-10-18) is **not** listed as TBD.

## JSON output (`--json`)

Top-level keys: `source`, `fetched_at`, `display_timezone`, `category`, `now_utc`,
`filters` (`days`, `ranks`, `limit`, `all_kinds`), `tracked_series`, `events`, `tbd`.
Times are ISO-8601 with explicit offsets; `events` is ordered exactly like the table.

```json
{
  "source": "https://ccfddl.com/conference/allconf.json",
  "fetched_at": "2026-10-18T08:04:49+00:00",
  "display_timezone": "Asia/Shanghai",
  "category": "AI",
  "now_utc": "2026-10-18T08:04:48+00:00",
  "filters": {"days": 0, "ranks": null, "limit": 0, "all_kinds": false},
  "tracked_series": 61,
  "events": [
    {
      "conference_key": "AI/cvpr",
      "conference": "CVPR",
      "year": 2027,
      "ccf_rank": "A",
      "kind": "deadline",
      "deadline_utc": "2026-11-17T11:59:59+00:00",
      "deadline_local": "2026-11-17T19:59:59+08:00",
      "deadline_source": "2026-11-16 23:59:59",
      "source_timezone": "UTC-12",
      "abstract_utc": "2026-11-11T11:59:59+00:00",
      "abstract_local": "2026-11-11T19:59:59+08:00",
      "abstract_source": "2026-11-10 23:59:59",
      "days_left": 30,
      "seconds_left": 2606112,
      "comment": "",
      "event_date": "June 20-25, 2027",
      "place": "Seattle, WA, United States",
      "link": "https://cvpr.thecvf.com/Conferences/2027"
    }
  ],
  "tbd": [
    {"conference_key": "AI/iccv", "conference": "ICCV", "year": 2027, "ccf_rank": "A",
     "event_date": "October 2-8, 2027", "place": "Hong Kong, China",
     "link": "https://iccv.thecvf.com/Conferences/2027"}
  ]
}
```

`deadline_source` + `source_timezone` let every rendered instant be audited back to
the catalog. `deadline_utc`/`deadline_local` are the same instant in UTC and the
display zone; `days_left = floor(seconds_left / 86400)`. The `tbd` array is always
computed; `--include-tbd` only controls whether the human-readable section is printed.

## Environment

| Variable | Effect |
|---|---|
| `COLUMNS` | Preferred table width, honoured when piped (the request is clamped to 48–180; the rendered table cannot be narrower than its content, e.g. ~64 columns for the default view, ~71 with `--all-kinds`). Useful for screenshots/tests. |
| `NO_COLOR` | Any value disables ANSI colour (in addition to `--no-color` and non-TTY stdout). |
| `TZ` | System timezone used when `--tz` is omitted (IANA name). |

## Accuracy caveat

CCFDDL is a community-maintained catalog. Deadlines, timezones, places and even
edition years can contain errors or change without notice, and "TBD" means the venue
has not announced a date — this tool will never guess one. **Always verify a deadline
on the official venue page before submitting.** This tool is a convenience, not an
authority.
