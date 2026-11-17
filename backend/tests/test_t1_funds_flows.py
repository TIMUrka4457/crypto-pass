# T1 iteration_1: EasyCrypto funds flows (adjust->transfer->check->swap->invoice->debit back), fees, swap quote,
# withdraw quote, account settings, hidden admin gate, finance, cold validation, security headers.
# Run: /etc/supervisor/emergent-env-exec /root/.venv/bin/python -m pytest /app/backend/tests/test_t1_funds_flows.py -p no:xdist
# Prereq: /tmp/admin_token (admin_login_once.py) and /tmp/t1_init.json (t1_gen_init.py)
import json
import os
import uuid
from decimal import Decimal

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PANEL = "Lv9rXEr23KxmGpbhqZiz8xTy"
INIT = json.load(open("/tmp/t1_init.json"))
ADMIN = open("/tmp/admin_token").read().strip()
AH = {"Authorization": f"Bearer {ADMIN}", "X-Panel-Key": PANEL}


def login(k):
    r = requests.post(f"{BASE_URL}/api/auth/telegram", json={"init_data": INIT[k]}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def bal(h, asset):
    return Decimal(requests.get(f"{BASE_URL}/api/me", headers=h, timeout=30).json()["balances"][asset]["available"])


def idem():
    return uuid.uuid4().hex[:16]


@pytest.fixture(scope="module")
def A():
    return login("a")


@pytest.fixture(scope="module")
def B():
    return login("b")


# ---- public / security ----
class TestPublic:
    def test_fees(self):
        r = requests.get(f"{BASE_URL}/api/fees", timeout=30)
        assert r.status_code == 200
        d = r.json()
        print("fees", d)
        assert d["withdraw"]["TON"] == "0.05"
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_admin_gate(self):
        assert requests.get(f"{BASE_URL}/api/admin/me", timeout=30).status_code == 404
        r = requests.get(f"{BASE_URL}/api/p/{PANEL}", timeout=30)
        assert r.status_code == 200 and r.json().get("ok") is True
        assert requests.get(f"{BASE_URL}/api/p/wrongkey123", timeout=30).status_code == 404
        r = requests.get(f"{BASE_URL}/api/admin/me", headers=AH, timeout=30)
        assert r.status_code == 200, r.text


# ---- user quotes ----
class TestQuotes:
    def test_withdraw_quote(self, A):
        for a in ("TON", "USDT_TON", "USDT_TRC20"):
            r = requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": a}, headers=A, timeout=30)
            assert r.status_code == 200, r.text
            print(a, r.json())
        assert requests.get(f"{BASE_URL}/api/withdrawals/quote", params={"asset": "TON"}, headers=A).json()["fee"] == "0.05"

    def test_swap_quote(self, A):
        r = requests.get(f"{BASE_URL}/api/swap/quote", params={"from_asset": "TON", "to_asset": "USDT_TON", "amount": "10"}, headers=A)
        assert r.status_code == 200, r.text
        print("swap quote", r.json())
        assert Decimal(r.json()["receive"]) > 0

    def test_deposit_addresses(self, A):
        for n in ("ton", "tron"):
            r = requests.get(f"{BASE_URL}/api/deposit/{n}", headers=A, timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["address"]


# ---- funds flows ----
class TestFunds:
    def test_full_flow(self, A, B):
        ua = requests.get(f"{BASE_URL}/api/me", headers=A).json()["user"]["id"]
        login("b")
        a0, b0 = bal(A, "TON"), bal(B, "TON")
        r = requests.post(f"{BASE_URL}/api/admin/users/{ua}/adjust", headers=AH,
                          json={"asset": "TON", "amount": "5", "direction": "credit", "comment": "TEST funding"})
        assert r.status_code == 200, r.text
        assert bal(A, "TON") == a0 + 5

        # transfer A->B 0.5
        r = requests.post(f"{BASE_URL}/api/transfer", headers=A, json={"to_username": "test_ec_b", "asset": "TON",
                                                                       "amount": "0.5", "comment": "TEST", "idempotency_key": idem()})
        assert r.status_code == 200, r.text
        print("transfer", r.json())
        assert bal(B, "TON") == b0 + Decimal("0.5")

        # check 0.3 claimed by B
        r = requests.post(f"{BASE_URL}/api/checks", headers=A, json={"asset": "TON", "amount": "0.3"})
        assert r.status_code == 200, r.text
        code = r.json()["code"]
        r = requests.post(f"{BASE_URL}/api/checks/claim/{code}", headers=B, json={})
        assert r.status_code == 200, r.text
        print("claim", r.json())
        assert bal(B, "TON") == b0 + Decimal("0.8")
        r = requests.post(f"{BASE_URL}/api/checks/claim/{code}", headers=B, json={})
        assert r.status_code >= 400

        # swap 2 TON -> USDT_TON
        q = requests.get(f"{BASE_URL}/api/swap/quote", params={"from_asset": "TON", "to_asset": "USDT_TON", "amount": "2"}, headers=A).json()
        u0 = bal(A, "USDT_TON")
        r = requests.post(f"{BASE_URL}/api/swap", headers=A, json={"from_asset": "TON", "to_asset": "USDT_TON", "amount": "2",
                                                                   "min_receive": q["receive"], "idempotency_key": idem()})
        assert r.status_code == 200, r.text
        print("swap", r.json())
        assert bal(A, "USDT_TON") == u0 + Decimal(r.json()["receive"])
        # min_receive too high -> 409
        r = requests.post(f"{BASE_URL}/api/swap", headers=A, json={"from_asset": "TON", "to_asset": "USDT_TON", "amount": "2",
                                                                   "min_receive": "99999", "idempotency_key": idem()})
        assert r.status_code == 409, r.text

        # invoice by A paid by B
        r = requests.post(f"{BASE_URL}/api/invoices", headers=A, json={"asset": "TON", "amount": "0.2", "description": "TEST inv"})
        assert r.status_code == 200, r.text
        inv = r.json()
        a1 = bal(A, "TON")
        r = requests.post(f"{BASE_URL}/api/invoices/pay/{inv['code']}", headers=B)
        assert r.status_code == 200, r.text
        print("pay", r.json())
        assert bal(A, "TON") == a1 + Decimal("0.2")

        # history kinds
        kinds = {h["kind"] for h in requests.get(f"{BASE_URL}/api/history", headers=A).json()}
        print("kinds A", kinds)
        assert {"adjust", "transfer", "check_create", "swap", "invoice_payment"} <= kinds
        kb = {h["kind"] for h in requests.get(f"{BASE_URL}/api/history", headers=B).json()}
        assert {"transfer", "check_claim", "invoice_payment"} <= kb

        # over-debit fails, then debit back everything
        ub = requests.get(f"{BASE_URL}/api/me", headers=B).json()["user"]["id"]
        r = requests.post(f"{BASE_URL}/api/admin/users/{ua}/adjust", headers=AH,
                          json={"asset": "TON", "amount": "1000", "direction": "debit", "comment": "TEST"})
        assert r.status_code == 400
        for h, uid in ((A, ua), (B, ub)):
            for asset in ("TON", "USDT_TON"):
                v = bal(h, asset)
                if v > 0:
                    r = requests.post(f"{BASE_URL}/api/admin/users/{uid}/adjust", headers=AH,
                                      json={"asset": asset, "amount": str(v), "direction": "debit", "comment": "TEST cleanup"})
                    assert r.status_code == 200, r.text
            assert bal(h, "TON") == 0 and bal(h, "USDT_TON") == 0


# ---- admin ----
class TestAdmin:
    def test_finance(self):
        for d in (7, 30, 90):
            r = requests.get(f"{BASE_URL}/api/admin/finance", params={"days": d}, headers=AH, timeout=60)
            assert r.status_code == 200, r.text
        print("finance keys", list(r.json().keys()))

    def test_cold_invalid(self):
        r = requests.put(f"{BASE_URL}/api/admin/cold", headers=AH, json={"ton": "abc", "tron": ""})
        assert r.status_code == 400, r.text
        print("cold invalid", r.json())

    def test_hot_wallet(self):
        r = requests.get(f"{BASE_URL}/api/admin/hot-wallet", headers=AH, timeout=60)
        assert r.status_code == 200, r.text

    def test_settings(self):
        r = requests.get(f"{BASE_URL}/api/admin/settings", headers=AH)
        assert r.status_code == 200
        s = r.json()
        assert "fees" in s and "swap" in s and "security" in s


# ---- account (throwaway user) ----
class TestAccount:
    def test_recreate_and_delete(self):
        h = login("del")
        a1 = requests.get(f"{BASE_URL}/api/deposit/ton", headers=h).json()["address"]
        r = requests.post(f"{BASE_URL}/api/account/recreate-addresses", headers=h)
        assert r.status_code == 200 and r.json()["retired"] >= 1, r.text
        a2 = requests.get(f"{BASE_URL}/api/deposit/ton", headers=h).json()["address"]
        assert a1 != a2
        r = requests.post(f"{BASE_URL}/api/account/delete", headers=h, json={"confirm": "нет"})
        assert r.status_code == 400
        # actual delete (УДАЛИТЬ) is exercised via the mini app UI on the same throwaway user
