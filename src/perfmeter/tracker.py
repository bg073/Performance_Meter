import threading
import time
import math
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

import psutil
import sys
import subprocess
from pynput import keyboard, mouse


@dataclass
class InputStats:
    words_typed: int = 0
    backspaces: int = 0
    keys_pressed: int = 0
    mouse_distance: float = 0.0  # pixels


@dataclass
class AppSession:
    exe: str
    title: str
    start_ts: float
    last_ts: float
    input: InputStats = field(default_factory=InputStats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'exe': self.exe,
            'title': self.title,
            'start_ts': self.start_ts,
            'end_ts': self.last_ts,
            'duration_sec': max(0.0, self.last_ts - self.start_ts),
            'words_typed': self.input.words_typed,
            'backspaces': self.input.backspaces,
            'keys_pressed': self.input.keys_pressed,
            'mouse_distance': self.input.mouse_distance,
        }


class ActiveAppTracker:
    def __init__(self, allow_input_metrics_fn):
        self._lock = threading.RLock()
        self._current: Optional[AppSession] = None
        self._allow_input_metrics_fn = allow_input_metrics_fn
        self._sessions = []
        self._stop = threading.Event()
        # keyboard/mouse
        self._km_enabled = True
        self._last_mouse_pos = None
        self._kb_listener = keyboard.Listener(on_press=self._on_key_press)
        self._ms_listener = mouse.Listener(on_move=self._on_mouse_move)
        self._is_windows = sys.platform.startswith('win')

    def start(self):
        self._kb_listener.start()
        self._ms_listener.start()
        threading.Thread(target=self._poll_foreground, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._kb_listener.stop()
        self._ms_listener.stop()
        with self._lock:
            if self._current:
                self._current.last_ts = time.time()
                self._sessions.append(self._current)
                self._current = None

    def sessions_flush(self):
        with self._lock:
            out, self._sessions = self._sessions, []
            return out

    def _get_foreground_exe_and_title(self):
        if self._is_windows:
            try:
                import win32gui  # type: ignore
                import win32process  # type: ignore
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) or ''
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = psutil.Process(pid)
                    exe = proc.name() or ''
                except Exception:
                    exe = ''
                return (exe.lower(), title)
            except Exception:
                return ('', '')
        else:
            return self._linux_active_window_exe_title()

    def _linux_active_window_exe_title(self):
        try:
            proc = subprocess.run(
                ['xprop', '-root', '_NET_ACTIVE_WINDOW'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            line = proc.stdout.strip()
            if not line:
                return ('', '')
            parts = line.split()
            wid_hex = parts[-1] if parts else ''
            if wid_hex in ('0x0', '0x0,', 'None') or not wid_hex.startswith('0x'):
                return ('', '')
            proc2 = subprocess.run(
                ['xprop', '-id', wid_hex, '_NET_WM_PID', '_NET_WM_NAME'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
            pid = None
            title = ''
            for l in proc2.stdout.splitlines():
                if l.startswith('_NET_WM_PID'):
                    try:
                        pid = int(l.split()[-1])
                    except Exception:
                        pid = None
                elif l.startswith('_NET_WM_NAME') or l.startswith('WM_NAME'):
                    s = l.split('=', 1)[-1].strip()
                    if s.startswith('"') and s.endswith('"'):
                        s = s[1:-1]
                    title = s
            exe = ''
            if pid:
                try:
                    p = psutil.Process(pid)
                    exe = p.name() or ''
                except Exception:
                    exe = ''
            return (exe.lower(), title)
        except Exception:
            return ('', '')

    def _rotate_session_if_needed(self, exe: str, title: str):
        now = time.time()
        with self._lock:
            if self._current and (self._current.exe != exe or self._current.title != title):
                self._current.last_ts = now
                self._sessions.append(self._current)
                self._current = None
            if not self._current:
                self._current = AppSession(exe=exe, title=title, start_ts=now, last_ts=now)
            else:
                self._current.last_ts = now
            self._km_enabled = self._allow_input_metrics_fn(exe)

    def _poll_foreground(self):
        while not self._stop.is_set():
            exe, title = self._get_foreground_exe_and_title()
            self._rotate_session_if_needed(exe, title)
            time.sleep(0.5)

    def _on_key_press(self, key):
        with self._lock:
            if not self._current:
                return
            self._current.last_ts = time.time()
            if self._km_enabled:
                self._current.input.keys_pressed += 1
                try:
                    if key == keyboard.Key.backspace:
                        self._current.input.backspaces += 1
                    elif key in (keyboard.Key.space, keyboard.Key.enter, keyboard.Key.tab):
                        self._current.input.words_typed += 1
                except Exception:
                    pass

    def _on_mouse_move(self, x, y):
        with self._lock:
            if not self._current:
                self._last_mouse_pos = (x, y)
                return
            self._current.last_ts = time.time()
            if self._km_enabled:
                if self._last_mouse_pos is not None:
                    lx, ly = self._last_mouse_pos
                    dist = math.hypot(x - lx, y - ly)
                    self._current.input.mouse_distance += dist
                self._last_mouse_pos = (x, y)
