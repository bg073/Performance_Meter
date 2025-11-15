import json
import os
from pathlib import Path
from typing import Dict, Any

from flask import Flask, jsonify, render_template_string, request
from werkzeug.serving import make_server
import threading
import time

from .gemini_client import GeminiClient

APP = Flask(__name__)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv('PERFMETER_DATA_DIR', ROOT / 'data'))

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Performance Meter Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-6xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-4">Performance Meter</h1>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
      <div class="bg-white shadow rounded p-4">
        <div class="text-sm text-slate-500">Total Time</div>
        <div id="total_time" class="text-2xl font-semibold">--</div>
      </div>
      <div class="bg-white shadow rounded p-4">
        <div class="text-sm text-slate-500">WPM</div>
        <div id="wpm" class="text-2xl font-semibold">--</div>
      </div>
      <div class="bg-white shadow rounded p-4">
        <div class="text-sm text-slate-500">Score</div>
        <div id="score" class="text-2xl font-semibold">--</div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
      <div class="bg-white shadow rounded p-4">
        <div class="flex items-center justify-between mb-2">
          <h2 class="font-semibold">Typing & Input</h2>
          <div class="text-xs text-slate-500" id="keys_meta"></div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="text-sm text-slate-500">Words</div>
            <div id="typing_words" class="text-xl font-semibold">--</div>
          </div>
          <div>
            <div class="text-sm text-slate-500">Backspaces</div>
            <div id="backspaces" class="text-xl font-semibold">--</div>
          </div>
          <div>
            <div class="text-sm text-slate-500">Keys</div>
            <div id="keys_pressed" class="text-xl font-semibold">--</div>
          </div>
          <div>
            <div class="text-sm text-slate-500">Mouse Distance (px)</div>
            <div id="mouse_distance" class="text-xl font-semibold">--</div>
          </div>
        </div>
      </div>

      <div class="bg-white shadow rounded p-4">
        <h2 class="font-semibold mb-2">Gemini Evaluation</h2>
        <div id="grade" class="text-lg font-semibold mb-1">--</div>
        <div id="notes" class="text-sm text-slate-700 mb-2">--</div>
        <pre id="rationale" class="text-xs bg-slate-50 p-2 rounded overflow-auto max-h-40">--</pre>
      </div>
    </div>

    <div class="bg-white shadow rounded p-4 mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="font-semibold">Time by App</h2>
        <div class="text-xs text-slate-500" id="apps_meta"></div>
      </div>
      <canvas id="apps_chart" height="120"></canvas>
      <div class="mt-4 overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="text-left text-slate-500">
            <tr>
              <th class="py-2 pr-4">Application</th>
              <th class="py-2">Time (sec)</th>
            </tr>
          </thead>
          <tbody id="apps_table"></tbody>
        </table>
      </div>
    </div>

    <div class="bg-white shadow rounded p-4 mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="font-semibold">Stress Analysis (last <span id="stress_days">7</span> days)</h2>
        <button id="stress_btn" class="text-sm px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">Re-analyze</button>
      </div>
      <div id="stress_status" class="text-sm text-slate-500 mb-2">Waiting...</div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <div class="text-sm text-slate-500">Level</div>
          <div id="stress_level" class="text-xl font-semibold">--</div>
        </div>
        <div>
          <div class="text-sm text-slate-500">Score (0-100)</div>
          <div id="stress_score" class="text-xl font-semibold">--</div>
        </div>
        <div>
          <div class="text-sm text-slate-500">Confidence</div>
          <div id="stress_conf" class="text-xl font-semibold">--</div>
        </div>
      </div>
      <div class="mt-3">
        <div class="text-sm text-slate-500">Signals</div>
        <ul id="stress_signals" class="list-disc list-inside text-sm"></ul>
      </div>
      <pre id="stress_notes" class="text-xs bg-slate-50 p-2 rounded overflow-auto max-h-40 mt-3">--</pre>
    </div>

    <div class="text-xs text-slate-500">Auto-refreshes every 5s. Data dir: {{ data_dir }}</div>
  </div>

