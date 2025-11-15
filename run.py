import os
import sys
from pathlib import Path

# Ensure 'src' is on sys.path
ROOT = Path(__file__).parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.perfmeter.main import main  # noqa: E402

if __name__ == '__main__':
    main()