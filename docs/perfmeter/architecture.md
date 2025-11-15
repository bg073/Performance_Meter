# Architecture

```mermaid
flowchart TD
  A[Active Window Poller (win32)] --> B[Session Manager]
  K[Keyboard Hook (pynput)] --> B
  M[Mouse Hook (pynput)] --> B
  R[Rules Engine] --> B
  B --> C[Aggregator -> JSONL]
  B --> S[Current Session Summary]
  S --> D[Flask Dashboard]
  C --> D
  D -->|/api/stress| G{Gemini 2.5 Flash}
  E[Profiles (YAML)] --> H[Gemini Client]
  H --> G
  S --> H
```

- Active Window Poller: win32gui + win32process + psutil to resolve exe + title.
- Rules Engine: include/exclude apps to pause input metrics; time-in-app always tracked.
- Session Manager: rotates on exe+title change; accumulates InputStats.
- Aggregator: appends sessions to data/metrics-YYYYMMDD.jsonl.
- Current Session Summary: data/current-session.json preferred by dashboard to avoid day-mix.
- Dashboard: Tailwind + Chart.js; shows metrics, app times, Gemini eval, stress.
- Gemini Client: strict JSON prompt; header x-goog-api-key; model gemini-2.5-flash.