<script>
let chart;
function secsToHMS(sec){
  const s = Math.floor(sec % 60);
  const m = Math.floor((sec / 60) % 60);
  const h = Math.floor(sec / 3600);
  const pad = n => n.toString().padStart(2,'0');
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}
async function loadData(){
  try{
    const res = await fetch('/api/summary');
    const data = await res.json();
    const sum = data.summary || {};
    const gem = (data.gemini && data.gemini.ok && data.gemini.data) ? data.gemini.data : {};

    document.getElementById('total_time').textContent = secsToHMS(sum.total_time_sec||0);
    document.getElementById('wpm').textContent = (sum.wpm||0).toFixed(1);
    document.getElementById('typing_words').textContent = sum.typing_words||0;
    document.getElementById('backspaces').textContent = sum.backspaces||0;
    document.getElementById('keys_pressed').textContent = sum.keys_pressed||0;
    document.getElementById('mouse_distance').textContent = Math.round(sum.mouse_distance||0);
    document.getElementById('keys_meta').textContent = `Switches: ${sum.app_switches||0}`;

    if(Object.keys(gem).length === 0){
      document.getElementById('score').textContent = '--';
      document.getElementById('grade').textContent = 'Grade: (waiting for AI evaluation...)';
      document.getElementById('notes').textContent = 'Awaiting AI evaluation...';
      document.getElementById('rationale').textContent = '';
    } else {
      document.getElementById('score').textContent = (gem.score!=null)? gem.score : '--';
      document.getElementById('grade').textContent = gem.grade? `Grade: ${gem.grade}`: 'Grade: --';
      document.getElementById('notes').textContent = gem.notes|| '--';
      document.getElementById('rationale').textContent = gem.rationale || '--';
    }

    const tba = sum.time_by_app_sec || {};
    const labels = Object.keys(tba);
    const values = labels.map(k => tba[k]);
    document.getElementById('apps_meta').textContent = `${labels.length} apps`;

    const rows = labels
      .map(k => `<tr class='border-t border-slate-100'><td class='py-2 pr-4 font-mono'>${k}</td><td class='py-2'>${(tba[k]).toFixed(1)}</td></tr>`) 
      .join('');
    document.getElementById('apps_table').innerHTML = rows || '<tr><td class="py-2" colspan="2">No data</td></tr>';

    const ctx = document.getElementById('apps_chart').getContext('2d');
    if(chart){ chart.destroy(); }
    chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Seconds',
          data: values,
          backgroundColor: 'rgba(59,130,246,0.6)'
        }]
      },
      options: { responsive: true, plugins: { legend: { display: false } }, scales:{ y:{ beginAtZero:true }}}
    });
  }catch(e){
    console.error(e);
  }
}
loadData();
setInterval(loadData, 5000);

async function analyzeStress(days=7){
  document.getElementById('stress_days').textContent = days;
  document.getElementById('stress_status').textContent = 'Analyzing...';
  document.getElementById('stress_level').textContent = '--';
  document.getElementById('stress_score').textContent = '--';
  document.getElementById('stress_conf').textContent = '--';
  document.getElementById('stress_signals').innerHTML = '';
  document.getElementById('stress_notes').textContent = '';
  try{
    const res = await fetch(`/api/stress?days=${days}`);
    const data = await res.json();
    if(data && data.ok){
      const s = data.data || {};
      document.getElementById('stress_status').textContent = 'Done';
      document.getElementById('stress_level').textContent = s.level || '--';
      document.getElementById('stress_score').textContent = (s.score!=null)? s.score : '--';
      document.getElementById('stress_conf').textContent = (s.confidence!=null)? s.confidence : '--';
      const sigs = Array.isArray(s.signals)? s.signals: [];
      document.getElementById('stress_signals').innerHTML = sigs.map(x=>`<li>${x}</li>`).join('');
      document.getElementById('stress_notes').textContent = s.notes || '';
    } else {
      document.getElementById('stress_status').textContent = data.error || 'Failed';
    }
  }catch(e){
    document.getElementById('stress_status').textContent = 'Failed';
  }
}

