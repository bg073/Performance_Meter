import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.job_portal.app import APP, init_db  # noqa: E402

if __name__ == '__main__':
    os.environ.setdefault('JOB_PORTAL_PORT', '8770')
    init_db()
    APP.run(host='127.0.0.1', port=int(os.getenv('JOB_PORTAL_PORT', '8770')), debug=False)
