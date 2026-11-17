# Performs ONE admin API login (sends real OTP email); reads OTP from backend log; saves token to /tmp/admin_token
import os
import re
import sys
import time

import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
LOG = "/var/log/supervisor/backend.err.log"
EMAIL, PW = sys.argv[1], sys.argv[2]

r = requests.post(f"{BASE}/api/admin/auth/login", json={"email": EMAIL, "password": PW}, timeout=30)
print("login", r.status_code, list(r.json().keys()))
cid = r.json()["challenge_id"]
otp = None
for _ in range(10):
    time.sleep(1)
    m = re.findall(r"ADMIN OTP for [^:]+: (\d{6})", open(LOG, errors="ignore").read())
    if m:
        otp = m[-1]
        break
r = requests.post(f"{BASE}/api/admin/auth/verify", json={"challenge_id": cid, "code": otp}, timeout=30)
print("verify", r.status_code, {k: v for k, v in r.json().items() if k != "token"})
open("/tmp/admin_token", "w").write(r.json()["token"])
