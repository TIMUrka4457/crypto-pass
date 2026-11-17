# Generates signed Telegram WebApp initData for TEST users (run via emergent-env-exec to get TELEGRAM_BOT_TOKEN)
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

USERS = {"alice": (900000001, "TEST_alice"), "bob": (900000002, "TEST_bob")}


def build(tg_id, username):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    pairs = {"auth_date": str(int(time.time())), "query_id": f"AAtest{tg_id}",
             "user": json.dumps({"id": tg_id, "first_name": username, "username": username}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


if __name__ == "__main__":
    out = {k: build(*v) for k, v in USERS.items()}
    with open("/tmp/test_init_data.json", "w") as f:
        json.dump(out, f)
    print("written /tmp/test_init_data.json")
