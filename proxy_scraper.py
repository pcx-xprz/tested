"""
Hatcher.host Tools — Proxy Scraper + Scanner v2
================================================
Scrape dari 35+ sumber publik, scan async concurrent:
  - Alive check: HTTP/HTTPS/SOCKS4/SOCKS5
  - Latency (ms)
  - Anonimitas: elite / anonymous / transparent
  - Output berwarna (Windows CMD & WSL Ubuntu)

Install:
  pip install aiohttp aiohttp-socks PySocks colorama
  python proxy_scraper.py
"""

# ── Fix Windows Proactor event loop error (WinError 10054) ────────────────────
import sys, os

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
import aiohttp
import json
import logging
import re
import time
import socket
from datetime import datetime

# ── Warna (colorama untuk Windows CMD, ANSI untuk WSL/Linux) ──────────────────
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    C_GREEN   = Fore.GREEN
    C_RED     = Fore.RED
    C_YELLOW  = Fore.YELLOW
    C_CYAN    = Fore.CYAN
    C_BLUE    = Fore.BLUE
    C_MAGENTA = Fore.MAGENTA
    C_WHITE   = Fore.WHITE
    C_BOLD    = Style.BRIGHT
    C_RESET   = Style.RESET_ALL
    HAS_COLOR = True
except ImportError:
    # Fallback ANSI tanpa colorama (untuk WSL/Linux)
    C_GREEN   = "\033[92m"
    C_RED     = "\033[91m"
    C_YELLOW  = "\033[93m"
    C_CYAN    = "\033[96m"
    C_BLUE    = "\033[94m"
    C_MAGENTA = "\033[95m"
    C_WHITE   = "\033[97m"
    C_BOLD    = "\033[1m"
    C_RESET   = "\033[0m"
    HAS_COLOR = True
    print("[INFO] colorama tidak terinstall, pakai ANSI. Install: pip install colorama")



# ── SOCKS support ──────────────────────────────────────────────────────────────
try:
    from aiohttp_socks import ProxyConnector, ProxyType
    SOCKS_SUPPORT = True
except ImportError:
    SOCKS_SUPPORT = False

# ─── CONFIG ───────────────────────────────────────────────────────────────────
OUTPUT_RAW   = "proxies_all.txt"
OUTPUT_ALIVE = "proxies_alive.txt"
OUTPUT_JSON  = "proxies_alive.json"
LOG_FILE     = "proxy_scan.log"

TIMEOUT    = 7       # detik timeout per proxy (lebih pendek = lebih cepat)
CONCURRENT = 300     # concurrent checks (naikkan jika RAM cukup)
# URL ringan untuk check — plain text IP return, bukan JSON besar
CHECK_URLS = [
    "http://ifconfig.me/ip",
    "http://api.ipify.org",
    "http://checkip.amazonaws.com",
]

# ── Fix encoding Windows ───────────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Logging (file plain, console dengan warna) ────────────────────────────────
class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG:    C_WHITE,
        logging.INFO:     C_CYAN,
        logging.WARNING:  C_YELLOW,
        logging.ERROR:    C_RED,
        logging.CRITICAL: C_MAGENTA + C_BOLD,
    }
    def format(self, record):
        color  = self.LEVEL_COLORS.get(record.levelno, C_RESET)
        msg    = super().format(record)
        return f"{color}{msg}{C_RESET}"

file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColorFormatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
log = logging.getLogger(__name__)



