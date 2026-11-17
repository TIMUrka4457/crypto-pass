# EasyCrypto API regression: tg auth, withdraw quote (dynamic fees), hidden admin gate. Run via /etc/supervisor/emergent-env-exec
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
BASE_URL = BASE_URL.rstrip("/")
PANEL = "Lv9rXEr23KxmGpbhqZiz8xTy"
TEST_TG_ID = 9990000001


def build_init(tg_id, username, first):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    pairs = {"auth_date": str(int(time.time())), "query_id": f"AAtest{tg_id}",
             "user": json.dumps({"id": tg_id, "first_name": first, "username": username}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


@pytest.fixture(scope="module")
def user_token():
    r = requests.post(f"{BASE_URL}/api/auth/telegram", json={"init_data": build_init(TEST_TG_ID, "test_wallet_a", "TEST_A")}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


# --- auth ---
class TestAuth:
    def test_bad_hash_rejected(self):
        bad = build_init(TEST_TG_ID, "test_wallet_a", "TEST_A")[:-4] + "0000"
        r = requests.post(f"{BASE_URL}/api/auth/telegram", json={"init_data": bad}, timeout=30)
        assert r.status_code in (400, 401, 403)

    def test_me(self, user_token):
        r = requests.get(f"{BASE_URL}/api/me", headers=H(user_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["tg_id"] == TEST_TG_ID
        assert set(d["balances"].keys()) == {"TON", "USDT_TON", "USDT_TRC20"}

    def test_config(self):
        r = requests.get(f"{BASE_URL}/api/config", timeout=30)
        assert r.status_code == 200
        assert "assets" in r.json()


# --- withdraw quote ---
class TestQuote:
    def test_ton_fixed(self, user_token):
        r = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "TON"}, headers=H(user_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        print("TON", d)
        assert d["dynamic"] is False and float(d["fee"]) > 0

    def test_usdt_ton_dynamic(self, user_token):
        r = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "USDT_TON"}, headers=H(user_token), timeout=30)
        d = r.json()
        print("USDT_TON", d)
        assert r.status_code == 200 and d["dynamic"] is True and float(d["fee"]) > 0

    def test_trc20_new_vs_existing(self, user_token):
        r1 = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "USDT_TRC20"}, headers=H(user_token), timeout=30)
        r2 = requests.get(f"{BASE_URL}/api/withdrawals/quote",
                          params={"asset": "USDT_TRC20", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"}, headers=H(user_token), timeout=60)
        print("TRC20 new", r1.json(), "existing", r2.json())
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["dynamic"] is True
        assert float(r1.json()["fee"]) >= float(r2.json()["fee"]) > 0

    def test_unknown_asset(self, user_token):
        r = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "BTC"}, headers=H(user_token), timeout=30)
        assert r.status_code == 400

    def test_no_token(self):
        r = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "TON"}, timeout=30)
        assert r.status_code in (401, 403)


# --- read-only user endpoints ---
class TestUserRead:
    @pytest.mark.parametrize("path", ["/api/history", "/api/checks", "/api/invoices", "/api/referral", "/api/merchant",
                                      "/api/withdrawals", "/api/deposit/ton", "/api/deposit/tron"])
    def test_get(self, user_token, path):
        r = requests.get(f"{BASE_URL}{path}", headers=H(user_token), timeout=60)
        assert r.status_code == 200, r.text


# --- hidden admin gate ---
class TestAdminGate:
    def test_admin_me_no_header_404(self):
        assert requests.get(f"{BASE_URL}/api/admin/me", timeout=30).status_code == 404

    def test_admin_login_no_header_404(self):
        r = requests.post(f"{BASE_URL}/api/admin/auth/login", json={"email": "x@y.z", "password": "x"}, timeout=30)
        assert r.status_code == 404

    def test_admin_me_wrong_header_404(self):
        assert requests.get(f"{BASE_URL}/api/admin/me", headers={"X-Panel-Key": "wrong"}, timeout=30).status_code == 404

    def test_admin_me_right_header_no_token_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/me", headers={"X-Panel-Key": PANEL}, timeout=30)
        assert r.status_code in (401, 403)

    def test_gate_wrong(self):
        assert requests.get(f"{BASE_URL}/api/p/wrongwrongwrongwrongwron", timeout=30).status_code == 404

    def test_gate_right(self):
        r = requests.get(f"{BASE_URL}/api/p/{PANEL}", timeout=30)
        assert r.status_code == 200 and r.json() == {"ok": True}
