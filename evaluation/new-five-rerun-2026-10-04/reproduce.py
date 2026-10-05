"""Run this evaluation against pinned local checkouts with an isolated database.

From the repository root: .venv/bin/python evaluation/new-five-rerun-2026-10-04/reproduce.py index
Then replace index with run. Existing outputs resume; use a new output directory
and isolated data directory to perform another independent repeat.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["DEVPILOT_DATA"] = str(ROOT / ".devpilot/new-five-rerun-2026-10-04")

from scripts import test_new_repositories as runner  # noqa: E402

runner.OUTPUT = Path(__file__).resolve().parent
runner.main()
