# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

2026 FIFA World Cup interactive bracket simulator: predict or AI-simulate the full
48-team tournament, follow real results live, and share/browse brackets.

## Commands

```bash
pip install -r requirements.txt
python3 server.py          # http://localhost:3000 — runs without ANTHROPIC_API_KEY
                           # (AI endpoints then return 503; everything else works)
ANTHROPIC_API_KEY=sk-... python3 server.py   # with AI mode
```

No build step, lint, or tests — `index.html` is a single self-contained file with all
CSS/JS inline. Verify changes by loading the page (see Preview caveat below).

Deployment: push to `main` → GitHub auto-deploy to Vercel
(repo `aidanlconnolly/world-cup-bracket-picker`, project `world-cup-bracket-picker`,
live at world-cup-bracket-picker.vercel.app). `gh` and `vercel` CLIs are at
`/opt/homebrew/bin/`, both authenticated.

## Architecture

- `index.html` — the entire app; four views (`#view-bracket`, `#view-live`,
  `#view-explore`, `#view-tickets`) toggled by `setTab()`
- `server.py` — Flask app serving index.html + all `/api` routes. **Vercel deploys this
  Flask app via its Python/Flask preset and routes `/api/*` through it** (confirmed via
  prod tracebacks) — so server-side changes must land in `server.py`, not just `api/`
- `api/simulate.py` / `api/final.py` / `api/brackets.py` / `api/prices.py` —
  standalone Vercel Python handlers kept in parity with the Flask routes in case
  routing ever switches to per-function mode; they are NOT what answers in prod today
- `vercel.json` — rewrites pinning the `/api/*` paths ahead of the catch-all
  `/(.*) → /index.html`; edit it when adding a new API route

It's a **pick-only, score-oriented** game (March-Madness style): you predict, then
get scored against the real results. There is **no AI mode** — `state.mode` is always
`'pick'` (the field is kept only for back-compat in old share hashes; `simulateAll()`
is now a local odds-based **Auto-fill**, the Claude `/api/simulate` + `/api/final`
routes and `callSimulate`/`callFinal` are dead code left in place).

### Bracket state model (`state` in index.html)

`{ mode:'pick', name, groups, picks, ko, finals:{final, thirdPlace}, awards,
selectedThirds, thirdAssign, koFromReal }`. Group entries are `{done, standings, real?,
live?, played?}` — `live:true` means a partial real-results table that renders but does
NOT resolve the bracket (only `done:true` does). Match results are
`{winner, loser, prob, reasoning, real?, score?}`. `freshState()` is the canonical
empty bracket. `name` labels a bracket on the leaderboard; `koFromReal` is the Phase-2
toggle (below).

