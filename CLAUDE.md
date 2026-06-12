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

- `index.html` — the entire app; three views (`#view-bracket`, `#view-live`,
  `#view-explore`) toggled by `setTab()`
- `server.py` — Flask app serving index.html + all `/api` routes. **Vercel deploys this
  Flask app via its Python/Flask preset and routes `/api/*` through it** (confirmed via
  prod tracebacks) — so server-side changes must land in `server.py`, not just `api/`
- `api/simulate.py` / `api/final.py` / `api/brackets.py` — standalone Vercel Python
  handlers kept in parity with the Flask routes in case routing ever switches to
  per-function mode; they are NOT what answers in prod today

### Bracket state model (`state` in index.html)

`{ mode: 'ai'|'pick', groups, picks, ko, finals: {final, thirdPlace}, awards,
selectedThirds, thirdAssign }`. Group entries are `{done, standings, real?, live?,
played?}` — `live:true` means a partial real-results table that renders but does NOT
resolve the bracket (only `done:true` does). Match results are
`{winner, loser, prob, reasoning, real?, score?}`.

Bracket slots resolve through a small grammar in `resolveSlot()`: `'1A'`/`'2B'`
(group position), `'3rd:A/B/C/D/F'` (third-place slot, eligibility in `THIRD_SLOTS`),
`'W:r32-5'`/`'L:sf-1'` (winner/loser of match id). `assignThirds()` checks
`state.thirdAssign` (real FIFA allocation captured from ESPN's actual R32 fixtures by
Sync Real) before falling back to eligibility-order assignment. Bracket cards are
absolutely positioned via `MATCH_ROW` row indices; SVG connectors are drawn per render.

### Share links, persistence, and the sanitizer coupling

- Full state persists to localStorage; the URL hash carries a **slimmed** copy from
  `stripStateForShare()` (drops AI reasoning), encoded UTF-8-safe by
  `encodeHash()`/`decodeHash()` (plain `btoa` breaks on Unicode in reasoning text).
- All externally-sourced states (share-link hashes, Explore entries) pass through
  `sanitizeBracketState()`, which whitelists team names against `TEAMS` and nulls
  reasoning/awards — these reach `innerHTML`, so this is the XSS barrier.
- `loadState()` detects "own" hashes by re-encoding localStorage through
  `stripStateForShare()` and comparing; own state loads at full fidelity.
- **Gotcha: a new `state` field must be added to BOTH `stripStateForShare()` and
  `sanitizeBracketState()`** or it silently disappears from share links and Explore views.

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

### Shared brackets (Explore)

One JSON array under KV key `wc2026:brackets`. `server.py` uses Vercel KV via REST
(stdlib urllib) when `KV_REST_API_URL`+`KV_REST_API_TOKEN` (or `UPSTASH_REDIS_REST_*`)
exist, else `brackets.local.json` (gitignored). One bracket per name (newest wins,
case-insensitive), capped at 100. POST `{"name": X, "remove": true}` unpublishes —
no auth, friend-group toy.

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
