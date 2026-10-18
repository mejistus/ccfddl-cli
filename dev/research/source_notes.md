# CCFDDL live source research + independent AI ground truth

Author: `source-scout` (data-source research, independent of `builder`).
Date: 2026-10-18 (Asia/Shanghai). Spec: `SPEC.md` (Lead-owned; re-read after the
15:58 UTC-12 correction).
Status: **complete**. All facts below were verified against live `ccfddl.com` on
2026-10-18; nothing is copied from SPEC's appendix values.

Independent deliverables:

| File | Purpose |
|---|---|
| `research/source_notes.md` | this document — verified source facts, traps, cross-checks |
| `research/expected_ai_deadlines.json` | machine-readable ground truth snapshot (as_of `2026-10-18T08:00:41Z`) |
| `research/check_ground_truth.py` | stdlib-only generator/validator (live fetch, `--data-file`, `--as-of`, `--audit`, `--selftest`, `--summary`) |
| `research/raw/MANIFEST.txt` | SHA-256 + byte size of every raw snapshot (catalog, feeds, HTML pages) |

TL;DR numbers at recon time: catalog **378 series / 2315 editions / 2892 timeline
entries**, 777,074 bytes, SHA-256 `19ad4305b5d80c5ea599d320bee33bd09b537c1000f5c8fd4d522c359ca88879`;
**61 AI series**, **20 upcoming AI paper deadlines**, **3 TBD series** (COLT 2027,
GECCO 2027, ICCV 2027). RSS and ICS secondary feeds independently confirm the exact
same 20 UTC instants.

---

## 1. Fetch log and endpoint verification

Fetch window: 2026-10-18 07:55–07:59 UTC (15:55–15:59 Asia/Shanghai).
User-Agent used: `ccfddl-research/1.0 (source-scout; independent ground-truth audit)`.

### 1.1 Canonical catalog (primary source)

Commands actually run:

```bash
curl -sS -D raw/allconf.headers -o raw/allconf.json \
     -A 'ccfddl-research/1.0 (source-scout)' \
     https://ccfddl.com/conference/allconf.json
shasum -a 256 research/raw/allconf.json
```

Observed response (header verbatim subset):

```
HTTP/2 200
date: Sun, 18 Oct 2026 07:55:18 GMT
content-type: application/json; charset=utf-8
server: cloudflare
x-origin-cache: HIT
last-modified: Sat, 17 Oct 2026 03:43:17 GMT
access-control-allow-origin: *
etag: W/"6ad2eed5-bdb72"
cache-control: max-age=600
cf-cache-status: DYNAMIC
```

* HTTP status **200**, `content-type: application/json; charset=utf-8`.
* **777,074 bytes** (`Content-Length` is not sent; size measured by download).
  (`~777 KB` in SPEC §2 matches.)
* `Last-Modified: 2026-10-17 03:43:17 GMT` → catalog was last published the day
  before recon; `Cache-Control: max-age=600` means a client may see a 10-minute cache.
* SHA-256 of the fetched body: **`19ad4305b5d80c5ea599d320bee33bd09b537c1000f5c8fd4d522c359ca88879`**.
* Fetched repeatedly in this window: raw snapshot at `2026-10-18T07:55:19Z` (curl)
  and the ground-truth script's own live fetches at `07:58:33Z` and `08:00:41Z` —
  **identical SHA-256 and byte count** every time, so data was stable during recon.
* Catalog bytes are also archived at `research/raw/allconf.json` for offline replay.
* **ETag** `W/"6ad2eed5-bdb72"`; **`X-Origin-Cache: HIT`**, `cf-cache-status: DYNAMIC`
  (Cloudflare in front of GitHub Pages origin; `x-github-request-id`/`x-github-edge-region`
  headers were also present). No auth, no cookies, CORS `*` — safe for plain
  `urllib.request`.

### 1.2 Documentation for agents

`https://ccfddl.com/llms.txt` → HTTP 200, `text/plain; charset=utf-8`, **6,057 bytes**,
SHA-256 `b92913c8cf428f378f113eb8d42cf69340fc0887dcf578cc9d69feb23067f87c`
(saved as `research/raw/llms.txt`). It explicitly lists the machine-readable endpoints
quoted in §1.3 and states interpretation rules. Key quotes used below:

> - `TBD`, missing dates and missing statistics are unknown, not estimates.
> - The latest listed venue is the greatest edition year in the catalog; it may
>   have no announced deadline or may already have passed.
> - Pacific (`PT`) clock times skipped or repeated during daylight-saving changes
>   do not identify a unique instant. MCP retains the original time but leaves UTC
>   conversions empty and omits these nodes from upcoming results.
> - Different submission rounds and abstract/paper deadlines are separate events.
> - `opening` timestamps are derived ... They are not verified local event start times.

### 1.3 Secondary endpoints (cross-check only — not needed by the CLI)

