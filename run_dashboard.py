import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Allow overriding data dir and port via env
os.environ.setdefault('PERFMETER_DATA_DIR', str(ROOT / 'data'))
os.environ.setdefault('PERFMETER_PORT', '8765')

from perfmeter.dashboard import APP  # noqa: E402

if __name__ == '__main__':
    APP.run(host='127.0.0.1', port=int(os.getenv('PERFMETER_PORT', '8765')), debug=False)