Bracket slots resolve through a small grammar in `resolveSlot()`: `'1A'`/`'2B'`
(group position), `'3rd:A/B/C/D/F'` (third-place slot, eligibility in `THIRD_SLOTS`),
`'W:r32-5'`/`'L:sf-1'` (winner/loser of match id). When `state.koFromReal` is on,
`getGroupStandings()` returns the **real** group tables (`realStandings()`) instead of
your picks, so the knockout bracket is seeded from the actual qualifiers — a second
tournament independent of Phase 1. `assignThirds()` checks `state.thirdAssign` (real
FIFA allocation captured from ESPN's actual R32 fixtures by Sync Real) before falling
back to eligibility-order assignment. Bracket cards are absolutely positioned via
`MATCH_ROW` row indices; SVG connectors are drawn per render.

### Scoring (two "tournaments", March-Madness style)

`buildAnswerKey()` derives reality **purely from the ESPN live feed** (`live.matches`),
never from anyone's picks: real group standings per decided group, the real best-8
thirds (once all 12 groups final), and per-round "reached" sets for knockouts
(`koRoundOf()` classifies a finished KO match by ESPN round label, falling back to date
windows). `scoreState(s, key)` compares a prediction to that key:
- **Phase 1 (Group Stage)**: exact 1st +5, exact 2nd +3, right team / wrong slot +2,
  each correctly-tipped 3rd-place qualifier +2 (`GROUP_PTS`).
- **Phase 2 (Knockouts)**: every team you correctly send THROUGH a round, escalating —
  reach R16 +2, QF +4, SF +8, Final +16, champion +32, 3rd-place match +8
  (`KO_REACH_PTS`, via `predictedReached()`).
Results flagged `real:true` (pulled in by Sync Real) are **skipped** so syncing never
inflates your own score. `renderScoreboard()` shows the live tally on the bracket view
(hidden until any real result exists); the same function powers the leaderboard.

### Share links, persistence, and the sanitizer coupling

- Full state persists to localStorage; the URL hash carries a **slimmed** copy from
  `stripStateForShare()` (drops AI reasoning), encoded UTF-8-safe by
  `encodeHash()`/`decodeHash()` (plain `btoa` breaks on Unicode in reasoning text).
- All externally-sourced states (share-link hashes, Global-Brackets entries) pass through
  `sanitizeBracketState()`, which whitelists team names against `TEAMS` and nulls
  reasoning/awards — these reach `innerHTML`, so this is the XSS barrier.
- `loadState()` detects "own" hashes by re-encoding localStorage through
  `stripStateForShare()` and comparing; own state loads at full fidelity.
- **Gotcha: a new `state` field must be added to BOTH `stripStateForShare()` and
  `sanitizeBracketState()`** or it silently disappears from share links and Global
  Brackets (`name` and `koFromReal` are carried by both).

### Live data (Matches tab, Sync Real, dynamic ratings)

ESPN's public scoreboard API (CORS-open, no key):
`site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD-YYYYMMDD&limit=200`.
Full schedule fetched once per session; ±1-day window polled every 60 s while the
Matches tab is open; cached in localStorage (`wcLiveCache`). Events are slimmed by
`normalizeEvent()`; goal scorers come from `competitions[0].details` (`scoringPlay`);
ESPN names map to `TEAMS` keys via `ESPN_NAME_MAP` (`United States`→`USA`,
`Bosnia-Herzegovina`→`Bosnia & Herzegovina`); placeholder knockout slots ("Group A
Winner") render as TBD.

- **Sync Real** (`syncRealResults()`): builds real group standings from finished
  matches, matches finished knockout games to bracket slots by team pair, stores real
  scores on results, and captures the third-place allocation once R32 fixtures are known.
- **Dynamic ratings**: `effectiveProb()` = static `TEAMS[t].prob` prior + `dynAdj`
  (form string W/L ±1.6 each + real results ±4/match + goal diff, capped ±18),
  recomputed in `computeRatings()` after every fetch; rendered as ▲/▼ deltas and used
  by all simulations.

### Ticket analytics (Tickets Analysis tab)

Monte Carlo over the remaining tournament (5,000 sims, ~600 ms, synchronous in
`runTicketsMC()`), independent of the user's bracket picks. Anchoring, in priority
order: finished matches are locked (`koLocks` by team pair), partially-played groups
start from real points/GD (`buildMCInputs()`), and any fixture with posted odds uses
DraftKings 3-way moneylines from ESPN (`comp.odds[0].moneyline`, vig-normalized in
`normalizeEvent()` → `m.odds`) instead of the model; everything else uses
`effectiveProb()`. KO through-prob with odds = P(win 90') + P(draw)×strength-split.
Outputs: `mc.matchProbs[matchId]` (P(team appears in each physical game)) and
`mc.teamRounds` (round-reach + champion). `mc` is derived data, NOT part of `state` —
no share/sanitizer coupling. KO defs carry exact `date:` kickoffs extracted from ESPN
fixtures (R32 mapped via bracket-slot placeholder names; R16+ via venue, unique within
each round).

`gameRows()` builds one stable-keyed row per future game (group fixtures `'g'+id` +
KO slots by match id), the spine for all Tickets views. Demand = Σ P×`DEMAND` weight,
hosts ×1.5 at home venues (`VENUES` capacities + `DEMAND` fanbase weights are editable
guesses). Views, top to bottom:
- **Buy board** (always visible, the hero): `buildTiers()` grades every `gameRows()`
  row S→D by buy score = 40·demand pctile + 20·scarcity pctile + 15·certainty +
  10·momentum ± value adj + host bonus. Tier cuts are relative (S≈top 7%, A 12%,
  B 18%, C 25%, D rest). Each card carries its headline thesis [in brackets] + up to
  5 cross-signal rationale bullets. S/A render expanded, B is a fold; C (Speculative)
  and D (Pass) render below a "Supporting details & analysis" divider with the rest.
  `thesisByKey()`/`thesisTag()` (cached per render) put the same bracketed thesis on
  game rows in Hot tickets, Since yesterday, My inventory, and the match explorer.
- **Theses**: `thesisList()` buckets `gameRows()` into investment archetypes
  (blue-chip locks, host gravity, small-building squeeze, trophy rounds, superpower
  lottery, momentum rides, mispriced paper — the last only with ≥3 entered prices);
  overlap allowed. Ranked by edge = conviction × avg demand of the top-5 qualifying
  games + their trend vs yesterday; empty theses are hidden.

Everything below the Buy board is wrapped in `fold(id, title, body, sub)` —
`<details>` sections whose open state persists in `wcFolds` (all closed by default;
My inventory auto-opens when holdings exist). Shared row helpers `rowTrend()` /
`hostPull()` feed both the theses and the tier grader.
- **Since yesterday**: demand + appearance-prob moves vs the most recent prior daily
  snapshot (`wcMCSnaps`, ≤21 days kept; `saveDailySnapshot()` writes today's after each
  run; `prevDailySnapshot()` reads the latest day `< today`).
- **My inventory**: ☆ watchlist (`wcWatch`: gameKey→{keyTeam?, cost?}) with hold/sell
  signals from `signalFor()` (locked matchup → sell window; key team fading <35% →
  elimination-risk sell; else demand trend vs yesterday) + P/L from cost vs ask price.
- **City board**: per-venue scarcity = remaining demand per 1k seats (`VENUES[].cap`),
  total demand, yesterday trend, avg entered price, aggregated hold/sell lean.
- Hot Tickets, per-round match explorer, reach matrix, title movers (`wcMCPrev`).

Prices (`wcPrices`: gameKey→get-in $) auto-fill keylessly — no sign-up — or are
entered by hand. Primary feed is our own `/api/prices`: a server-side StubHub
scrape (discovery = the World Cup grouping page `grouping/45410` + the public
explore feed; get-in = event-page JSON-LD `AggregateOffer.lowPrice`). Coverage is
partial (soonest games first — the tradeable ones) and the route caches 30 min and
degrades to `[]` when StubHub's edge 202-challenges the client (it does this to
bursty or datacenter IPs — keep request volume low). The client auto-pulls after a
Tickets MC run at most every 6 h (`wcPricesAt`); Ticketmaster/SeatGeek fetchers
still run as silent extras if keys were saved (`wcTicketmasterKey`/`wcSeatGeekKey`)
but are never prompted for. Quotes match games by venue + kickoff, minimum across
sources wins, and feed quotes overwrite stored prices (they ARE the current
cheapest ask). With ≥3 priced games, value tags (UNDERPRICED/FAIR/RICH) compare
$/demand vs the median (`medianVpd()`).

### Global Brackets (the `#view-explore` tab — leaderboard)

Storage: one JSON array under KV key `wc2026:brackets`. `server.py` uses Vercel KV via
REST (stdlib urllib) when `KV_REST_API_URL`+`KV_REST_API_TOKEN` (or
`UPSTASH_REDIS_REST_*`) exist, else `brackets.local.json` (gitignored). One bracket per
name (newest wins, case-insensitive), capped at 100. POST `{"name": X, "remove": true}`
unpublishes — no auth, friend-group toy. Prod KV is confirmed working; if "publish
seems broken" it's almost always client-side, not storage.

UI: `renderExplore()` is a **leaderboard**, not a grid — `scoredEntries()` decodes every
published bracket's hash, runs `scoreState()` against the current answer key, and ranks
by the active `gbTab` (`total`/`group`/`ko`). Your locally-saved brackets
(`wcMyBrackets`) are merged in and flagged `YOU`; unpublished local drafts also show
(`localOnly`), deduped against published entries by hash. Until a real result exists,
rows sort by recency and all show 0.

- **Publish** (`openPublishModal()` → `submitPublish()`): an **inline modal**, not
  `prompt()` — `prompt()` is silently suppressed in many mobile/in-app browsers, which
  was the old "publish doesn't work for friends" bug. Partial (group-stage-only)
  brackets publish fine (empty `champion`). Publishing also banks a local copy.
- **New Bracket** (`newBracket()`, the old Reset): banks the current bracket into
  `wcMyBrackets` (via `saveMyBracket()`), then starts a `freshState()` — so you can keep
  several entries (one per pool). `bracketHasPicks()` gates both publish and banking.

## Vercel environment notes

- The KV store `upstash-kv-amethyst-anchor` is connected to this project (env vars are
  integration-managed, type *sensitive* — values can never be read back via CLI/API).
  It's shared with penalty-shootout and finance-tracker; keys are namespaced by prefix.
- The project has **no `ANTHROPIC_API_KEY`** env var (there's an odd one named
  `world_cup_picker` that may hold the key under the wrong name) — prod AI mode 503s
  gracefully until that's fixed in the dashboard.

## Preview caveat

The Claude Code preview runner cannot read this Desktop folder (macOS TCC), so
`.claude/launch.json` runs a scratch copy from `/tmp/wc-bracket-preview` (Flask
`server.py`, so /api/brackets works; no ANTHROPIC_API_KEY → AI endpoints 503).
Re-copy `index.html` (and `server.py`/`api/` if changed) there after edits when
previewing. For real local dev, run `python3 server.py` directly.
