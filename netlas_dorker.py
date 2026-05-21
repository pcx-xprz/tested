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
    Smart API key rotator dengan dua level exhaustion:

    SOFT exhaustion (per-dork):
      Key kena limit/403 → dimasukkan ke `soft_exhausted` untuk dork saat ini.
      Saat dork berikutnya mulai, soft_exhausted di-reset → key bisa dipakai lagi.
      Ini penting karena limit Netlas free adalah per-hari, bukan per-dork.
      Key yang habis quota untuk satu dork masih bisa dipakai untuk dork lain
      di hari yang sama (jika masih ada sisa quota) atau setelah beberapa menit.

    HARD exhaustion (permanent):
      Key yang return 401 (Unauthorized/invalid) → hard_exhausted selamanya,
      karena key memang tidak valid dan tidak akan pernah bisa dipakai.

    Dengan skema ini:
      - 84 key × 5 page/key = sampai 420 page per dork (jika semua key masih segar)
      - Key yang kena limit di dork #14 → dicoba lagi di dork #15
      - Hanya key invalid (401) yang dibuang permanent
    """

    def __init__(self, keys: list):
        self.keys           = list(keys)
        self.current        = 0
        self.soft_exhausted = set()   # limit untuk dork ini saja (reset antar dork)
        self.hard_exhausted = set()   # key invalid permanen (401)
        self.error_cnt      = {}      # {index: consecutive_error_count}

    # ── Akses key saat ini ────────────────────────────────────
    def current_key(self) -> str:
        return self.keys[self.current]

    def current_index(self) -> int:
        return self.current

    # ── Statistik ─────────────────────────────────────────────
    def total_hard_dead(self) -> int:
        return len(self.hard_exhausted)

    def total_soft_limited(self) -> int:
        return len(self.soft_exhausted - self.hard_exhausted)

    def total_usable(self) -> int:
        """Key yang benar-benar bisa dipakai sekarang (tidak soft NOR hard exhausted)."""
        return len(self.keys) - len(self.soft_exhausted | self.hard_exhausted)

    # ── Exhaustion ────────────────────────────────────────────
    def mark_soft_exhausted(self, reason: str = ""):
        """Key kena limit/403 untuk dork ini → soft skip, reset di dork berikutnya."""
        idx = self.current
        self.soft_exhausted.add(idx)
        key_preview = self.keys[idx][:8] + "..."
        print(f"\n{ts()} {YELLOW}[SKIP KEY #{idx+1}] {key_preview} — {reason}{RESET}")
        self._advance()

    def mark_hard_exhausted(self, reason: str = ""):
        """Key 401/invalid → buang permanent."""
        idx = self.current
        self.hard_exhausted.add(idx)
        self.soft_exhausted.add(idx)   # juga masuk soft supaya advance benar
        key_preview = self.keys[idx][:8] + "..."
        print(f"\n{ts()} {RED}[DEAD KEY #{idx+1}] {key_preview} — {reason} (permanent){RESET}")
        self._advance()

    def reset_soft_for_next_dork(self):
        """
        Panggil ini sebelum setiap dork baru.

        Yang dilakukan:
        1. Key soft-exhausted (403/429) di-reset → bisa dicoba lagi di dork ini
           (meski kemungkinan masih 403, tapi tetap dicoba agar tidak terlewat)
        2. TIDAK reset current ke key #1 — lanjutkan round-robin dari key
           berikutnya setelah key yang terakhir berhasil dipakai.
           Ini penting agar key yang sama tidak langsung dipanggil lagi
           di awal dork berikutnya (menghindari 403 beruntun di awal).
        3. Key hard-dead (401) tetap dibuang permanen.
        """
        recovered = self.soft_exhausted - self.hard_exhausted
        if recovered:
            print(f"{ts()} {DIM}[KEY POOL] {len(recovered)} key di-reset "
                  f"→ siap dicoba lagi di dork berikutnya{RESET}")

        # Simpan posisi current sebelum reset (key yang terakhir dipakai)
        last_used = self.current if self.current != -1 else 0

        # Hapus soft-exhaustion (kecuali hard-dead)
        self.soft_exhausted = set(self.hard_exhausted)
        self.error_cnt      = {}

        # Lanjutkan dari key SETELAH yang terakhir dipakai (round-robin)
        # Ini mencegah key yang sama langsung dipanggil lagi di awal dork berikutnya
        self._find_next_from(last_used)

    def _find_next_from(self, start_after: int):
        """
        Cari key aktif berikutnya setelah posisi start_after (round-robin).
        Jika semua hard-dead, set current = -1.
        """
        total = len(self.keys)
        for i in range(1, total + 1):
            nxt = (start_after + i) % total
            if nxt not in self.soft_exhausted:
                self.current = nxt
                return
        self.current = -1  # semua hard-dead

    def _find_active_start(self):
        """Posisikan current ke key aktif pertama setelah reset (fallback)."""
        for i in range(len(self.keys)):
            if i not in self.soft_exhausted:
                self.current = i
                return
        self.current = -1   # semua hard-dead

    def _advance(self):
        """Cari key berikutnya yang tidak di soft_exhausted."""
        total = len(self.keys)
        tried = 0
        start = self.current
        while tried < total:
            nxt = (start + tried + 1) % total
            if nxt not in self.soft_exhausted:
                self.current = nxt
                key_preview  = self.keys[nxt][:8] + "..."
                print(f"{ts()} {CYAN}[ROTATE] Pindah ke API Key #{nxt+1} ({key_preview}){RESET}")
                return
            tried += 1
        # semua key habis untuk dork ini
        print(f"\n{ts()} {YELLOW}[!!] Semua key sudah habis quota untuk dork ini.{RESET}")
        self.current = -1

    def all_exhausted_for_dork(self) -> bool:
        """True jika tidak ada key yang tersisa untuk dork saat ini."""
        return self.current == -1 or len(self.soft_exhausted | self.hard_exhausted) >= len(self.keys)

    def all_hard_dead(self) -> bool:
        """True jika semua key invalid/dead permanent → hentikan seluruh session."""
        return len(self.hard_exhausted) >= len(self.keys)

    def increment_error(self, is_conn_error: bool = False):
        """
        Hitung error berturut-turut.
        Connection error (jaringan) tidak langsung soft-exhaust,
        tapi setelah 5x berturut = soft-exhaust sementara.
        """
        idx = self.current
        self.error_cnt[idx] = self.error_cnt.get(idx, 0) + 1
        threshold = 5 if is_conn_error else 3
        if self.error_cnt[idx] >= threshold:
            self.mark_soft_exhausted(f"Error berturut {self.error_cnt[idx]}x")



# ─── CORE FETCHER ─────────────────────────────────────────────
def fetch_page(query: str, page: int, key_mgr: APIKeyManager,
               delay_api: float = 1.5) -> list:
    """
    Ambil satu halaman hasil dari Netlas API.
    Retry otomatis dengan key baru jika key kena limit/error.
    Tidak ada batas `retry_on_rotate` — akan terus coba semua key yang masih aktif.

    Return: List URI string (kosong jika semua key habis atau tidak ada hasil)
    """
    start = page * ITEMS_PER_PAGE

    while not key_mgr.all_exhausted_for_dork():
        api_key = key_mgr.current_key()
        headers = build_headers(api_key)
        params  = {
            "q":           query,
            "source_type": "include",
            "start":       start,
            "fields":      "uri,ip,http.title,port",
        }

        try:
            jitter(0.3, 0.8)
            resp = requests.get(BASE_URL, headers=headers, params=params, timeout=20)

            # ── 401: key invalid/dead → hard exhaust ─────────
            if resp.status_code == 401:
                key_mgr.mark_hard_exhausted("Unauthorized (key tidak valid)")
                time.sleep(delay_api)
                continue

            # ── Deteksi Cloudflare IP BAN (Error 1006) ────────
            # Cloudflare 1006 = IP address di-ban oleh pemilik site.
            # Semua key akan kena selama IP sama → tidak ada gunanya
            # rotasi key. Tampilkan peringatan dan hentikan dork ini.
            if resp.status_code == 403:
                body_text = ""
                try:
                    body_text = resp.text[:500].lower()
                except Exception:
                    pass
                if "1006" in body_text or "banned your ip" in body_text or "access denied" in body_text:
                    print(f"\n{ts()} {RED}{'═'*55}{RESET}")
                    print(f"{ts()} {RED}[IP BAN] Cloudflare Error 1006 — IP kamu di-ban oleh Netlas!{RESET}")
                    print(f"{ts()} {RED}  Semua request dari IP ini akan gagal, apapun API key-nya.{RESET}")
                    print(f"{ts()} {YELLOW}  Solusi: Ganti IP (on/off mode pesawat / VPN / proxy){RESET}")
                    print(f"{ts()} {YELLOW}  Gunakan flag --proxy socks5://127.0.0.1:PORT jika pakai proxy{RESET}")
                    print(f"{ts()} {RED}{'═'*55}{RESET}")
                    # Kembalikan None sebagai sinyal khusus IP ban
                    return None  # type: ignore[return-value]

            # ── Quota/limit errors → soft exhaust ────────────
            if resp.status_code in SKIP_CODES:
                reason_map = {
                    429: "Rate limit (quota harian habis)",
                    403: "Forbidden (quota habis / key terbatas)",
                    402: "Payment Required (quota habis)",
                    500: "Internal Server Error",
                    502: "Bad Gateway",
                    503: "Service Unavailable",
                    504: "Gateway Timeout",
                }
                reason = reason_map.get(resp.status_code, f"HTTP {resp.status_code}")
                key_mgr.mark_soft_exhausted(reason)
                time.sleep(delay_api)
                continue

            # ── 200: sukses ───────────────────────────────────
            if resp.status_code == 200:
                data  = resp.json()
                items = data.get("items", [])
                uris  = []
                for item in items:
                    raw_uri = item.get("data", {}).get("uri", "")
                    if raw_uri:
                        uris.append(raw_uri)
                    elif item.get("data", {}).get("ip"):
                        ip     = item["data"]["ip"]
                        port   = item["data"].get("port", 80)
                        scheme = "https" if port == 443 else "http"
                        uris.append(f"{scheme}://{ip}:{port}")
                time.sleep(delay_api)
                # Reset error counter untuk key ini karena berhasil
                key_mgr.error_cnt[key_mgr.current_index()] = 0
                return uris

            # ── Kode lain yang tidak diexpect ─────────────────
            print(f"{ts()} {RED}[WARN] HTTP {resp.status_code} dari key #{key_mgr.current_index()+1}{RESET}")
            key_mgr.increment_error()
            time.sleep(delay_api * 2)

        except requests.exceptions.Timeout:
            print(f"{ts()} {YELLOW}[TIMEOUT] Page {page+1}, key #{key_mgr.current_index()+1}{RESET}")
            key_mgr.increment_error(is_conn_error=True)
            time.sleep(delay_api)

        except requests.exceptions.ConnectionError as e:
            short = str(e)[:60]
            print(f"{ts()} {YELLOW}[CONN ERR] {short}. Retry...{RESET}")
            key_mgr.increment_error(is_conn_error=True)
            time.sleep(delay_api * 2)

        except requests.exceptions.JSONDecodeError:
            print(f"{ts()} {RED}[JSON ERR] Response tidak valid. Skip page.{RESET}")
            return []

        except Exception as e:
            print(f"{ts()} {RED}[ERR] {str(e)[:80]}{RESET}")
            key_mgr.increment_error()
            time.sleep(delay_api)

    # Keluar loop = semua key habis untuk dork ini
    return []



# ─── DORK RUNNER ──────────────────────────────────────────────
def run_dork(dork: dict, key_mgr: APIKeyManager, max_pages: int,
             output_file: str, seen: set,
             delay_api: float = 1.5, delay_dork: float = 5.0) -> int:
    """
    Jalankan satu dork: ambil sampai max_pages halaman.

    Setiap dork dimulai dengan reset soft-exhaustion → semua key yang sebelumnya
    kena limit (tapi masih valid) dikembalikan ke pool aktif.
    """
    query    = dork["query"]
    name     = dork["name"]
    dork_id  = dork["id"]
    category = dork["category"]
    found    = 0

    # ── Reset soft-exhaustion untuk dork baru ─────────────────
    key_mgr.reset_soft_for_next_dork()

    # Jika semua key hard-dead → tidak ada gunanya lanjut
    if key_mgr.all_hard_dead():
        print(f"{ts()} {RED}[SKIP DORK #{dork_id}] Semua key invalid permanent. Session berhenti.{RESET}")
        return 0

    active_now = key_mgr.total_usable()
    print(f"\n{ts()} {BOLD}{CYAN}[DORK #{dork_id}] {name}{RESET}")
    print(f"{DIM}  Category : {category}{RESET}")
    print(f"{DIM}  Query    : {query}{RESET}")
    print(f"{DIM}  Pages    : {max_pages} | Key aktif: {active_now}/{len(key_mgr.keys)}{RESET}")
    print(f"  {'─'*55}")

    page = 0
    while page < max_pages:
        if key_mgr.all_exhausted_for_dork():
            print(f"\n{ts()} {YELLOW}[DORK #{dork_id}] Semua key habis quota untuk dork ini. "
                  f"Lanjut dork berikutnya.{RESET}")
            break

        key_before = key_mgr.current_index()
        print(f"{ts()} {WHITE}  Page {page+1}/{max_pages} → Key #{key_before+1} | Found: {found}{RESET}", end="\r")

        uris = fetch_page(query, page, key_mgr, delay_api=delay_api)

        # None = sinyal IP ban (Cloudflare 1006) → hentikan seluruh session
        if uris is None:
            print(f"\n{ts()} {RED}[ABORT] IP ban terdeteksi. Hentikan dorking.{RESET}")
            print(f"{ts()} {YELLOW}  Ganti IP terlebih dahulu lalu jalankan ulang dengan --append{RESET}")
            return -1  # sinyal IP ban ke caller

        key_after = key_mgr.current_index()

        # Key rotasi saat fetch (kena limit di tengah fetch) → ulangi page yang sama
        if key_before != key_after and not key_mgr.all_exhausted_for_dork():
            print(f"\n{ts()} {YELLOW}  [KEY ROTATED] Ulangi page {page+1} dengan key #{key_after+1}{RESET}")
            time.sleep(delay_api)
            continue

        # Proses URI yang kembali
        if uris:
            new_count = 0
            for uri in uris:
                if save_result(uri, output_file, seen):
                    new_count += 1
                    found     += 1
                    print(f"\n{ts()} {GREEN}  [+] {normalize_uri(uri)}{RESET}")
            if new_count == 0:
                print(f"\n{ts()} {DIM}  Page {page+1}: {len(uris)} item (semua duplikat){RESET}")
        else:
            # Kosong & key tidak rotasi = query benar-benar habis hasilnya
            if not key_mgr.all_exhausted_for_dork():
                print(f"\n{ts()} {DIM}  Page {page+1}: Kosong — tidak ada hasil lebih lanjut.{RESET}")
                break

        page += 1

        if page < max_pages and not key_mgr.all_exhausted_for_dork():
            time.sleep(random.uniform(delay_api * 0.5, delay_api * 1.5))

    print(f"\n{ts()} {GREEN}[DORK #{dork_id}] Selesai → {found} URI baru ditemukan{RESET}")
    print(f"  {'─'*55}")

    if delay_dork > 0:
        jd = random.uniform(delay_dork * 0.8, delay_dork * 1.4)
        print(f"{ts()} {DIM}  [JEDA] {jd:.1f}s sebelum dork berikutnya...{RESET}")
        time.sleep(jd)

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


# ─── POST-PROCESS DEDUP ───────────────────────────────────────
def final_dedup(output_file: str) -> tuple:
    """
    Baca file output, hapus semua duplikat (case-insensitive untuk scheme+host),
    tulis ulang file dengan bersih, tampilkan statistik.

    Return: (total_sebelum, total_sesudah, total_dihapus)
    """
    if not os.path.exists(output_file):
        return 0, 0, 0

    print(f"\n{ts()} {BOLD}{CYAN}[FINAL DEDUP] Memproses file: {output_file}{RESET}")

    # Baca semua baris
    with open(output_file, "r", encoding="utf-8", errors="ignore") as f:
        raw_lines = f.readlines()

    total_before = len([l for l in raw_lines if l.strip()])

    # Pass 1: normalize semua URI
    # Key dedup = scheme://hostname_lowercase[:port]
    # Value     = URI asli (pertama yang ditemukan = yang disimpan)
    seen_keys   = {}   # normalized_key → original_uri
    duplicates  = 0
    invalid     = 0

    for line in raw_lines:
        uri = line.strip()
        if not uri:
            continue

        # Normalize
        clean = normalize_uri(uri)
        if not clean:
            invalid += 1
            continue

        # Key = lowercase hostname untuk case-insensitive dedup
        # Misal: https://Example.com == https://example.com
        try:
            p    = urlparse(clean)
            key  = f"{p.scheme}://{p.hostname.lower()}"
            if p.port and p.port not in (80, 443):
                key += f":{p.port}"
        except Exception:
            key = clean.lower()

        if key not in seen_keys:
            seen_keys[key] = clean
        else:
            duplicates += 1

    # Hasil bersih — sorted untuk output yang rapi
    clean_uris   = sorted(seen_keys.values())
    total_after  = len(clean_uris)
    total_removed = total_before - total_after

    # Tulis ulang file
    with open(output_file, "w", encoding="utf-8") as f:
        for uri in clean_uris:
            f.write(uri + "\n")

    # Laporan
    print(f"  {'─'*55}")
    print(f"  URI sebelum dedup : {WHITE}{total_before}{RESET}")
    print(f"  URI duplikat      : {YELLOW}{duplicates}{RESET}")
    print(f"  URI invalid/skip  : {RED}{invalid}{RESET}")
    print(f"  URI bersih final  : {GREEN}{total_after}{RESET}")
    if total_removed > 0:
        print(f"  {GREEN}✓ {total_removed} duplikat berhasil dihapus dari file.{RESET}")
    else:
        print(f"  {DIM}✓ Tidak ada duplikat — file sudah bersih.{RESET}")
    print(f"  {'─'*55}")

    return total_before, total_after, total_removed


# ─── STATS ────────────────────────────────────────────────────
def print_stats(total_found: int, total_dorks: int, elapsed: float,
                output_file: str, key_mgr: APIKeyManager,
                dedup_before: int = 0, dedup_after: int = 0, dedup_removed: int = 0):
    print(f"\n{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{WHITE}  NETLAS DORKER — SELESAI{RESET}")
    print(f"{CYAN}{'═'*60}{RESET}")
    print(f"  Total URI ditemukan  : {GREEN}{total_found}{RESET}")
    print(f"  Dorks dijalankan     : {WHITE}{total_dorks}{RESET}")
    print(f"  Key valid (aktif)    : {CYAN}{len(key_mgr.keys) - key_mgr.total_hard_dead()}/{len(key_mgr.keys)}{RESET}")
    print(f"  Key invalid (dead)   : {RED}{key_mgr.total_hard_dead()}{RESET}")
    print(f"  Waktu total          : {WHITE}{elapsed:.1f}s{RESET}")
    if dedup_removed > 0:
        print(f"  {'─'*40}")
        print(f"  URI sebelum dedup    : {WHITE}{dedup_before}{RESET}")
        print(f"  Duplikat dihapus     : {YELLOW}{dedup_removed}{RESET}")
        print(f"  URI final (bersih)   : {GREEN}{dedup_after}{RESET}")
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

  # Single API key langsung (tanpa file key_list.txt)
  python3 netlas_dorker.py --api YOUR_API_KEY --pages 5
  python3 netlas_dorker.py --api YOUR_API_KEY --dork-index 1 3 7 --pages 8

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

    # Files / API key
    parser.add_argument("--key-file",   default=API_KEY_FILE,
                        help=f"Path file API key (default: {API_KEY_FILE})")
    parser.add_argument("--api",        default=None, metavar="KEY",
                        help="Gunakan satu API key langsung (tanpa file). "
                             "Contoh: --api ABC123xyz")
    parser.add_argument("--output",     default=OUTPUT_DEFAULT,
                        help=f"File output hasil (default: {OUTPUT_DEFAULT})")
    parser.add_argument("--append",     action="store_true",
                        help="Append ke output file yang sudah ada (default: overwrite)")

    # Timing / stealth
    parser.add_argument("--delay-api",  type=float, default=3.0,
                        help="Jeda antar request ke API (detik, default: 3.0)")
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
    # Prioritas: --api (single key) > --key-file (file)
    if args.api:
        api_key_clean = args.api.strip()
        if not api_key_clean:
            print(f"{RED}[!] --api diberikan tapi kosong.{RESET}")
            return 1
        keys = [api_key_clean]
        print(f"{ts()} {GREEN}[KEYS] Single API key dari --api: {api_key_clean[:8]}...{RESET}")
    else:
        keys = load_api_keys(args.key_file)
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
        if key_mgr.all_hard_dead():
            print(f"\n{ts()} {RED}[STOP] Semua key invalid/dead permanent. "
                  f"Dork selesai: {dorks_done}/{len(dorks_to_run)}{RESET}")
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

        # -1 = sinyal IP ban → stop seluruh session
        if found == -1:
            print(f"\n{ts()} {RED}[SESSION STOP] IP ban aktif. Jalankan ulang setelah ganti IP.{RESET}")
            print(f"{ts()} {DIM}  Tip: python3 netlas_dorker.py --pages {args.pages} --append{RESET}")
            elapsed = time.monotonic() - start_time
            if not args.no_dedup:
                dedup_before, dedup_after, dedup_removed = final_dedup(output_file)
            print_stats(total_found, dorks_done, elapsed, output_file, key_mgr,
                        dedup_before, dedup_after, dedup_removed)
            return 1

        total_found += found
        dorks_done  += 1

        elapsed_so_far = time.monotonic() - start_time
        remaining      = len(dorks_to_run) - dorks_done
        dead           = key_mgr.total_hard_dead()
        print(f"{ts()} {DIM}  Progress: {dorks_done}/{len(dorks_to_run)} dork | "
              f"URI: {total_found} | "
              f"Elapsed: {elapsed_so_far:.0f}s | "
              f"Sisa: {remaining} dork | "
              f"Key dead: {dead}/{len(key_mgr.keys)}{RESET}")

    elapsed = time.monotonic() - start_time

    # ── Final dedup: bersihkan file output dari semua duplikat ──
    dedup_before = dedup_after = dedup_removed = 0
    if not args.no_dedup:
        dedup_before, dedup_after, dedup_removed = final_dedup(output_file)

    print_stats(total_found, dorks_done, elapsed, output_file, key_mgr,
                dedup_before, dedup_after, dedup_removed)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}[!] Dihentikan oleh user (Ctrl+C). Hasil yang ada sudah tersimpan.{RESET}\n")
        sys.exit(0)
