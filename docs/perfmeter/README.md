# Performance Meter (Windows)

Edge-device productivity metrics with rules-based privacy, role-aware scoring (Gemini 2.5 Flash), and a local dashboard.

- Code: src/perfmeter/
- UI: http://127.0.0.1:8765/
- Data: data/

## Key Features
- Rules file controls privacy for keyboard/mouse metrics per app.
- Tracks time-in-app, words, backspaces, keys, mouse distance, app switches.
- Role weights loaded from profiles.yaml.
- On Ctrl+C: final summary → opens dashboard → async Gemini evaluation.
- Stress analysis over past N days (dashboard > Stress Analysis).

## Getting Started
- python -m venv .venv
- .\.venv\Scripts\pip install -r requirements.txt
- Configure .env (GEMINI_API_KEY + gemini-2.5-flash)
- Run meter: .\.venv\Scripts\python .\run.py --role coder --rules rules.txt

## Docs
- architecture.md
- flows.md
- wireframes.md
- configuration.md
- api.md
- privacy.md
- operations.md
- roadmap.md
