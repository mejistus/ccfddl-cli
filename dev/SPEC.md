# CCFDDL CLI — Rebuild Specification (v2)

Status: authoritative brief for teammates. Lead owns this file; do not edit without telling the Lead.
Date: 2026-10-18 (Asia/Shanghai). Owner of implementation: `builder`. Independent validation: `verifier`.

## 1. Goal

Rebuild the existing hardcoded CLI (`legacy/ccfddl-v1-hardcoded.py`, formerly `./ccfddl`) into a tool that
**retrieves AI conference deadlines live from the CCFDDL website every run**, with **no hardcoded
conferences or dates**, and prints a clean table to the terminal.

Priority: **accuracy first, aesthetics second.** Beauty must never distort data (no fake rows, no
estimated dates filling TBDs, no silent stale cache).

Target path/name stays: `./ccfddl` (executable, shebang `#!/usr/bin/env python3`), plus `README.md`.

## 2. Authoritative data source (live, public, machine-readable)

- Catalog JSON (use this): `https://ccfddl.com/conference/allconf.json`
  - `content-type: application/json; charset=utf-8`; ~777 KB; updated several times a week.
  - Site docs for agents: `https://ccfddl.com/llms.txt` (states this is the "Conference catalog").
- Site: `https://ccfddl.com/` (old host `https://ccfddl.github.io/` 301-redirects to it).
- Secondary feeds for cross-checks only: `https://ccfddl.com/conference/deadlines/deadlines_en.xml`
  (RSS), `.../deadlines_en.ics`, `https://ccfddl.com/conference/allacc.json` (acceptance stats,
  NOT needed for this tool), source repo `https://github.com/ccfddl/ccf-deadlines`.

### 2.1 Catalog schema (verified on 2026-10-18)

`allconf.json` is a JSON **list** of 378 conference series. Each series:

```json
{
  "title": "CVPR",
  "description": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
  "sub": "AI",                                   // research area code
  "rank": {"ccf": "A", "core": "A*", "thcpl": "A"},
  "dblp": "cvpr",
  "conference_key": "AI/cvpr",
  "confs": [                                     // list of editions (1..many, includes historical)
    {
      "year": 2027,
      "id": "cvpr27",
      "link": "https://cvpr.thecvf.com/...",
      "timeline": [
        {
          "abstract_deadline": "2026-11-10 23:59:59",
          "deadline": "2026-11-16 23:59:59",
          "rebuttal_deadline": "2027-02-01 23:59:59",
          "decision_deadline": "2027-02-25 23:59:59",
          "comment": "optional label, e.g. Round 1 / ARR Submission / Main track"
        }
      ],
      "timezone": "UTC-12",
      "date": "June 20-25, 2027",               // free text event date, can be "TBD"
      "place": "Seattle, WA, United States",     // free text, can be "TBD"
      "opening": "2027-06-20 08:00:00",
      "opening_is_derived": true
    }
  ]
}
```

Verified facts (as of 2026-10-18, 378 series / 2315 editions):

- Area codes present: `AI` (61 series, the default), `CG` (36), `DS` (61), `SC` (50), `SE` (48),
  `DB` (27), `MX` (23), `HI` (22), `CT` (20), `NW` (30). Do **not** hardcode this list: categories
  are discovered/filtered from the JSON `sub` field. `sub` value matching is case-insensitive.
- `timeline` is a list: several deadline rounds per edition are separate entries (e.g. NeurIPS
  abstract/paper; COLING "ARR Submission" + "commitment"). 1–12 entries observed.
- Each timeline entry has `deadline` (paper submission) plus optional `abstract_deadline`,
  `rebuttal_deadline`, `decision_deadline`, `comment`. Deadline values are either
  `"YYYY-MM-DD HH:MM:SS"` (naive, to be interpreted in the edition `timezone`) or the literal
  string `"TBD"` (unknown — NOT a date; must never be compared/sorted as a string).
- Edition `timezone` values observed: `AoE`, `UTC-12`, `UTC-11`, `UTC-10`, `UTC-8`, `UTC-7`,
  `UTC-6`, `UTC-5`, `UTC-4`, `UTC-3?` (not seen), `UTC+0`, `UTC`, `UTC+1`, `UTC+2`, `UTC+3`,
  `UTC+7`, `UTC+8`, `UTC+10`, `PT`.
  Semantics: `AoE` == UTC-12 (Anywhere on Earth); `UTC±N` == fixed offset; `UTC` == +00:00;
  `PT` == America/Los_Angeles (DST-aware, do not replace with a fixed -8).
  Unknown timezone must be reported/skipped, never silently treated as local time.