# ─────────────────────────────────────────────────────────────────────────────
# SUMBER PROXY (35+ sumber, update frequent)
# ─────────────────────────────────────────────────────────────────────────────
PROXY_SOURCES = [
    # ProxyScrape API — update tiap 5 menit
    ("https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&timeout=10000&proxy_format=ipport&format=text",   "http",   "plain"),
    ("https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks4&timeout=10000&proxy_format=ipport&format=text", "socks4", "plain"),
    ("https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=10000&proxy_format=ipport&format=text", "socks5", "plain"),
    # TheSpeedX — update harian
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "socks5", "plain"),
    # monosans — update tiap jam
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "socks5", "plain"),
    # prxchk — update tiap 10 menit
    ("https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/prxchk/proxy-list/main/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt", "socks5", "plain"),
    # r00tee
    ("https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",  "https",  "plain"),
    ("https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt", "socks5", "plain"),
    # ShiftyTR
    ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",  "https",  "plain"),
    ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt", "socks5", "plain"),
    # vakhov fresh-proxy-list
    ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",  "https",  "plain"),
    ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt", "socks5", "plain"),
    # hookzof socks5
    ("https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "socks5", "plain"),
    # jetkai
    ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",  "https",  "plain"),
    ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt", "socks5", "plain"),
    # clarketm
    ("https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "http", "plain"),
    # mmpx12
    ("https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt",  "https",  "plain"),
    ("https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt", "socks5", "plain"),
    # ProxyScraper/ProxyScraper
    ("https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",   "http",   "plain"),
    ("https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt", "socks4", "plain"),
    ("https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt", "socks5", "plain"),
]

PROXY_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}:\d{2,5}$")



# ─────────────────────────────────────────────────────────────────────────────
# HELPER: print berwarna langsung ke stdout (bypass logging format)
# ─────────────────────────────────────────────────────────────────────────────
def cprint(msg: str, color: str = C_RESET, bold: bool = False):
    prefix = C_BOLD if bold else ""
    print(f"{prefix}{color}{msg}{C_RESET}", flush=True)


def banner():
    cprint("╔══════════════════════════════════════════════════════════════╗", C_CYAN, True)
    cprint("║      Hatcher Tools — Proxy Scraper + Scanner  v2.0          ║", C_CYAN, True)
    cprint("║  35+ sumber  |  HTTP / HTTPS / SOCKS4 / SOCKS5              ║", C_CYAN, True)
    cprint("║  Async concurrent  |  Latency  |  Anonimitas                ║", C_CYAN, True)
    cprint("╚══════════════════════════════════════════════════════════════╝", C_CYAN, True)
    print()
    if not SOCKS_SUPPORT:
        cprint("  [!] aiohttp-socks belum terinstall → SOCKS4/5 di-skip!", C_YELLOW, True)
        cprint("      Jalankan: pip install aiohttp-socks PySocks", C_YELLOW)
        print()


# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 1: SCRAPER
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_source(session: aiohttp.ClientSession,
                       url: str, proxy_type: str, mode: str) -> list:
    proxies = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning(f"SKIP {url[:55]} → HTTP {resp.status}")
                return []
            text = await resp.text(encoding="utf-8", errors="ignore")

        if mode == "plain":
            for line in text.splitlines():
                line = line.strip()
                line = re.sub(r"^(https?|socks[45])://", "", line)
                m = re.match(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5})", line)
                if m:
                    proxies.append((m.group(1), proxy_type))

        log.info(f"OK  {url[40:90]:<50}  {C_GREEN}{len(proxies):>5}{C_RESET} proxy")
    except Exception as e:
        log.warning(f"ERR {url[:55]} → {str(e)[:60]}")
    return proxies


