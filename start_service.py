# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Ensure stdout and stderr exist even under pythonw.exe
if sys.stdout is None:
    sys.stdout = open(LOG_DIR / "server_stdout.log", "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(LOG_DIR / "server_stderr.log", "a", encoding="utf-8")

import uvicorn
from server import app, HOST, PORT

if __name__ == "__main__":
    print(f"Starting server on http://{HOST}:{PORT}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
