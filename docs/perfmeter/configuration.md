# Configuration

## .env
- GEMINI_API_KEY=...
- GEMINI_MODEL=gemini-2.5-flash
- GEMINI_ENDPOINT=https://generativelanguage.googleapis.com/v1beta/models
- PERFMETER_PORT=8765 (optional)

## rules.txt
```
[exclude_apps]
chrome.exe
spotify.exe

# [include_apps]
# vscode.exe
```

## profiles.yaml
```yaml
roles:
  coder:
    metrics_weights:
      time_in_focus: 0.4
      typing_words: 0.35
      backspace_rate: 0.1
      app_switches: 0.05
      mouse_distance: 0.1
```