| URL | Status | Content-Type | Bytes | SHA-256 |
|---|---|---|---|---|
| `https://ccfddl.github.io/` (old host) | **301** → `Location: http://ccfddl.com/` | text/html | 0 | — |
| `https://ccfddl.com/` | 200 | text/html; charset=utf-8 | 4,868 | `b39a04ab…94ad9b` |
| `https://ccfddl.com/venues/ai/` | 200 | text/html; charset=utf-8 | 37,650 | `74c71c36…435e76a` |
| `…/conference/deadlines/deadlines_en.xml` (RSS) | 200 | `application/xml` | 2,481,757 | `c977b4b1…9cf8016e` |
| `…/conference/deadlines/deadlines_en.ics` (ICS) | 200 | `text/calendar` | 3,007,425 | `4f38621e…3bf468` |
| `https://ccfddl.com/conference/allacc.json` | 200 | application/json; charset=utf-8 | 224,786 | `140f4a8b…302f1c` |

Note the redirect target is **`http://`** (not https) and it is a 301 to the apex host.
`allacc.json` is a 321-element JSON list of `{title, conference_key, accept_rates}`
— **not** needed by this tool (SPEC §5 non-goal).

---

## 2. Catalog schema (verified)

`allconf.json` root is a **JSON list** (not an object) of 378 series.

**Series object — every series has exactly these keys** (378/378 each):

| Key | Type | Notes |
|---|---|---|
| `title` | str | acronym as displayed, e.g. `"CVPR"`, `"IEEE CEC"`, `"CoNLL"`, `"RuleML+RR"` |
| `description` | str | full conference name |
| `sub` | str | research-area code, uppercase (`AI`, `CG`, …) |
| `rank` | object | `{ccf, core, thcpl}` — see missing-rank trap below |
| `dblp` | str | DBLP key |
| `conference_key` | str | **identity**, `"<area>/<slug>"` e.g. `AI/cvpr`; unique across all 378 |
| `confs` | list | editions, 1..many, **includes historical** |

**Edition object — every edition has exactly these keys** (2315/2315 each):

| Key | Type | Notes |
|---|---|---|
| `year` | int | edition year, 2019–2028 observed |
| `id` | str | unique edition id, e.g. `cvpr27` (no duplicate ids in catalog) |
| `link` | str | official conference URL |
| `timeline` | list | 1..12 entries; never empty in this snapshot |
| `timezone` | str | source timezone for the naive datetimes in `timeline` |
| `date` | str | free-text event date, e.g. `"June 20-25, 2027"` or `"TBD"` |
| `place` | str | free-text location, e.g. `"Seattle, WA, United States"` or `"TBD"` |
| `opening` | str | derived countdown anchor (not a verified start time) |
| `opening_is_derived` | bool | `true` on all derived openings |

**Timeline entry object** (2892 entries; keys are optional except `deadline`):

| Key | Type | Present | Notes |
|---|---|---|---|
| `deadline` | str | **2892/2892** | paper submission: `"YYYY-MM-DD HH:MM:SS"` or `"TBD"` |
| `abstract_deadline` | str | 1241 | same formats; can be `"TBD"` while paper is dated |
| `rebuttal_deadline` | str | 83 | datetime only |
| `decision_deadline` | str | 137 | datetime only |
| `comment` | str | 1099 | round/track label, free text, can contain `;`, `:`, dates |

`deadline` is **always present**; `comment` is often absent (1793/2892 entries have no
comment). No timeline entry is `null`, no `confs` list is empty.

---

## 3. Data statistics (as fetched 2026-10-18)

Reproduce with:

```bash
python3 research/check_ground_truth.py --data-file research/raw/allconf.json \
        --as-of 2026-10-18T07:55:19Z --audit
```

* **Series per area** (`sub`, case-insensitive, 10 areas, do not hardcode):
  AI 61, DS 61, SC 50, SE 48, CG 36, NW 30, DB 27, MX 23, HI 22, CT 20.
