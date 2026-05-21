#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║          NETLAS DORKER - nginx CVE Target Scanner            ║
║      Auto multi-API key rotation with smart pagination       ║
║         For authorized security research & CTF only          ║
╚══════════════════════════════════════════════════════════════╝

Usage:
  python3 netlas_dorker.py --pages 10
  python3 netlas_dorker.py --pages 20 --output results.txt
  python3 netlas_dorker.py --dork-index 3 --pages 5
  python3 netlas_dorker.py --list-dorks
  python3 netlas_dorker.py --pages 10 --delay-dork 5 --delay-api 2
"""

import requests
import time
import random
import argparse
import os
import sys
import re
import json
from datetime import datetime
from urllib.parse import urlparse, urlencode, quote_plus

# ─── ANSI Colors ─────────────────────────────────────────────
RED    = "\033[91;1m"
GREEN  = "\033[92;1m"
YELLOW = "\033[93;1m"
CYAN   = "\033[96;1m"
WHITE  = "\033[97;1m"
BLUE   = "\033[94;1m"
RESET  = "\033[0m"
DIM    = "\033[2m"
BOLD   = "\033[1m"

# ─── CONFIG ──────────────────────────────────────────────────
API_KEY_FILE   = "key_list.txt"       # File berisi API keys Netlas (1 per baris)
OUTPUT_DEFAULT = "netlas_results.txt" # Output file default
ITEMS_PER_PAGE = 20                   # Netlas returns 20 items per page (fixed)
BASE_URL       = "https://app.netlas.io/api/responses/"
BASE_URL_COUNT = "https://app.netlas.io/api/responses/count/"

# Error codes yang dianggap "api limit / skip"
SKIP_CODES = {429, 403, 401, 402, 500, 502, 503, 504}



# ─── DORK DATABASE (nginx CVE focus) ─────────────────────────
DORKS = [
    # ── CVE langsung ──────────────────────────────────────────
    {
        "id": 1,
        "name": "CVE-2026-42945 Heap Overflow RCE (nginx rewrite)",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2026-42945',
        "category": "CVE-RCE",
    },
    {
        "id": 2,
        "name": "CVE-2021-23017 Off-by-one resolver nginx",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2021-23017',
        "category": "CVE-RCE",
    },
    {
        "id": 3,
        "name": "CVE-2017-7529 Integer overflow range filter",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2017-7529',
        "category": "CVE-INFO",
    },
    {
        "id": 4,
        "name": "CVE-2019-20372 HTTP Request Smuggling",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2019-20372',
        "category": "CVE-SMUGGLING",
    },
    {
        "id": 5,
        "name": "CVE-2024-24990 UAF HTTP/3 QUIC nginx",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2024-24990',
        "category": "CVE-RCE",
    },
    {
        "id": 6,
        "name": "CVE-2013-2028 Chunked Stack Overflow nginx",
        "query": 'http.headers.server:nginx AND cve.name:CVE-2013-2028',
        "category": "CVE-RCE",
    },
    {
        "id": 7,
        "name": "nginx vuln range 0.6.27 - 1.30.0 (all CVE)",
        "query": 'http.headers.server:nginx AND cve:*',
        "category": "CVE-GENERIC",
    },
    # ── nginx version targeting ────────────────────────────────
    {
        "id": 8,
        "name": "nginx/1.25.x (CVE-2026-42945 affected)",
        "query": 'http.headers.server:"nginx/1.25"',
        "category": "VERSION",
    },
    {
        "id": 9,
        "name": "nginx/1.26.x (CVE-2026-42945 affected)",
        "query": 'http.headers.server:"nginx/1.26"',
        "category": "VERSION",
    },
    {
        "id": 10,
        "name": "nginx/1.27.x (CVE-2026-42945 affected)",
        "query": 'http.headers.server:"nginx/1.27"',
        "category": "VERSION",
    },
    {
        "id": 11,
        "name": "nginx/1.28.x (CVE-2026-42945 affected)",
        "query": 'http.headers.server:"nginx/1.28"',
        "category": "VERSION",
    },
    {
        "id": 12,
        "name": "nginx/1.29.x (CVE-2026-42945 affected)",
        "query": 'http.headers.server:"nginx/1.29"',
        "category": "VERSION",
    },
    {
        "id": 13,
        "name": "nginx/1.30.0 (CVE-2026-42945 affected, last vuln)",
        "query": 'http.headers.server:"nginx/1.30.0"',
        "category": "VERSION",
    },
    # ── nginx + exposed panels ─────────────────────────────────
    {
        "id": 14,
        "name": "nginx stub_status exposed + has CVE",
        "query": 'http.title:"nginx" AND http.body:"Active connections" AND cve:*',
        "category": "MISCONFIG",
    },
    {
        "id": 15,
        "name": "nginx default page exposed (server_tokens on)",
        "query": 'http.title:"Welcome to nginx" AND cve:*',
        "category": "MISCONFIG",
    },
    {
        "id": 16,
        "name": "nginx + phpMyAdmin exposed + has exploit CVE",
        "query": 'http.title:phpMyAdmin AND http.headers.server:nginx AND cve.has_exploit:true',
        "category": "MISCONFIG",
    },
    {
        "id": 17,
        "name": "nginx admin panel exposed with CVE exploit",
        "query": 'http.headers.server:nginx AND (uri:*admin* OR http.title:admin) AND cve.has_exploit:true',
        "category": "MISCONFIG",
    },
    # ── nginx + .env leak ──────────────────────────────────────
    {
        "id": 18,
        "name": "nginx .env file exposed (APP_KEY leak)",
        "query": 'http.headers.server:nginx AND http.body:"APP_KEY=" AND http.body:"DB_PASSWORD"',
        "category": "ENV-LEAK",
    },
    {
        "id": 19,
        "name": "nginx .env Laravel exposed",
        "query": 'http.headers.server:nginx AND http.body:"APP_ENV=" AND http.body:"APP_KEY="',
        "category": "ENV-LEAK",
    },
    # ── nginx + git exposed ────────────────────────────────────
    {
        "id": 20,
        "name": "nginx .git/config exposed",
        "query": 'http.headers.server:nginx AND http.body:"[core]" AND http.body:"repositoryformatversion"',
        "category": "GIT-LEAK",
    },
    # ── nginx + API docs exposed ───────────────────────────────
    {
        "id": 21,
        "name": "nginx Swagger UI exposed + has CVE",
        "query": 'http.headers.server:nginx AND http.title:swagger AND cve:*',
        "category": "API-EXPOSURE",
    },
    {
        "id": 22,
        "name": "nginx Spring Boot actuator exposed + CVE",
        "query": 'http.headers.server:nginx AND uri:*actuator* AND cve:*',
        "category": "API-EXPOSURE",
    },
    # ── nginx + RCE via CVE description ───────────────────────
    {
        "id": 23,
        "name": "nginx RCE exploit available (any CVE)",
        "query": 'http.headers.server:nginx AND cve.has_exploit:true AND cve.description:nginx',
        "category": "CVE-RCE",
    },
    # ── nginx + specific tech stacks ──────────────────────────
    {
        "id": 24,
        "name": "nginx + PHP-FPM (common rewrite config) + CVE",
        "query": 'http.headers.server:nginx AND http.headers:"X-Powered-By: PHP" AND cve:*',
        "category": "TECH-STACK",
    },
    {
        "id": 25,
        "name": "nginx + WordPress (rewrite heavy) + CVE exploit",
        "query": 'http.headers.server:nginx AND tag.name:wordpress AND cve.has_exploit:true',
        "category": "TECH-STACK",
    },
    # ── Geolocation targeting ──────────────────────────────────
    {
        "id": 26,
        "name": "nginx CVE RCE - Asia (high-density targets)",
        "query": 'http.headers.server:nginx AND cve.has_exploit:true AND geo.continent:Asia',
        "category": "GEO",
    },
    {
        "id": 27,
        "name": "nginx CVE RCE - Europe",
        "query": 'http.headers.server:nginx AND cve.has_exploit:true AND geo.continent:Europe',
        "category": "GEO",
    },
    # ── Additional misconfig ───────────────────────────────────
    {
        "id": 28,
        "name": "nginx server-status exposed + CVE",
        "query": 'http.headers.server:nginx AND http.body:"Server Status" AND cve:*',
        "category": "MISCONFIG",
    },
    {
        "id": 29,
        "name": "nginx + Prometheus metrics exposed",
        "query": 'http.headers.server:nginx AND uri:*metrics* AND http.body:"# HELP" AND cve:*',
        "category": "MISCONFIG",
    },
    {
        "id": 30,
        "name": "nginx + backup files exposed (zip/sql/tar)",
        "query": 'http.headers.server:nginx AND (http.body:"backup.zip" OR http.body:"dump.sql") AND cve:*',
        "category": "BACKUP-LEAK",
    },
]



# ─── HELPERS ─────────────────────────────────────────────────
def banner():
    b = f"""
{CYAN}╔══════════════════════════════════════════════════════════════╗
║{YELLOW}       NETLAS DORKER  ─  nginx CVE Target Scanner            {CYAN}║
║{WHITE}    Auto API Key Rotation  ·  Smart Pagination  ·  Stealth   {CYAN}║
╚══════════════════════════════════════════════════════════════╝{RESET}
{DIM}  API Base : {BASE_URL}
  Dorks    : {len(DORKS)} queries loaded
  Key File : {API_KEY_FILE}{RESET}
