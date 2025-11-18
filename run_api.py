import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Allow overriding data dir and port via env
os.environ.setdefault('PERFMETER_DATA_DIR', str(ROOT / 'data'))

from perfmeter.api import run  # noqa: E402

if __name__ == '__main__':
    run(host='127.0.0.1', port=int(os.getenv('PERFMETER_API_PORT', '8766')))
