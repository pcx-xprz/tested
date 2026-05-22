"""
Hatcher.host - Account Checker & Coin Balance Monitor
=======================================================
Fitur:
  - Login multi-akun dari registered_accounts.json
  - Cek coin/credit balance per akun
  - Cek status email verifikasi
  - Cek referral stats (berapa yang udah daftar + buat agent)
  - Export summary ke coins_report.json

Jalankan SETELAH verifikasi email manual selesai.
"""

import requests
import json
import time
import random
import logging
import os
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ACCOUNTS_FILE  = "registered_accounts.json"
OUTPUT_FILE    = "coins_report.json"
LOG_FILE       = "checker.log"
BASE_API       = "https://api.hatcher.host"
DELAY_MIN      = 2
DELAY_MAX      = 5
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://hatcher.host",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


def delay():
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(t)


def login(session: requests.Session, email: str, password: str) -> dict | None:
    """
    POST /auth/login → dapat access token (JWT / session cookie)
    Returns: {"token": "...", "user": {...}} atau None
    """
    url = f"{BASE_API}/auth/login"
    payload = {"email": email, "password": password}
    try:
        r = session.post(url, headers=BASE_HEADERS, json=payload, timeout=20)
        if r.status_code == 200:
            data = r.json()
            log.info(f"  ✅ Login sukses: {email}")
            return data
        elif r.status_code == 401:
            log.warning(f"  ❌ Login gagal (401 - belum verifikasi email atau password salah): {email}")
        elif r.status_code == 403:
            log.warning(f"  ❌ Login gagal (403 - email belum terverifikasi): {email}")
        else:
            log.warning(f"  ❌ Login gagal [{r.status_code}]: {r.text[:200]}")
        return None
    except Exception as e:
        log.error(f"  ❌ Exception login {email}: {e}")
        return None


def get_auth_headers(token: str) -> dict:
    h = BASE_HEADERS.copy()
    h["Authorization"] = f"Bearer {token}"
    return h


def get_user_profile(session: requests.Session, headers: dict) -> dict:
    """GET /auth/me atau /users/me → info user + coin balance"""
    for endpoint in ["/auth/me", "/users/me", "/user/me", "/me"]:
        try:
            r = session.get(f"{BASE_API}{endpoint}", headers=headers, timeout=15)
            if r.status_code == 200:
                log.info(f"  ✅ Profile endpoint: {endpoint}")
                return r.json()
        except Exception:
            pass
    log.warning("  ⚠️  Semua endpoint /me tidak berhasil")
    return {}


def get_coins_balance(session: requests.Session, headers: dict) -> dict:
    """GET /coins, /credits, /wallet — coba beberapa kemungkinan endpoint"""
    candidates = [
        "/coins",
        "/credits",
        "/wallet",
        "/user/coins",
        "/user/credits",
        "/users/me/coins",
        "/users/me/credits",
    ]
    for endpoint in candidates:
        try:
            r = session.get(f"{BASE_API}{endpoint}", headers=headers, timeout=15)
            if r.status_code == 200:
                log.info(f"  💰 Coins endpoint: {endpoint}")
                return {"endpoint": endpoint, "data": r.json()}
        except Exception:
            pass
    return {}


def get_referral_stats(session: requests.Session, headers: dict) -> dict:
    """GET /referrals/stats atau /referrals/me → berapa referral aktif"""
    candidates = [
        "/referrals/stats",
        "/referrals/me",
        "/referrals",
        "/user/referrals",
    ]
    for endpoint in candidates:
        try:
            r = session.get(f"{BASE_API}{endpoint}", headers=headers, timeout=15)
            if r.status_code == 200:
                log.info(f"  🔗 Referral endpoint: {endpoint}")
                return {"endpoint": endpoint, "data": r.json()}
        except Exception:
            pass
    return {}


def get_agents(session: requests.Session, headers: dict) -> dict:
    """GET /agents → list agent milik akun ini"""
    candidates = ["/agents", "/user/agents", "/my/agents"]
    for endpoint in candidates:
        try:
            r = session.get(f"{BASE_API}{endpoint}", headers=headers, timeout=15)
            if r.status_code == 200:
                log.info(f"  🤖 Agents endpoint: {endpoint}")
                return {"endpoint": endpoint, "data": r.json()}
        except Exception:
            pass
    return {}


