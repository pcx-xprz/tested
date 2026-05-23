"""
Hatcher.host — Referral Reward Checker & Auto Claimer
======================================================
Script ini:
  1. Login ke akun referrer (akun KAMU yang punya referral code)
  2. Tampilkan status semua referral — siapa yang sudah buat agent,
     siapa yang belum, dan berapa credits yang sudah/belum diclaim
  3. Coba POST /referrals/claim untuk trigger release reward
  4. Jika ada akun referral di registered_accounts.json, login tiap
     akun tersebut dan cek apakah mereka sudah punya agent
  5. Tampilkan ringkasan: credits saat ini vs potensi

Flow reward hatcher.host:
  - Referral sign up pakai kode referrer → referral terdaftar
  - Referral HARUS buat 1 agent dulu   → reward di-release ke referrer
  - Referrer POST /referrals/claim      → credits masuk ke balance

Cara pakai:
  1. Isi REFERRER_EMAIL dan REFERRER_PASSWORD di bawah
  2. Pastikan registered_accounts.json ada di folder yang sama
  3. python check_coins.py
"""

import requests
import json
import logging
import os
import sys
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Akun REFERRER = akun kamu yang menyebarkan referral code
REFERRER_EMAIL    = ""   # ← isi email akun referrer kamu
REFERRER_PASSWORD = ""   # ← isi password akun referrer kamu

# File akun referral (hasil auto_register.py)
ACCOUNTS_FILE = "registered_accounts.json"

BASE_API      = "https://api.hatcher.host"
# ──────────────────────────────────────────────────────────────────────────────

# Fix encoding Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Origin":       "https://hatcher.host",
    "Referer":      "https://hatcher.host/",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def auth_headers(token: str) -> dict:
    h = HEADERS.copy()
    h["Authorization"] = f"Bearer {token}"
    return h


def login(email: str, password: str, session: requests.Session) -> str:
    """Login dan return JWT token, atau None jika gagal."""
    try:
        r = session.post(
            f"{BASE_API}/auth/login",
            headers=HEADERS,
            json={"email": email, "password": password},
            timeout=15
        )
        d = r.json() if r.content else {}
        if r.status_code == 200 and d.get("success"):
            return d["data"]["token"]
        log.warning(f"  Login gagal [{r.status_code}]: {d.get('error','')}")
    except Exception as e:
        log.error(f"  Login exception: {e}")
    return None


def get_me(token: str, session: requests.Session) -> dict:
    """GET /auth/me — profil + credits balance."""
    try:
        r = session.get(f"{BASE_API}/auth/me", headers=auth_headers(token), timeout=10)
        d = r.json() if r.content else {}
        if d.get("success"):
            return d["data"]
    except Exception as e:
        log.error(f"  get_me exception: {e}")
    return {}


def get_referral_stats(token: str, session: requests.Session) -> dict:
    """GET /referrals/stats — semua data referral."""
    try:
        r = session.get(f"{BASE_API}/referrals/stats", headers=auth_headers(token), timeout=10)
        d = r.json() if r.content else {}
        if d.get("success"):
            return d["data"]
    except Exception as e:
        log.error(f"  get_referral_stats exception: {e}")
    return {}


def claim_rewards(token: str, session: requests.Session) -> dict:
    """
    POST /referrals/claim
    Trigger release reward untuk semua referral yang sudah buat agent.
    Return { claimed: N, message: "..." }
    """
    try:
        r = session.post(
            f"{BASE_API}/referrals/claim",
            headers=auth_headers(token),
            json={},
            timeout=15
        )
        d = r.json() if r.content else {}
        if d.get("success"):
            return d["data"]
        log.warning(f"  Claim gagal [{r.status_code}]: {d.get('error','')}")
    except Exception as e:
        log.error(f"  Claim exception: {e}")
    return {}