"""
    print(b)


def ts():
    """Timestamp prefix for log output."""
    return f"{DIM}[{datetime.now().strftime('%H:%M:%S')}]{RESET}"


def load_api_keys(path=API_KEY_FILE):
    """Load API keys dari file, strip whitespace, hapus duplikat & kosong."""
    if not os.path.exists(path):
        print(f"{RED}[!] Key file tidak ditemukan: {path}{RESET}")
        sys.exit(1)
    keys = []
    with open(path, "r") as f:
        for line in f:
            k = line.strip()
            if k and k not in keys:
                keys.append(k)
    if not keys:
        print(f"{RED}[!] Tidak ada API key di {path}{RESET}")
        sys.exit(1)
    print(f"{ts()} {GREEN}[KEYS] Loaded {len(keys)} API key(s) dari {path}{RESET}")
    return keys


def normalize_uri(uri: str) -> str:
    """
    Konversi URI Netlas ke format http(s)://domain saja.
    Hapus path, port non-standard jika mau murni domain.
    """
    if not uri:
        return None
    # pastikan ada scheme
    if not uri.startswith("http://") and not uri.startswith("https://"):
        uri = "http://" + uri
    try:
        p = urlparse(uri)
        scheme = p.scheme or "http"
        host   = p.hostname or ""
        port   = p.port
        if not host:
            return None
        # bangun kembali hanya scheme://host[:port]
        if port and port not in (80, 443):
            return f"{scheme}://{host}:{port}"
        return f"{scheme}://{host}"
    except Exception:
        return None


def save_result(uri: str, output_file: str, seen: set) -> bool:
    """Simpan URI ke file jika belum ada (dedup). Return True jika baru."""
    clean = normalize_uri(uri)
    if not clean or clean in seen:
        return False
    seen.add(clean)
    with open(output_file, "a") as f:
        f.write(clean + "\n")
    return True


def random_ua():
    """Rotate User-Agent agar tidak terdeteksi sebagai bot."""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 Version/17.4.1 Safari/605.1.15",
        "netlas-python/0.4.0",
    ]
    return random.choice(agents)


def build_headers(api_key: str) -> dict:
    return {
        "X-API-Key":    api_key,
        "Accept":       "application/json",
        "User-Agent":   random_ua(),
        "Content-Type": "application/json",
    }


def jitter(min_s=0.5, max_s=2.0):
    """Jitter acak untuk stealth."""
    time.sleep(random.uniform(min_s, max_s))



# ─── API KEY MANAGER ─────────────────────────────────────────
class APIKeyManager:
    """
    Smart API key rotator.
    - Track key status (active / exhausted / error)
    - Auto skip ke key berikutnya jika kena limit/error
    - Lanjutkan halaman yang belum selesai dengan key baru
    """

    def __init__(self, keys: list):
        self.keys       = list(keys)
        self.current    = 0
        self.exhausted  = set()   # index key yang sudah habis
        self.error_cnt  = {}      # {index: count} error per key

    def current_key(self) -> str:
        return self.keys[self.current]

    def current_index(self) -> int:
        return self.current

    def total_active(self) -> int:
        return len(self.keys) - len(self.exhausted)

    def mark_exhausted(self, reason: str = ""):
        idx = self.current
        self.exhausted.add(idx)
        key_preview = self.keys[idx][:8] + "..."
        print(f"\n{ts()} {YELLOW}[SKIP KEY #{idx+1}] {key_preview} — {reason}{RESET}")
        self._advance()

    def _advance(self):
        """Cari key berikutnya yang masih aktif."""
        total = len(self.keys)
        tried = 0
        while tried < total:
            self.current = (self.current + 1) % total
            if self.current not in self.exhausted:
                key_preview = self.keys[self.current][:8] + "..."
                print(f"{ts()} {CYAN}[ROTATE] Pindah ke API Key #{self.current+1} ({key_preview}){RESET}")
                return
            tried += 1
        # semua key exhausted
        print(f"\n{ts()} {RED}[!!] SEMUA API KEY HABIS / ERROR. Tidak ada key tersisa.{RESET}")
        self.current = -1  # sentinel

    def all_exhausted(self) -> bool:
        return self.current == -1 or len(self.exhausted) >= len(self.keys)

    def increment_error(self):
        idx = self.current
        self.error_cnt[idx] = self.error_cnt.get(idx, 0) + 1
        if self.error_cnt[idx] >= 3:
            self.mark_exhausted(f"Error beruntun {self.error_cnt[idx]}x")



# ─── CORE FETCHER ─────────────────────────────────────────────
def fetch_page(query: str, page: int, key_mgr: APIKeyManager,
               delay_api: float = 1.5, retry_on_rotate: int = 3) -> list:
    """
    Ambil satu halaman hasil dari Netlas API.

    Parameter:
      query         : Netlas search query string
      page          : halaman ke-N (0-indexed, setiap halaman = 20 item)
      key_mgr       : APIKeyManager instance
      delay_api     : jeda antar request (detik)
      retry_on_rotate: max retry dengan key baru sebelum menyerah

    Return:
      List URI string (bisa kosong jika tidak ada hasil / semua key habis)
    """
    start    = page * ITEMS_PER_PAGE  # offset pagination Netlas
    attempts = 0

    while attempts < retry_on_rotate:
        if key_mgr.all_exhausted():
            print(f"{ts()} {RED}[ABORT] Semua key exhausted saat fetch page {page+1}{RESET}")
            return []

        api_key = key_mgr.current_key()
        headers = build_headers(api_key)
        params  = {
            "q":           query,
            "source_type": "include",
            "start":       start,
            "fields":      "uri,ip,http.title,port",  # ambil field minimal (hemat quota)
        }

        try:
            jitter(0.3, 0.8)  # micro-jitter sebelum request
            resp = requests.get(
                BASE_URL,
                headers=headers,
                params=params,
                timeout=20,
            )

            # ── Handle error codes ────────────────────────────
            if resp.status_code in SKIP_CODES:
                reason_map = {
                    429: "Rate limit / Too Many Requests",
                    403: "Forbidden (API quota habis atau key invalid)",
                    401: "Unauthorized (key tidak valid)",
                    402: "Payment Required (quota habis)",
                    500: "Internal Server Error",
                    502: "Bad Gateway",
                    503: "Service Unavailable",
                    504: "Gateway Timeout",
                }
                reason = reason_map.get(resp.status_code, f"HTTP {resp.status_code}")
                key_mgr.mark_exhausted(reason)
                attempts += 1
                time.sleep(delay_api)
                continue  # retry dengan key berikutnya

            if resp.status_code == 200:
                data  = resp.json()
                items = data.get("items", [])

                uris = []
                for item in items:
                    raw_uri = item.get("data", {}).get("uri", "")
                    if raw_uri:
                        uris.append(raw_uri)
                    # fallback: bangun dari ip + port jika uri kosong
                    elif item.get("data", {}).get("ip"):
                        ip   = item["data"]["ip"]
                        port = item["data"].get("port", 80)
                        scheme = "https" if port == 443 else "http"
                        uris.append(f"{scheme}://{ip}:{port}")

                time.sleep(delay_api)
                return uris

            else:
                # kode lain yang tidak diexpect
                print(f"{ts()} {RED}[WARN] HTTP {resp.status_code} — skip & increment error{RESET}")
                key_mgr.increment_error()
                attempts += 1
                time.sleep(delay_api * 2)
                continue

        except requests.exceptions.Timeout:
            print(f"{ts()} {YELLOW}[TIMEOUT] Page {page+1}, retry...{RESET}")
            key_mgr.increment_error()
            attempts += 1
            time.sleep(delay_api)

        except requests.exceptions.ConnectionError as e:
            print(f"{ts()} {YELLOW}[CONN ERR] {str(e)[:60]}. Retry...{RESET}")
            key_mgr.increment_error()
            attempts += 1
            time.sleep(delay_api * 2)

        except requests.exceptions.JSONDecodeError:
            print(f"{ts()} {RED}[JSON ERR] Response bukan JSON valid. Skip page.{RESET}")
            return []

        except Exception as e:
            print(f"{ts()} {RED}[ERR] Unexpected: {str(e)[:80]}{RESET}")
            key_mgr.increment_error()
            attempts += 1
            time.sleep(delay_api)

    print(f"{ts()} {RED}[FAIL] Page {page+1} gagal setelah {retry_on_rotate} percobaan. Lewati.{RESET}")
    return []



# ─── DORK RUNNER ──────────────────────────────────────────────
def run_dork(dork: dict, key_mgr: APIKeyManager, max_pages: int,
             output_file: str, seen: set,
             delay_api: float = 1.5, delay_dork: float = 5.0) -> int:
    """
    Jalankan satu dork: ambil sampai max_pages halaman.

    Logika smart pagination:
      - Jika key ke-N kena limit di halaman ke-X (misalnya halaman 3 dari 10),
        script akan rotasi ke key berikutnya dan LANJUT dari halaman 3,
        bukan mengulang dari awal.
      - Proses berhenti jika: semua halaman selesai, atau semua key habis.

    Return: jumlah URI baru yang ditemukan
    """
    query    = dork["query"]
    name     = dork["name"]
    dork_id  = dork["id"]
    category = dork["category"]
    found    = 0

    print(f"\n{ts()} {BOLD}{CYAN}[DORK #{dork_id}] {name}{RESET}")
    print(f"{DIM}  Category : {category}{RESET}")
    print(f"{DIM}  Query    : {query}{RESET}")
    print(f"{DIM}  Pages    : {max_pages} (max {max_pages * ITEMS_PER_PAGE} results){RESET}")
    print(f"  {'─'*55}")

    page = 0
    while page < max_pages:
        if key_mgr.all_exhausted():
            print(f"{ts()} {RED}[DORK #{dork_id}] Semua key habis. Lanjut ke dork berikutnya.{RESET}")
            break

        active_key_before = key_mgr.current_index()

        print(f"{ts()} {WHITE}  Page {page+1}/{max_pages} → Key #{key_mgr.current_index()+1} | Found: {found}{RESET}", end="\r")

        uris = fetch_page(query, page, key_mgr, delay_api=delay_api)

        # Cek apakah key berubah (rotasi terjadi)
        active_key_after = key_mgr.current_index()
        if active_key_before != active_key_after and not key_mgr.all_exhausted():
            print(f"\n{ts()} {YELLOW}  [KEY ROTATED] Melanjutkan dari page {page+1} dengan key #{active_key_after+1}{RESET}")
            # TIDAK increment page → ulangi page yang sama dengan key baru
            time.sleep(delay_api)
            continue

        # Proses hasil
        if uris:
            new_count = 0
            for uri in uris:
                if save_result(uri, output_file, seen):
                    new_count += 1
                    found += 1
                    print(f"\n{ts()} {GREEN}  [+] {normalize_uri(uri)}{RESET}")

            if new_count == 0:
                print(f"\n{ts()} {DIM}  Page {page+1}: {len(uris)} items (semua duplikat){RESET}")
        else:
            # Tidak ada hasil → kemungkinan sudah habis
            if not key_mgr.all_exhausted():
                print(f"\n{ts()} {DIM}  Page {page+1}: Kosong. Query mungkin sudah habis.{RESET}")
                break

        page += 1

        # Jeda antar halaman (stealth)
        if page < max_pages:
            jitter_time = random.uniform(delay_api * 0.5, delay_api * 1.5)
            time.sleep(jitter_time)

    print(f"\n{ts()} {GREEN}[DORK #{dork_id}] Selesai → {found} URI baru ditemukan{RESET}")
    print(f"  {'─'*55}")

    # Jeda antar dork (stealth)
    if delay_dork > 0:
        jitter_delay = random.uniform(delay_dork * 0.8, delay_dork * 1.4)
        print(f"{ts()} {DIM}  [JEDA] {jitter_delay:.1f}s sebelum dork berikutnya...{RESET}")
        time.sleep(jitter_delay)

    return found



# ─── LIST DORKS ───────────────────────────────────────────────
def list_dorks():
    """Tampilkan semua dork yang tersedia."""
    print(f"\n{BOLD}{CYAN}{'─'*70}{RESET}")
    print(f"{BOLD}{WHITE}  {'ID':<4} {'CATEGORY':<18} {'NAME'}{RESET}")
    print(f"{CYAN}{'─'*70}{RESET}")

    category_colors = {
        "CVE-RCE":      RED,
        "CVE-INFO":     YELLOW,
        "CVE-SMUGGLING":YELLOW,
        "CVE-GENERIC":  YELLOW,
        "VERSION":      CYAN,
        "MISCONFIG":    BLUE,
        "ENV-LEAK":     RED,
        "GIT-LEAK":     RED,
        "API-EXPOSURE": BLUE,
        "TECH-STACK":   WHITE,
        "GEO":          GREEN,
        "BACKUP-LEAK":  YELLOW,
    }

    for d in DORKS:
        cat   = d["category"]
        color = category_colors.get(cat, WHITE)
        print(f"  {WHITE}{d['id']:<4}{RESET} {color}{cat:<18}{RESET} {d['name']}")

    print(f"{CYAN}{'─'*70}{RESET}")
    print(f"\n{DIM}  Gunakan --dork-index ID untuk menjalankan dork tertentu{RESET}")
    print(f"{DIM}  Contoh: python3 netlas_dorker.py --dork-index 1 --pages 5{RESET}\n")


# ─── STATS ────────────────────────────────────────────────────
def print_stats(total_found: int, total_dorks: int, elapsed: float,
                output_file: str, key_mgr: APIKeyManager):
    print(f"\n{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{WHITE}  NETLAS DORKER — SELESAI{RESET}")
    print(f"{CYAN}{'═'*60}{RESET}")
    print(f"  Total URI ditemukan  : {GREEN}{total_found}{RESET}")
    print(f"  Dorks dijalankan     : {WHITE}{total_dorks}{RESET}")
    print(f"  API Key aktif sisa   : {CYAN}{key_mgr.total_active()}/{len(key_mgr.keys)}{RESET}")
    print(f"  Key exhausted        : {YELLOW}{len(key_mgr.exhausted)}{RESET}")
    print(f"  Waktu total          : {WHITE}{elapsed:.1f}s{RESET}")
    print(f"  Output file          : {GREEN}{output_file}{RESET}")
    print(f"{CYAN}{'═'*60}{RESET}\n")



# ─── MAIN ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="netlas_dorker.py",
        description="Netlas nginx CVE Dorker — Multi-API Key Rotator dengan Smart Pagination",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Jalankan semua dork, 10 halaman per dork
  python3 netlas_dorker.py --pages 10

  # Dork tertentu saja (ID dari --list-dorks), 5 halaman
  python3 netlas_dorker.py --dork-index 1 --pages 5

  # Multiple dork ID
  python3 netlas_dorker.py --dork-index 1 3 7 --pages 8

  # Custom output + jeda custom
  python3 netlas_dorker.py --pages 15 --output targets.txt --delay-dork 8 --delay-api 2

  # Lihat semua dork
  python3 netlas_dorker.py --list-dorks

  # Custom key file
  python3 netlas_dorker.py --pages 10 --key-file mykeys.txt

Catatan:
  - 1 halaman = 20 hasil
  - Free API key Netlas: ~50 req/hari → max ~5 halaman per key
  - Script otomatis rotasi key jika kena 429/403/limit
  - Jika key kena limit di tengah dork, page dilanjutkan dengan key baru
""",
    )

    # Mode
    parser.add_argument("--list-dorks",  action="store_true",
                        help="Tampilkan semua dork yang tersedia lalu keluar")
    parser.add_argument("--pages",       type=int,  default=5,
                        help="Jumlah halaman per dork (default: 5, 1 page = 20 hasil)")
    parser.add_argument("--dork-index",  type=int,  nargs="*", default=None,
                        help="ID dork yang dijalankan (default: semua). Contoh: --dork-index 1 3 7")

    # Files
    parser.add_argument("--key-file",   default=API_KEY_FILE,
                        help=f"Path file API key (default: {API_KEY_FILE})")
    parser.add_argument("--output",     default=OUTPUT_DEFAULT,
                        help=f"File output hasil (default: {OUTPUT_DEFAULT})")
    parser.add_argument("--append",     action="store_true",
                        help="Append ke output file yang sudah ada (default: overwrite)")

    # Timing / stealth
    parser.add_argument("--delay-api",  type=float, default=1.5,
                        help="Jeda antar request ke API (detik, default: 1.5)")
    parser.add_argument("--delay-dork", type=float, default=5.0,
                        help="Jeda antar pergantian dork (detik, default: 5.0)")

    # Misc
    parser.add_argument("--no-dedup",   action="store_true",
                        help="Matikan deduplication (simpan semua URI termasuk duplikat)")
    parser.add_argument("--verbose",    action="store_true",
                        help="Output lebih detail")

    args = parser.parse_args()

    # ── List dorks mode ───────────────────────────────────────
    if args.list_dorks:
        banner()
        list_dorks()
        return 0

    banner()

    # ── Load API keys ─────────────────────────────────────────
    keys    = load_api_keys(args.key_file)
    key_mgr = APIKeyManager(keys)

    # ── Setup output file ─────────────────────────────────────
    output_file = args.output
    if not args.append and os.path.exists(output_file):
        os.remove(output_file)
        print(f"{ts()} {DIM}[OUTPUT] File {output_file} di-reset.{RESET}")

    # Load URI yang sudah ada (dedup cross-session)
    seen = set()
    if not args.no_dedup and os.path.exists(output_file):
        with open(output_file, "r") as f:
            for line in f:
                l = line.strip()
                if l:
                    seen.add(l)
        print(f"{ts()} {DIM}[DEDUP] {len(seen)} URI sudah ada dari sesi sebelumnya.{RESET}")

    # ── Pilih dork yang akan dijalankan ───────────────────────
    if args.dork_index:
        selected_ids = set(args.dork_index)
        dorks_to_run = [d for d in DORKS if d["id"] in selected_ids]
        if not dorks_to_run:
            print(f"{RED}[!] Tidak ada dork dengan ID: {args.dork_index}{RESET}")
            list_dorks()
            return 1
    else:
        dorks_to_run = DORKS

    print(f"\n{ts()} {WHITE}[CONFIG]{RESET}")
    print(f"  Dorks    : {len(dorks_to_run)} dork dipilih")
    print(f"  Pages    : {args.pages} per dork ({args.pages * ITEMS_PER_PAGE} max hasil per dork)")
    print(f"  Keys     : {len(keys)} API key(s)")
    print(f"  Output   : {output_file}")
    print(f"  Delay    : {args.delay_api}s per request, {args.delay_dork}s antar dork")
    print(f"  Dedup    : {'OFF' if args.no_dedup else 'ON'}")
    print(f"\n  Mulai dalam 3 detik...")
    time.sleep(3)

    # ── Main loop ─────────────────────────────────────────────
    total_found  = 0
    dorks_done   = 0
    start_time   = time.monotonic()

    for i, dork in enumerate(dorks_to_run):
        if key_mgr.all_exhausted():
            print(f"\n{ts()} {RED}[STOP] Semua API key habis. Total dork selesai: {dorks_done}/{len(dorks_to_run)}{RESET}")
            break

        found = run_dork(
            dork=dork,
            key_mgr=key_mgr,
            max_pages=args.pages,
            output_file=output_file,
            seen=seen if not args.no_dedup else set(),
            delay_api=args.delay_api,
            delay_dork=args.delay_dork,
        )

        total_found += found
        dorks_done  += 1

        # Progress summary per dork
        elapsed_so_far = time.monotonic() - start_time
        remaining      = len(dorks_to_run) - dorks_done
        print(f"{ts()} {DIM}  Progress: {dorks_done}/{len(dorks_to_run)} dork | "
              f"Total URI: {total_found} | "
              f"Elapsed: {elapsed_so_far:.0f}s | "
              f"Sisa dork: {remaining} | "
              f"Key aktif: {key_mgr.total_active()}/{len(keys)}{RESET}")

    elapsed = time.monotonic() - start_time
    print_stats(total_found, dorks_done, elapsed, output_file, key_mgr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}[!] Dihentikan oleh user (Ctrl+C). Hasil yang ada sudah tersimpan.{RESET}\n")
        sys.exit(0)
