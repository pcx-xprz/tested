"""
Hatcher.host Auto Register Script
===================================
Flow:
  1. Validasi referral code
  2. Check availability email & username
  3. POST /auth/register
  4. Simpan hasil ke registered_accounts.json
  5. Email verification MANUAL (klik link di inbox)

Format accounts.txt (satu baris per akun):
  email|username|password

Contoh:
  test1@gmail.com|username1|P@ssw0rd1
  test2@gmail.com|username2|P@ssw0rd2
"""

import requests
import json
import time
import random
import string
import logging
import os
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
REFERRAL_CODE   = "28deea96"
ACCOUNTS_FILE   = "accounts.txt"
OUTPUT_FILE     = "registered_accounts.json"
LOG_FILE        = "register.log"

BASE_API        = "https://api.hatcher.host"
DELAY_MIN       = 3    # detik antar request (anti-rate-limit)
DELAY_MAX       = 7
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

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://hatcher.host",
    "Referer": f"https://hatcher.host/register?ref={REFERRAL_CODE}",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


def delay():
    t = random.uniform(DELAY_MIN, DELAY_MAX)
    log.info(f"  ⏳ Delay {t:.1f}s ...")
    time.sleep(t)


def validate_referral(session: requests.Session, ref_code: str) -> bool:
    """Validasi referral code sebelum mulai register."""
    url = f"{BASE_API}/referrals/validate/{ref_code}"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            log.info(f"✅ Referral '{ref_code}' valid: {data}")
            return True
        else:
            log.warning(f"⚠️  Referral check status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log.error(f"❌ Gagal validasi referral: {e}")
        return False


def check_availability(session: requests.Session, field: str, value: str) -> bool:
    """
    Cek apakah email atau username tersedia.
    field: 'email' | 'username'
    """
    url = f"{BASE_API}/auth/check-availability"
    params = {field: value}
    try:
        r = session.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # API mengembalikan {available: true/false} atau {exists: false}
            available = data.get("available", not data.get("exists", False))
            if available:
                log.info(f"  ✅ {field} '{value}' tersedia")
            else:
                log.warning(f"  ⚠️  {field} '{value}' sudah dipakai")
            return available
        else:
            log.warning(f"  ⚠️  check-availability status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log.error(f"  ❌ Error check {field}: {e}")
        return False


def register_account(session: requests.Session, email: str, username: str, password: str) -> dict:
    """
    POST /auth/register
    Returns dict hasil register atau None jika gagal.
    """
    url = f"{BASE_API}/auth/register"
    payload = {
        "email": email,
        "username": username,
        "password": password,
        "referralCode": REFERRAL_CODE,
    }
    try:
        r = session.post(url, headers=HEADERS, json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code in (200, 201):
            log.info(f"  🎉 Register SUKSES: {email}")
            return {"status": "success", "code": r.status_code, "data": data}
        else:
            log.warning(f"  ❌ Register GAGAL [{r.status_code}]: {r.text}")
            return {"status": "failed", "code": r.status_code, "data": data}
    except Exception as e:
        log.error(f"  ❌ Exception register {email}: {e}")
        return {"status": "error", "error": str(e)}


def load_accounts(filepath: str) -> list:
    """Baca file accounts.txt → list of {email, username, password}."""
    accounts = []
    if not os.path.exists(filepath):
        log.error(f"File '{filepath}' tidak ditemukan!")
        return accounts
    with open(filepath, "r") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 3:
                log.warning(f"Baris {i} format salah (skip): {line}")
                continue
            accounts.append({
                "email": parts[0].strip(),
                "username": parts[1].strip(),
                "password": parts[2].strip(),
            })
    log.info(f"📋 Loaded {len(accounts)} akun dari {filepath}")
    return accounts


def load_results(filepath: str) -> list:
    """Load hasil register sebelumnya agar tidak double-register."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return []


def save_results(filepath: str, results: list):
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"💾 Hasil disimpan ke {filepath}")


def already_registered(results: list, email: str) -> bool:
    for r in results:
        if r.get("email") == email and r.get("status") == "success":
            return True
    return False


def main():
    log.info("=" * 60)
    log.info("  Hatcher.host Auto Register")
    log.info(f"  Referral Code: {REFERRAL_CODE}")
    log.info("=" * 60)

    accounts = load_accounts(ACCOUNTS_FILE)
    if not accounts:
        log.error("Tidak ada akun yang dimuat. Buat file accounts.txt terlebih dahulu.")
        return

    results = load_results(OUTPUT_FILE)
    session = requests.Session()

    # Validasi referral code sekali di awal
    log.info("\n[STEP 0] Validasi referral code ...")
    if not validate_referral(session, REFERRAL_CODE):
        log.warning("Referral code tidak valid, tapi lanjut proses...")
    delay()

    success_count = 0
    fail_count    = 0

    for idx, acc in enumerate(accounts, 1):
        email    = acc["email"]
        username = acc["username"]
        password = acc["password"]

        log.info(f"\n[{idx}/{len(accounts)}] Proses: {email}")

        # Skip jika sudah berhasil diregister sebelumnya
        if already_registered(results, email):
            log.info(f"  ⏭️  Skip (sudah terdaftar sebelumnya)")
            continue

        # STEP 1: Check email availability
        log.info(f"  [1/3] Cek ketersediaan email ...")
        if not check_availability(session, "email", email):
            result_entry = {
                "email": email, "username": username,
                "status": "failed", "reason": "email sudah dipakai",
                "timestamp": datetime.now().isoformat()
            }
            results.append(result_entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue
        delay()

        # STEP 2: Check username availability
        log.info(f"  [2/3] Cek ketersediaan username ...")
        if not check_availability(session, "username", username):
            result_entry = {
                "email": email, "username": username,
                "status": "failed", "reason": "username sudah dipakai",
                "timestamp": datetime.now().isoformat()
            }
            results.append(result_entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue
        delay()

        # STEP 3: Register
        log.info(f"  [3/3] Mendaftar akun ...")
        result = register_account(session, email, username, password)

        result_entry = {
            "email":     email,
            "username":  username,
            "password":  password,
            "status":    result["status"],
            "response":  result.get("data", {}),
            "timestamp": datetime.now().isoformat()
        }
        results.append(result_entry)
        save_results(OUTPUT_FILE, results)

        if result["status"] == "success":
            success_count += 1
            log.info(f"  📧 Cek inbox {email} untuk link verifikasi!")
        else:
            fail_count += 1

        delay()

    # Summary
    log.info("\n" + "=" * 60)
    log.info(f"  SELESAI: {success_count} sukses | {fail_count} gagal")
    log.info(f"  Hasil lengkap: {OUTPUT_FILE}")
    log.info(f"  ⚠️  Verifikasi email MANUAL untuk setiap akun!")
    log.info(f"  ⚠️  Buat 1 agent per akun untuk trigger 500 coin referral!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
