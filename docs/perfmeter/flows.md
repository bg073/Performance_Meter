# Flows

## Run and Summarize
```mermaid
sequenceDiagram
  participant User
  participant Meter
  participant Dashboard
  participant Gemini
  User->>Meter: run.py --role coder
  Meter->>Meter: poll fg window, hooks, rules
  Meter->>Meter: write JSONL (periodic)
  User->>Meter: Ctrl+C
  Meter->>Meter: finalize sessions → current-session.json
  Meter->>Dashboard: start server + open browser
  Meter->>Gemini: async evaluation (summary + weights)
  Gemini-->>Meter: strict JSON score
  Meter->>Dashboard: write gemini-summaries.jsonl
  Dashboard->>User: auto-refresh shows evaluation
```

## Stress Analysis (UI)
- Dashboard loads last N days JSONL.
- Builds features (per-day WPM, totals, top apps).
- Calls Gemini with compact prompt.
- Displays level/score/confidence/signals.