async def scrape_all() -> dict:
    TYPE_PRIO = {"socks5": 4, "socks4": 3, "https": 2, "http": 1}
    all_proxies: dict = {}

    cprint(f"\n[SCRAPE] Memulai scraping dari {len(PROXY_SOURCES)} sumber ...", C_CYAN, True)
    connector = aiohttp.TCPConnector(ssl=False, limit=50)
    headers   = {"User-Agent": "Mozilla/5.0 (compatible; ProxyScraper/2.0)"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        results = await asyncio.gather(
            *[fetch_source(session, u, t, m) for u, t, m in PROXY_SOURCES],
            return_exceptions=True
        )

    for res in results:
        if isinstance(res, list):
            for addr, ptype in res:
                if PROXY_RE.match(addr):
                    if TYPE_PRIO.get(ptype, 0) >= TYPE_PRIO.get(all_proxies.get(addr, ""), 0):
                        all_proxies[addr] = ptype

    # Statistik breakdown
    counts = {}
    for t in all_proxies.values():
        counts[t] = counts.get(t, 0) + 1

    cprint(f"\n[SCRAPE] Selesai — {C_GREEN}{C_BOLD}{len(all_proxies)}{C_RESET}{C_CYAN} proxy unik", C_CYAN)
    for t in ("http", "https", "socks4", "socks5"):
        if counts.get(t, 0):
            cprint(f"         {t.upper():<8}: {counts[t]}", C_WHITE)
    print()
    return all_proxies



# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 2: SCANNER
# ─────────────────────────────────────────────────────────────────────────────
def detect_anon(body: str, proxy_addr: str) -> str:
    ip   = proxy_addr.split(":")[0]
    blow = body.lower()
    if ip in body:
        return "transparent"
    if "x-forwarded-for" in blow or "via" in blow or "forwarded" in blow:
        return "anonymous"
    return "elite"


async def _http_check(session: aiohttp.ClientSession, addr: str, ptype: str) -> dict:
    """
    Coba CHECK_URLS satu per satu sampai berhasil.
    Suppress semua exception (WinError 10054, dll) — cukup return alive=False.
    """
    for url in CHECK_URLS:
        try:
            start = time.perf_counter()
            async with session.get(
                url,
                proxy=f"http://{addr}",
                timeout=aiohttp.ClientTimeout(total=TIMEOUT, connect=4),
                ssl=False,
            ) as resp:
                if resp.status == 200:
                    latency = round((time.perf_counter() - start) * 1000)
                    body    = (await resp.text(errors="ignore")).strip()
                    return {
                        "proxy": addr, "type": ptype, "alive": True,
                        "latency": latency, "anon": detect_anon(body, addr),
                    }
        except Exception:
            # Tangkap semua error: ConnectionReset, Timeout, SSL, dll
            continue
    return {"proxy": addr, "type": ptype, "alive": False}


async def _socks_check(addr: str, ptype: str) -> dict:
    if not SOCKS_SUPPORT:
        return {"proxy": addr, "type": ptype, "alive": False}
    host, port = addr.rsplit(":", 1)
    stype = ProxyType.SOCKS5 if ptype == "socks5" else ProxyType.SOCKS4
    for url in CHECK_URLS:
        try:
            conn  = ProxyConnector(proxy_type=stype, host=host, port=int(port), rdns=True)
            start = time.perf_counter()
            async with aiohttp.ClientSession(
                connector=conn,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT, connect=4)
            ) as sess:
                async with sess.get(url, ssl=False) as resp:
                    if resp.status == 200:
                        latency = round((time.perf_counter() - start) * 1000)
                        body    = (await resp.text(errors="ignore")).strip()
                        return {
                            "proxy": addr, "type": ptype, "alive": True,
                            "latency": latency, "anon": detect_anon(body, addr),
                        }
        except Exception:
            continue
    return {"proxy": addr, "type": ptype, "alive": False}