def load_registered_accounts(filepath: str) -> list:
    if not os.path.exists(filepath):
        log.error(f"File '{filepath}' tidak ditemukan!")
        return []
    with open(filepath, "r") as f:
        data = json.load(f)
    # Filter hanya akun yang sukses register
    accounts = [a for a in data if a.get("status") == "success"]
    log.info(f"📋 Loaded {len(accounts)} akun terregistrasi dari {filepath}")
    return accounts


def save_report(filepath: str, report: list):
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"💾 Report disimpan ke {filepath}")


def check_single_account(acc: dict) -> dict:
    email    = acc["email"]
    username = acc.get("username", "")
    password = acc["password"]

    log.info(f"\n── Checking: {email} ({username})")

    session = requests.Session()
    result = {
        "email":      email,
        "username":   username,
        "login":      False,
        "profile":    {},
        "coins":      {},
        "referrals":  {},
        "agents":     {},
        "checked_at": datetime.now().isoformat(),
    }

    # LOGIN
    login_data = login(session, email, password)
    if not login_data:
        result["login"] = False
        result["note"]  = "Login gagal – cek verifikasi email"
        return result

    result["login"] = True

    # Extract token — coba beberapa key umum
    token = (
        login_data.get("token") or
        login_data.get("accessToken") or
        login_data.get("access_token") or
        login_data.get("jwt") or
        ""
    )

    # Kalau tidak ada token eksplisit, mungkin pakai cookie session
    auth_headers = get_auth_headers(token) if token else BASE_HEADERS.copy()

    delay()

    # PROFILE
    result["profile"] = get_user_profile(session, auth_headers)
    delay()

    # COINS / CREDITS
    result["coins"] = get_coins_balance(session, auth_headers)
    delay()

    # REFERRALS
    result["referrals"] = get_referral_stats(session, auth_headers)
    delay()

    # AGENTS
    result["agents"] = get_agents(session, auth_headers)

    # Print ringkasan
    profile = result["profile"]
    coins   = result["coins"].get("data", {})

    coin_val = (
        coins.get("balance") or
        coins.get("coins") or
        coins.get("credits") or
        profile.get("coins") or
        profile.get("credits") or
        profile.get("balance") or
        "?"
    )
    log.info(f"  📊 Coin balance: {coin_val}")

    return result


def print_summary(report: list):
    log.info("\n" + "=" * 60)
    log.info("  SUMMARY COINS REPORT")
    log.info("=" * 60)
    total_coins = 0
    for r in report:
        status = "✅" if r["login"] else "❌"
        coin_val = "?"
        if r.get("coins", {}).get("data"):
            d = r["coins"]["data"]
            coin_val = d.get("balance") or d.get("coins") or d.get("credits") or "?"
        elif r.get("profile"):
            d = r["profile"]
            coin_val = d.get("coins") or d.get("credits") or d.get("balance") or "?"

        agents_count = 0
        if r.get("agents", {}).get("data"):
            ad = r["agents"]["data"]
            if isinstance(ad, list):
                agents_count = len(ad)
            elif isinstance(ad, dict):
                agents_count = ad.get("total", ad.get("count", 0))

        log.info(f"  {status} {r['email']:40s} | Coins: {str(coin_val):>8} | Agents: {agents_count}")

        try:
            total_coins += int(coin_val)
        except (ValueError, TypeError):
            pass

    log.info(f"\n  Total estimasi coins: {total_coins}")
    log.info("=" * 60)


def main():
    log.info("=" * 60)
    log.info("  Hatcher.host Account & Coin Checker")
    log.info("=" * 60)

    accounts = load_registered_accounts(ACCOUNTS_FILE)
    if not accounts:
        log.error("Tidak ada akun. Jalankan auto_register.py terlebih dahulu.")
        return

    report = []
    for idx, acc in enumerate(accounts, 1):
        log.info(f"\n[{idx}/{len(accounts)}]")
        result = check_single_account(acc)
        report.append(result)
        save_report(OUTPUT_FILE, report)  # save incremental
        if idx < len(accounts):
            delay()

    print_summary(report)
    log.info(f"\n✅ Report lengkap tersimpan di: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
