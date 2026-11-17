# NeonWallet/EasyCrypto regression tests: health, mini-app auth, deposit addresses, transfer/check/invoice, admin read APIs.
# Prereqs: /tmp/test_init_data.json (gen_init_data.py via emergent-env-exec) and /tmp/admin_token (admin_login_once.py).
# Safe for MAINNET: no withdrawals, sweeps, broadcasts or settings changes.
import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


def _init():
    with open("/tmp/test_init_data.json") as f:
        return json.load(f)


def _admin_headers():
    if not os.path.exists("/tmp/admin_token"):
        pytest.skip("no admin token")
    return {"Authorization": "Bearer " + open("/tmp/admin_token").read().strip()}


def _login(name):
    r = requests.post(f"{BASE_URL}/api/auth/telegram", json={"init_data": _init()[name]}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def alice():
    return _login("alice")


@pytest.fixture(scope="module")
def bob():
    return _login("bob")


# ---------- health / public ----------
class TestHealth:
    def test_health(self):
        d = requests.get(f"{BASE_URL}/api/health", timeout=30).json()
        assert d["ok"] is True and d["transactions"] is True and d["replica_set"] == "rs0"

    def test_config(self):
        d = requests.get(f"{BASE_URL}/api/config", timeout=30).json()
        assert set(d["assets"]) == {"TON", "USDT_TON", "USDT_TRC20"}
        assert d["bot_username"] == "EasyCrypto_bot"


# ---------- telegram auth ----------
class TestTelegramAuth:
    def test_bad_signature(self):
        bad = _init()["alice"].replace("hash=", "hash=00")
        r = requests.post(f"{BASE_URL}/api/auth/telegram", json={"init_data": bad}, timeout=30)
        assert r.status_code == 401

    def test_me(self, alice):
        d = requests.get(f"{BASE_URL}/api/me", headers=alice, timeout=30).json()
        assert d["user"]["id"] == "900000001" and d["user"]["username"] == "test_alice"
        assert set(d["balances"]) == {"TON", "USDT_TON", "USDT_TRC20"}

    def test_me_no_token(self):
        assert requests.get(f"{BASE_URL}/api/me", timeout=30).status_code == 401


# ---------- deposit addresses ----------
class TestDeposit:
    @pytest.mark.parametrize("net,prefix", [("ton", ("EQ", "UQ", "0:")), ("tron", ("T",))])
    def test_deterministic(self, alice, net, prefix):
        a1 = requests.get(f"{BASE_URL}/api/deposit/{net}", headers=alice, timeout=60)
        assert a1.status_code == 200, a1.text
        a2 = requests.get(f"{BASE_URL}/api/deposit/{net}", headers=alice, timeout=60).json()
        assert a1.json()["address"] == a2["address"] and a2["address"].startswith(prefix)

    def test_unknown_network(self, alice):
        assert requests.get(f"{BASE_URL}/api/deposit/btc", headers=alice, timeout=30).status_code == 400


# ---------- transfers / checks / invoices ----------
class TestMoney:
    def test_transfer_zero_balance(self, alice, bob):
        r = requests.post(f"{BASE_URL}/api/transfer", headers=alice, timeout=30,
                          json={"to_username": "TEST_bob", "asset": "TON", "amount": "1",
                                "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 400 and "Недостаточно средств" in r.text

    def test_transfer_unknown_user(self, alice):
        r = requests.post(f"{BASE_URL}/api/transfer", headers=alice, timeout=30,
                          json={"to_username": "TEST_nobody_xyz", "asset": "TON", "amount": "1",
                                "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 400

    def test_transfer_self(self, alice):
        r = requests.post(f"{BASE_URL}/api/transfer", headers=alice, timeout=30,
                          json={"to_username": "TEST_alice", "asset": "TON", "amount": "1",
                                "idempotency_key": uuid.uuid4().hex})
        assert r.status_code == 400

    def test_check_zero_balance(self, alice):
        r = requests.post(f"{BASE_URL}/api/checks", headers=alice, timeout=30,
                          json={"asset": "USDT_TON", "amount": "1", "kind": "personal"})
        assert r.status_code == 400 and "Недостаточно средств" in r.text
        lst = requests.get(f"{BASE_URL}/api/checks", headers=alice, timeout=30).json()
        assert lst == []  # failed check must not persist (txn rollback)

    def test_invoice_crud(self, alice, bob):
        r = requests.post(f"{BASE_URL}/api/invoices", headers=alice, timeout=30,
                          json={"asset": "USDT_TON", "amount": "5", "description": "TEST_invoice"})
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["amount"] == "5" and inv["status"] == "active" and "EasyCrypto_bot" in inv["pay_url"]
        lst = requests.get(f"{BASE_URL}/api/invoices", headers=alice, timeout=30).json()
        assert any(i["id"] == inv["id"] for i in lst)
        v = requests.get(f"{BASE_URL}/api/invoices/view/{inv['code']}", headers=bob, timeout=60).json()
        assert v["recipient"] == "@test_alice" and v["external_address"]
        p = requests.post(f"{BASE_URL}/api/invoices/pay/{inv['code']}", headers=bob, timeout=30)
        assert p.status_code == 400 and "Недостаточно средств" in p.text
        c = requests.post(f"{BASE_URL}/api/invoices/{inv['id']}/cancel", headers=alice, timeout=30)
        assert c.status_code == 200 and c.json()["status"] == "cancelled"

    def test_history_referral(self, alice):
        assert requests.get(f"{BASE_URL}/api/history", headers=alice, timeout=30).json() == []
        r = requests.get(f"{BASE_URL}/api/referral", headers=alice, timeout=30).json()
        assert r["link"].endswith("r_900000001")


# ---------- admin read-only ----------
class TestAdmin:
    @pytest.mark.parametrize("path", ["me", "stats", "users", "deposits", "withdrawals", "settings", "audit",
                                      "hot-wallet", "merchants", "checks", "invoices", "aml/blocklist", "admins",
                                      "broadcasts"])
    def test_get(self, path):
        r = requests.get(f"{BASE_URL}/api/admin/{path}", headers=_admin_headers(), timeout=60)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:300]}"

    def test_aml_disabled(self):
        s = requests.get(f"{BASE_URL}/api/admin/settings", headers=_admin_headers(), timeout=30).json()
        assert s.get("aml", {}).get("enabled") is False, s.get("aml")

    def test_reconcile(self):
        d = requests.get(f"{BASE_URL}/api/admin/ledger/reconcile", headers=_admin_headers(), timeout=60).json()
        assert d["ok"] is True, d

    def test_admin_no_token(self):
        assert requests.get(f"{BASE_URL}/api/admin/stats", timeout=30).status_code == 401
