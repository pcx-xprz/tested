"""
Hatcher.host Auto Register Script
===================================
Flow:
  1. Baca daftar email dari email.txt (satu email per baris)
  2. Generate username dari potongan nama email
     contoh: hariyantipohang7128@gmail.com -> hariyantipohang
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
import sys
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
REFERRAL_CODE   = ""
EMAIL_FILE      = "email.txt"
OUTPUT_FILE     = "registered_accounts.json"
LOG_FILE        = "register.log"

BASE_API        = "https://api.hatcher.host"
DELAY_MIN       = 3    # detik antar request (anti-rate-limit)
DELAY_MAX       = 7
# ──────────────────────────────────────────────────────────────────────────────

# Fix Windows cp1252 encoding - paksa stdout ke UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Handler untuk file (UTF-8) dan console (ASCII-safe)
file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, console_handler]
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
    log.info(f"  [WAIT] Delay {t:.1f}s ...")
    time.sleep(t)


def extract_username(email: str) -> str:
    """
    Ambil nama dari local-part email, buang angka di belakang.
    Contoh:
      hariyantipohang7128@gmail.com  -> hariyantipohang
      budisantoso99@gmail.com        -> budisantoso
      siti.nur_haliza@yahoo.com      -> sitinurhaliza
    """
    local = email.split("@")[0]
    local = local.replace(".", "").replace("_", "").replace("-", "")
    local = re.sub(r"\d+$", "", local)           # buang angka di UJUNG
    local = re.sub(r"[^a-zA-Z0-9]", "", local)  # buang karakter non-alfanumerik
    local = local.lower()

    # Jika username terlalu pendek setelah trim, pakai semua local-part
    if len(local) < 3:
        local = re.sub(r"[^a-zA-Z0-9]", "", email.split("@")[0]).lower()

    return local[:30]  # max 30 karakter


def generate_password(length: int = 12) -> str:
    """
    Generate password acak:
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
            log.info(f"[OK] Referral '{ref_code}' valid: {data}")
            return True
        else:
            log.warning(f"[WARN] Referral check status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log.error(f"[ERR] Gagal validasi referral: {e}")
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
                log.info(f"  [OK] {field} '{value}' tersedia")
            else:
                log.warning(f"  [SKIP] {field} '{value}' sudah dipakai")
            return available
        else:
            log.warning(f"  [WARN] check-availability status {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log.error(f"  [ERR] Error check {field}: {e}")
        return False


def resolve_username_conflict(session: requests.Session, base_username: str) -> str:
    """
    Jika username sudah dipakai, coba tambahkan suffix angka acak.
    Max 5 percobaan.
    """
    for _ in range(5):
        suffix    = str(random.randint(10, 999))
        candidate = f"{base_username}{suffix}"[:30]
        if check_availability(session, "username", candidate):
            return candidate
        time.sleep(1)
    # Fallback: tambah timestamp pendek
    return f"{base_username}{int(time.time()) % 10000}"[:30]


def register_account(session: requests.Session, email: str, username: str, password: str) -> dict:
    """POST /auth/register -> returns dict hasil register."""
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
            log.info(f"  [SUCCESS] Register SUKSES: {email}")
            return {"status": "success", "code": r.status_code, "data": data}
        else:
            # Tangani error spesifik dari API
            error_msg = data.get("error", r.text)
            error_code = data.get("code", "")

            if "Email already registered" in str(error_msg):
                log.warning(f"  [SKIP] Email sudah terdaftar: {email}")
                return {"status": "already_exists", "code": r.status_code, "data": data}
            elif "Username" in str(error_msg) and "taken" in str(error_msg).lower():
                log.warning(f"  [SKIP] Username sudah dipakai: {username}")
                return {"status": "username_taken", "code": r.status_code, "data": data}
            else:
                log.warning(f"  [FAIL] Register GAGAL [{r.status_code}] {error_code}: {error_msg}")
                return {"status": "failed", "code": r.status_code, "data": data}
    except Exception as e:
        log.error(f"  [ERR] Exception register {email}: {e}")
        return {"status": "error", "error": str(e)}


def load_emails(filepath: str) -> list:
    """Baca file email.txt -> list of email string."""
    emails = []
    if not os.path.exists(filepath):
        log.error(f"[ERR] File '{filepath}' tidak ditemukan!")
        return emails
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "@" not in line:
                log.warning(f"[WARN] Baris {i} bukan email valid (skip): {line}")
                continue
            emails.append(line)
    log.info(f"[INFO] Loaded {len(emails)} email dari {filepath}")
    return emails


def load_results(filepath: str) -> list:
    """Load hasil register sebelumnya agar tidak double-register."""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_results(filepath: str, results: list):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    log.info(f"[SAVE] Hasil disimpan ke {filepath}")


def already_processed(results: list, email: str) -> bool:
    """Skip email yang sudah success atau already_exists."""
    for r in results:
        if r.get("email") == email and r.get("status") in ("success", "already_exists"):
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
        log.error(f"[ERR] Tidak ada email. Buat file '{EMAIL_FILE}' terlebih dahulu.")
        return

    results  = load_results(OUTPUT_FILE)
    session  = requests.Session()

    # Validasi referral code sekali di awal
    log.info("\n[STEP 0] Validasi referral code ...")
    if not validate_referral(session, REFERRAL_CODE):
        log.warning("[WARN] Referral code tidak valid, tetap lanjut proses ...")
    delay()

    success_count      = 0
    fail_count         = 0
    skip_count         = 0
    already_exist_count = 0

    for idx, email in enumerate(emails, 1):
        log.info(f"\n[{idx}/{len(emails)}] Proses: {email}")

        # Skip jika sudah berhasil / already exists sebelumnya
        if already_processed(results, email):
            log.info(f"  [SKIP] Sudah diproses sebelumnya")
            skip_count += 1
            continue

        # Generate username & password
        base_username = extract_username(email)
        password      = generate_password()
        log.info(f"  Username (base) : {base_username}")
        log.info(f"  Password        : {password}")

        # STEP 1: Cek ketersediaan email
        log.info(f"  [1/3] Cek ketersediaan email ...")
        email_available = check_availability(session, "email", email)
        delay()

        # STEP 2: Cek ketersediaan username
        log.info(f"  [2/3] Cek ketersediaan username ...")
        username = base_username
        if not check_availability(session, "username", username):
            log.info(f"  [INFO] Username '{username}' dipakai, mencari alternatif ...")
            username = resolve_username_conflict(session, base_username)
            log.info(f"  [OK] Pakai username alternatif: {username}")
        delay()

        # STEP 3: Register (tetap coba meski check-availability bilang email taken,
        # karena API check-availability tidak selalu akurat)
        log.info(f"  [3/3] Mendaftar akun ...")
        result = register_account(session, email, username, password)

        # Tentukan status final
        final_status = result["status"]

        result_entry = {
            "email":     email,
            "username":  username,
            "password":  password,
            "status":    final_status,
            "response":  result.get("data", {}),
            "timestamp": datetime.now().isoformat()
        }
        results.append(result_entry)
        save_results(OUTPUT_FILE, results)

        if final_status == "success":
            success_count += 1
            log.info(f"  [>>] Cek inbox {email} untuk link verifikasi!")
        elif final_status == "already_exists":
            already_exist_count += 1
            log.info(f"  [INFO] Email sudah pernah terdaftar sebelumnya")
        else:
            fail_count += 1

        delay()

    # ─── Summary ──────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info(f"  SELESAI")
    log.info(f"  Sukses          : {success_count}")
    log.info(f"  Sudah ada       : {already_exist_count}")
    log.info(f"  Gagal           : {fail_count}")
    log.info(f"  Skip (processed): {skip_count}")
    log.info(f"  Hasil lengkap   : {OUTPUT_FILE}")
    log.info(f"  [!] Verifikasi email MANUAL untuk setiap akun!")
    log.info(f"  [!] Buat 1 agent per akun untuk trigger 500 coin referral!")
    log.info("=" * 60)

    # Tabel ringkas akun yang berhasil
    success_accounts = [r for r in results if r.get("status") == "success"]
    if success_accounts:
        log.info(f"\n  Daftar {len(success_accounts)} akun berhasil:")
        log.info(f"  {'Email':<40} {'Username':<20} {'Password'}")
        log.info(f"  {'-'*40} {'-'*20} {'-'*15}")
        for acc in success_accounts:
            log.info(f"  {acc['email']:<40} {acc['username']:<20} {acc['password']}")


if __name__ == "__main__":
    main()