- `rank` may be missing `core`/`thcpl` (17 series only have `ccf`). `ccf` ∈ {A,B,C,N}; `N` means
  "not ranked in CCF", display it as-is or as `–`, but never invent a rank.
- Historical editions are included (back to 2021 and earlier); selection must consider **all**
  editions and keep only future deadlines.
- Duplicate `title` exists across areas (`SEC`, `FSE`); identity is `conference_key` (e.g. `AI/cvpr`),
  not title. Edition `id` is unique.

Known AI "latest edition announced but paper deadline TBD" cases on 2026-10-18: COLT 2027,
GECCO 2027, ICCV 2027. These must be shown as TBD only under `--include-tbd` (see §4.5).

## 3. Accuracy rules (MUST)

1. **No hardcoded data.** The script must contain no conference names, acronyms, years or deadline
   dates used as data. Allowed literals: the data URL, timezone alias mapping, format strings,
   argparse help text, version. (Docstring examples may mention filters like `cvpr` only as CLI
   examples; do not use them in logic.)
2. **Freshness.** Default runs fetch live data on every invocation. No silent stale cache. If the
   fetch fails: print a clear error to stderr, exit non-zero, do not print a table. No fallback to
   a previously cached snapshot unless the user explicitly passes `--data-file`.
3. **Timezone correctness.** Parse naive datetimes with the edition timezone, then convert to UTC
   for ordering/filtering. `AoE` = UTC-12. `PT` = `America/Los_Angeles` via `zoneinfo`. `UTC±N` =
   fixed offsets. Display in the user's display timezone (default: system zone, currently
   Asia/Shanghai) via `zoneinfo`, so DST transitions are respected for `PT`.
4. **TBD is unknown.** Never parse/sort/compare `"TBD"` as a date. Never invent/estimate dates.
5. **Deadline selection.** Default table = upcoming **paper submission** events (`deadline` field)
   from any edition of the series, `deadline_utc > now`, sorted ascending by UTC instant. Abstract /
   rebuttal / decision nodes are not paper deadlines; they appear only in `--details` or JSON when
   explicitly requested (`--all-kinds` optional). Multiple rounds = multiple rows, labeled by
   `comment`; never merge distinct rounds.
6. **No arbitrary truncation by default.** Do not silently cap at 10 rows or 90 days like v1.
   Default shows all upcoming paper deadlines (currently 20 for AI). `--days`/`--limit` are opt-in.
7. **Filters are server-data driven.** `--category` matches `sub` (default `AI`; `all` disables).
   `--rank` matches `rank.ccf` (comma-separated). Unknown filter values → informative error.
8. **Deduplicate** exact duplicate events (same `conference_key`, edition id, UTC instant, comment)
   without removing genuinely distinct rounds/editions.
9. **Timezone-label displayed times.** The deadline column header must name the display timezone;
   each rendered deadline must be unambiguous (full date incl. year + 24h time). Source timezone
   and raw source string must be available in `--json` and `--details` output so any value can be
   audited back to the source.
10. **CLI output must be reproducible/inspectable.** `--json` is the machine-checkable form and is
     used by tests/verification. `--data-file` allows offline deterministic runs.

## 4. CLI contract (v2)

```
usage: ccfddl [options]
```

Behavior with **no arguments**: category `AI`, display tz = system local, all upcoming paper
deadlines, pretty table only (**quiet by default**: no footer). Exit 0. Pass `-v`/`--verbose` to
append the source/fetch-time/counts/caveat footer.

Options (minimum):

| Option | Meaning |
|---|---|
| `-d, --days N` | Only deadlines within the next N days (default 0 = all upcoming; N>0). |
| `-r, --rank LIST` | CCF rank filter, comma-separated subset of `A,B,C,N` (default all). |
| `-c, --category CODE` | Research area filter from JSON `sub` (default `AI`; `all` = every area). |
| `--tz TZ` | Display timezone (IANA name, e.g. `Asia/Shanghai`, `America/Los_Angeles`, `UTC`). Default system local. Unknown tz → error exit 2/1, no table. |
| `-i, --details QUERY` | Case-insensitive substring match on series title / `conference_key` / description; show a per-series detail view (see §4.4). |
| `-j, --json` | Machine-readable JSON to stdout (no table, no ANSI). |
| `--limit N` | Max table rows (default 0 = no limit; still show "N more" note if cut). |
| `--include-tbd` | Append a clearly separate "TBD / not yet announced" section (see §4.5). |
| `--all-kinds` | Include abstract/rebuttal/decision events as table rows (default only paper). |
| `--data-file PATH` | Read catalog JSON from a local file (`-` = stdin) instead of network. |
| `--timeout SECS` | Network timeout (default 20s). |
| `--no-color` | Disable ANSI colors (also honor `NO_COLOR` env; auto-disable if stdout is not a TTY). |
| `-v, --verbose` | Append the footer (data source, fetch time, counts, display tz, caveat). Hidden by default. |
| `--version` | Print version, exit 0. |

