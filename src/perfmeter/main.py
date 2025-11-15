import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
import webbrowser
import os

from .rules import load_rules
from .tracker import ActiveAppTracker
from .aggregator import Aggregator
from .gemini_client import GeminiClient


def summarize_for_gemini(sessions):
    total_time = 0.0
    words = 0
    backspaces = 0
    keys = 0
    mouse = 0.0
    apps = {}
    for s in sessions:
        d = s['duration_sec']
        total_time += d
        words += s['words_typed']
        backspaces += s['backspaces']
        keys += s['keys_pressed']
        mouse += s['mouse_distance']
        apps[s['exe']] = apps.get(s['exe'], 0.0) + d
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


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description='Performance Meter (Windows)')
    parser.add_argument('--role', required=True, help='Role profile, e.g., coder, engineer, hr')
    parser.add_argument('--rules', default='rules.txt', help='Path to rules.txt')
    parser.add_argument('--profiles', default='profiles.yaml', help='Path to profiles.yaml')
    parser.add_argument('--data-dir', default='data', help='Output directory for JSONL logs')
    parser.add_argument('--flush-sec', type=int, default=60, help='Flush interval seconds')
    parser.add_argument('--gemini-interval-sec', type=int, default=0, help='If >0, send summary to Gemini every N seconds; if 0, only on exit')
    args = parser.parse_args()

    rules_path = Path(args.rules)
    if not rules_path.exists():
        print(f"[warn] rules file not found at {rules_path}. Proceeding with no exclusions.")
    rules = load_rules(rules_path)
    # brief rules summary
    try:
        from .rules import Rules  # type: ignore
        excl = sorted(getattr(rules, 'exclude_apps', []))
        incl = sorted(getattr(rules, 'include_apps', []))
        if incl:
            print(f"[rules] include_apps={incl}")
        if excl:
            print(f"[rules] exclude_apps={excl}")
    except Exception:
        pass

    profiles_path = Path(args.profiles)
    profiles = {}
    if profiles_path.exists():
        profiles = yaml.safe_load(profiles_path.read_text(encoding='utf-8')) or {}
    roles = (profiles.get('roles', {}) or {})
    role_cfg = roles.get(args.role, {})
    if not role_cfg:
        print(f"[warn] Role '{args.role}' not found in profiles; continuing without weights.")
    weights = role_cfg.get('metrics_weights', {}) if isinstance(role_cfg, dict) else {}

    tracker = ActiveAppTracker(allow_input_metrics_fn=rules.is_app_metrics_allowed)
    tracker.start()

    agg = Aggregator(Path(args.data_dir), flush_interval_sec=args.flush_sec)
    gemini = GeminiClient()

    stop = threading.Event()
    exit_now = threading.Event()
    first_interrupt = threading.Event()

    def handle_stop(signum=None, frame=None):
        if not first_interrupt.is_set():
            first_interrupt.set()
        else:
            exit_now.set()

    signal.signal(signal.SIGINT, handle_stop)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handle_stop)

    last_gem = time.time()
    gem_buffer = []  # accumulate sessions between Gemini sends
    all_buffer = []  # accumulate all sessions for final summary

    print('Performance meter running. Press Ctrl+C to finalize and open dashboard. Press Ctrl+C again to exit.')
    try:
        while not first_interrupt.is_set():
            time.sleep(5)
            sessions = [s.to_dict() for s in tracker.sessions_flush()]
            if sessions:
                agg.add_sessions(sessions)
                gem_buffer.extend(sessions)
                all_buffer.extend(sessions)
            now = time.time()
            if gemini.enabled() and args.gemini_interval_sec > 0 and (now - last_gem) >= args.gemini_interval_sec:
                # summarize accumulated data since last send
                summary = summarize_for_gemini(gem_buffer)
                res = gemini.score_metrics(args.role, summary, weights=weights)
                # write local sidecar
                out = {
                    'ts': now,
                    'role': args.role,
                    'summary': summary,
                    'gemini': res,
                }
                out_path = Path(args.data_dir) / 'gemini-summaries.jsonl'
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with out_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(out) + '\n')
                last_gem = now
                gem_buffer = []
    finally:
        # First interrupt phase: finalize capture, start dashboard, async Gemini, wait for second interrupt to exit
        tracker.stop()
        # one more drain
        sessions = [s.to_dict() for s in tracker.sessions_flush()]
        if sessions:
            agg.add_sessions(sessions)
            all_buffer.extend(sessions)
        agg.stop()

        if all_buffer:
            final_summary = summarize_for_gemini(all_buffer)
        else:
            final_summary = {'note': 'no data recorded'}

        # Print to console
        print("\n===== Session Summary =====")
        print(json.dumps(final_summary, indent=2))

        # Start dashboard server and open browser
        try:
            os.environ['PERFMETER_DATA_DIR'] = str(Path(args.data_dir).resolve())
            # Persist current session summary for dashboard to prefer over full-day aggregation
            cur_sess_path = Path(args.data_dir) / 'current-session.json'
            cur_sess_path.parent.mkdir(parents=True, exist_ok=True)
            with cur_sess_path.open('w', encoding='utf-8') as f:
                json.dump({'summary': final_summary, 'ts': time.time()}, f)
            from .dashboard import start_in_thread  # lazy import to avoid Flask unless needed
            host = '127.0.0.1'
            port = int(os.getenv('PERFMETER_PORT', '8765'))
            server, thread = start_in_thread(host=host, port=port)
            url = f"http://{host}:{port}/"
            print(f"Opening dashboard at {url} ...")
            try:
                webbrowser.open_new_tab(url)
            except Exception:
                pass
        except Exception as e:
            print(f"[warn] Failed to start dashboard: {e}")
            server = None

        # Kick off Gemini scoring in background and persist result
        def _score_and_write():
            if not gemini.enabled():
                return
            res = gemini.score_metrics(args.role, final_summary, weights=weights)
            out = {
                'ts': time.time(),
                'role': args.role,
                'summary': final_summary,
                'gemini': res,
            }
            out_path = Path(args.data_dir) / 'gemini-summaries.jsonl'
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(out) + '\n')
            print("Gemini evaluation updated. Refresh dashboard if needed.")

        if gemini.enabled():
            threading.Thread(target=_score_and_write, daemon=True).start()
        else:
            print('[info] GEMINI_API_KEY not set; dashboard will show waiting state until configured.')

        # Wait for second Ctrl+C
        print('Press Ctrl+C again to exit and stop the dashboard...')
        try:
            while not exit_now.is_set():
                time.sleep(0.5)
        finally:
            if server:
                try:
                    server.shutdown()
                except Exception:
                    pass


if __name__ == '__main__':
    main()
