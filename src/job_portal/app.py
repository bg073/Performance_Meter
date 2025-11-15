import os
import re
import sqlite3
import json
import time
from pathlib import Path
from typing import List, Dict, Any

from flask import Flask, request, redirect, url_for, render_template_string, send_from_directory, jsonify
from werkzeug.utils import secure_filename
from PyPDF2 import PdfReader
from docx import Document

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data' / 'job_portal'
UPLOADS = DATA_DIR / 'uploads'
DB_PATH = DATA_DIR / 'job_portal.db'

ALLOWED_EXT = {'.pdf', '.docx', '.txt'}
APP = Flask(__name__)
APP.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
try:
    # Reuse Gemini client from perfmeter package
    from perfmeter.gemini_client import GeminiClient  # type: ignore
except Exception:
    GeminiClient = None  # type: ignore


def ensure_dirs():
    UPLOADS.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def db():
    ensure_dirs()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            questions_json TEXT,
            created_at REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS applicants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            name TEXT,
            email TEXT,
            answers_json TEXT,
            resume_path TEXT,
            resume_text TEXT,
            score REAL DEFAULT 0,
            created_at REAL,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    con.commit()
    con.close()


INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job Portal Admin</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-5xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-4">Job Portal - Admin</h1>
    <a class="inline-block bg-blue-600 text-white px-3 py-2 rounded hover:bg-blue-700" href="{{ url_for('new_job') }}">+ New Job</a>
    <div class="mt-6 bg-white shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-50 text-left text-slate-600 border-b">
          <tr><th class="py-2 px-3">ID</th><th class="py-2 px-3">Title</th><th class="py-2 px-3">Created</th><th class="py-2 px-3">Actions</th></tr>
        </thead>
        <tbody>
        {% for j in jobs %}
          <tr class="border-b hover:bg-slate-50">
            <td class="py-2 px-3">{{ j['id'] }}</td>
            <td class="py-2 px-3">{{ j['title'] }}</td>
            <td class="py-2 px-3">{{ j['created_at']|round(0) }}</td>
            <td class="py-2 px-3">
              <a class="text-blue-700 underline hover:text-blue-800" href="{{ url_for('job_detail', job_id=j['id']) }}">View →</a>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

NEW_JOB_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>New Job</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-3xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-4">Create Job</h1>
    <form method="post" class="space-y-4">
      <div>
        <label class="block text-sm text-slate-600">Title</label>
        <input name="title" class="w-full border rounded px-3 py-2" required />
      </div>
      <div>
        <label class="block text-sm text-slate-600">Description</label>
        <textarea name="description" class="w-full border rounded px-3 py-2" rows="5" placeholder="Responsibilities, requirements, must-have skills..."></textarea>
      </div>
      <div>
        <label class="block text-sm text-slate-600">Questions (one per line)</label>
        <textarea name="questions" class="w-full border rounded px-3 py-2" rows="6" placeholder="Example:\nYears of experience in Python?\nExperience with cloud (AWS/GCP/Azure)?\nKey projects relevant to this role?\n"></textarea>
      </div>
      <button class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Create</button>
    </form>
  </div>
</body>
</html>
"""

JOB_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job {{ job['title'] }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-5xl mx-auto p-6">
    <a class="text-blue-700 underline" href="{{ url_for('index') }}">← Back</a>
    <h1 class="text-2xl font-bold mb-2">{{ job['title'] }}</h1>
    <p class="text-slate-700 mb-4 whitespace-pre-wrap">{{ job['description'] }}</p>

    <div class="mb-6">
      <div class="text-sm text-slate-500">Public application link</div>
      <div class="font-mono bg-white rounded border px-3 py-2">{{ apply_url }}</div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="bg-white shadow rounded p-4">
        <h2 class="font-semibold mb-2">Applications</h2>
        <a class="text-blue-700 underline" href="{{ url_for('candidates', job_id=job['id']) }}">View candidates</a>
      </div>
      <div class="bg-white shadow rounded p-4">
        <h2 class="font-semibold mb-2">Questions</h2>
        <ul class="list-disc list-inside text-sm">
        {% for q in questions %}
          <li>{{ q }}</li>
        {% endfor %}
        </ul>
      </div>
    </div>
  </div>
</body>
</html>
"""

