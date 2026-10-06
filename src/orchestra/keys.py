from __future__ import annotations

import os
import sys

IS_MAC = sys.platform == "darwin"
NEW_ORCH_KEY = os.environ.get("ORCHESTRA_NEW_KEY") or ("ctrl+t" if IS_MAC else "ctrl+n")
ALT_ORCH_KEY = "ctrl+n" if NEW_ORCH_KEY != "ctrl+n" else "ctrl+t"