async def scan_all(proxy_dict: dict) -> list:
    total      = len(proxy_dict)
    sem        = asyncio.Semaphore(CONCURRENT)
    results    = []
    checked    = 0
    lock       = asyncio.Lock()
    start_all  = time.perf_counter()

    # Progress bar sederhana
    def _progress(checked, total, alive_count, eta_s):
        pct  = checked / total * 100
        bar  = int(pct / 2)
        fill = "█" * bar + "░" * (50 - bar)
        eta  = f"{int(eta_s)}s" if eta_s > 0 else "?"
        line = (
            f"\r  {C_CYAN}[{fill}]{C_RESET} "
            f"{C_BOLD}{pct:5.1f}%{C_RESET}  "
            f"{C_GREEN}{alive_count}{C_RESET} alive  "
            f"{checked}/{total}  ETA {eta}   "
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    cprint(f"[SCAN] Mulai scan {C_BOLD}{total}{C_RESET}{C_CYAN} proxy "
           f"(concurrent={CONCURRENT}, timeout={TIMEOUT}s) ...", C_CYAN, False)
    if not SOCKS_SUPPORT:
        cprint("       SOCKS4/SOCKS5 di-skip (install aiohttp-socks)", C_YELLOW)
    print()

    async def run_http(addr, ptype):
        nonlocal checked
        async with sem:
            conn = aiohttp.TCPConnector(ssl=False, enable_cleanup_closed=True)
            try:
                async with aiohttp.ClientSession(connector=conn) as sess:
                    res = await _http_check(sess, addr, ptype)
            except Exception:
                res = {"proxy": addr, "type": ptype, "alive": False}
            finally:
                # Pastikan connector ditutup untuk hindari ResourceWarning
                await conn.close()
        async with lock:
            checked += 1
            results.append(res)
            if checked % 200 == 0 or checked == total:
                alive_n = sum(1 for r in results if r.get("alive"))
                elapsed = time.perf_counter() - start_all
                rate    = checked / elapsed if elapsed > 0 else 1
                eta     = (total - checked) / rate if rate > 0 else 0
                _progress(checked, total, alive_n, eta)

    async def run_socks(addr, ptype):
        nonlocal checked
        async with sem:
            try:
                res = await _socks_check(addr, ptype)
            except Exception:
                res = {"proxy": addr, "type": ptype, "alive": False}
        async with lock:
            checked += 1
            results.append(res)
            if checked % 200 == 0 or checked == total:
                alive_n = sum(1 for r in results if r.get("alive"))
                elapsed = time.perf_counter() - start_all
                rate    = checked / elapsed if elapsed > 0 else 1
                eta     = (total - checked) / rate if rate > 0 else 0
                _progress(checked, total, alive_n, eta)

    tasks = []
    for addr, ptype in proxy_dict.items():
        if ptype in ("http", "https"):
            tasks.append(asyncio.create_task(run_http(addr, ptype)))
        else:
            tasks.append(asyncio.create_task(run_socks(addr, ptype)))

    await asyncio.gather(*tasks, return_exceptions=True)

    print()  # newline setelah progress bar

    alive = [r for r in results if r.get("alive")]
    order = {"socks5": 0, "socks4": 1, "https": 2, "http": 3}
    alive.sort(key=lambda x: (order.get(x["type"], 9), x.get("latency", 9999)))
    return alive



# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 3: OUTPUT & SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def save_raw(proxy_dict: dict):
    with open(OUTPUT_RAW, "w", encoding="utf-8") as f:
        for addr, ptype in proxy_dict.items():
            f.write(f"{ptype}://{addr}\n")


def save_alive(alive: list):
    with open(OUTPUT_ALIVE, "w", encoding="utf-8") as f:
        for p in alive:
            f.write(f"{p['type']}://{p['proxy']}\n")

    out = {
        "generated_at": datetime.now().isoformat(),
        "total_alive":  len(alive),
        "breakdown": {
            "http":   sum(1 for p in alive if p["type"] == "http"),
            "https":  sum(1 for p in alive if p["type"] == "https"),
            "socks4": sum(1 for p in alive if p["type"] == "socks4"),
            "socks5": sum(1 for p in alive if p["type"] == "socks5"),
        },
        "proxies": alive,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def print_summary(proxy_dict: dict, alive: list, t_scrape: float, t_scan: float):
    total = len(proxy_dict)
    print()
    cprint("╔══════════════════════════════════════════════════════════════╗", C_GREEN, True)
    cprint("║                      HASIL AKHIR                            ║", C_GREEN, True)
    cprint("╚══════════════════════════════════════════════════════════════╝", C_GREEN, True)

    cprint(f"  Waktu      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", C_WHITE)
    cprint(f"  Total scan : {total}  |  Scrape: {t_scrape:.1f}s  Scan: {t_scan:.1f}s", C_WHITE)
    cprint(f"  Alive      : {C_GREEN}{C_BOLD}{len(alive)}{C_RESET}  /  "
           f"Dead: {C_RED}{total - len(alive)}{C_RESET}", "")

    if alive:
        print()
        cprint("  Breakdown Tipe:", C_CYAN, True)
        TYPE_COLOR = {"http": C_BLUE, "https": C_CYAN, "socks4": C_MAGENTA, "socks5": C_GREEN}
        for ptype in ("socks5", "socks4", "https", "http"):
            c = sum(1 for p in alive if p["type"] == ptype)
            if c:
                bar = "█" * min(c, 40)
                cprint(f"    {ptype.upper():<8} {TYPE_COLOR.get(ptype,C_WHITE)}{bar} {c}{C_RESET}", "")

        avg_lat = sum(p["latency"] for p in alive) // len(alive)
        min_lat = min(p["latency"] for p in alive)
        print()
        cprint(f"  Latency rata-rata : {avg_lat} ms", C_WHITE)
        cprint(f"  Latency terbaik   : {C_GREEN}{min_lat} ms{C_RESET}", "")

        # Anonimitas
        anon_cnt: dict = {}
        for p in alive:
            k = p.get("anon", "?")
            anon_cnt[k] = anon_cnt.get(k, 0) + 1
        print()
        cprint("  Anonimitas:", C_CYAN, True)
        ANON_COLOR = {"elite": C_GREEN, "anonymous": C_YELLOW, "transparent": C_RED}
        for lvl in ("elite", "anonymous", "transparent"):
            n = anon_cnt.get(lvl, 0)
            if n:
                cprint(f"    {lvl:<12} : {ANON_COLOR.get(lvl, C_WHITE)}{n}{C_RESET}", "")

        # Top 15 tercepat
        print()
        cprint("  Top 15 Proxy Tercepat:", C_CYAN, True)
        cprint(f"  {'#':<4} {'TYPE':<8} {'PROXY':<26} {'LATENCY':>9}  {'ANON'}", C_WHITE, True)
        cprint(f"  {'─'*4} {'─'*8} {'─'*26} {'─'*9}  {'─'*12}", C_WHITE)
        ANON_SYM = {"elite": f"{C_GREEN}●{C_RESET}", "anonymous": f"{C_YELLOW}◉{C_RESET}", "transparent": f"{C_RED}○{C_RESET}"}
        for i, p in enumerate(alive[:15], 1):
            tc   = TYPE_COLOR.get(p["type"], C_WHITE)
            lat  = p["latency"]
            lc   = C_GREEN if lat < 1000 else (C_YELLOW if lat < 3000 else C_RED)
            sym  = ANON_SYM.get(p.get("anon", "?"), "?")
            print(
                f"  {C_WHITE}{i:<4}{C_RESET}"
                f"{tc}{p['type'].upper():<8}{C_RESET}"
                f"{p['proxy']:<26} "
                f"{lc}{lat:>6}ms{C_RESET}  "
                f"{sym} {p.get('anon','?')}"
            )

    print()
    cprint("  Output files:", C_CYAN, True)
    cprint(f"    {C_WHITE}{OUTPUT_RAW:<20}{C_RESET}  — semua proxy mentah ({total})", "")
    cprint(f"    {C_WHITE}{OUTPUT_ALIVE:<20}{C_RESET}  — proxy hidup ({len(alive)})", "")
    cprint(f"    {C_WHITE}{OUTPUT_JSON:<20}{C_RESET}  — detail JSON (type, latency, anon)", "")
    cprint(f"    {C_WHITE}{LOG_FILE:<20}{C_RESET}  — log lengkap", "")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    banner()

    # ── SCRAPE ────────────────────────────────────────────────────────────
    t0         = time.perf_counter()
    proxy_dict = await scrape_all()
    t_scrape   = round(time.perf_counter() - t0, 1)
    save_raw(proxy_dict)
    cprint(f"[SAVE] {len(proxy_dict)} proxy mentah → {OUTPUT_RAW}  ({t_scrape}s)", C_CYAN)

    if not proxy_dict:
        cprint("[ERR] Tidak ada proxy! Periksa koneksi internet.", C_RED, True)
        return

    # ── SCAN ──────────────────────────────────────────────────────────────
    t1     = time.perf_counter()
    alive  = await scan_all(proxy_dict)
    t_scan = round(time.perf_counter() - t1, 1)
    cprint(f"[SCAN] Selesai — {C_GREEN}{len(alive)}{C_RESET}{C_CYAN} proxy hidup  ({t_scan}s)", C_CYAN)

    # ── SIMPAN ────────────────────────────────────────────────────────────
    save_alive(alive)
    print_summary(proxy_dict, alive, t_scrape, t_scan)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cprint("\n[STOP] Dihentikan oleh user.", C_YELLOW, True)