* **Editions**: 2315 total. Per year: 2019:1, 2020:4, 2021:343, 2022:345, 2023:347,
  2024:357, 2025:355, 2026:364, 2027:197, 2028:2. Earliest edition is **2019**
  (`MX/aft`), latest **2028** (`CG/icassp`, `MX/miccai`). (SPEC says "back to 2021 and
  earlier" — 2019 is the true minimum.)
* **AI subset**: 61 series / **358 editions** / **436 timeline entries**; latest edition
  year 2026 for 28 series, 2027 for 33 series (none 2028).
* **AI rank distribution**: A 7, B 14, C 21, N 19. Global `ccf`: A 58, B 131, C 146, N 43.
* **Rank key shapes**: 361 series have `{ccf, core, thcpl}`; **17 have only `{ccf}`**
  (AI has exactly one: `AI/cvc` → `{"ccf": "N"}`; the other 16 are in CT/DB/DS/HI/MX/SE).
  Do not assume `core`/`thcpl` exist; do not invent ranks.
* **Round distribution** (timeline entries per edition): 1→1928, 2→296, 3→52, 4→31,
  8→1, 12→7 editions. In AI: 1→295, 2→54, 3→7, 4→1, 8→1 (63 AI editions have >1 round).
* **Exact duplicate timeline events** (`conference_key`, edition id, UTC instant,
  comment): **0** in the whole catalog → dedup is a no-op today but must still be
  implemented (SPEC §3.8); it also protects if upstream ever duplicates.
* No duplicate `conference_key`; no duplicate edition `id`; no series has two editions
  with the same `year`.

`date`/`place`/deadline TBD counts are in §5/§6.

---

## 4. Deadline string formats and timezone values

### 4.1 Accepted value formats (exhaustive)

Across all 4,353 datetime values present in the catalog (2892 `deadline` + 1241
`abstract_deadline` + 83 `rebuttal_deadline` + 137 `decision_deadline`; 4235 dated +
118 TBD), exactly two value kinds exist:

* `"YYYY-MM-DD HH:MM:SS"` — naive wall-clock time to be interpreted in the edition's
  `timezone` (regex `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$`);
* the literal string `"TBD"`.

There are **no** ISO-8601 strings with offsets, no empty strings, no `null`, no
timezone suffixes inside the value. So a parser that rejects anything not matching
the regex (other than `"TBD"`) is safe.

**TBD counts by field (whole catalog)**: `deadline` 99, `abstract_deadline` 19,
`rebuttal_deadline` 0, `decision_deadline` 0. In AI editions: `deadline` 16,
`abstract_deadline` 3. There are 10 catalog entries where `abstract_deadline` is
`"TBD"` while `deadline` is dated — never treat abstract absence as fatal.

**Seconds are not always `:59`.** e.g. `AI/ijcai` 2027 source is
`2027-01-11 23:59:00` (seconds `:00`, and it is in the upcoming list), and some
`AI/icml`/`NeurIPS` cutoffs are `11:59:00`. Do not assume `:59`.
(AI editions have 31 dated entries whose seconds ≠ `:59`.)

### 4.2 Timezone value domain (whole catalog)

Exact observed domain (whole catalog; AI count in parentheses):

| value | global | AI | meaning |
|---|---|---|---|
| `AoE` | 1501 | 153 | Anywhere on Earth = **UTC−12** |
| `UTC-12` | 287 | 114 | fixed **UTC−12** (same instant as AoE) |
| `UTC-7` | 93 | 20 | fixed UTC−7 |
| `UTC-8` | 73 | 32 | fixed UTC−8 |
| `UTC+0` | 73 | 15 | fixed UTC+0 |
| `UTC` | 73 | 0 | fixed UTC+0 (no AI edition uses bare `UTC`) |
| `UTC-4` | 55 | 0 | fixed UTC−4 |
| `UTC-5` | 49 | 6 | fixed UTC−5 |
| `UTC+8` | 38 | 9 | fixed UTC+8 |
| `PT` | 34 | 4 | **America/Los_Angeles, DST-aware** |
| `UTC-10` | 12 | 0 | fixed UTC−10 |
| `UTC+1` | 9 | 3 | fixed UTC+1 |
| `UTC+2` | 7 | 0 | fixed UTC+2 |
| `UTC-11` | 5 | 0 | fixed UTC−11 |
| `UTC+7` | 2 | 1 | fixed UTC+7 |
| `UTC+3` | 2 | 0 | fixed UTC+3 |
| `UTC-6` | 1 | 1 | fixed UTC−6 |
| `UTC+10` | 1 | 0 | fixed UTC+10 |

No `UTC-3`/`UTC-9`/`UTC+4`/`UTC+5`/`UTC+6`/`UTC+9`/`UTC+11`/`UTC+12` value appears
(`UTC-3?` in SPEC §2 indeed "not seen"). AI PT editions are the four `AI/icmla`
editions 2023–2026; **no upcoming AI paper deadline uses `PT`** at recon time, but
`PT` must still be implemented correctly (SPEC §7.3 synthetic fixture).

A robust resolver:

```
AoE        -> timezone(timedelta(hours=-12))          # fixed
UTC-12     -> timezone(timedelta(hours=-12))          # fixed, same as AoE
UTC        -> timezone.utc
UTC+N / UTC-N (N = 1..14) -> timezone(timedelta(hours=±N))
PT         -> ZoneInfo("America/Los_Angeles")         # DST-aware, NEVER fixed -8
anything else -> report + skip; never fall back to local time or UTC
```

### 4.3 ⚠ The UTC-12 sign trap (the exact bug that was caught in SPEC review)

`UTC-12` / `AoE` means **offset −12 hours**, not +12. A wrong sign moves a deadline
**one calendar day earlier** in UTC and therefore also in Asia/Shanghai.

Concrete CVPR 2027 case (also SPEC §7.3):

```
source:           2026-11-16 23:59:59   timezone UTC-12
correct UTC:      2026-11-17T11:59:59Z          (2026-11-16 23:59:59 + 12h)
correct Shanghai: 2026-11-17T19:59:59+08:00     (+8h)
wrong (+12) UTC:  2026-11-16T11:59:59Z
wrong (+12) SH:   2026-11-16T19:59:59+08:00     (one day early)
```

Independent evidence for the **negative** sign, from three separate artifacts:

1. Site annual page `https://ccfddl.com/venues/ai/cvpr-2027/` (HTM, not JS-guessed):
   `<time class="deadline-time" datetime="2026-11-16T23:59:59-12:00"
   data-raw="2026-11-16 23:59:59" data-source-tz="UTC-12"
   title="Original: 2026-11-16 23:59:59 UTC-12">23:59, Nov 16, 2026 · UTC-12</time>`
   → the offset literal is **`-12:00`**.
2. RSS `deadlines_en.xml`: `<title>CVPR 2027 Deadline</title>` with description
   `Deadline (UTC-12): 2026-11-16 23:59:59`.
3. ICS `deadlines_en.ics`: `DTSTART;TZID="UTC-12:00":20261116T235959`.

`research/check_ground_truth.py --selftest` asserts this conversion for both `AoE`
and `UTC-12` (UTC **and** Asia/Shanghai outputs), plus PT winter/summer DST, the PT
nonexistent/ambiguous cases, the unknown-timezone rejection, and TBD non-parsing.
Run it as a regression guard before trusting any derived table.

### 4.4 `PT` (America/Los_Angeles) DST semantics

Use `zoneinfo.ZoneInfo("America/Los_Angeles")` — never a fixed −8. Synthetic fixture
values the verifier can assert (all verified by `--selftest`):

| source (PT) | local offset | UTC | Asia/Shanghai |
|---|---|---|---|
| `2026-01-15 23:59:59` (PST) | UTC−8 | `2026-01-16T07:59:59Z` | `2026-01-16T15:59:59+08:00` |
| `2026-07-15 23:59:59` (PDT) | UTC−7 | `2026-07-16T06:59:59Z` | `2026-07-16T14:59:59+08:00` |
| `2026-03-08 02:30:00` | **nonexistent** (spring-forward gap) | undefined | — |
| `2026-11-01 01:30:00` | **ambiguous** (fall-back, occurs twice) | two instants | — |

For the two DST edge cases `llms.txt` states the upstream MCP policy: keep the
original wall time but leave UTC conversions empty and omit the node from upcoming
results. That is a *site API* policy, not the CLI contract: SPEC §3.3 requires
`zoneinfo` conversion. My generator chooses `fold=0` (earlier instant) for ambiguous
times and marks nonexistent times undefined (skipped), so any future data hitting a
DST gap is surfaced rather than silently shifted. No AI deadline currently hits
either case (cutoffs are 23:59/11:59, not 01:xx–02:xx).

---

## 5. `TBD` semantics and SPEC §4.4

`TBD` is **unknown**, never a date: never parse, never `str`-compare, never sort
against datetimes, never estimate. Site pages for TBD venues literally show
`Dates to be announced` (no `TBD` string appears in their HTML).

**Refined SPEC §4.4 rule implemented** (Lead clarification 2026-10-18; the earlier
wording "no upcoming dated paper deadline + latest year ≥ current year" would have
wrongly included 38 venues whose latest deadline already *passed*):

A series is TBD iff **ALL** of:
(a) no upcoming dated paper deadline in **any** edition (`deadline_utc > as_of`);
(b) in its **latest edition**, every timeline entry's `deadline` is `"TBD"` or absent
    (i.e. the paper deadline is genuinely not announced);
(c) latest edition year ≥ current display year (2026 on 2026-10-18 in Asia/Shanghai).

Derived dynamically (not hardcoded); on 2026-10-18 the set is exactly:

| Conference | key | latest ed. | CCF / CORE / THCPL | event date | place | link |
|---|---|---|---|---|---|---|
| COLT 2027 | `AI/colt` | 2027 | B / A* / A | June 28 – July 2, 2027 | Tokyo, Japan | https://learningtheory.org/colt2027/ |
| GECCO 2027 | `AI/gecco` | 2027 | C / A / B | July 12-16, 2027 | Kraków, Poland | https://gecco-2027.sigevo.org/HomePage |
| ICCV 2027 | `AI/iccv` | 2027 | A / A* / A | October 2-8, 2027 | Hong Kong, China | https://iccv.thecvf.com/Conferences/2027 |

Their latest-edition timeline is literally `[{"deadline": "TBD"}]`. Site pages for
`colt-2027` / `iccv-2027` show only `Conference Opening` plus `Dates to be announced`
— no paper-deadline node (cross-check in §7.1).

**Explicitly NOT TBD** (38 AI series): latest edition announced with a dated paper
deadline that has already passed, e.g. AAAI 2027 (`2026-07-28 23:59:59 UTC-12`),
AAMAS 2027, ACCV 2026, ACML 2026, AISTATS 2027, ALT 2027, BMVC 2026, ICLR 2027
(`2026-09-25`), NeurIPS 2026, ICML 2026, WACV 2027, … Per SPEC §4.4 note these must
**not** be listed as "deadline not announced". `expected_ai_deadlines.json` keeps them
for audit at `checks.non_upcoming_passed_deadline_series` (count
`non_upcoming_passed_deadline_series_count = 38`), clearly labelled
`reason: latest edition deadline already passed; NOT TBD per SPEC §4.4`.

TBD comments can contain date-like or explanatory text on other TBD entries
(e.g. historical `AI/alt` 2022 TBD with comment `"2021-10-05 17:00: EST/ET conflict"`,
`AI/log` `"Full-paper cutoff unresolved"`) — the comment is not a deadline; do not
parse it for dates.

Free-text `date`/`place` may also be `"TBD"`: catalog-wide 55 editions have
`date == "TBD"` and 4 have `place == "TBD"` (AI: 7 editions with date TBD, e.g.
`AI/acml` acml26, and 0 place TBD). Show as `TBD`, never estimate.

---

## 6. Data-quality traps checklist (all verified on this snapshot)

1. **Historical editions included** (2019–2028). Selection must scan *all* editions
   and keep only `deadline_utc > now`. At recon time every upcoming AI event happens
   to belong to its series' latest edition (verified), but do not assume that.
2. **Multiple rounds are separate events**, never merged. 296 editions catalog-wide
   have 2 timeline entries, 52 have 3, 31 have 4, 1 has 8, 7 have 12. Distinguish by
   `comment`; e.g. COLING 2027 has `ARR Submission` (2026-10-12, now passed) and a
   `COLING commitment after ARR meta-reviews; reviewed papers only` (2026-12-23,
   upcoming). 10 series *globally* currently have ≥2 upcoming paper rows from the same
   edition (CG/cog, DB/vldb ×5 cycles, NW/conext, SC/acisp, SC/blocksys, SC/ches,
   SC/pets, SC/sacmat, SC/securecomm, SE/ecoop) — AI has none at recon, but the code
   path must handle it. Do not dedupe by (conference, year) alone.
3. **Duplicate titles across areas**: `SEC` exists as `DS/sec` and `SC/sec`; `FSE` as
   `SC/fse` and `SE/fse` (not in AI). Identity is `conference_key`, not `title`.
4. **Missing `core`/`thcpl` ranks**: 17 series only have `ccf` (AI: `AI/cvc`,
   `{"ccf":"N"}`). Render missing as `–`; never invent. `ccf == "N"` means unranked in
   CCF — display as-is or `–`.
5. **`TBD` never parsed**: 99 `deadline` and 19 `abstract_deadline` TBDs catalog-wide.
   Do not sort them as strings.
6. **Free-text `date`/`place`**: not machine-parseable; some are `TBD`; some contain
   non-ASCII (e.g. `Montréal`, `Kraków`, `Xi'an`) — output must be UTF-8 clean.
7. **Abstract vs paper ordering**: abstract is usually before paper (0 cases of
   abstract > paper in the same tz across all entries), but 10 entries have
   abstract `"TBD"` + dated paper. Abstract is a separate kind; it must not replace
   or sort into the paper-deadline list.
8. **Non-`:59` seconds** (IJCAI 2027 `23:59:00`, some `11:59:00`) — do not hardcode
   `:59`.
9. **Timezone domain is exactly the list in §4.2**; report/skip unknowns. Bare `UTC`
   means +00:00.
10. **`comment` is free text** (up to 122 chars in AI, may contain `;`, `:`, digits,
    commas, e.g. `"All dates tentative; March 1 is paper registration; author
    rebuttal..."`); truncate only for display, keep the full value in `--json`/details.
11. **`opening`/`opening_is_derived`** are derived countdown anchors, not verified
    start times (`llms.txt` warns explicitly). Do not display them as event times.
12. **`--category` is data-driven**: 10 area codes; match `sub` case-insensitively;
    `ai` must equal `AI`. Do not hardcode the area list.
13. **`title` is not the display name you might expect**: `IEEE CEC`, `CoNLL`, `CoRL`,
    `NeurIPS`, `ProbML`, `RuleML+RR` — build `"<title> <year>"` verbatim.
14. **Latest-edition ambiguity**: a series' greatest `year` may already have passed or
    be TBD; do not infer "latest = accepting submissions" (`llms.txt` warning).

---

## 7. Cross-checks against the live site (independent confirmation)

### 7.1 Annual venue pages (7 pages; links followed from the `/venues/ai/` directory, never guessed)

`https://ccfddl.com/venues/ai/` (37,650 bytes) links exactly **61 AI series pages and
61 annual pages** — consistent with the JSON's 61 AI series.

| # | Page URL | Observed text (verbatim) | Derived from JSON | Match? |
|---|---|---|---|---|
| 1 | https://ccfddl.com/venues/ai/cvpr-2027/ | `Abstract Submission` → `23:59, Nov 10, 2026 · UTC-12`; `Paper Submission` → `23:59, Nov 16, 2026 · UTC-12`; plus `Feb 1, 2027` rebuttal, `Feb 25, 2027` decision | `2026-11-16 23:59:59` UTC-12 → UTC `2026-11-17T11:59:59Z`, SH `2026-11-17T19:59:59+08:00` | ✅ |
| 2 | https://ccfddl.com/venues/ai/icaps-2027/ | `Paper Submission` → `23:59, Dec 14, 2026 · UTC-12`; `Abstract Submission` → `Dec 7, 2026` | `2026-12-14 23:59:59` UTC-12 → UTC `2026-12-15T11:59:59Z`, SH `2026-12-15T19:59:59+08:00` | ✅ |
| 3 | https://ccfddl.com/venues/ai/esann-2027/ | `Paper Submission` → `23:59, Nov 18, 2026 · UTC-8` | `2026-11-18 23:59:59` UTC-8 → UTC `2026-11-19T07:59:59Z`, SH `2026-11-19T15:59:59+08:00` | ✅ |
| 4 | https://ccfddl.com/venues/ai/coling-2027/ | `Round 1 Paper Submission` → `23:59, Oct 12, 2026 · UTC-12`; `Round 2 Paper Submission` → `23:59, Dec 23, 2026 · UTC-12`; `Round 2 Final Decisions` → `Feb 10, 2027`; page "next deadline" is the Nov 30 **rebuttal**, not a paper deadline | JSON same edition: node0 = `2026-10-12` tz UTC-12 comment `ARR Submission` (already passed); node1 = `2026-12-23` tz UTC-12 comment `COLING commitment after ARR meta-reviews; reviewed papers only` → UTC `2026-12-24T11:59:59Z`, SH `2026-12-24T19:59:59+08:00` | ✅ instants; ⚠ label wording differs (page derives "Round N", JSON keeps raw `comment`) |
| 5 | https://ccfddl.com/venues/ai/aaai-2027/ | `Abstract Submission` → `23:59, Jul 21, 2026 · UTC-12`; `Paper Submission` → `23:59, Jul 28, 2026 · UTC-12`; `Rebuttal Submission` → `Oct 25, 2026`; `Final Decisions` → `Nov 30, 2026` | AAAI 2027 dated paper deadline `2026-07-28`, **passed** at as_of → correctly **not** upcoming and **not** TBD | ✅ (confirms the "passed ≠ TBD" rule) |
| 6 | https://ccfddl.com/venues/ai/iccv-2027/ | `IMPORTANT DEADLINES` → `Dates to be announced`; only `Conference Opening` → `08:00, Oct 2, 2027 · AoE`; no paper-deadline node; zero occurrences of string `TBD` | JSON latest edition `iccv27` timeline = `[{"deadline":"TBD"}]`, tz AoE, date/place present | ✅ TBD |
| 7 | https://ccfddl.com/venues/ai/colt-2027/ | same pattern: `Dates to be announced`; only `Conference Opening` → `08:00, Jun 28, 2027 · AoE` | JSON latest edition `colt27` timeline = `[{"deadline":"TBD"}]`, tz AoE | ✅ TBD |

Timestamps displayed by the site use the **edition's source timezone** (e.g. `· UTC-12`,
`· AoE`, `· UTC-8`), and each `<time>` element also carries machine-readable
`datetime="...-12:00"`/`data-source-tz` attributes used in §4.3. The site also renders
localized area names (`人工智能` for AI) — not part of the JSON contract.

