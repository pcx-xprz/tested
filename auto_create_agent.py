"""
Hatcher.host Auto Create Agent
=================================
Baca registered_accounts.json -> login tiap akun -> buat 1 agent per akun

Flow per akun:
  1. Login  POST /auth/login           -> dapat token JWT
  2. Create POST /agents               -> buat agent (status: paused)
  3. Start  POST /agents/{id}/start    -> jalankan container (status: active)
  4. Config PATCH /agents/{id}         -> set systemPrompt, model, description
  5. Simpan hasil ke agent_results.json

Support 2 format registered_accounts.json:

Format LAMA:
  { "email": "...", "username": "...", "password": "...", "status": "success",
    "response": { "success": true, "data": { "token": "...", "user": {...} } } }

Format BARU (dari auto_register.py v2 + TempMail):
  { "email": "...", "username": "...", "password": "...", "status": "success",
    "verified": true, "verify_link": "https://...", "proxy": "direct",
    "response": { "success": true, "data": { "token": "...", "user": {...} } },
    "timestamp": "2026-..." }
"""

import requests
import json
import time
import random
import logging
import os
import sys
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
INPUT_FILE   = "registered_accounts.json"   # hasil dari auto_register.py
OUTPUT_FILE  = "agent_results.json"         # hasil pembuatan agent
LOG_FILE     = "agent_create.log"

BASE_API     = "https://api.hatcher.host"
DELAY_MIN    = 3     # detik antar akun (anti rate-limit)
DELAY_MAX    = 7

# Template agent default — bisa diganti sesuai kebutuhan
AGENT_NAME_TEMPLATE  = "{username} agent"   # {username} diganti otomatis
AGENT_DESCRIPTION    = "Auto-created AI agent"
AGENT_SYSTEM_PROMPT  = (
    "You are a helpful and friendly AI assistant. "
    "Answer questions clearly and concisely."
)
AGENT_MODEL          = "gpt-4o-mini"        # model yang tersedia di hatcher
AGENT_IS_PUBLIC      = True
# ──────────────────────────────────────────────────────────────────────────────

# Fix encoding Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, console_handler]
)
log = logging.getLogger(__name__)

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://hatcher.host",
    "Referer":      "https://hatcher.host/create",
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