Unknown args → argparse error (exit 2). Network/parse errors → stderr message, exit 1.

### 4.1 Default table

Columns (in this order, keep fit for ~80–120 cols terminals):

1. `Conference` — `CVPR 2027` (title + edition year).
2. `CCF` — data `rank.ccf` (`–` when absent/N).
3. `Deadline (<display tz name>)` — e.g. `2026-11-17 Tue 19:59` (full date incl. year, 24h).
4. `Left` — countdown, e.g. `28d 4h`, `3h 12m`, `<1h`; red ≤3 days, yellow ≤14 days, green otherwise
   (colors only when enabled).
5. `Abstract` — local abstract deadline for the same timeline entry, or `–`.
6. `Note` — `comment` label (round etc.), truncated with `…`; empty → `–`.

Footer (`-v`/`--verbose` only; quiet by default): data source URL, fetch time (UTC and/or local),
count of shown events, count of tracked series in the filtered category, display timezone, and a
one-line "verify against official venue page" caveat. No hardcoded count values.

Sorting: UTC instant ascending; tie-break title, then year.

### 4.2 JSON schema (`--json`)

Top-level object:

```json
{
  "source": "https://ccfddl.com/conference/allconf.json",
  "fetched_at": "2026-10-18T08:00:00+00:00",
  "display_timezone": "Asia/Shanghai",
  "category": "AI",
  "now_utc": "2026-10-18T08:00:00+00:00",
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
      "days_left": 28,
      "seconds_left": 2451600,
      "comment": "",
      "event_date": "June 20-25, 2027",
      "place": "Seattle, WA, United States",
      "link": "https://cvpr.thecvf.com/..."
    }
  ],
  "tbd": [
    {"conference_key": "AI/iccv", "conference": "ICCV", "year": 2027, "ccf_rank": "A",
     "event_date": "October 2-8, 2027", "place": "Hong Kong, China", "link": "https://iccv.thecvf.com/"}
  ]
}
```

`events` ordered like the table. `deadline_*` fields are ISO-8601 with explicit offset. `days_left`
= floor(seconds_left / 86400). Times must be exact instants from source tz; e.g. for an `AoE`
23:59:59 deadline, UTC = next day 11:59:59, Asia/Shanghai = next day 19:59:59.

### 4.3 `--details QUERY`

Match by case-insensitive substring against `title`, `conference_key`, `description`. For each
match, print: title, full description, area, CCF/CORE/THCPL ranks, official link, event date,
place, edition year, source timezone, and the **full timeline of the latest edition** (all kinds:
paper/abstract/rebuttal/decision) with both the raw source datetime+tz and the local display
datetime; mark passed nodes `PASSED`. If multiple series match (e.g. `SEC`), print each with its
`conference_key` so they are distinguishable. No matches → message + exit 0 (or non-zero? use 0
with message; document it).

### 4.4 TBD section (`--include-tbd`)

After the main table, list series in the filtered category that satisfy ALL of:
(a) no upcoming dated paper deadline across all editions, (b) in their latest edition every
timeline entry's `deadline` is `"TBD"`/absent (i.e. not announced), and (c) latest edition year ≥
current display year. Show event date/place/rank/link and an explicit "deadline not announced
(TBD)" label; sort by title. These are not table rows and not countdowns. (Note: a series whose
latest edition deadline already PASSED is not TBD — do not list it.) On 2026-10-18 the expected
set is {COLT 2027, GECCO 2027, ICCV 2027}; do not hardcode that list.

### 4.5 Rendering / aesthetics

- Preferred renderer: `rich` (installed) for a clean table; if `rich` import fails, fall back to a
  self-contained Unicode-width-aware table (use `unicodedata.east_asian_width`, no dependency).
- Zero *required* third-party deps: use stdlib `urllib.request` for fetching (send a descriptive
  User-Agent), `json`, `argparse`, `zoneinfo`, `datetime`. `rich` is optional sugar.