**One explicit discrepancy, noted rather than smoothed over:** the site's human labels
for COLING's two rounds ("Round 1/2 Paper Submission") are *derived display labels*;
the JSON `comment` fields are `ARR Submission` / `COLING commitment after ARR
meta-reviews; reviewed papers only`. A CLI that prints `comment` will read differently
from the page but represents the same instants. Do not treat page labels as the
`comment` source.

### 7.2 RSS feed cross-check (`deadlines_en.xml`, 4235 items, 2.48 MB)

Parsed every `<item>` with `<category>AI</category>` and a paper-deadline title
(`"<conf> <year> Deadline"`, optional `[comment]` suffix — note comments are embedded
in RSS titles, and abstract/rebuttal/decision items are titled differently). Converted
the `Deadline (<tz>): <naive>` value from the description with independent code.

* AI paper-deadline items of all time: **420**; **upcoming at as_of: 20**.
* The 20 UTC instants are a **multiset-identical match** to
  `expected_ai_deadlines.json` (0 ground-truth-only, 0 RSS-only).
* Example: `<title>CVPR 2027 Deadline</title>` →
  `Deadline (UTC-12): 2026-11-16 23:59:59` → `2026-11-17T11:59:59Z` ✅.

### 7.3 ICS feed cross-check (`deadlines_en.ics`, 4235 VEVENTs, 3.0 MB)

