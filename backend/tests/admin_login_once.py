# Performs ONE admin API login (sends real OTP email); reads OTP from backend log; saves token to /tmp/admin_token
# usage: python admin_login_once.py EMAIL PASSWORD PANEL_KEY
import os
import re
import sys
import time

import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
LOG = "/var/log/supervisor/backend.err.log"
EMAIL, PW, PK = sys.argv[1], sys.argv[2], sys.argv[3]
H = {"X-Panel-Key": PK}

before = len(re.findall(r"ADMIN OTP for [^:]+: (\d{6})", open(LOG, errors="ignore").read()))
r = requests.post(f"{BASE}/api/admin/auth/login", json={"email": EMAIL, "password": PW}, headers=H, timeout=30)
print("login", r.status_code, r.text[:200])
cid = r.json()["challenge_id"]
otp = None
for _ in range(15):
    time.sleep(1)
    m = re.findall(r"ADMIN OTP for [^:]+: (\d{6})", open(LOG, errors="ignore").read())
    if len(m) > before:
        otp = m[-1]
        break
r = requests.post(f"{BASE}/api/admin/auth/verify", json={"challenge_id": cid, "code": otp}, headers=H, timeout=30)
print("verify", r.status_code, {k: v for k, v in r.json().items() if k != "token"})
open("/tmp/admin_token", "w").write(r.json()["token"])
