# API Surface

## CLI
- run.py / python -m perfmeter
  - --role <role>
  - --rules <rules.txt>
  - --profiles <profiles.yaml>
  - --data-dir <dir>
  - --flush-sec <int>
  - --gemini-interval-sec <int> (0 = only on exit)

## Dashboard HTTP
- GET / → UI
- GET /api/summary → { summary, gemini }
- GET /api/stress?days=N → stress JSON and persists to data/stress-summaries.jsonl

## Data Files
- data/metrics-YYYYMMDD.jsonl (per-session rows)
- data/current-session.json (finalized summary for UI)
- data/gemini-summaries.jsonl (evaluation appends)
- data/stress-summaries.jsonl
