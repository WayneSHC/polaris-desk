"""Package entry point so `python -m polaris ...` works (delegates to CLI)."""
from __future__ import annotations

import sys

from polaris.cli import main

if __name__ == "__main__":
    sys.exit(main())