Parsed `SUMMARY` (paper kind), `Category: ... (AI)`, and
`Original Deadline (<tz>): <naive>` from each unfolded VEVENT.

* AI paper-deadline VEVENTs of all time: **420**; **upcoming: 20**; skipped: 0.
* **Multiset-identical** to the ground truth again.
* Quirks: `DTSTART;TZID="UTC-12:00":20261116T235959` — ICS TZID strings use
  `UTC±HH:MM` including a colon; `AoE`/`PT` are already converted to fixed offsets in
  the ICS TZID domain (`UTC-12:00`, `UTC-08:00`/`UTC-07:00`). The ICS is *not* the
  tool's source; it is only corroboration.

**Conclusion:** the live JSON is internally consistent and two independently generated
upstream feeds reproduce the exact same 20 UTC instants for upcoming AI paper
deadlines. The count `20` is a *snapshot* property, not a constant.

---

## 8. Ground truth: 20 upcoming AI paper deadlines (as_of 2026-10-18T08:00:41Z)

Selection: `sub == "AI"`, field `deadline`, all 358 editions, all rounds,
`deadline_utc > as_of`, `TBD` excluded, sorted by `(deadline_utc, conference, year)`.
Display timezone `Asia/Shanghai`. Full fields (including `abstract_*`, `link`,
`event_date`, `place`, `seconds_left`, rank core/thcpl, `edition_id`) are in
`research/expected_ai_deadlines.json`.

