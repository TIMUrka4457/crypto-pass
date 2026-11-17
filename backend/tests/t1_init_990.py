# T1 iteration_1: signed Telegram initData for TEST users (tg ids 990000xxx) -> /tmp/t1_990_init.json
# Run: /etc/supervisor/emergent-env-exec /root/.venv/bin/python t1_init_990.py
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

USERS = {"a": (990000001, "test_t1_alice"), "b": (990000002, "test_t1_bob")}


def build(tg_id, username):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    pairs = {"auth_date": str(int(time.time())), "query_id": f"AAtest{tg_id}",
             "user": json.dumps({"id": tg_id, "first_name": username, "username": username}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


if __name__ == "__main__":
    json.dump({k: build(*v) for k, v in USERS.items()}, open("/tmp/t1_990_init.json", "w"))
    print("init written")
