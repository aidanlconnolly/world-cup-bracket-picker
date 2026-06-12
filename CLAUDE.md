# World Cup Bracket Picker

2026 FIFA World Cup interactive bracket simulator.

## Running locally
```bash
pip install -r requirements.txt
ANTHROPIC_API_KEY=your_key python server.py
```
Open http://localhost:3000

## Features
- 48 teams, 12 groups, full knockout bracket through Final + 3rd place game
- AI mode: Claude (claude-sonnet-4-6) picks winners with probability and 2-sentence reasoning
- Pick mode: click teams manually to advance them
- Share bracket via URL hash (fully client-side); bracket also persists in localStorage.
  Hash states from share links are untrusted → run through `sanitizeBracketState()`
  (validates team names against `TEAMS`, strips reasoning/awards) unless the hash matches
  our own localStorage copy
- **📡 Sync Real**: pulls actual tournament results into the bracket — completed groups
  become final standings (`real:true`), partial groups show a live table (`live:true`,
  doesn't resolve the bracket), finished knockout games are matched by team pair and
  show the real score in the winner badge. Once all groups are done and ESPN's R32
  fixtures name real teams, FIFA's actual third-place allocation is mirrored via
  `state.thirdAssign` (checked first in `assignThirds()`)
- **Dynamic ratings**: `effectiveProb()` = static prior + `dynAdj` (ESPN form strings
  W/L ±1.6 each + real results ±4/match, capped ±18), recomputed each fetch; shown as
  ▲/▼ deltas next to probs and used by all simulations
- **🌍 Publish / Explore tab**: publish a finished bracket under a name (POST
  /api/brackets), browse everyone's on the Explore tab, click to view read-only
  (`viewing` flag suppresses saveState; `exitViewing()` restores backup). One bracket
  per name (newest wins), capped at 100
- **Matches tab (live feed)**: real results, live scores, and fixtures for the actual
  tournament, fetched client-side from ESPN's public scoreboard API
  (`site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD-YYYYMMDD`,
  CORS-open, no key). Full schedule fetched once per session; a ±1-day window is polled
  every 60 s while the tab is open. Goal scorers come from `competitions[0].details`
  (`scoringPlay` entries). ESPN team names map to local `TEAMS` keys via `ESPN_NAME_MAP`
  (`United States`→`USA`, `Bosnia-Herzegovina`→`Bosnia & Herzegovina`); unresolved knockout
  slots ("Group A Winner") render as TBD rows. Cached in localStorage (`wcLiveCache`) for
  instant paint.

## Architecture
- `index.html` — single-page app, all JS inline; three tabs (`#view-bracket`, `#view-live`, `#view-explore`) toggled by `setTab()`
- `server.py` — Flask dev server serving index.html + proxying Claude API calls; Anthropic
  client is lazy (boots without `ANTHROPIC_API_KEY`, AI endpoints then 503). Local
  /api/brackets stores to `brackets.local.json` (gitignored)
- `api/simulate.py` — Vercel serverless function for /api/simulate
- `api/final.py` — Vercel serverless function for /api/final
- `api/brackets.py` — Vercel serverless function for /api/brackets (shared Explore
  brackets). Stores one JSON array under key `wc2026:brackets` in Vercel KV via its REST
  API (stdlib urllib, no deps). **Needs `KV_REST_API_URL` + `KV_REST_API_TOKEN`** (or
  `UPSTASH_REDIS_REST_*`) env vars on the Vercel project — connect a KV/Upstash store in
  the dashboard, same as Penalty shootout. Without them it returns 503 and the Explore
  tab shows a friendly error.

## Preview caveat
The Claude Code preview runner cannot read this Desktop folder (macOS TCC), so
`.claude/launch.json` runs a scratch copy from `/tmp/wc-bracket-preview` (Flask
`server.py`, so /api/brackets works; no ANTHROPIC_API_KEY → AI endpoints 503).
Re-copy `index.html` (and `server.py`/`api/` if changed) there after edits when
previewing. For real local dev, run `python3 server.py` directly.
