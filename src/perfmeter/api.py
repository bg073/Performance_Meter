import os
import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

from flask import Flask, jsonify, request

from .tracker import ActiveAppTracker
from .aggregator import Aggregator
from .gemini_client import GeminiClient

APP = Flask(__name__)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('PERFMETER_DATA_DIR', ROOT / 'data'))

# --- helpers ---

def _summarize(sessions: list[Dict[str, Any]]) -> Dict[str, Any]:
    total_time = 0.0
    words = 0
    backspaces = 0
    keys = 0
    mouse = 0.0
    apps: Dict[str, float] = {}
    for s in sessions:
        d = float(s.get('duration_sec', 0.0))
        total_time += d
        words += int(s.get('words_typed', 0))
        backspaces += int(s.get('backspaces', 0))
        keys += int(s.get('keys_pressed', 0))
        mouse += float(s.get('mouse_distance', 0.0))
        exe = str(s.get('exe') or '').lower()
        apps[exe] = apps.get(exe, 0.0) + d
    switches = max(0, len(sessions) - 1)
    wpm = (words / (total_time / 60.0)) if total_time > 0 else 0.0
    return {
        'total_time_sec': total_time,
        'typing_words': words,
        'wpm': wpm,
        'backspaces': backspaces,
        'keys_pressed': keys,
        'mouse_distance': mouse,
        'app_switches': switches,
        'time_by_app_sec': apps,
    }