| # | Conference | CCF | Deadline (UTC) | Deadline (Asia/Shanghai) | Source string | Source tz | Comment |
|---|---|---|---|---|---|---|---|
| 1 | EuroGP 2027 | N | 2026-11-02T11:59:59Z | 2026-11-02T19:59:59+08:00 | `2026-11-01 23:59:59` | AoE | Full papers |
| 2 | EvoApplications 2027 | N | 2026-11-02T11:59:59Z | 2026-11-02T19:59:59+08:00 | `2026-11-01 23:59:59` | AoE | Full papers |
| 3 | EvoCOP 2027 | N | 2026-11-02T11:59:59Z | 2026-11-02T19:59:59+08:00 | `2026-11-01 23:59:59` | AoE | Full papers |
| 4 | EvoMUSART 2027 | N | 2026-11-02T11:59:59Z | 2026-11-02T19:59:59+08:00 | `2026-11-01 23:59:59` | AoE | Full papers |
| 5 | CVPR 2027 | A | 2026-11-17T11:59:59Z | 2026-11-17T19:59:59+08:00 | `2026-11-16 23:59:59` | UTC-12 | — |
| 6 | ESANN 2027 | N | 2026-11-19T07:59:59Z | 2026-11-19T15:59:59+08:00 | `2026-11-18 23:59:59` | UTC-8 | — |
| 7 | RSS 2027 | N | 2026-12-05T11:59:59Z | 2026-12-05T19:59:59+08:00 | `2026-12-04 23:59:59` | AoE | Stage 1: initial 6-page extended abstract submission |
| 8 | CPAL 2027 | N | 2026-12-06T11:59:59Z | 2026-12-06T19:59:59+08:00 | `2026-12-05 23:59:59` | AoE | — |
| 9 | ICAPS 2027 | B | 2026-12-15T11:59:59Z | 2026-12-15T19:59:59+08:00 | `2026-12-14 23:59:59` | UTC-12 | — |
| 10 | COLING 2027 | B | 2026-12-24T11:59:59Z | 2026-12-24T19:59:59+08:00 | `2026-12-23 23:59:59` | UTC-12 | COLING commitment after ARR meta-reviews; reviewed papers only |
| 11 | NAACL 2027 | B | 2026-12-24T11:59:59Z | 2026-12-24T19:59:59+08:00 | `2026-12-23 23:59:59` | UTC-12 | NAACL commitment after ARR meta-reviews; reviewed papers only |
| 12 | ACL 2027 | A | 2027-01-05T11:59:59Z | 2027-01-05T19:59:59+08:00 | `2027-01-04 23:59:59` | UTC-12 | ARR Submission |
| 13 | IJCAI 2027 | B | 2027-01-12T11:59:00Z | 2027-01-12T19:59:00+08:00 | `2027-01-11 23:59:00` | AoE | Separate satellite event: August 15-17, 2027, Hengqin, China |
| 14 | IJCNN 2027 | C | 2027-02-01T11:59:59Z | 2027-02-01T19:59:59+08:00 | `2027-01-31 23:59:59` | UTC-12 | — |
| 15 | ICDAR 2027 | C | 2027-02-21T11:59:59Z | 2027-02-21T19:59:59+08:00 | `2027-02-20 23:59:59` | AoE | — |
| 16 | IEEE CEC 2027 | C | 2027-03-01T11:59:59Z | 2027-03-01T19:59:59+08:00 | `2027-02-28 23:59:59` | UTC-12 | — |
| 17 | IROS 2027 | C | 2027-03-02T11:59:59Z | 2027-03-02T19:59:59+08:00 | `2027-03-01 23:59:59` | AoE | Paper submission deadline: March 1, 2027; exact cutoff time and tim… |
| 18 | ICPR 2027 | C | 2027-03-09T11:59:59Z | 2027-03-09T19:59:59+08:00 | `2027-03-08 23:59:59` | AoE | All dates tentative; March 1 is paper registration; author rebuttal… |
| 19 | ECAI 2027 | B | 2027-04-15T11:59:59Z | 2027-04-15T19:59:59+08:00 | `2027-04-14 23:59:59` | AoE | — |
| 20 | KR 2027 | B | 2027-04-29T11:59:59Z | 2027-04-29T19:59:59+08:00 | `2027-04-28 23:59:59` | AoE | Main track; author response period: June 15-18, 2027 |