- Respect terminal width; no wrapping mid-date; long `Note` values truncated with `…`; no color
  when piped/`--no-color`/`NO_COLOR`.
- Title line naming the report, e.g. `Upcoming AI Conference Deadlines — live CCFDDL data`.
- Never print ANSI codes in `--json`.

## 5. Non-goals

- No persistent cache/database, no config files, no interactive TUI, no calendar/ICS export,
  no acceptance-rate stats, no hardcoded category full names, no non-AI defaults hidden.
- Do not modify `legacy/` (archived v1), `SPEC.md`, or `research/` as part of implementation.

## 6. Project layout & write scopes (advisory, disjoint)

```
tools/
├── ccfddl                     # executable CLI
├── README.md                  # usage, data source, accuracy notes
└── dev/                       # development & verification material (not needed at runtime)
    ├── SPEC.md
    ├── legacy/ccfddl-v1-hardcoded.py   # archived v1 (read-only reference)
    ├── research/
    │   ├── source_notes.md
    │   └── expected_ai_deadlines.json
    └── tests/
        ├── test_ccfddl.py
        ├── fixtures/...
        └── VERIFICATION.md
```

## 7. Acceptance criteria (verifier checks all)

1. `./ccfddl` runs clean (exit 0) with no args; table shows the live upcoming AI paper deadlines
   (currently ~20 rows, verify against live data dynamically — do not hardcode the count) with
   correct local times; output is quiet by default (no footer) and `-v`/`--verbose` adds it; no
   hardcoded venue/date data in the script (grep proves it; only URL/tz/format constants allowed).
2. `./ccfddl --json` valid JSON; every event's `deadline_utc` matches independent ground truth
   computed from the same live catalog within 1 second; ordering ascending; `tracked_series` equals
   the live number of `sub == "AI"` series (61 on 2026-10-18 — verify dynamically, do not hardcode).
3. Timezone semantics verified, at minimum: `AoE`/`UTC-12` deadline 2026-11-16 23:59:59 →
   UTC 2026-11-17T11:59:59Z → Asia/Shanghai 2026-11-17T19:59:59+08:00; CVPR 2027 is the concrete
   case (site shows "23:59, Nov 16, 2026 · UTC-12"). `PT` handling verified with synthetic fixture
   covering a DST boundary; `TBD` never parsed. WARNING: a naive `UTC-12` → `+12` sign error shifts
   such deadlines one day earlier — this exact bug was caught during spec review; verify the sign
   explicitly with both UTC and local assertions.
4. Filters: `--rank A` keeps only A; `--category CG` yields CG venues; `--days 30` filters correctly;
   `--tz UTC` changes displayed instants, not selection; `--limit` and `--include-tbd` behave as
   specified; bad `--tz` and missing `--data-file` exit non-zero with clear stderr.
5. No stale-cache fallback: fetch failure produces error, not a table.
6. Table aesthetics: aligned, readable at 80 and 120 columns; colors optional; no ANSI in `--json`;
   `--no-color` output clean; quiet default output has no footer, `-v` footer complete.
7. `README.md` documents data source, semantics, flags, examples, and the accuracy caveat (TBD is
   unknown; check official venue page before acting).

## 8. Recon appendix (verified 2026-10-18; do not treat as expected output to hardcode)

- Upcoming AI *paper* deadlines (local Asia/Shanghai, timezone-corrected after fixing an earlier
  UTC-12 sign error in this appendix) at recon time began with:
  EuroGP/EvoApplications/EvoCOP/EvoMUSART 2027 (2026-11-02 19:59:59), CVPR 2027
  (2026-11-17 19:59:59), ESANN 2027 (2026-11-19 15:59:59), RSS 2027 (2026-12-05 19:59:59),
  CPAL 2027 (2026-12-06 19:59:59), ICAPS 2027 (2026-12-15 19:59:59), COLING/NAACL 2027
  (2026-12-24 19:59:59), ACL 2027 (2027-01-05 19:59:59), IJCAI 2027 (2027-01-12 19:59:59), ...
  These values are derived from live data and may change upstream; they are for sanity checks only,
  never to hardcode. The authoritative check is UTC: e.g. CVPR 2027 source `2026-11-16 23:59:59`
  UTC-12 == `2026-11-17T11:59:59Z`.
- v1 (`dev/legacy/ccfddl-v1-hardcoded.py`) hardcodes 8 venues/dates and fake notification/location
  fields; it must be fully replaced. Keep the same CLI filename for compatibility.
