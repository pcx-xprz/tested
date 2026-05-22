"""
Hatcher.host Auto Create Agent
=================================
Baca registered_accounts.json -> login tiap akun -> buat 1 agent per akun

Flow per akun:
  1. Buat session requests dengan proxy dari akun (jika ada)
  2. Login  POST /auth/login           -> dapat token JWT
  3. Create POST /agents               -> buat agent (status: paused)
  4. Start  POST /agents/{id}/start    -> jalankan container (status: active)
  5. Config PATCH /agents/{id}         -> set systemPrompt, model, description
  6. Simpan hasil ke agent_results.json

Support 2 format registered_accounts.json:

Format LAMA:
  { "email": "...", "username": "...", "password": "...", "status": "success",
    "response": { "success": true, "data": { "token": "...", "user": {...} } } }

Format BARU (dari auto_register.py v2 + TempMail):
  { "email": "...", "username": "...", "password": "...", "status": "success",
    "verified": true, "verify_link": "https://...", "proxy": "1.2.3.4:8080",
    "response": { "success": true, "data": { "token": "...", "user": {...} } },
    "timestamp": "2026-..." }

Format proxy yang didukung di field "proxy":
  - "direct"                       → tidak pakai proxy
  - "1.2.3.4:8080"                 → HTTP proxy
  - "http://1.2.3.4:8080"          → HTTP proxy (eksplisit)
  - "https://1.2.3.4:8080"         → HTTPS proxy
  - "socks5://1.2.3.4:1080"        → SOCKS5 proxy
  - "socks4://1.2.3.4:1080"        → SOCKS4 proxy
  - "http://user:pass@1.2.3.4:80"  → HTTP proxy dengan auth
  - "socks5://user:pass@1.2.3.4:1080" → SOCKS5 dengan auth
"""

import requests
import json
import time
import random
import logging
import os
import re
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
# PROXY HANDLER
# ─────────────────────────────────────────────────────────────────────────────
def parse_proxy(proxy_str: str) -> dict:
    """
    Parse string proxy menjadi dict requests-compatible.

    Input contoh:
      "direct"                          → {} (tidak pakai proxy)
      "1.2.3.4:8080"                    → http & https proxy
      "http://1.2.3.4:8080"             → http & https proxy
      "https://1.2.3.4:8080"            → http & https proxy
      "socks5://1.2.3.4:1080"           → socks5 proxy
      "socks4://1.2.3.4:1080"           → socks4 proxy
      "http://user:pass@1.2.3.4:8080"   → http proxy dengan auth
      "socks5://user:pass@1.2.3.4:1080" → socks5 proxy dengan auth

    Output: dict { "http": "...", "https": "..." } atau {}
    """
    if not proxy_str or proxy_str.strip().lower() in ("", "direct", "none", "no"):
        return {}

    proxy_str = proxy_str.strip()

    # Jika tidak ada scheme, default ke http://
    if not re.match(r"^(http|https|socks4|socks5)://", proxy_str, re.IGNORECASE):
        proxy_str = f"http://{proxy_str}"

    scheme = proxy_str.split("://")[0].lower()

    if scheme in ("socks5", "socks4"):
        # SOCKS proxy — dipakai untuk http dan https
        return {
            "http":  proxy_str,
            "https": proxy_str,
        }
    else:
        # HTTP/HTTPS proxy
        return {
            "http":  proxy_str,
            "https": proxy_str,
        }


def build_session(proxy_str: str) -> requests.Session:
    """
    Buat requests.Session baru dengan proxy dari string.
    Setiap akun dapat session TERPISAH dengan proxy masing-masing.
    """
    session = requests.Session()
    proxies = parse_proxy(proxy_str)

    if proxies:
        session.proxies.update(proxies)
        log.info(f"  [PROXY] Menggunakan proxy: {proxy_str}")
    else:
        log.info(f"  [PROXY] Direct connection (tanpa proxy)")

    return session