Distribution check: 20 events / **20 distinct series**; source tz AoE 12, UTC-12 7,
UTC-8 1; 7 events have an `abstract_deadline`; 0 duplicate events; 0 unknown tz.

Note rows 1–4: four different series (EuroGP, EvoApplications, EvoCOP, EvoMUSART) share
the identical source datetime — they are distinct series, not duplicates. The JSON
`events` list keeps all four (dedup key includes `conference_key`).

---

## 9. TBD list (SPEC §4.4), as derived dynamically

`COLT 2027`, `GECCO 2027`, `ICCV 2027` — see the table and rule in §5. Serialized as
`tbd[]` in `expected_ai_deadlines.json` (sorted by title), each with
`latest_edition_year`, `latest_edition_id`, ranks, `event_date`, `place`, `link`,
`deadline_status: "TBD"`.

Not TBD: 38 "latest deadline already passed" series, listed for audit under
`checks.non_upcoming_passed_deadline_series` (not in `tbd[]`).

---

## 10. Reproduction commands (exact)

From the repo root `/Users/eculid/Desktop/CodeBase/tools`:

```bash
# 1) timezone-semantics regression guard (UTC-12 sign, AoE, PT DST, TBD, unknown tz)
python3 research/check_ground_truth.py --selftest

# 2) catalog schema / domain / data-quality audit (offline, from archived snapshot)
python3 research/check_ground_truth.py \
        --data-file research/raw/allconf.json \
        --as-of 2026-10-18T07:55:19Z --audit

# 3) deterministic regeneration of the committed ground-truth snapshot
python3 research/check_ground_truth.py \
        --data-file research/raw/allconf.json \
        --as-of 2026-10-18T08:00:41Z \
        --out research/expected_ai_deadlines.json

# 4) live regeneration from ccfddl.com (this is how the committed file was made;
#    as_of becomes the live fetch time)
python3 research/check_ground_truth.py

# 5) human-readable summary without writing anything
python3 research/check_ground_truth.py \
        --data-file research/raw/allconf.json \
        --as-of 2026-10-18T08:00:41Z --summary
```