def auth_headers(token: str) -> dict:
    h = BASE_HEADERS.copy()
    h["Authorization"] = f"Bearer {token}"
    return h


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Login
# ─────────────────────────────────────────────────────────────────────────────
def login(session: requests.Session, email: str, password: str):
    """
    POST /auth/login
    Returns dict: { token, refreshToken, user }  atau None jika gagal
    """
    url = f"{BASE_API}/auth/login"
    payload = {"email": email, "password": password}
    try:
        r = session.post(url, headers=BASE_HEADERS, json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            token = data["data"]["token"]
            user  = data["data"]["user"]
            log.info(f"  [OK] Login sukses: {email} (id={user['id']})")
            return {
                "token":        token,
                "refreshToken": data["data"].get("refreshToken"),
                "user":         user
            }
        else:
            err = data.get("error", r.text)
            log.warning(f"  [FAIL] Login gagal [{r.status_code}]: {err}")
            return None
    except Exception as e:
        log.error(f"  [ERR] Login exception: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Create Agent
# ─────────────────────────────────────────────────────────────────────────────
def create_agent(session: requests.Session, token: str, username: str):
    """
    POST /agents
    Body: { name, prompt (opsional), isPublic }
    Returns agent dict atau None
    """
    url     = f"{BASE_API}/agents"
    name    = AGENT_NAME_TEMPLATE.format(username=username)
    payload = {
        "name":     name,
        "isPublic": AGENT_IS_PUBLIC,
    }
    try:
        r = session.post(url, headers=auth_headers(token), json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code in (200, 201) and data.get("success"):
            agent = data["data"]
            log.info(f"  [OK] Agent dibuat: '{agent['name']}' (id={agent['id']})")
            return agent
        else:
            err = data.get("error", r.text)
            log.warning(f"  [FAIL] Create agent gagal [{r.status_code}]: {err}")
            return None
    except Exception as e:
        log.error(f"  [ERR] Create agent exception: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Start Agent (Hatch)
# ─────────────────────────────────────────────────────────────────────────────
def start_agent(session: requests.Session, token: str, agent_id: str) -> bool:
    """
    POST /agents/{id}/start
    Memulai container agent (setara klik 'Hatch This Agent')
    """
    url = f"{BASE_API}/agents/{agent_id}/start"
    try:
        r = session.post(url, headers=auth_headers(token), json={}, timeout=30)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            status      = data["data"].get("status", "unknown")
            container   = data["data"].get("containerId", "")[:20]
            log.info(f"  [OK] Agent started: status={status}, container={container}...")
            return True
        else:
            err = data.get("error", r.text)
            log.warning(f"  [FAIL] Start agent gagal [{r.status_code}]: {err}")
            return False
    except Exception as e:
        log.error(f"  [ERR] Start agent exception: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Configure Agent
# ─────────────────────────────────────────────────────────────────────────────
def configure_agent(session: requests.Session, token: str, agent_id: str, username: str) -> bool:
    """
    PATCH /agents/{id}
    Set systemPrompt, model, description setelah agent berjalan.
    """
    url     = f"{BASE_API}/agents/{agent_id}"
    payload = {
        "description": AGENT_DESCRIPTION,
        "config": {
            "systemPrompt": AGENT_SYSTEM_PROMPT,
            "model":        AGENT_MODEL,
        },
        "isPublic": AGENT_IS_PUBLIC,
    }
    try:
        r = session.patch(url, headers=auth_headers(token), json=payload, timeout=20)
        data = r.json() if r.content else {}
        if r.status_code == 200 and data.get("success"):
            log.info(f"  [OK] Agent dikonfigurasi: model={AGENT_MODEL}")
            return True
        else:
            err = data.get("error", r.text)
            log.warning(f"  [WARN] Config agent gagal [{r.status_code}]: {err}")
            return False
    except Exception as e:
        log.error(f"  [ERR] Configure agent exception: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def extract_token_from_response(acc: dict) -> str:
    """
    Ambil JWT token dari field response jika ada,
    untuk dipakai langsung tanpa perlu login ulang.

    Support 2 format:
      Format lama : response.data.token
      Format baru : response.data.token  (sama, tapi ada field verified/proxy)
    """
    try:
        return acc["response"]["data"]["token"]
    except (KeyError, TypeError):
        return None


def is_verified(acc: dict) -> bool:
    """
    Cek apakah akun sudah terverifikasi emailnya.
    Support field 'verified' (format baru) dan fallback ke emailVerified dari JWT.
    """
    # Format baru: field 'verified' langsung di root
    if "verified" in acc:
        return bool(acc["verified"])
    # Cek dari response data (format lama tidak ada info ini)
    return False


def load_accounts(filepath: str) -> list:
    """
    Load akun dari registered_accounts.json.
    Support format lama (tanpa verified/proxy) dan format baru (dengan verified/proxy).

    Filter:
      - status == "success" wajib
      - verified boleh True atau False (keduanya diproses)
        → akun unverified tetap diproses, login akan handle sendiri
    """
    if not os.path.exists(filepath):
        log.error(f"[ERR] File '{filepath}' tidak ditemukan!")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            log.error(f"[ERR] JSON error di '{filepath}': {e}")
            return []

    total     = len(data)
    accounts  = [a for a in data if a.get("status") == "success"]
    verified  = sum(1 for a in accounts if is_verified(a))
    unverified = len(accounts) - verified

    log.info(f"[INFO] {len(accounts)} akun status=success dari {total} total")
    log.info(f"[INFO]   Verified   : {verified}")
    log.info(f"[INFO]   Unverified : {unverified}  (tetap diproses, login bisa tetap berhasil)")
    return accounts


def load_results(filepath: str) -> list:
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


def already_created(results: list, email: str) -> bool:
    """Skip akun yang sudah punya agent berhasil dibuat sebelumnya."""
    for r in results:
        if r.get("email") == email and r.get("agent_status") == "active":
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("  Hatcher.host Auto Create Agent")
    log.info(f"  Input  : {INPUT_FILE}")
    log.info(f"  Output : {OUTPUT_FILE}")
    log.info("=" * 60)

    accounts = load_accounts(INPUT_FILE)
    if not accounts:
        log.error("[ERR] Tidak ada akun. Jalankan auto_register.py terlebih dahulu.")
        return

    results       = load_results(OUTPUT_FILE)
    session       = requests.Session()

    ok_count      = 0
    fail_count    = 0
    skip_count    = 0

    for idx, acc in enumerate(accounts, 1):
        email    = acc.get("email", "")
        username = acc.get("username", "")
        password = acc.get("password", "")

        # ── Info tambahan dari format baru ─────────────────────────────────
        verified     = is_verified(acc)
        verify_link  = acc.get("verify_link", "")
        proxy_used   = acc.get("proxy", "direct")
        saved_token  = extract_token_from_response(acc)  # JWT dari register

        log.info(f"\n[{idx}/{len(accounts)}] Proses akun: {email}")
        log.info(f"  Verified  : {'YES' if verified else 'NO'}")
        log.info(f"  Proxy     : {proxy_used}")
        if not verified:
            log.warning(f"  [WARN] Akun belum verified — login mungkin berhasil tapi emailVerified=false")

        # Skip jika sudah berhasil
        if already_created(results, email):
            log.info("  [SKIP] Agent sudah dibuat sebelumnya")
            skip_count += 1
            continue

        entry = {
            "email":        email,
            "username":     username,
            "verified":     verified,
            "proxy":        proxy_used,
            "timestamp":    datetime.now().isoformat(),
            "agent_status": "pending",
        }

        # ── STEP 1: Login ──────────────────────────────────────────────────
        log.info("  [1/4] Login ...")
        auth = login(session, email, password)
        if not auth:
            entry["agent_status"] = "login_failed"
            results.append(entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue

        token    = auth["token"]
        user_id  = auth["user"]["id"]
        entry["user_id"] = user_id
        delay()

        # ── STEP 2: Create Agent ───────────────────────────────────────────
        log.info("  [2/4] Membuat agent ...")
        agent = create_agent(session, token, username)
        if not agent:
            entry["agent_status"] = "create_failed"
            results.append(entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue

        agent_id   = agent["id"]
        agent_name = agent["name"]
        agent_slug = agent["slug"]

        entry["agent_id"]   = agent_id
        entry["agent_name"] = agent_name
        entry["agent_slug"] = agent_slug
        entry["agent_url"]  = f"https://hatcher.host/agent/{agent_slug}"
        delay()

        # ── STEP 3: Start / Hatch Agent ────────────────────────────────────
        log.info("  [3/4] Menjalankan agent (hatch) ...")
        started = start_agent(session, token, agent_id)
        if not started:
            entry["agent_status"] = "start_failed"
            results.append(entry)
            save_results(OUTPUT_FILE, results)
            fail_count += 1
            delay()
            continue

        # Tunggu sebentar agar container siap
        log.info("  [INFO] Menunggu container siap (5s) ...")
        time.sleep(5)

        # ── STEP 4: Configure Agent ────────────────────────────────────────
        log.info("  [4/4] Mengkonfigurasi agent ...")
        configured = configure_agent(session, token, agent_id, username)

        entry["agent_status"]     = "active"
        entry["agent_configured"] = configured

        results.append(entry)
        save_results(OUTPUT_FILE, results)
        ok_count += 1

        log.info(f"  [SUCCESS] Agent aktif!")
        log.info(f"  URL: https://hatcher.host/agent/{agent_slug}")
        delay()

    # ─── Summary ──────────────────────────────────────────────────────────────
    log.info("\n" + "=" * 60)
    log.info("  SELESAI")
    log.info(f"  Agent berhasil dibuat : {ok_count}")
    log.info(f"  Gagal                 : {fail_count}")
    log.info(f"  Skip (sudah ada)      : {skip_count}")
    log.info(f"  Hasil lengkap         : {OUTPUT_FILE}")
    log.info("=" * 60)

    # Tampilkan tabel hasil
    active = [r for r in results if r.get("agent_status") == "active"]
    if active:
        log.info(f"\n  Daftar {len(active)} agent aktif:")
        log.info(f"  {'Email':<35} {'Verified':<10} {'Agent URL'}")
        log.info(f"  {'-'*35} {'-'*10} {'-'*45}")
        for r in active:
            v = "YES" if r.get("verified") else "NO"
            log.info(f"  {r['email']:<35} {v:<10} {r.get('agent_url', '-')}")


if __name__ == "__main__":
    main()
