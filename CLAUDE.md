# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

2026 FIFA World Cup interactive bracket simulator: predict or AI-simulate the full
48-team tournament, follow real results live, and share/browse brackets.

## Commands

```bash
pip install -r requirements.txt
python3 server.py          # http://localhost:3000 — no API key needed
```

The app no longer has an AI mode, so `ANTHROPIC_API_KEY` is irrelevant to normal use;
the `/api/simulate` + `/api/final` Claude routes (and `callSimulate`/`callFinal`) are
vestigial — nothing in the UI calls them.

No build step, lint, or tests — `index.html` is a single self-contained file with all
CSS/JS inline. Verify changes by loading the page (see Preview caveat below).

Deployment: push to `main` → GitHub auto-deploy to Vercel
(repo `aidanlconnolly/world-cup-bracket-picker`, project `world-cup-bracket-picker`,
live at world-cup-bracket-picker.vercel.app). `gh` and `vercel` CLIs are at
`/opt/homebrew/bin/`, both authenticated.

## Architecture

- `index.html` — the entire app; four views (`#view-bracket`, `#view-explore`,
  `#view-live`, `#view-predictor`) toggled by `setTab()`. **`#view-predictor` =
  "🎯 Knockout bracket" is now the HOME tab** (first, default-active; init calls
  `setTab('predictor')`, `activeTab`/`predFilter` default to `'predictor'`/`'ko'`, and the
  inline view `display` defaults were swapped so it paints first with no flash). Nav order:
  Knockout bracket · 🌍 Global Brackets · Matches · **Group stage picks (`#view-bracket`,
  last)**. Internal ids/tab-keys are unchanged (`bracket`/`explore`/`live`/`predictor`) —
  only button text/order changed, so all `setTab('predictor')` etc. calls still work. The old
  Tickets Analysis tab (`#view-tickets`) was removed from
  the UI; its Monte-Carlo/prices code (`computeTickets`, `runTicketsMC`, `gameRows`,
  `fold`, `buildTiers`, price feeds, etc.) is now **dead/unreachable** — left in place,
  not wired to any button or `setTab` branch. `lsGet`/`lsSet` are declared at the top of
  the script on purpose — several modules (predictor, folds, watchlist) read their stores
  at evaluation time, and a TDZ hit there kills the whole script
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

`{ mode:'pick', id, name, groups, picks, ko, finals:{final, thirdPlace}, awards,
selectedThirds, thirdAssign, koFromReal }`. Group entries are `{done, standings, real?,
live?, played?}` — `live:true` means a partial real-results table that renders but does
NOT resolve the bracket (only `done:true` does). Match results are
`{winner, loser, prob, reasoning, real?, score?}`. `freshState()` is the canonical
empty bracket. `name` labels a bracket on the leaderboard; `koFromReal` is the Phase-2
toggle (below).