def get_agents(token: str, session: requests.Session) -> list:
    """GET /agents — list agent milik akun yang sedang login."""
    try:
        r = session.get(f"{BASE_API}/agents", headers=auth_headers(token), timeout=10)
        d = r.json() if r.content else {}
        if d.get("success"):
            return d.get("data", [])
    except Exception as e:
        log.error(f"  get_agents exception: {e}")
    return []


def load_accounts(filepath: str) -> list:
    """Load semua akun dari registered_accounts.json."""
    VALID = {"success", "verified"}
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return [a for a in data if a.get("status") in VALID]


def sep(char="=", n=65):
    log.info(char * n)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    sep()
    log.info("  Hatcher.host — Referral Reward Checker")
    log.info(f"  Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sep()

    if not REFERRER_EMAIL or not REFERRER_PASSWORD:
        log.error("[ERR] Isi REFERRER_EMAIL dan REFERRER_PASSWORD di bagian CONFIG!")
        sys.exit(1)

    session = requests.Session()

    # ── 1. Login referrer ─────────────────────────────────────────────────────
    log.info(f"\n[1] Login sebagai referrer: {REFERRER_EMAIL}")
    token = login(REFERRER_EMAIL, REFERRER_PASSWORD, session)
    if not token:
        log.error("Gagal login! Cek email/password referrer.")
        sys.exit(1)

    # ── 2. Profil referrer ────────────────────────────────────────────────────
    me = get_me(token, session)
    log.info(f"\n{'─'*65}")
    log.info(f"  Referrer     : @{me.get('username')} ({me.get('email')})")
    log.info(f"  Tier         : {me.get('tier','?').upper()}")
    log.info(f"  emailVerified: {me.get('emailVerified', '?')}")
    log.info(f"  AI Credits   : {me.get('aiCreditsBalance', 0):,}")
    log.info(f"  Hatch Credits: {me.get('hatchCredits', 0):,}")
    log.info(f"  Agents aktif : {me.get('activeAgentCount', 0)}")
    log.info(f"{'─'*65}")

    # ── 3. Referral stats ─────────────────────────────────────────────────────
    stats = get_referral_stats(token, session)
    referrals     = stats.get("referrals", [])
    total_referred = stats.get("totalReferred", 0)
    total_earned   = stats.get("totalEarned", 0)
    reward_per    = stats.get("rewardPerReferral", 500)

    claimed_list   = [r for r in referrals if r.get("rewardClaimed")]
    unclaimed_list = [r for r in referrals if not r.get("rewardClaimed")]

    log.info(f"\n[2] STATUS REFERRAL ({total_referred} total)")
    log.info(f"{'─'*65}")
    log.info(f"  {'Username':<25} {'Tanggal':<14} {'Status'}")
    log.info(f"  {'-'*25} {'-'*14} {'-'*20}")

    for ref in referrals:
        claimed = ref.get("rewardClaimed", False)
        mark    = "✓ CLAIMED  (+500)" if claimed else "✗ PENDING  (belum buat agent?)"
        date    = ref["date"][:10]
        log.info(f"  {ref['username']:<25} {date:<14} {mark}")

    log.info(f"{'─'*65}")
    log.info(f"  Sudah claimed : {len(claimed_list)} referral = {len(claimed_list)*reward_per:,} credits")
    log.info(f"  Belum claimed : {len(unclaimed_list)} referral = {len(unclaimed_list)*reward_per:,} credits (potensial)")
    log.info(f"  Total potensi : {total_referred * reward_per:,} credits")
    log.info(f"  Total diterima: {total_earned:,} credits")
    log.info(f"  Kurang        : {(total_referred * reward_per) - total_earned:,} credits")

    # ── 4. Coba claim reward sekarang ─────────────────────────────────────────
    log.info(f"\n[3] MENCOBA CLAIM REWARD ...")
    credits_before = me.get("aiCreditsBalance", 0)
    claim_result   = claim_rewards(token, session)
    newly_claimed  = claim_result.get("claimed", 0)

    # Cek balance setelah claim
    me_after = get_me(token, session)
    credits_after = me_after.get("aiCreditsBalance", 0)
    diff = credits_after - credits_before

    log.info(f"  Hasil claim   : {claim_result.get('message', '-')}")
    log.info(f"  Claimed baru  : {newly_claimed}")
    log.info(f"  Credits sebelum: {credits_before:,}")
    log.info(f"  Credits sesudah: {credits_after:,}")
    log.info(f"  Bertambah     : +{diff:,}" if diff > 0 else f"  Bertambah     : {diff:,} (tidak ada perubahan)")

    # ── 5. Cek akun referral dari registered_accounts.json ───────────────────
    accounts = load_accounts(ACCOUNTS_FILE)
    if accounts:
        log.info(f"\n[4] CEK AKUN REFERRAL DI {ACCOUNTS_FILE} ({len(accounts)} akun)")
        log.info(f"{'─'*65}")
        log.info(f"  {'Email':<35} {'Username':<20} {'Agent':<8} {'Reward'}")
        log.info(f"  {'-'*35} {'-'*20} {'-'*8} {'-'*15}")

        # Buat lookup dari username → rewardClaimed
        reward_map = {r["username"]: r.get("rewardClaimed", False) for r in referrals}

        for acc in accounts:
            email    = acc.get("email", "")
            username = acc.get("username", "")
            password = acc.get("password", "")

            # Cek apakah username ada di referral list
            if username not in reward_map:
                log.info(f"  {email:<35} {username:<20} {'?':<8} NOT IN REFERRAL LIST")
                continue

            reward_claimed = reward_map[username]

            if reward_claimed:
                log.info(f"  {email:<35} {username:<20} {'?':<8} CLAIMED ✓")
                continue

            # Login akun ini untuk cek apakah sudah punya agent
            acc_session = requests.Session()
            acc_token   = login(email, password, acc_session)
            if not acc_token:
                log.warning(f"  {email:<35} {username:<20} {'?':<8} LOGIN GAGAL")
                continue

            agents = get_agents(acc_token, acc_session)
            has_agent = len(agents) > 0
            agent_info = f"{len(agents)} agent" if has_agent else "0 agent"

            if has_agent:
                # Sudah punya agent tapi reward belum claimed → harusnya bisa di-claim
                log.warning(f"  {email:<35} {username:<20} {agent_info:<8} PENDING → coba claim!")
            else:
                # Belum punya agent = itu penyebab reward belum di-release
                log.warning(f"  {email:<35} {username:<20} {agent_info:<8} BELUM BUAT AGENT ← ini masalahnya!")

        # Coba claim ulang setelah cek semua akun
        log.info(f"\n[5] CLAIM ULANG setelah pengecekan ...")
        claim2 = claim_rewards(token, session)
        me_final = get_me(token, session)
        log.info(f"  Hasil  : {claim2.get('message', '-')}")
        log.info(f"  Claimed: {claim2.get('claimed', 0)}")
        log.info(f"  Balance final: {me_final.get('aiCreditsBalance', 0):,} AI Credits")

    # ── 6. Ringkasan akhir ───────────────────────────────────────────────────
    me_final = get_me(token, session)
    log.info(f"\n{'='*65}")
    log.info("  RINGKASAN AKHIR")
    log.info(f"{'='*65}")
    log.info(f"  Akun referrer    : @{me_final.get('username')}")
    log.info(f"  AI Credits       : {me_final.get('aiCreditsBalance', 0):,}")
    log.info(f"  Referral berhasil: {len(claimed_list)} / {total_referred}")
    log.info(f"  Masih pending    : {len(unclaimed_list)} akun belum release reward")
    if unclaimed_list:
        log.info(f"\n  Akun yang BELUM release reward (perlu buat agent):")
        for ref in unclaimed_list:
            log.info(f"    - @{ref['username']}  ({ref['date'][:10]})")
    log.info(f"\n  SOLUSI: Jalankan auto_create_agent.py untuk akun-akun di atas")
    log.info(f"          agar reward 500 credits per referral ter-release!")
    log.info("=" * 65)


if __name__ == "__main__":
    main()
