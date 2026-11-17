# T1 setup: signed initData for TEST users (999000xxx) + optional ONE admin API login (X-Panel-Key) -> /tmp files
# Run: /etc/supervisor/emergent-env-exec python3 t1_setup.py [login]
import hashlib
import hmac
import json
import os
import re
import sys
import time
from urllib.parse import urlencode

import requests

USERS = {"a": (999000001, "test_t1a"), "b": (999000002, "test_t1b")}


def build(tg_id, username):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    pairs = {"auth_date": str(int(time.time())), "query_id": f"AAtest{tg_id}",
             "user": json.dumps({"id": tg_id, "first_name": username, "username": username}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


if __name__ == "__main__":
    json.dump({k: build(*v) for k, v in USERS.items()}, open("/tmp/t1_init.json", "w"))
    print("init written")
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        base = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
        h = {"X-Panel-Key": os.environ["ADMIN_PANEL_PATH"]}
        r = requests.post(f"{base}/api/admin/auth/login", headers=h, timeout=30,
                          json={"email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]})
        print("login", r.status_code)
        cid = r.json()["challenge_id"]
        time.sleep(3)
        otp = re.findall(r"ADMIN OTP for [^:]+: (\d{6})", open("/var/log/supervisor/backend.err.log", errors="ignore").read())[-1]
        r = requests.post(f"{base}/api/admin/auth/verify", headers=h, json={"challenge_id": cid, "code": otp}, timeout=30)
        print("verify", r.status_code)
        open("/tmp/t1_admin_token", "w").write(r.json()["token"])