// auto-run on load
analyzeStress(7);
document.getElementById('stress_btn').addEventListener('click', ()=> analyzeStress(7));
</script>
</body>
</html>
"""


def summarize(sessions: list[Dict[str, Any]]) -> Dict[str, Any]:
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


def load_sessions_today():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    date = __import__('time').strftime('%Y%m%d')
    f = DATA_DIR / f'metrics-{date}.jsonl'
    sessions = []
    if f.exists():
        with f.open('r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    sessions.append(json.loads(line))
                except Exception:
                    continue
    return sessions

def load_current_session_summary():
    f = DATA_DIR / 'current-session.json'
    if not f.exists():
        return None
    try:
        with f.open('r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None

def load_sessions_days(days: int = 7):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    now = time.time()
    for i in range(days):
        t = now - i * 86400
        date = time.strftime('%Y%m%d', time.localtime(t))
        f = DATA_DIR / f'metrics-{date}.jsonl'
        if f.exists():
            with f.open('r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        sessions.append(json.loads(line))
                    except Exception:
                        continue
    return sessions


def load_latest_gemini():
    f = DATA_DIR / 'gemini-summaries.jsonl'
    if not f.exists():
        return None
    last = None
    with f.open('r', encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except Exception:
        return None


@APP.get('/')
def index():
    return render_template_string(INDEX_HTML, data_dir=str(DATA_DIR))


@APP.get('/api/summary')
def api_summary():
    # If a current-session.json exists, prefer it to avoid mixing with earlier sessions
    cur = load_current_session_summary()
    if isinstance(cur, dict) and cur.get('summary'):
        summary = cur.get('summary')
    else:
        sessions = load_sessions_today()
        summary = summarize(sessions)
    latest = load_latest_gemini()
    gem = latest.get('gemini') if isinstance(latest, dict) else None
    return jsonify({'summary': summary, 'gemini': gem})


@APP.get('/api/stress')
def api_stress():
    try:
        days = int(request.args.get('days', '7'))
    except Exception:
        days = 7
    sessions = load_sessions_days(days)
    # build multi-day summary features
    daily: Dict[str, Any] = {}
    by_app: Dict[str, float] = {}
    total = {'total_time_sec': 0.0, 'typing_words': 0, 'backspaces': 0, 'keys_pressed': 0, 'mouse_distance': 0.0, 'app_switches': 0}
    last_title = None
    for s in sessions:
        ts = float(s.get('start_ts', 0))
        dstr = time.strftime('%Y-%m-%d', time.localtime(ts)) if ts else 'unknown'
        d = float(s.get('duration_sec', 0.0))
        total['total_time_sec'] += d
        total['typing_words'] += int(s.get('words_typed', 0))
        total['backspaces'] += int(s.get('backspaces', 0))
        total['keys_pressed'] += int(s.get('keys_pressed', 0))
        total['mouse_distance'] += float(s.get('mouse_distance', 0.0))
        exe = str(s.get('exe') or '').lower()
        by_app[exe] = by_app.get(exe, 0.0) + d
        # daily aggregates
        dd = daily.setdefault(dstr, {'time': 0.0, 'words': 0, 'backspaces': 0, 'keys': 0, 'mouse': 0.0, 'switches': 0})
        dd['time'] += d
        dd['words'] += int(s.get('words_typed', 0))
        dd['backspaces'] += int(s.get('backspaces', 0))
        dd['keys'] += int(s.get('keys_pressed', 0))
        dd['mouse'] += float(s.get('mouse_distance', 0.0))
        # naive switch count by session boundaries
        dd['switches'] += 1

    # features for Gemini
    features = {
        'window_days': days,
        'totals': total,
        'by_app_top': sorted([{ 'exe': k, 'time_sec': v } for k,v in by_app.items()], key=lambda x: -x['time_sec'])[:10],
        'per_day': [ {'date': k, **v, 'wpm': (v['words']/ (v['time']/60.0) if v['time']>0 else 0.0)} for k,v in sorted(daily.items()) ],
    }

    # call Gemini
    client = GeminiClient()
    if not client.enabled():
        return jsonify({'ok': False, 'error': 'Gemini not configured'}), 200

    prompt = (
        "You are a workplace well-being analyst. Analyze historical productivity metrics to estimate employee stress level. "
        "Return STRICT JSON only with: {\"level\": one of [low, medium, high], \"score\": 0-100 (higher is more stress), \"confidence\": 0-1, \"signals\": string[], \"notes\": string}. "
        "Consider: sustained high input without output (backspace rate), extreme app switching, high mouse distance with low words, very long or very short total time, and day-to-day volatility. "
        f"MetricsWindow: {json.dumps(features, ensure_ascii=False)}\n"
    )

    url = f"/api/stress"
    # reuse score_metrics transport but different prompt via same endpoint shape
    # build a temporary request using the same generateContent call
    try:
        # mimic client.score_metrics but with custom prompt
        endpoint = os.getenv('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')
        model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        api_key = os.getenv('GEMINI_API_KEY')
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        body = {'contents': [{'parts': [{'text': prompt}]}]}
        import requests
        r = requests.post(f"{endpoint}/{model}:generateContent", headers=headers, json=body, timeout=20)
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
        # persist
        out = {
            'ts': time.time(),
            'window_days': days,
            'features': features,
            'stress': data,
        }
        fpath = DATA_DIR / 'stress-summaries.jsonl'
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with fpath.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(out) + '\n')
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200


if __name__ == '__main__':
    APP.run(host='127.0.0.1', port=int(os.getenv('PERFMETER_PORT', '8765')), debug=False)


def start_in_thread(host: str = '127.0.0.1', port: int = 8765):
    server = make_server(host, port, APP)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
