#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys
import urllib.error
import urllib.request

port = int(os.environ.get("WAN2GP_PORT", "7860"))
try:
    with socket.create_connection(("127.0.0.1", port), timeout=5):
        pass
    request = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    if status not in {200, 302, 303, 307, 401, 403}:
        raise RuntimeError(f"unexpected HTTP status {status}")
except Exception as error:
    print(f"unhealthy: {error}", file=sys.stderr)
    raise SystemExit(1)
print("healthy")