APPLY_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Apply - {{ job['title'] }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-3xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-2">Apply: {{ job['title'] }}</h1>
    <p class="text-slate-700 mb-4">Please fill your details and upload resume.</p>
    <form method="post" enctype="multipart/form-data" class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm text-slate-600">Name</label>
          <input name="name" class="w-full border rounded px-3 py-2" required />
        </div>
        <div>
          <label class="block text-sm text-slate-600">Email</label>
          <input name="email" type="email" class="w-full border rounded px-3 py-2" required />
        </div>
      </div>
      <div>
        <label class="block text-sm text-slate-600">Resume (.pdf, .docx, .txt)</label>
        <input name="resume" type="file" accept=".pdf,.docx,.txt" class="w-full border rounded px-3 py-2 bg-white" required />
      </div>
      <div class="space-y-3">
        {% for i,q in enumerate(questions) %}
        <div>
          <label class="block text-sm text-slate-600">{{ q }}</label>
          <textarea name="q{{ i }}" rows="3" class="w-full border rounded px-3 py-2"></textarea>
        </div>
        {% endfor %}
      </div>
      <button class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">Submit</button>
    </form>
  </div>
</body>
</html>
"""

CANDIDATES_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Candidates - {{ job['title'] }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-6xl mx-auto p-6">
    <a class="text-blue-700 underline" href="{{ url_for('job_detail', job_id=job['id']) }}">← Back</a>
    <h1 class="text-2xl font-bold mb-4">Candidates - {{ job['title'] }}</h1>
    <form class="bg-white shadow-sm ring-1 ring-slate-200 rounded-lg p-4 mb-4" method="get">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
        <input class="border border-slate-300 rounded px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500" name="q" value="{{ q }}" placeholder="Search (name/email/keywords)" />
        <input class="border border-slate-300 rounded px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500" name="skill" value="{{ skill }}" placeholder="Must-have skill keyword" />
        <input class="border border-slate-300 rounded px-3 py-2 bg-white focus:ring-2 focus:ring-blue-500" name="min_words" value="{{ min_words }}" placeholder="Min words (resume+answers)" />
        <button class="bg-blue-600 text-white px-3 py-2 rounded hover:bg-blue-700">Filter</button>
      </div>
    </form>

    <div class="bg-white shadow-sm ring-1 ring-slate-200 rounded-lg p-4 mb-4">
      <form id="propose" class="flex items-center gap-3" onsubmit="event.preventDefault(); runPropose();">
        <div class="text-sm text-slate-600">Target interviews:</div>
        <input id="target" value="5" class="border border-slate-300 rounded px-3 py-2 w-24 bg-white focus:ring-2 focus:ring-violet-500" />
        <button class="bg-violet-600 text-white px-3 py-2 rounded hover:bg-violet-700">Propose Filters</button>
        <div id="pf_status" class="text-sm text-slate-500"></div>
      </form>
      <div id="pf_filters" class="mt-3 text-sm"></div>
      <div id="pf_preview" class="mt-3 text-sm"></div>

      <div class="mt-6">
        <form id="gpropose" class="flex items-center gap-3" onsubmit="event.preventDefault(); runGeminiSuggest();">
          <div class="text-sm text-slate-600">Gemini-assisted filters (≤500 tokens context)</div>
          <button class="bg-emerald-600 text-white px-3 py-2 rounded hover:bg-emerald-700">Suggest with Gemini</button>
          <div id="gp_status" class="text-sm text-slate-500"></div>
        </form>
        <div id="gp_filters" class="mt-3 text-sm"></div>
        <div id="gp_preview" class="mt-3 text-sm"></div>
      </div>
    </div>

    <div class="bg-white shadow-sm ring-1 ring-slate-200 rounded-lg overflow-hidden">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-50 text-left text-slate-600 border-b">
          <tr><th class="py-2 px-3">Name</th><th class="py-2 px-3">Email</th><th class="py-2 px-3">Score</th><th class="py-2 px-3">Actions</th></tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          {% for a in applicants %}
          <tr class="hover:bg-slate-50">
            <td class="py-2 px-3">{{ a['name'] }}</td>
            <td class="py-2 px-3">{{ a['email'] }}</td>
            <td class="py-2 px-3">{{ '%.2f'|format(a['score'] or 0) }}</td>
            <td class="py-2 px-3"><a class="text-blue-700 underline" href="{{ url_for('download_resume', path=a['resume_path']) }}">Resume</a></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
<script>
async function runPropose(){
  const el = document.getElementById('pf_status');
  el.textContent = 'Proposing filters...';
  const target = document.getElementById('target').value || 5;
  const res = await fetch('{{ url_for('propose_filters', job_id=job['id']) }}?target='+encodeURIComponent(target));
  const data = await res.json();
  if(data.ok){
    el.textContent = 'Done';
    const f = data.filters;
    const pv = data.preview;
    document.getElementById('pf_filters').innerHTML = `<div class='text-slate-700'>Filters:</div>
      <ul class='list-disc list-inside'><li>Must-have keywords: <b>${(f.must_keywords||[]).join(', ')||'-'}</b></li>
      <li>Min words: <b>${f.min_words||0}</b></li></ul>`;
    document.getElementById('pf_preview').innerHTML = `<div class='text-slate-700'>Selected (${pv.selected.length}/${pv.total})</div>` +
      `<ol class='list-decimal list-inside'>` + pv.selected.map(x=>`<li>${x.name} (${x.email}) score=${x.score.toFixed(2)}</li>`).join('') + `</ol>`;
  } else {
    el.textContent = data.error || 'Failed';
  }
}
</script>
</body>
</html>
"""


def parse_resume_to_text(path: Path) -> str:
    try:
        if path.suffix.lower() == '.pdf':
            text = []
            with path.open('rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text() or '')
            return '\n'.join(text)
        elif path.suffix.lower() == '.docx':
            doc = Document(str(path))
            return '\n'.join(p.text for p in doc.paragraphs)
        elif path.suffix.lower() == '.txt':
            return path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ''
    return ''


def basic_score(text: str, job_desc: str, answers: List[str]) -> float:
    text_all = (text or '') + '\n' + (job_desc or '') + '\n' + '\n'.join(answers or [])
    text_all = text_all.lower()
    # naive keyword weight from job description
    words = re.findall(r"[a-zA-Z0-9+#\.]{2,}", job_desc.lower()) if job_desc else []
    keywords = [w for w in words if w.isalpha() or any(c in w for c in ['#','+','.',])]
    uniq = list(dict.fromkeys(keywords))
    hits = sum(1 for k in uniq if k in text_all)
    density = hits / max(1, len(uniq))
    length = len(text_all.split())
    return 0.7 * density + 0.3 * min(1.0, length / 2000)


@APP.route('/jp/')
def index():
    init_db()
    con = db()
    rows = con.execute('SELECT * FROM jobs ORDER BY id DESC').fetchall()
    con.close()
    return render_template_string(INDEX_HTML, jobs=rows)


@APP.route('/')
def root_redirect():
    return redirect(url_for('index'))


@APP.route('/jp/job/new', methods=['GET','POST'])
def new_job():
    init_db()
    if request.method == 'POST':
        title = request.form.get('title','').strip()
        description = request.form.get('description','')
        questions = [q.strip() for q in (request.form.get('questions','').splitlines()) if q.strip()]
        con = db()
        con.execute('INSERT INTO jobs(title, description, questions_json, created_at) VALUES (?,?,?,?)', (
            title, description, json.dumps(questions), time.time()
        ))
        job_id = con.execute('SELECT last_insert_rowid() as id').fetchone()['id']
        con.commit(); con.close()
        return redirect(url_for('job_detail', job_id=job_id))
    return render_template_string(NEW_JOB_HTML)


@APP.route('/jp/job/<int:job_id>')
def job_detail(job_id: int):
    con = db()
    job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    con.close()
    if not job:
        return 'Not found', 404
    questions = json.loads(job['questions_json'] or '[]')
    apply_url = request.url_root.strip('/') + url_for('apply', job_id=job_id)
    return render_template_string(JOB_HTML, job=job, questions=questions, apply_url=apply_url)


@APP.route('/jp/apply/<int:job_id>', methods=['GET','POST'])
def apply(job_id: int):
    con = db()
    job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    con.close()
    if not job:
        return 'Not found', 404
    questions: List[str] = json.loads(job['questions_json'] or '[]')
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        email = request.form.get('email','').strip()
        answers = []
        for i,_q in enumerate(questions):
            answers.append(request.form.get(f'q{i}',''))
        file = request.files.get('resume')
        if not file:
            return 'Resume required', 400
        fname = secure_filename(file.filename)
        ext = Path(fname).suffix.lower()
        if ext not in ALLOWED_EXT:
            return 'Unsupported file type', 400
        ensure_dirs()
        save_path = UPLOADS / f"{int(time.time()*1000)}_{fname}"
        file.save(str(save_path))
        resume_text = parse_resume_to_text(save_path)
        score = basic_score(resume_text, job['description'] or '', answers)
        con = db()
        con.execute('INSERT INTO applicants(job_id,name,email,answers_json,resume_path,resume_text,score,created_at) VALUES (?,?,?,?,?,?,?,?)', (
            job_id, name, email, json.dumps(answers), str(save_path), resume_text, float(score), time.time()
        ))
        con.commit(); con.close()
        return 'Application submitted. Thank you!'
    return render_template_string(APPLY_HTML, job=job, questions=questions, enumerate=enumerate)


@APP.route('/jp/resume/<path:path>')
def download_resume(path: str):
    p = Path(path)
    if not p.exists():
        return 'Not found', 404
    return send_from_directory(p.parent, p.name, as_attachment=True)


@APP.route('/jp/job/<int:job_id>/candidates')
def candidates(job_id: int):
    q = request.args.get('q','')
    skill = request.args.get('skill','')
    min_words = int(request.args.get('min_words','0') or '0')
    con = db()
    job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    rows = con.execute('SELECT * FROM applicants WHERE job_id=? ORDER BY score DESC', (job_id,)).fetchall()
    filtered = []
    for r in rows:
        txt = (r['resume_text'] or '') + '\n' + ' '.join(json.loads(r['answers_json'] or '[]'))
        words = len(txt.split())
        if q and (q.lower() not in (r['name'] or '').lower() and q.lower() not in (r['email'] or '').lower() and q.lower() not in txt.lower()):
            continue
        if skill and skill.lower() not in txt.lower():
            continue
        if words < min_words:
            continue
        filtered.append(r)
    con.close()
    return render_template_string(CANDIDATES_HTML, job=job, applicants=filtered, q=q, skill=skill, min_words=min_words)


@APP.route('/jp/job/<int:job_id>/filters/propose')
def propose_filters(job_id: int):
    target = int(request.args.get('target','5') or '5')
    con = db()
    job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    rows = con.execute('SELECT * FROM applicants WHERE job_id=?', (job_id,)).fetchall()
    con.close()
    # derive must-have keywords from job description top tokens
    desc = job['description'] or ''
    tokens = re.findall(r"[A-Za-z0-9+#\.]{3,}", desc.lower())
    # pick top 5 unique tokens by frequency
    freq: Dict[str,int] = {}
    for t in tokens:
        freq[t] = freq.get(t,0)+1
    must = [x for x,_ in sorted(freq.items(), key=lambda kv: -kv[1])[:5]]
    # progressive filtering until <= target
    def apply_filters(rows, must, min_words):
        out = []
        for r in rows:
            txt = (r['resume_text'] or '') + '\n' + ' '.join(json.loads(r['answers_json'] or '[]'))
            if all(m in txt.lower() for m in must) and len(txt.split()) >= min_words:
                out.append({ 'id': r['id'], 'name': r['name'], 'email': r['email'], 'score': float(r['score'] or 0.0) })
        # if too few, relax to any keyword match
        if len(out) < target:
            out2 = []
            for r in rows:
                txt = (r['resume_text'] or '') + '\n' + ' '.join(json.loads(r['answers_json'] or '[]'))
                if any(m in txt.lower() for m in must) and len(txt.split()) >= min_words:
                    out2.append({ 'id': r['id'], 'name': r['name'], 'email': r['email'], 'score': float(r['score'] or 0.0) })
            out = out + [x for x in out2 if x not in out]
        # cap by score
        out = sorted(out, key=lambda x: -x['score'])[:target]
        return out

    min_words = 200
    selected = apply_filters(rows, must, min_words)
    # If still too many/too few, adjust min_words heuristically
    while len(selected) > target and min_words > 50:
        min_words += 50
        selected = apply_filters(rows, must, min_words)
    while len(selected) < target and min_words > 50:
        min_words -= 50
        selected = apply_filters(rows, must, min_words)

    return jsonify({
        'ok': True,
        'filters': { 'must_keywords': must, 'min_words': max(0, min_words) },
        'preview': { 'total': len(rows), 'selected': selected }
    })


@APP.route('/jp/job/<int:job_id>/filters/gemini')
def gemini_filters(job_id: int):
    target = int(request.args.get('target','5') or '5')
    if GeminiClient is None:
        return jsonify({'ok': False, 'error': 'Gemini client unavailable'}), 200
    client = GeminiClient()
    if not client.enabled():
        return jsonify({'ok': False, 'error': 'Gemini not configured'}), 200
    con = db()
    job = con.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    rows = con.execute('SELECT * FROM applicants WHERE job_id=?', (job_id,)).fetchall()
    con.close()
    # Build compact corpus stats (<=500 tokens target)
    desc = (job['description'] or '')[:600]
    tokens = re.findall(r"[A-Za-z0-9+#\.]{3,}", desc.lower())
    freq: Dict[str,int] = {}
    for t in tokens:
        freq[t] = freq.get(t,0)+1
    top_desc = [x for x,_ in sorted(freq.items(), key=lambda kv: -kv[1])[:10]]
    # Sample up to 20 applicants' key info without full text
    sample = []
    for r in rows[:20]:
        txt = (r['resume_text'] or '')
        words = len(txt.split())
        # extract top hits from desc keywords present in resume
        hits = [k for k in top_desc if k in txt.lower()][:5]
        sample.append({'name': r['name'], 'email': r['email'], 'words': words, 'hits': hits, 'score': float(r['score'] or 0.0)})
    corpus = {
        'job_title': job['title'],
        'desc_top_tokens': top_desc,
        'applicants_n': len(rows),
        'avg_len': int(sum(len((r['resume_text'] or '').split()) for r in rows)/max(1,len(rows))),
        'sample': sample
    }
    # Strict, short prompt
    schema = {
        'must_keywords': 'array<=5 of strings',
        'nice_keywords': 'array<=5 of strings',
        'min_words': 'integer >=0',
        'notes': 'short string'
    }
    prompt = (
        "You are an assistant that proposes concise candidate filters for a job. "
        "Return STRICT JSON only with keys: must_keywords, nice_keywords, min_words, notes. "
        f"Schema: {json.dumps(schema)}. Limit keywords to <=5 each.\n"
        f"Job/corpus stats (compact): {json.dumps(corpus, ensure_ascii=False)}\n"
        f"Target interviews: {target}\n"
    )
    # Call Gemini
    import requests
    endpoint = os.getenv('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    api_key = os.getenv('GEMINI_API_KEY')
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {'contents': [{'parts': [{'text': prompt}]}]}
    try:
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
            return jsonify({'ok': False, 'error': 'Parse failure'}), 200
        # Apply suggested filters locally for preview
        must = [s.strip().lower() for s in (data.get('must_keywords') or [])][:5]
        nice = [s.strip().lower() for s in (data.get('nice_keywords') or [])][:5]
        min_words = max(0, int(data.get('min_words') or 0))
        selected = []
        for r in rows:
            txt = (r['resume_text'] or '') + '\n' + ' '.join(json.loads(r['answers_json'] or '[]'))
            ltxt = txt.lower()
            if must and not all(k in ltxt for k in must):
                continue
            if len(txt.split()) < min_words:
                continue
            # soft bonus on nice keywords is for ordering only
            bonus = sum(1 for k in nice if k in ltxt) * 0.01
            selected.append({ 'id': r['id'], 'name': r['name'], 'email': r['email'], 'score': float(r['score'] or 0.0) + bonus })
        selected = sorted(selected, key=lambda x: -x['score'])[:target]
        return jsonify({'ok': True, 'filters': { 'must_keywords': must, 'nice_keywords': nice, 'min_words': min_words, 'notes': data.get('notes','') }, 'preview': { 'total': len(rows), 'selected': selected }})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200


if __name__ == '__main__':
    init_db()
    APP.run(host='127.0.0.1', port=int(os.getenv('JOB_PORTAL_PORT', '8770')), debug=False)