def _load_sessions_file(f: Path) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    if f.exists():
        with f.open('r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    return items

def _load_sessions_today() -> list[Dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    date = time.strftime('%Y%m%d')
    f = DATA_DIR / f'metrics-{date}.jsonl'
    return _load_sessions_file(f)

# --- capture manager ---

class CaptureManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.tracker: ActiveAppTracker | None = None
        self.agg: Aggregator | None = None
        self.rules_fn = None
        self.running = False

    def start(self, role: str = 'coder', rules_path: str = 'rules.txt', profiles: str = 'profiles.yaml', data_dir: str = 'data', flush_sec: int = 60):
        from .rules import load_rules
        data_dir_path = Path(data_dir)
        rules = load_rules(Path(rules_path))
        tracker = ActiveAppTracker(allow_input_metrics_fn=rules.is_app_metrics_allowed)
        tracker.start()
        agg = Aggregator(Path(data_dir_path), flush_interval_sec=flush_sec)
        with self.lock:
            self.tracker = tracker
            self.agg = agg
            self.running = True
        return True

    def stop(self) -> Dict[str, Any]:
        with self.lock:
            if not self.running:
                return {'ok': False, 'error': 'not_running'}
            tracker = self.tracker
            agg = self.agg
        try:
            if tracker:
                tracker.stop()
                sessions = [s.to_dict() for s in tracker.sessions_flush()]
            else:
                sessions = []
            if agg:
                if sessions:
                    agg.add_sessions(sessions)
                agg.stop()
            summary = _summarize(_load_sessions_today())
        finally:
            with self.lock:
                self.tracker = None
                self.agg = None
                self.running = False
        return {'ok': True, 'summary': summary}

    def tick_flush(self):
        with self.lock:
            tracker = self.tracker
            agg = self.agg
        if not tracker or not agg:
            return
        sessions = [s.to_dict() for s in tracker.sessions_flush()]
        if sessions:
            agg.add_sessions(sessions)

    def status(self) -> Dict[str, Any]:
        with self.lock:
            return {'running': self.running}

MANAGER = CaptureManager()

# --- routes ---

@APP.get('/status')
def status():
    return jsonify(MANAGER.status())

@APP.post('/capture/start')
def capture_start():
    payload = request.get_json(silent=True) or {}
    role = str(payload.get('role', 'coder'))
    rules = str(payload.get('rules', 'rules.txt'))
    profiles = str(payload.get('profiles', 'profiles.yaml'))
    data_dir = str(payload.get('data_dir', str(DATA_DIR)))
    flush_sec = int(payload.get('flush_sec', 60))
    if MANAGER.status().get('running'):
        return jsonify({'ok': False, 'error': 'already_running'}), 400
    MANAGER.start(role=role, rules_path=rules, profiles=profiles, data_dir=data_dir, flush_sec=flush_sec)
    return jsonify({'ok': True})

@APP.post('/capture/stop')
def capture_stop():
    res = MANAGER.stop()
    return jsonify(res)

@APP.post('/capture/flush')
def capture_flush():
    MANAGER.tick_flush()
    return jsonify({'ok': True})

@APP.get('/summary')
def get_summary():
    # flush any pending in-memory sessions before reading file view
    MANAGER.tick_flush()
    sessions = _load_sessions_today()
    return jsonify({'summary': _summarize(sessions)})

@APP.get('/sessions/today')
def sessions_today():
    MANAGER.tick_flush()
    items = _load_sessions_today()
    # Optional paging
    try:
        n = int(request.args.get('limit', '200'))
    except Exception:
        n = 200
    if n > 0:
        items = items[-n:]
    return jsonify({'items': items, 'count': len(items)})

@APP.get('/stress')
def stress():
    # simple wrapper to call Gemini using dashboard-like prompt
    try:
        days = int(request.args.get('days', '7'))
    except Exception:
        days = 7
    # build features from current file set for last N days
    sessions: list[Dict[str, Any]] = []
    now = time.time()
    for i in range(days):
        d = time.strftime('%Y%m%d', time.localtime(now - i*86400))
        f = DATA_DIR / f'metrics-{d}.jsonl'
        sessions.extend(_load_sessions_file(f))
    # aggregate minimal features
    by_app: Dict[str, float] = {}
    daily: Dict[str, Dict[str, Any]] = {}
    totals = {'total_time_sec': 0.0, 'typing_words': 0, 'backspaces': 0, 'keys_pressed': 0, 'mouse_distance': 0.0}
    for s in sessions:
        d = float(s.get('duration_sec', 0.0))
        totals['total_time_sec'] += d
        totals['typing_words'] += int(s.get('words_typed', 0))
        totals['backspaces'] += int(s.get('backspaces', 0))
        totals['keys_pressed'] += int(s.get('keys_pressed', 0))
        totals['mouse_distance'] += float(s.get('mouse_distance', 0.0))
        exe = str(s.get('exe') or '').lower()
        by_app[exe] = by_app.get(exe, 0.0) + d
        ts = float(s.get('start_ts', 0))
        day = time.strftime('%Y-%m-%d', time.localtime(ts)) if ts else 'unknown'
        dd = daily.setdefault(day, {'time': 0.0, 'words': 0})
        dd['time'] += d
        dd['words'] += int(s.get('words_typed', 0))
    features = {
        'window_days': days,
        'totals': totals,
        'by_app_top': sorted([{ 'exe': k, 'time_sec': v } for k,v in by_app.items()], key=lambda x: -x['time_sec'])[:10],
        'per_day': [ {'date': k, **v, 'wpm': (v['words']/ (v['time']/60.0) if v['time']>0 else 0.0)} for k,v in sorted(daily.items()) ],
    }
    client = GeminiClient()
    if not client.enabled():
        return jsonify({'ok': False, 'error': 'Gemini not configured'}), 200
    # Use same transport as client.score_metrics but with custom prompt
    prompt = (
        "You are a workplace well-being analyst. Analyze historical productivity metrics to estimate employee stress level. "
        "Return STRICT JSON only with: {\"level\": one of [low, medium, high], \"score\": 0-100, \"confidence\": 0-1, \"signals\": string[], \"notes\": string}. "
        f"MetricsWindow: {json.dumps(features, ensure_ascii=False)}\n"
    )
    import requests
    endpoint = os.getenv('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    api_key = os.getenv('GEMINI_API_KEY')
    try:
        r = requests.post(
            f"{endpoint}/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={'contents': [{'parts': [{'text': prompt}]}]},
            timeout=20,
        )
        r.raise_for_status()
        resp = r.json()
        text = resp.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        data = None
        try:
            data = json.loads(text)
        except Exception:
            st = text.find('{'); en = text.rfind('}')
            if st!=-1 and en!=-1 and en>st:
                data = json.loads(text[st:en+1])
        if not isinstance(data, dict):
            return jsonify({'ok': False, 'error': 'Parse failure', 'raw': resp}), 200
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200


# --- simple in-app UI to exercise the API (same-origin, no CORS hassles) ---
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Performance Meter API UI</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style> pre{white-space:pre-wrap} </style>
  <script>
    async function call(method, url, body){
      const opts = { method, headers: { } };
      if(body!==undefined){
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      const res = await fetch(url, opts);
      const txt = await res.text();
      try { return JSON.parse(txt); } catch { return txt; }
    }
    async function onStatus(){ out(await call('GET','/status')); }
    async function onStart(){
      const role = document.getElementById('role').value || 'coder';
      const rules = document.getElementById('rules').value || 'rules.txt';
      const profiles = document.getElementById('profiles').value || 'profiles.yaml';
      const data_dir = document.getElementById('data_dir').value || 'data';
      const flush_sec = parseInt(document.getElementById('flush').value||'60');
      out(await call('POST','/capture/start',{role, rules, profiles, data_dir, flush_sec}));
    }
    async function onFlush(){ out(await call('POST','/capture/flush')); }
    async function onStop(){ out(await call('POST','/capture/stop')); }
    async function onSummary(){ out(await call('GET','/summary')); }
    async function onSessions(){
      const limit = parseInt(document.getElementById('limit').value||'200');
      out(await call('GET',`/sessions/today?limit=${limit}`));
    }
    async function onStress(){
      const days = parseInt(document.getElementById('days').value||'7');
      out(await call('GET',`/stress?days=${days}`));
    }
    function out(v){
      const el = document.getElementById('out');
      el.textContent = (typeof v === 'string') ? v : JSON.stringify(v, null, 2);
    }
  </script>
  </head>
  <body class="bg-slate-50 text-slate-900">
    <div class="max-w-4xl mx-auto p-6">
      <h1 class="text-2xl font-bold mb-4">Performance Meter API UI</h1>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div class="bg-white shadow rounded p-4 space-y-3">
          <div class="grid grid-cols-2 gap-2">
            <label class="text-sm">Role<input id="role" class="mt-1 w-full border rounded px-2 py-1" value="coder"/></label>
            <label class="text-sm">Flush sec<input id="flush" class="mt-1 w-full border rounded px-2 py-1" value="60"/></label>
            <label class="text-sm col-span-2">Rules path<input id="rules" class="mt-1 w-full border rounded px-2 py-1" value="rules.txt"/></label>
            <label class="text-sm col-span-2">Profiles path<input id="profiles" class="mt-1 w-full border rounded px-2 py-1" value="profiles.yaml"/></label>
            <label class="text-sm col-span-2">Data dir<input id="data_dir" class="mt-1 w-full border rounded px-2 py-1" value="data"/></label>
          </div>
          <div class="flex flex-wrap gap-2">
            <button class="px-3 py-1 rounded bg-green-600 text-white" onclick="onStart()">Start</button>
            <button class="px-3 py-1 rounded bg-blue-600 text-white" onclick="onFlush()">Flush</button>
            <button class="px-3 py-1 rounded bg-red-600 text-white" onclick="onStop()">Stop</button>
          </div>
        </div>
        <div class="bg-white shadow rounded p-4 space-y-3">
          <div class="flex gap-2 items-end">
            <button class="px-3 py-1 rounded bg-slate-700 text-white" onclick="onStatus()">Status</button>
            <button class="px-3 py-1 rounded bg-slate-700 text-white" onclick="onSummary()">Summary</button>
          </div>
          <div class="flex gap-2 items-end">
            <label class="text-sm">Limit<input id="limit" class="mt-1 w-24 border rounded px-2 py-1" value="200"/></label>
            <button class="px-3 py-1 rounded bg-slate-700 text-white" onclick="onSessions()">Sessions Today</button>
          </div>
          <div class="flex gap-2 items-end">
            <label class="text-sm">Days<input id="days" class="mt-1 w-24 border rounded px-2 py-1" value="7"/></label>
            <button class="px-3 py-1 rounded bg-purple-700 text-white" onclick="onStress()">Stress (Gemini)</button>
          </div>
        </div>
      </div>
      <div class="bg-white shadow rounded p-4">
        <div class="text-sm text-slate-500 mb-2">Output</div>
        <pre id="out" class="text-xs"></pre>
      </div>
      <div class="text-xs text-slate-500 mt-4">Base URL: same origin. Start this UI via python run_api.py and open <code>/ui</code>.</div>
    </div>
  </body>
</html>
"""

@APP.get('/ui')
def ui_page():
    return INDEX_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}


def run(host: str = '127.0.0.1', port: int = 8766):
    APP.run(host=host, port=port, debug=False)

if __name__ == '__main__':
    run()
