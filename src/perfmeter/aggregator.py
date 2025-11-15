import json
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Dict, Any


class Aggregator:
    def __init__(self, out_dir: Path, flush_interval_sec: int = 60):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.flush_interval_sec = flush_interval_sec
        self._queue = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        threading.Thread(target=self._flusher, daemon=True).start()

    def add_sessions(self, sessions: Iterable[Dict[str, Any]]):
        with self._lock:
            self._queue.extend(sessions)

    def stop(self):
        self._stop.set()
        time.sleep(0.1)
        self._flush_now()

    def _flusher(self):
        while not self._stop.is_set():
            time.sleep(self.flush_interval_sec)
            self._flush_now()

    def _flush_now(self):
        with self._lock:
            if not self._queue:
                return
            data, self._queue = self._queue, []
        date = time.strftime('%Y%m%d')
        fpath = self.out_dir / f'metrics-{date}.jsonl'
        with fpath.open('a', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