**Multi-bracket**: `state.id` (local-only — NOT in share hashes) keys an entry in
`wcMyBrackets` (full-state snapshots, newest-edited first, cap 20). `saveState()` →
`persistActive()` keeps the collection in sync on every edit; `renderExplore()` also
calls it up front so the bracket you're editing always shows under **📝 My brackets**
(saveState only fires on edits, so a fresh load otherwise left it missing from its own
list); `switchToBracket(id)` swaps the active bracket for editing; `newBracket()` (the
nav's ➕, formerly Reset) banks the current one and starts fresh; `deleteMyBracket(id)`
resets to fresh if you delete the one being edited. Old hash-only `wcMyBrackets` entries
migrate lazily in `myBrackets()`.

Bracket slots resolve through a small grammar in `resolveSlot()`: `'1A'`/`'2B'`
(group position), `'3rd:A/B/C/D/F'` (third-place slot, eligibility in `THIRD_SLOTS`),
`'W:r32-5'`/`'L:sf-1'` (winner/loser of match id). When `state.koFromReal` is on,
`getGroupStandings()` returns the **real** group tables (`realStandings()`) instead of
your picks, so the knockout bracket is seeded from the actual qualifiers — a second
tournament independent of Phase 1. `assignThirds()` checks `state.thirdAssign` (real
FIFA allocation captured from ESPN's actual R32 fixtures by Sync Real) before falling
back to eligibility-order assignment. Bracket cards are absolutely positioned via
`MATCH_ROW` row indices; SVG connectors are drawn per render.

**`R32_DEF` order is load-bearing.** The R16/QF/SF defs wire a plain binary tree
(`r16-1 = W:r32-1 vs W:r32-2`, `qf-1 = W:r16-1 vs W:r16-2`, …), so the *roads* (who can
meet whom, and when) come entirely from how the 16 R32 matchups are ordered top-to-bottom.
They mirror the **official 2026 bracket layout exactly as ESPN/FIFA draw it** (top-to-bottom
the R32 reads 2A2B, 1F2C, 1E3rd, 1I3rd, 1G3rd, 1D3rd, 1H2J, 2K2L, 1C2F, 2E2I, 1A3rd, 1L3rd,
1B3rd, 1K3rd, 2D2G, 1J2H): top half `r32-1..8` → `sf-1`, bottom half `r32-9..16` → `sf-2`.
Concretely `1J` (`r32-16`) and `1K` (`r32-14`) are both in the bottom half and meet earliest
at `qf-4` — *not* the R16 (an earlier bug had them adjacent in `r16-8`); `1J` vs `2K` (the
real field, since Colombia won Group K) only meet in the Final (opposite halves). `THIRD_SLOTS`
keys and the `slotOrder` arrays in `assignThirds()` (and the dead MC `mcAssignThirds`) must
stay in sync with the third-slot positions, now `r32-3,4,5,6,11,12,13,14`. The R16/QF/SF
`venue`/`date` fields are pinned to bracket *position* (= official match number), re-mapped to
the official schedule after the reorder. `MATCH_ROW['third-place']` is `10` (was 14) so the
🥉 3rd-place playoff card renders directly under the 🏆 Final in the last column.

**Scroll-preserving re-render.** `pickWinner`/`resetKO` call `renderBracketKeepingScroll()`
(not bare `renderBracket()`), and the predictor's `setPredKO` calls
`renderPredictorKeepingScroll()`. Both capture the `.bracket-scroll` horizontal position,
re-render, restore it (a fresh render used to snap mobile users back to the Round of 32 after
every tap), then call the shared `advanceOrHold()`: on **mobile** (`isMobileView()`,
≤768px), when the just-picked match *completes its whole round* it glides to the next
round's column (`COLS[next]`). Scrolling uses a plain `scrollLeft` assignment
(`setBracketScroll`) — `scrollTo({behavior:'smooth'})`/rAF animations silently no-op in some
renderers, so don't reintroduce them.

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

### Match Predictor / "Knockout bracket" (`#view-predictor` tab — the HOME tab)

This is the headline game now (the group stage is over). State lives in
`wcPredictor` = `{picks:{espnEventId: teamName|'DRAW'}, ko:{matchId:{winner,loser}},
finals:{final, thirdPlace}}` — `picks` are the legacy 1X2 group calls keyed off ESPN ids;
`ko`/`finals` mirror the bracket's shape so the existing KO grammar can run.

**Real seeding once the groups finish.** `predStateFrom(pd)` checks `realFieldReady()`:
when all 12 real group tables are final it seeds the knockout bracket from the **real**
qualifiers (`realStandings(g)`, not the user's group picks) AND FIFA's **real 3rd-place
allocation** — `realThirdAssignFor(ps)` reads ESPN's actual R32 fixtures (each seeded group
winner's opponent IS that slot's real 3rd) into `ps.thirdAssign`, so `assignThirds()` uses
it instead of the greedy fallback. This is what makes the matchups mirror the real draw
(Germany–Paraguay, France–Sweden, Belgium–Senegal, Mexico–Ecuador, …) rather than the
greedy guess. Before the groups finish it falls back to `deriveGroupStandings` (the
predicted tables). **Group picking is disabled once `realFieldReady()`** (`setPredPick`
early-returns), the filter chips are `Knockout bracket` then `Group results` (read-only),
and `predFilter` defaults to `'ko'` so the tab opens straight to the bracket tree.

- **Group phase** (`predFilter==='group'`): 12 per-group cards, each the 6 real
  fixtures (`groupFixtures(g)`) + a live standings table to the right.
  `deriveGroupStandings(g, picks)` tallies W=3/D=1 from your picks (real results used
  for already-played games via `groupOutcome()`; tiebreak pts→GD→GF→prob prior since
  1X2 picks carry no score) and returns null until all 6 are decided. A CTA bar tracks
  `n/12` tables; `gotoFirstMissing()` scrolls to + flags the next undecided group.
- **Knockouts** (`predFilter==='ko'`) gate until all 12 tables are set. The filter is
  just two chips — **Group stage** / **Knockout bracket** — and the KO stage renders the
  **same visual bracket tree as the Bracket tab** (R32→Final columns + SVG connectors),
  not a round-by-round list. Both views share `paintBracketInto(ids, cardHTML, winnerOf)`
  (the painter `renderBracket()` was refactored into); the predictor passes
  `predMatchCardHTML(def, ps, key)` (tap a team → `setPredKO`, gold winner / greyed loser,
  footer `+pts`/`✗0` badge) via `renderPredBracket()` — which also injects an
  absolutely-positioned `.pred-publish-cta` just ABOVE the Final card (top computed from
  the measured CTA height so it tucks against the Final). Its Publish button is enabled
  only once both `finals.final` and `finals.thirdPlace` have a winner; otherwise it's
  `.disabled` with a "pick a winner in the Final and 3rd-place game" hint. `predBracketState()` (=
  `predStateFrom(predictor)`) builds a real bracket `state` from the derived standings
  + `ko`/`finals`, and `withState(ps, fn)` temporarily swaps the global `state` so
  `resolveSlot`/`assignThirds`/`getThirdPlaces` seed the matchups from your predicted
  qualifiers. **The matchup teams are seeded but the winner is never pre-picked** —
  cards read "tap a team to advance" until you choose; `setPredKO()` stores
  `{winner,loser}`, `resetPredictorKO()` wipes them all, and `prunePredKO()` cascades —
  re-deciding a group or earlier KO drops any now-impossible downstream pick.
- **Scoring** (`scorePredictor(pd)`): group games grade per real finished match
  (+1 each, `PRED_PTS.group`); knockouts grade by **advancement** vs reality
  (`predictedReached(predStateFrom(pd))` ∩ `buildAnswerKey().reached`) with `PRED_PTS`
  escalation (R32 +2 · R16 +4 · QF +8 · SF +16 · 3rd +8 · Final +32) — same model as
  the bracket's Phase 2, so predicted matchups that never happen still score on who you
  sent through. `predPickable()` locks group picks at kickoff.

Published predictor entries go through `/api/brackets` with `kind:'predictor'`, the
full `{predictor:true, picks, ko, finals}` encoded in `hash` (champion = your final
winner), sanitized on read by `sanitizePredictorPicks()` + `predStateFrom()`'s
`validTeam` guards.

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

### Ticket analytics (REMOVED from UI — dead code)

> The Tickets Analysis tab was removed. Everything below still describes the code, which
> remains in `index.html` but is **unreachable** (no nav tab, no `setTab('tickets')`
> branch). Kept for reference / possible revival; safe to delete wholesale if desired.


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
`UPSTASH_REDIS_REST_*`) exist, else `brackets.local.json` (gitignored). Entries carry
`kind: 'bracket'|'predictor'` and dedupe by **(name, kind)** case-insensitively —
one name can hold both a bracket and predictor picks. Capped at 100. POST
`{"name": X, "remove": true}` unpublishes (with `kind` removes just that kind; legacy
removes without `kind` wipe the whole name) — no auth, friend-group toy. Prod KV is
confirmed working; if "publish seems broken" it's almost always client-side.

UI: split into **📝 My brackets** (editable — `myBracketsHTML()` cards open via
`switchToBracket()`, with EDITING/PUBLISHED badges and delete) and a **read-only
leaderboard** with a game switcher (`gbGame`: `predictor`/`brackets`). **`predictor` is
the default/home board, labelled "🎯 Knockout bracket"; `brackets` is "🏆 Group stage
brackets".** `splitEntries()` separates published entries by `kind` (falling back to payload
sniffing for old entries). `bracketLeaderboardHTML()` ranks by the active `gbTab`
(`total`/`group`/`ko`); rows whose name matches one of your local brackets get a
"YOU — tap to edit" badge and route to `switchToBracket()` instead of the read-only
viewer. `predictorLeaderboardHTML()` ranks predictor entries by
`scorePredictor()` (group +1 per real game + KO advancement). **Within the Knockout-bracket
board it splits live vs archived by `payload.knockout`:** new publishes carry
`knockout:true` inside the hash (`submitPublish`), so they rank on the live board; entries
without it (everything published before the pivot) collapse into a retrievable
`<details class="gb-archive">` ("Archived Match Predictor picks"). This archives the
*old* picks while keeping the category itself the headline game. Scoring is untouched.

