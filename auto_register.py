"""
Hatcher.host Auto Register Script
===================================
Flow:
  1. Baca daftar email dari email.txt (satu email per baris)
  2. Generate username dari potongan nama email
     contoh: hariyantipohang7128@gmail.com → hariyantipohang
  3. Generate password acak yang kuat
  4. Validasi referral code
  5. Check availability email & username
  6. POST /auth/register
  7. Simpan hasil ke registered_accounts.json (email, username, password)
  8. Email verification MANUAL (klik link di inbox)

Format email.txt:
  hariyantipohang7128@gmail.com
  budisantoso99@gmail.com
  sitinurhaliza2024@yahoo.com
"""

import requests
import json
import time
import random
import string
import re
import logging
import os
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
REFERRAL_CODE   = "28deea96"
EMAIL_FILE      = "email.txt"
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


def extract_username(email: str) -> str:
    """
    Ambil nama dari local-part email, buang angka di belakang.
    Contoh:
      hariyantipohang7128@gmail.com  → hariyantipohang
      budisantoso99@gmail.com        → budisantoso
      siti.nur_haliza@yahoo.com      → sitinurhaliza
    """
    local = email.split("@")[0]                  # ambil sebelum @
    local = local.replace(".", "").replace("_", "").replace("-", "")  # buang pemisah
    local = re.sub(r"\d+$", "", local)           # buang angka di UJUNG
    local = re.sub(r"[^a-zA-Z0-9]", "", local)  # buang karakter non-alfanumerik
    local = local.lower()

    # Jika username terlalu pendek setelah trim, pakai semua local-part
    if len(local) < 3:
        local = re.sub(r"[^a-zA-Z0-9]", "", email.split("@")[0]).lower()

    return local[:30]  # max 30 karakter


def generate_password(length: int = 12) -> str:
    """
    Generate password acak yang memenuhi syarat umum:
    - Minimal 1 huruf besar
    - Minimal 1 huruf kecil
    - Minimal 1 angka
    - Minimal 1 karakter spesial
    """
    lower   = random.choices(string.ascii_lowercase, k=4)
    upper   = random.choices(string.ascii_uppercase, k=3)
    digits  = random.choices(string.digits, k=3)
    special = random.choices("@#$!%*?&", k=2)

    all_chars = lower + upper + digits + special
    random.shuffle(all_chars)
    return "".join(all_chars)


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


def resolve_username_conflict(session: requests.Session, base_username: str) -> str:
    """
    Jika username sudah dipakai, coba tambahkan suffix angka acak
    sampai dapat yang tersedia. Max 5 percobaan.
    """
    for _ in range(5):
        suffix   = str(random.randint(10, 999))
        candidate = f"{base_username}{suffix}"[:30]
        if check_availability(session, "username", candidate):
            return candidate
        time.sleep(1)
    # Fallback: tambah timestamp pendek
    return f"{base_username}{int(time.time()) % 10000}"[:30]


def register_account(session: requests.Session, email: str, username: str, password: str) -> dict:
    """POST /auth/register → returns dict hasil register."""
    url = f"{BASE_API}/auth/register"
    payload = {
        "email":        email,
        "username":     username,
        "password":     password,
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


def load_emails(filepath: str) -> list:
    """Baca file email.txt → list of email string."""
    emails = []
    if not os.path.exists(filepath):
        log.error(f"File '{filepath}' tidak ditemukan!")
        return emails
    with open(filepath, "r") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "@" not in line:
                log.warning(f"Baris {i} bukan email valid (skip): {line}")
                continue
            emails.append(line)
    log.info(f"📋 Loaded {len(emails)} email dari {filepath}")
    return emails


def load_results(filepath: str) -> list:
    """Load hasil register sebelumnya agar tidak double-register."""
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
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
    log.info(f"  Referral Code : {REFERRAL_CODE}")
    log.info(f"  Email source  : {EMAIL_FILE}")
    log.info("=" * 60)

    emails = load_emails(EMAIL_FILE)
    if not emails:
        log.error(f"Tidak ada email. Buat file '{EMAIL_FILE}' terlebih dahulu.")
        return

    results = load_results(OUTPUT_FILE)
    session = requests.Session()

    # Validasi referral code sekali di awal
    log.info("\n[STEP 0] Validasi referral code ...")
    if not validate_referral(session, REFERRAL_CODE):
        log.warning("Referral code tidak valid, tetap lanjut proses ...")
    delay()

    success_count = 0
    fail_count    = 0

    for idx, email in enumerate(emails, 1):
        log.info(f"\n[{idx}/{len(emails)}] Proses: {email}")

        # Skip jika sudah berhasil diregister sebelumnya
        if already_registered(results, email):
            log.info(f"  ⏭️  Skip (sudah terdaftar sebelumnya)")
            continue

        # Generate username & password
        base_username = extract_username(email)
        password      = generate_password()
        log.info(f"  🔤 Username (base): {base_username}")
        log.info(f"  🔑 Password       : {password}")

        # STEP 1: Cek ketersediaan email
        log.info(f"  [1/3] Cek ketersediaan email ...")
        if not check_availability(session, "email", email):
            result_entry = {
                "email":     email,
                "username":  base_username,
                "password":  password,
                "status":    "failed",
                "reason":    "email sudah dipakai",
                "timestamp": datetime.now().isoformat()
            }
            results.append(result_entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue
        delay()

        # STEP 2: Cek ketersediaan username
        log.info(f"  [2/3] Cek ketersediaan username ...")
        username = base_username
        if not check_availability(session, "username", username):
            log.info(f"  🔄 Username '{username}' dipakai, mencari alternatif ...")
            username = resolve_username_conflict(session, base_username)
            log.info(f"  ✅ Pakai username alternatif: {username}")
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

    # ─── Summary ──────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info(f"  SELESAI: {success_count} sukses | {fail_count} gagal")
    log.info(f"  Hasil lengkap : {OUTPUT_FILE}")
    log.info(f"  ⚠️  Verifikasi email MANUAL untuk setiap akun!")
    log.info(f"  ⚠️  Buat 1 agent per akun untuk trigger 500 coin referral!")
    log.info("=" * 60)

    # Print tabel ringkas akun yang berhasil
    success_accounts = [r for r in results if r.get("status") == "success"]
    if success_accounts:
        log.info("\n  📋 Daftar akun berhasil:")
        log.info(f"  {'Email':<40} {'Username':<20} {'Password'}")
        log.info(f"  {'-'*40} {'-'*20} {'-'*15}")
        for acc in success_accounts:
            log.info(f"  {acc['email']:<40} {acc['username']:<20} {acc['password']}")


if __name__ == "__main__":
    main()
