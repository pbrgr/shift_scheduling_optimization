"""Drop-in replacement for the original wis_main.py of the DPService
integration — same path, same call, same contract: the Avanti payload on
stdin, the result JSON on stdout, logs on stderr, exit status 0 on success.

The DPService only needs its Lib\\Avanti folder swapped for this repository;
no Delphi change is required to run the new solver.
"""

import os
import sys

#the embedded Windows Python ignores PYTHONPATH and the working directory
#is owned by the service, so make the repository root importable based on
#this file's own location (root/src/core/wis_main.py -> root)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.app.avanti_filter import run  # noqa: E402  (needs ROOT on sys.path)

if __name__ == "__main__":
    sys.exit(run())
