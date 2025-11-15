# Performance Meter (Windows)

Edge-device activity meter with rules-based privacy, role profiles, local metrics aggregation, and optional Gemini scoring.

## Features
- Rules-driven privacy: exclude specific apps from keystroke/mouse metrics.
- Tracks per-app active time, words typed, backspaces, and cursor movement.
- Role profiles: engineer, hr, coder (editable in `profiles.yaml`).
- Local JSONL logs under `data/`.
- Optional Gemini API scoring (off by default).

## Quick start
1. Install Python 3.10+ (Windows).
2. Create venv and install deps:
   ```bash
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. Configure rules and profiles:
   - Edit `rules.txt` to list personal apps to exclude from input metrics.
   - Edit `profiles.yaml` to adjust role expectations.
4. (Optional) Create `.env` for Gemini (2.5 Flash):
   ```
   GEMINI_API_KEY=your_key
   GEMINI_MODEL=gemini-2.5-flash
   ```
5. Run:
   ```bash
   python -m perfmeter --role coder --rules rules.txt
   ```

## Rules file format
```
# lines starting with # are comments
[exclude_apps]
# exe names, case-insensitive
chrome.exe
spotify.exe
whatsapp.exe

[include_apps]
# optional; if provided, only these apps are tracked for metrics/time
# not set by default
```

## Privacy
- No content captured (no key text, only counts and word boundaries).
- When an app is excluded, keystroke/mouse metrics are paused. Time-in-app is still tracked.
- Data is stored locally as JSONL. You own it.

## Notes
- Requires Windows with desktop access.
- Some features may require normal user privileges; admin not required.
- If you use corporate lockdowns, hooks may be blocked.

### Gemini API
- Default model: `gemini-2.5-flash`.
- REST endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
- Auth: `x-goog-api-key` header is used by the client.
