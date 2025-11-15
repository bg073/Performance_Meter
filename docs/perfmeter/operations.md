# Operations

## Run
- .\.venv\Scripts\python .\run.py --role coder --rules rules.txt
- Ctrl+C once → open dashboard; Ctrl+C again → exit.

## Troubleshooting
- 403 from Gemini: ensure AI Studio key, header x-goog-api-key, model gemini-2.5-flash.
- Time looks too large: dashboard prefers current-session.json; ensure file writes.
- Hooks blocked: corp policy; run as standard user; admin not required.

## Logs
- JSONL in data/ folder. Inspect with any JSONL viewer; tail with PowerShell Get-Content -Wait.
