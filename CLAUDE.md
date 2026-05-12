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
- Share bracket via URL hash (fully client-side)

## Architecture
- `index.html` — single-page app, all JS inline
- `server.py` — Flask dev server serving index.html + proxying Claude API calls
- `api/simulate.py` — Vercel serverless function for /api/simulate
- `api/final.py` — Vercel serverless function for /api/final