The script is stdlib-only (`urllib.request`, `json`, `hashlib`, `argparse`,
`datetime`, `zoneinfo`) and exits non-zero with a stderr message on fetch/parse
failure. `--data-file -` reads stdin. `as_of` defaults to the fetch time; `--as-of`
pins it (accepts `Z` or `+00:00`). `expected_ai_deadlines.json` records the full fetch
metadata (`http_status`, `content_type`, `last_modified`, `etag`, `bytes`, `sha256`,
`fetched_at_utc`) plus `semantics`, `checks`, and `catalog_stats` so every value can
be audited back to the source.

---

## 11. Discrepancies, deviations, and notes for Lead / verifier

1. **UTC-12 sign (SPEC correction): independently confirmed.** SPEC §2/§4.4/§7/§8 were
   corrected at 15:58 to `UTC-12 = −12h`. This research independently confirms the
   negative sign from three independent artifacts (site `<time datetime="...-12:00">`
   attribute, RSS, ICS) *and* by recomputation: CVPR 2027 source `2026-11-16
   23:59:59` UTC-12 → `2026-11-17T11:59:59Z` → Asia/Shanghai
   `2026-11-17T19:59:59+08:00`. The ground truth was computed only from raw catalog
   values (never from SPEC appendix/example values), so it was correct even while the
   pre-correction appendix carried the flawed `2026-11-16` local value. No SPEC action
   requested.
2. **SPEC §4.4 (old literal wording) vs refined rule.** The pre-15:58 wording
   ("no upcoming dated paper deadline + latest year ≥ current year") literally yields
   **41** AI series (it includes venues like AAAI 2027 whose deadline merely passed).
   The refined rule (b: latest-edition deadlines all TBD/absent) yields exactly the
   three named cases. My generator implements the refined rule; the 38 excluded
   series are kept in `checks.non_upcoming_passed_deadline_series` (explicitly
   `NOT TBD`) so the distinction is auditable. If the verifier tests `--include-tbd`,
   it should expect {COLT 2027, GECCO 2027, ICCV 2027} — not the 41.
3. **SPEC §2.1 says historical editions go "back to 2021 and earlier"; actual min is
   2019** (`MX/aft`; 1 edition in 2019, 4 in 2020). Cosmetic only; selection logic
   must not assume a 2021 floor.
4. **SPEC §2.1 timezone list** matches the observed domain except `UTC-3?`, which is
   indeed not present. No other deviation.
5. **llms.txt PT-DST policy vs CLI contract.** The site's MCP drops ambiguous PT instants
   from upcoming results; the CLI per SPEC §3.3 must convert with `zoneinfo`. There is
   no current AI deadline in the DST gap, so no practical conflict; the script's PT
   behavior is documented in §4.4 and covered by `--selftest`.
6. **Count `20` is a snapshot.** If the verifier runs later, an event may pass or a TBD
   venue may announce (`COLT/GECCO/ICCV` 2027 deadlines are expected to appear). Always
   recompute from live data; compare against a freshly generated ground truth rather
   than the literal 20.
7. **Site labels ≠ JSON comments** for multi-round venues (COLING case in §7.1): match
   on UTC instants, not on display labels.
8. **`opening` is derived** — do not render it as the event time (`llms.txt` explicit
   warning). The pages show `Conference Opening` (derived 08:00) alongside deadlines;
   the CLI's paper list must not include it.

---

## 12. Current site behavior observed (2026-10-18)

* Apex host `https://ccfddl.com/` is the canonical site; old
  `https://ccfddl.github.io/` returns **301 → http://ccfddl.com/**.
* Area directory `/venues/ai/` is server-rendered HTML linking 61 series pages and 61
  annual pages; annual pages `…/<slug>-<year>/` show `IMPORTANT DEADLINES` with every
  timeline node (paper/abstract/rebuttal/decision/opening), each `<time>` carrying
  `datetime="<naive><offset>"`, `data-raw`, `data-source-tz`, and a human string
  `HH:MM, Mon DD, YYYY · <source-tz>`. TBD venues show `Dates to be announced`.
* Site area names are localized to Chinese (`人工智能` for AI); the JSON contract is
  the code `AI`.
* `allconf.json` is served through Cloudflare with `max-age=600`; `Last-Modified`
  reflected the previous day's publication at recon, i.e. "updated several times a
  week" as SPEC says.
* `llms.txt` documents the same four machine-readable endpoints and explicitly says
  TBD/missing are unknown, latest listed venue may not accept submissions, editions'
  years can differ from submission calendar years, and PT DST-gap/overlap times do not
  identify unique instants.