- **Publish** (`openPublishModal()` → `submitPublish()`): an **inline modal**, not
  `prompt()` — `prompt()` is silently suppressed in many mobile/in-app browsers, which
  was the old "publish doesn't work for friends" bug. Partial (group-stage-only)
  brackets publish fine (empty `champion`). Publishing also banks a local copy.
- **New Bracket** (`newBracket()`, the old Reset): banks the current bracket into
  `wcMyBrackets` (via `persistActive()`), then starts a `freshState()` — so you can keep
  several entries (one per pool). `bracketHasPicks()` gates both publish and banking.

## Vercel environment notes

- The KV store `upstash-kv-amethyst-anchor` is connected to this project (env vars are
  integration-managed, type *sensitive* — values can never be read back via CLI/API).
  It's shared with penalty-shootout and finance-tracker; keys are namespaced by prefix.
  **Publish to `/api/brackets` is confirmed working in prod** — verified via POST/GET.
- No `ANTHROPIC_API_KEY` is set, which no longer matters (AI mode is gone). The two
  Claude routes just 503 if ever hit; nothing in the UI hits them.

## Preview caveat

The Claude Code preview runner cannot read this Desktop folder (macOS TCC), so
`.claude/launch.json` runs a scratch copy from `/tmp/wc-bracket-preview` (Flask
`server.py`, so /api/brackets + /api/prices work). Re-copy `index.html` (and
`server.py`/`api/` if changed) there after edits when previewing. For real local dev,
run `python3 server.py` directly.
