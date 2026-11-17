# Generates signed Telegram WebApp initData for T1 TEST users -> /tmp/t1_init.json (run via emergent-env-exec)
import json
import sys

sys.path.insert(0, "/app/backend/tests")
from gen_init_data import build  # noqa: E402

USERS = {"a": (900000001, "test_ec_a"), "b": (900000002, "test_ec_b"), "del": (900000099, "test_ec_del")}

if __name__ == "__main__":
    out = {k: build(*v) for k, v in USERS.items()}
    with open("/tmp/t1_init.json", "w") as f:
        json.dump(out, f)
    print("written /tmp/t1_init.json")