def test_proxy(session: requests.Session, proxy_str: str) -> bool:
    """
    Quick test apakah proxy bisa dipakai.
    Cek ke endpoint yang ringan, timeout pendek.
    """
    if not proxy_str or proxy_str.strip().lower() in ("", "direct", "none", "no"):
        return True  # direct connection, skip test
    try:
        r = session.get(
            "http://api.ipify.org",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            log.info(f"  [PROXY] Test OK — IP via proxy: {r.text.strip()}")
            return True
        return False
    except Exception as e:
        log.warning(f"  [PROXY] Test GAGAL: {str(e)[:80]}")
        return False


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
            status    = data["data"].get("status", "unknown")
            container = data["data"].get("containerId", "")[:20]
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
    """Ambil JWT token dari field response jika ada."""
    try:
        return acc["response"]["data"]["token"]
    except (KeyError, TypeError):
        return None


def is_verified(acc: dict) -> bool:
    """Cek apakah akun sudah terverifikasi emailnya."""
    if "verified" in acc:
        return bool(acc["verified"])
    return False


def load_accounts(filepath: str) -> list:
    """
    Load akun dari registered_accounts.json.
    Support format lama dan baru (dengan verified/proxy/verify_link).

    Status yang diterima (semua dianggap akun valid siap diproses):
      - "success"   → register berhasil (belum tentu verified)
      - "verified"  → register + email sudah verified
    Status yang dilewati:
      - "failed", "error", "already_exists", dll
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

    # ✅ Terima status "success" DAN "verified"
    VALID_STATUSES = {"success", "verified"}

    total      = len(data)
    accounts   = [a for a in data if a.get("status") in VALID_STATUSES]
    skipped    = total - len(accounts)
    verified   = sum(1 for a in accounts if is_verified(a))
    unverified = len(accounts) - verified

    # Hitung berapa yang punya proxy
    with_proxy    = sum(1 for a in accounts
                        if a.get("proxy", "direct").lower() not in ("", "direct", "none", "no"))
    without_proxy = len(accounts) - with_proxy

    log.info(f"[INFO] {len(accounts)} akun valid dari {total} total  ({skipped} dilewati)")
    log.info(f"[INFO]   Verified        : {verified}")
    log.info(f"[INFO]   Unverified      : {unverified}")
    log.info(f"[INFO]   Pakai proxy     : {with_proxy}")
    log.info(f"[INFO]   Direct          : {without_proxy}")

    # Tampilkan daftar status yang ada untuk debug
    status_counts: dict = {}
    for a in data:
        s = a.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1
    log.info(f"[INFO]   Breakdown status: {status_counts}")

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

    results    = load_results(OUTPUT_FILE)
    ok_count   = 0
    fail_count = 0
    skip_count = 0

    for idx, acc in enumerate(accounts, 1):
        email      = acc.get("email", "")
        username   = acc.get("username", "")
        password   = acc.get("password", "")
        verified   = is_verified(acc)
        proxy_str  = acc.get("proxy", "direct")

        log.info(f"\n[{idx}/{len(accounts)}] {'='*50}")
        log.info(f"  Email     : {email}")
        log.info(f"  Verified  : {'YES' if verified else 'NO'}")
        log.info(f"  Proxy     : {proxy_str}")

        if not verified:
            log.warning("  [WARN] Akun belum verified — emailVerified=false di hatcher")

        # Skip jika sudah berhasil
        if already_created(results, email):
            log.info("  [SKIP] Agent sudah dibuat sebelumnya")
            skip_count += 1
            continue

        # ── Buat session dengan proxy akun ─────────────────────────────────
        # Setiap akun pakai session BARU agar proxy tidak tercampur
        session = build_session(proxy_str)

        # Test proxy dulu sebelum lanjut (skip jika direct)
        is_direct = proxy_str.strip().lower() in ("", "direct", "none", "no")
        if not is_direct:
            log.info("  [PROXY] Test koneksi proxy ...")
            proxy_ok = test_proxy(session, proxy_str)
            if not proxy_ok:
                log.warning("  [WARN] Proxy tidak response — tetap lanjut (mungkin restrict ip-api.com)")

        entry = {
            "email":        email,
            "username":     username,
            "verified":     verified,
            "proxy":        proxy_str,
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

        token   = auth["token"]
        user_id = auth["user"]["id"]
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

    active = [r for r in results if r.get("agent_status") == "active"]
    if active:
        log.info(f"\n  Daftar {len(active)} agent aktif:")
        log.info(f"  {'Email':<35} {'Verified':<10} {'Proxy':<22} {'Agent URL'}")
        log.info(f"  {'-'*35} {'-'*10} {'-'*22} {'-'*40}")
        for r in active:
            v     = "YES" if r.get("verified") else "NO"
            proxy = (r.get("proxy") or "direct")[:20]
            log.info(f"  {r['email']:<35} {v:<10} {proxy:<22} {r.get('agent_url', '-')}")


if __name__ == "__main__":
    main()
