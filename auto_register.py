"""
Hatcher.host Auto Register Script  v2
=======================================
Flow BARU (fully automated):
  1. Generate email temporer dari TempMail.lol API (POST /v2/inbox/create)
  2. Generate username dari prefix email
  3. Generate password acak yang kuat
  4. Validasi referral code
  5. Check availability email & username
  6. POST /auth/register ke hatcher.host
  7. Poll inbox tempmail sampai email verifikasi masuk (GET /v2/inbox?token=xxx)
  8. Ekstrak link verifikasi & hit endpoint verify otomatis
  9. Simpan hasil ke registered_accounts.json

Tidak perlu email.txt lagi — semua otomatis!

Install:
  pip install requests tempmail-lol
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
REFERRAL_CODE    = ""                        # isi referral code kamu di sini
NUM_ACCOUNTS     = 10                        # jumlah akun yang mau dibuat
OUTPUT_FILE      = "registered_accounts.json"
LOG_FILE         = "register.log"

BASE_API         = "https://api.hatcher.host"
TEMPMAIL_API     = "https://api.tempmail.lol/v2"  # TempMail.lol v2 API
TEMPMAIL_HEADERS = {
    "User-Agent": "TempMailPythonAPI/3.0",
    "Accept":     "application/json",
    "Content-Type": "application/json",
}

DELAY_MIN        = 3    # detik antar request (anti-rate-limit)
DELAY_MAX        = 6
VERIFY_POLL_SEC  = 5    # interval cek inbox (detik)
VERIFY_TIMEOUT   = 90   # max tunggu email verifikasi (detik)
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


# ─────────────────────────────────────────────────────────────────────────────
# TEMPMAIL.LOL — Generate & Poll Inbox
# ─────────────────────────────────────────────────────────────────────────────

def tempmail_create(session: requests.Session) -> dict:
    """
    POST /v2/inbox/create → { address, token }
    Return dict atau None jika gagal.
    """
    url = f"{TEMPMAIL_API}/inbox/create"
    try:
        r = session.post(url, headers=TEMPMAIL_HEADERS, json={"domain": None, "prefix": None}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            log.info(f"  [TEMPMAIL] Email: {data['address']}")
            return data   # { "address": "...", "token": "..." }
        else:
            log.warning(f"  [TEMPMAIL] Create gagal {r.status_code}: {r.text[:100]}")
            return None
    except Exception as e:
        log.error(f"  [TEMPMAIL] Exception create: {e}")
        return None


def tempmail_get_emails(session: requests.Session, token: str) -> list:
    """
    GET /v2/inbox?token=xxx → list of email dicts
    """
    url = f"{TEMPMAIL_API}/inbox?token={token}"
    try:
        r = session.get(url, headers=TEMPMAIL_HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("expired"):
                log.warning("  [TEMPMAIL] Token expired!")
                return []
            return data.get("emails") or []
        else:
            log.warning(f"  [TEMPMAIL] GetEmails {r.status_code}: {r.text[:80]}")
            return []
    except Exception as e:
        log.error(f"  [TEMPMAIL] Exception getEmails: {e}")
        return []


def tempmail_wait_verify(session: requests.Session, token: str) -> str:
    """
    Poll inbox sampai ada email verifikasi dari hatcher.host.
    Return link verifikasi (str) atau None jika timeout.
    """
    log.info(f"  [TEMPMAIL] Menunggu email verifikasi (max {VERIFY_TIMEOUT}s)...")
    waited = 0
    while waited < VERIFY_TIMEOUT:
        emails = tempmail_get_emails(session, token)
        for mail in emails:
            subject = mail.get("subject", "")
            body    = mail.get("body", "") + (mail.get("html") or "")
            # Cari link verifikasi dari hatcher.host
            links = re.findall(r"https?://[^\s\"'<>]+verify[^\s\"'<>]*", body, re.IGNORECASE)
            if not links:
                links = re.findall(r"https?://api\.hatcher\.host[^\s\"'<>]+", body, re.IGNORECASE)
            if not links:
                links = re.findall(r"https?://hatcher\.host[^\s\"'<>]+", body, re.IGNORECASE)
            if links:
                log.info(f"  [TEMPMAIL] Email masuk: '{subject}'")
                log.info(f"  [TEMPMAIL] Link verifikasi: {links[0]}")
                return links[0]
        time.sleep(VERIFY_POLL_SEC)
        waited += VERIFY_POLL_SEC
        log.info(f"  [TEMPMAIL] Belum ada email ({waited}s/{VERIFY_TIMEOUT}s)...")

    log.warning("  [TEMPMAIL] Timeout — email verifikasi tidak masuk!")
    return None


def do_verify(session: requests.Session, verify_link: str) -> bool:
    """
    Hit link verifikasi.
    Bisa berupa redirect ke hatcher.host atau langsung API endpoint.
    """
    if not verify_link:
        return False
    try:
        r = session.get(verify_link, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code in (200, 201, 302):
            log.info(f"  [VERIFY] Berhasil! Status {r.status_code}")
            return True
        else:
            log.warning(f"  [VERIFY] Status {r.status_code}: {r.text[:100]}")
            return False
    except Exception as e:
        log.error(f"  [VERIFY] Exception: {e}")
        return False


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


def main():
    log.info("=" * 60)
    log.info("  Hatcher.host Auto Register  v2 (TempMail.lol)")
    log.info(f"  Referral Code  : {REFERRAL_CODE or '(kosong)'}")
    log.info(f"  Jumlah akun    : {NUM_ACCOUNTS}")
    log.info(f"  TempMail API   : {TEMPMAIL_API}")
    log.info("=" * 60)

    results       = load_results(OUTPUT_FILE)
    session       = requests.Session()
    success_count = 0
    fail_count    = 0

    # Validasi referral sekali di awal
    if REFERRAL_CODE:
        log.info("\n[STEP 0] Validasi referral code ...")
        validate_referral(session, REFERRAL_CODE)
        delay()

    for idx in range(1, NUM_ACCOUNTS + 1):
        log.info(f"\n{'='*60}")
        log.info(f"[{idx}/{NUM_ACCOUNTS}] Membuat akun baru ...")

        # ── STEP 1: Generate TempMail ──────────────────────────────────
        log.info("  [1/5] Generate email temporer (TempMail.lol) ...")
        inbox = tempmail_create(session)
        if not inbox:
            log.error("  [FAIL] Tidak bisa buat email temporer, skip akun ini.")
            fail_count += 1
            delay()
            continue

        email = inbox["address"]
        token = inbox["token"]
        delay()

        # ── STEP 2: Generate username & password ───────────────────────
        base_username = extract_username(email)
        password      = generate_password()
        log.info(f"  Username (base) : {base_username}")
        log.info(f"  Password        : {password}")

        # ── STEP 3: Cek availability & resolve conflict ────────────────
        log.info("  [2/5] Cek ketersediaan username ...")
        username = base_username
        if not check_availability(session, "username", username):
            username = resolve_username_conflict(session, base_username)
            log.info(f"  [OK] Pakai username alternatif: {username}")
        delay()

        # ── STEP 4: Register ───────────────────────────────────────────
        log.info("  [3/5] Register akun ...")
        result = register_account(session, email, username, password)

        if result["status"] not in ("success", "already_exists"):
            log.warning(f"  [FAIL] Register gagal: {result}")
            results.append({
                "email": email, "username": username, "password": password,
                "status": result["status"], "response": result.get("data", {}),
                "timestamp": datetime.now().isoformat()
            })
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue

        # ── STEP 5: Tunggu & Verifikasi email ──────────────────────────
        log.info("  [4/5] Menunggu email verifikasi ...")
        verify_link = tempmail_wait_verify(session, token)

        verified = False
        if verify_link:
            log.info("  [5/5] Hit link verifikasi ...")
            verified = do_verify(session, verify_link)
        else:
            log.warning("  [5/5] Link verifikasi tidak ditemukan — akun tetap disimpan (verifikasi manual)")

        # ── Simpan ─────────────────────────────────────────────────────
        entry = {
            "email":       email,
            "username":    username,
            "password":    password,
            "status":      "success",
            "verified":    verified,
            "verify_link": verify_link,
            "response":    result.get("data", {}),
            "timestamp":   datetime.now().isoformat()
        }
        results.append(entry)
        save_results(OUTPUT_FILE, results)
        success_count += 1

        status_str = "✓ VERIFIED" if verified else "~ UNVERIFIED"
        log.info(f"  [{status_str}] Akun selesai: {email}")
        delay()

    # ─── Summary ──────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("  SELESAI")
    log.info(f"  Sukses  : {success_count}")
    log.info(f"  Gagal   : {fail_count}")
    log.info(f"  Output  : {OUTPUT_FILE}")
    log.info("=" * 60)

    ok = [r for r in results if r.get("status") == "success"]
    if ok:
        log.info(f"\n  {'Email':<35} {'Username':<20} {'Verified'}")
        log.info(f"  {'-'*35} {'-'*20} {'-'*8}")
        for acc in ok[-success_count:]:
            v = "YES" if acc.get("verified") else "NO"
            log.info(f"  {acc['email']:<35} {acc['username']:<20} {v}")


if __name__ == "__main__":
    main()
