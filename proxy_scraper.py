"""
Hatcher.host Tools — Proxy Scraper + Scanner
=============================================
Scrape proxy dari 15+ sumber publik terpercaya,
lalu scan secara async (concurrent) untuk cek:
  - Apakah proxy hidup / alive
  - Tipe: http / https / socks4 / socks5
  - Response time (latency ms)
  - Anonimitas (transparent / anonymous / elite)

Output:
  - proxies_all.txt       — semua proxy mentah (host:port)
  - proxies_alive.txt     — proxy hidup saja
  - proxies_alive.json    — detail lengkap (type, latency, anon)
  - proxy_scan.log        — log proses

Cara pakai:
  pip install aiohttp aiohttp-socks PySocks requests
  python3 proxy_scraper.py
"""

import asyncio
import aiohttp
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

try:
    from aiohttp_socks import ProxyConnector, ProxyType
    SOCKS_SUPPORT = True
except ImportError:
    SOCKS_SUPPORT = False
    print("[WARN] aiohttp-socks tidak terinstall, SOCKS4/5 check dinonaktifkan.")
    print("       Jalankan: pip install aiohttp-socks PySocks")

# ─── CONFIG ───────────────────────────────────────────────────────────────────
OUTPUT_RAW     = "proxies_all.txt"
OUTPUT_ALIVE   = "proxies_alive.txt"
OUTPUT_JSON    = "proxies_alive.json"
LOG_FILE       = "proxy_scan.log"

TIMEOUT        = 8          # detik timeout per proxy check
CONCURRENT     = 200        # jumlah check bersamaan (turunkan jika RAM terbatas)
CHECK_URL      = "http://ifconfig.me/ip"   # endpoint ringan untuk cek proxy hidup
CHECK_URL_ALT  = "http://ip-api.com/json"  # backup cek

# Fix encoding Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ─── LOGGING ──────────────────────────────────────────────────────────────────
file_handler    = logging.FileHandler(LOG_FILE, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[file_handler, console_handler]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 1: SUMBER PROXY
# ─────────────────────────────────────────────────────────────────────────────
# Setiap entry: (url, proxy_type, parser_mode)
# parser_mode: 'plain'  = satu proxy per baris (ip:port)
#              'csv'    = CSV format (ip,port,...)
#              'json'   = JSON API response

PROXY_SOURCES = [
    # ── ProxyScrape API (update tiap 5 menit) ─────────────────────────────
    (
        "https://api.proxyscrape.com/v3/free-proxy-list/get"
        "?request=displayproxies&protocol=http&timeout=10000&proxy_format=ipport&format=text",
        "http", "plain"
    ),
    (
        "https://api.proxyscrape.com/v3/free-proxy-list/get"
        "?request=displayproxies&protocol=socks4&timeout=10000&proxy_format=ipport&format=text",
        "socks4", "plain"
    ),
    (
        "https://api.proxyscrape.com/v3/free-proxy-list/get"
        "?request=displayproxies&protocol=socks5&timeout=10000&proxy_format=ipport&format=text",
        "socks5", "plain"
    ),

    # ── TheSpeedX/PROXY-List (update harian) ──────────────────────────────
    (
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "socks5", "plain"
    ),

    # ── monosans/proxy-list (update tiap jam) ─────────────────────────────
    (
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "socks5", "plain"
    ),

    # ── prxchk/proxy-list (update tiap 10 menit) ──────────────────────────
    (
        "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/prxchk/proxy-list/main/socks5.txt",
        "socks5", "plain"
    ),

    # ── r00tee/Proxy-List ─────────────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
        "https", "plain"
    ),
    (
        "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt",
        "socks5", "plain"
    ),

    # ── ShiftyTR/Proxy-List ───────────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
        "https", "plain"
    ),
    (
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
        "socks5", "plain"
    ),

    # ── vakhov/fresh-proxy-list ───────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
        "https", "plain"
    ),
    (
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
        "socks5", "plain"
    ),

    # ── hookzof/socks5_list ───────────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "socks5", "plain"
    ),

    # ── jetkai/proxy-list ─────────────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
        "https", "plain"
    ),
    (
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
        "socks5", "plain"
    ),

    # ── free-proxy-list.net (HTML parse) ──────────────────────────────────
    (
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "http", "plain"
    ),

    # ── mmpx12/proxy-list ─────────────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/https.txt",
        "https", "plain"
    ),
    (
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
        "socks5", "plain"
    ),

    # ── ProxyScraper/ProxyScraper ─────────────────────────────────────────
    (
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",
        "http", "plain"
    ),
    (
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt",
        "socks4", "plain"
    ),
    (
        "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt",
        "socks5", "plain"
    ),
]

PROXY_PATTERN = re.compile(r"^(\d{1,3}\.){3}\d{1,3}:\d{2,5}$")


# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 2: SCRAPER
# ─────────────────────────────────────────────────────────────────────────────
async def fetch_source(session: aiohttp.ClientSession, url: str, proxy_type: str, mode: str) -> list:
    """Download 1 sumber proxy, return list of (ip:port, proxy_type)."""
    proxies = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                log.warning(f"  [SKIP] {url[:60]} -> HTTP {resp.status}")
                return []
            text = await resp.text(encoding="utf-8", errors="ignore")

        if mode == "plain":
            for line in text.splitlines():
                line = line.strip()
                # Hapus prefix protocol jika ada (http://, socks5://, dll)
                line = re.sub(r"^(https?|socks[45])://", "", line)
                # Ambil hanya ip:port
                match = re.match(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5})", line)
                if match:
                    proxies.append((match.group(1), proxy_type))

        elif mode == "csv":
            # Format: ip,port,countryCode,anonymity,google,https,lastChecked
            for line in text.splitlines():
                parts = line.split(",")
                if len(parts) >= 2:
                    ip, port = parts[0].strip(), parts[1].strip()
                    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip) and port.isdigit():
                        proxies.append((f"{ip}:{port}", proxy_type))

        log.info(f"  [OK] {url[:70]} -> {len(proxies)} proxy")
    except Exception as e:
        log.warning(f"  [ERR] {url[:60]} -> {e}")
    return proxies


async def scrape_all_sources() -> dict:
    """
    Scrape semua sumber secara concurrent.
    Return: dict { 'ip:port' -> proxy_type }
    Jika ip:port muncul di beberapa sumber, prioritas: socks5 > socks4 > https > http
    """
    TYPE_PRIORITY = {"socks5": 4, "socks4": 3, "https": 2, "http": 1}
    all_proxies = {}

    log.info(f"\n[SCRAPE] Memulai scraping dari {len(PROXY_SOURCES)} sumber ...")
    connector = aiohttp.TCPConnector(ssl=False, limit=50)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ProxyScraper/2.0)"}

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = [
            fetch_source(session, url, ptype, mode)
            for url, ptype, mode in PROXY_SOURCES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            for addr, ptype in result:
                if PROXY_PATTERN.match(addr):
                    existing_prio  = TYPE_PRIORITY.get(all_proxies.get(addr, ""), 0)
                    new_prio       = TYPE_PRIORITY.get(ptype, 0)
                    if new_prio >= existing_prio:
                        all_proxies[addr] = ptype

    log.info(f"[SCRAPE] Total unik setelah deduplikasi: {len(all_proxies)} proxy\n")
    return all_proxies


# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 3: SCANNER (async)
# ─────────────────────────────────────────────────────────────────────────────
async def check_http_proxy(session: aiohttp.ClientSession, addr: str, ptype: str) -> dict:
    """Check HTTP/HTTPS proxy via aiohttp proxy parameter."""
    proxy_url = f"http://{addr}"
    start = time.perf_counter()
    try:
        async with session.get(
            CHECK_URL,
            proxy=proxy_url,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            ssl=False,
        ) as resp:
            if resp.status == 200:
                latency = round((time.perf_counter() - start) * 1000)
                body    = await resp.text()
                # Cek apakah IP yang dikembalikan berbeda dari IP kita (anonimitas)
                anon = detect_anonymity(body, addr)
                return {
                    "proxy":   addr,
                    "type":    ptype,
                    "alive":   True,
                    "latency": latency,
                    "anon":    anon,
                }
    except Exception:
        pass
    return {"proxy": addr, "type": ptype, "alive": False}


async def check_socks_proxy(addr: str, ptype: str) -> dict:
    """Check SOCKS4/SOCKS5 proxy via aiohttp-socks."""
    if not SOCKS_SUPPORT:
        return {"proxy": addr, "type": ptype, "alive": False}

    host, port_str = addr.rsplit(":", 1)
    port = int(port_str)

    socks_type = ProxyType.SOCKS5 if ptype == "socks5" else ProxyType.SOCKS4
    try:
        connector = ProxyConnector(
            proxy_type=socks_type,
            host=host,
            port=port,
            rdns=True,
        )
        start = time.perf_counter()
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=TIMEOUT)
        ) as session:
            async with session.get(CHECK_URL, ssl=False) as resp:
                if resp.status == 200:
                    latency = round((time.perf_counter() - start) * 1000)
                    body    = await resp.text()
                    anon    = detect_anonymity(body, addr)
                    return {
                        "proxy":   addr,
                        "type":    ptype,
                        "alive":   True,
                        "latency": latency,
                        "anon":    anon,
                    }
    except Exception:
        pass
    return {"proxy": addr, "type": ptype, "alive": False}


def detect_anonymity(response_body: str, proxy_addr: str) -> str:
    """
    Tentukan level anonimitas proxy:
      elite       - IP asli tidak terlihat, tidak ada header X-Forwarded-For
      anonymous   - IP asli tersembunyi tapi header proxy terdeteksi
      transparent - IP asli terekspos
    """
    proxy_ip  = proxy_addr.split(":")[0]
    body_low  = response_body.lower()
    # ifconfig.me /ip hanya return plain IP — kita cek apakah mirip IP proxy
    if proxy_ip in response_body:
        return "transparent"
    elif "x-forwarded-for" in body_low or "via" in body_low or "forwarded" in body_low:
        return "anonymous"
    else:
        return "elite"


async def scan_proxies(proxy_dict: dict) -> list:
    """
    Scan semua proxy secara concurrent menggunakan semaphore.
    Return list of alive proxy dicts.
    """
    total     = len(proxy_dict)
    alive     = []
    checked   = 0
    semaphore = asyncio.Semaphore(CONCURRENT)

    log.info(f"[SCAN] Mulai scan {total} proxy (concurrent={CONCURRENT}, timeout={TIMEOUT}s) ...")

    # Pisahkan HTTP/HTTPS dan SOCKS
    http_proxies  = [(a, t) for a, t in proxy_dict.items() if t in ("http", "https")]
    socks_proxies = [(a, t) for a, t in proxy_dict.items() if t in ("socks4", "socks5")]

    results = []
    lock    = asyncio.Lock()

    # ── HTTP/HTTPS checker ─────────────────────────────────────────────────
    async def check_http_task(addr, ptype):
        nonlocal checked
        async with semaphore:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                res = await check_http_proxy(session, addr, ptype)
            async with lock:
                checked += 1
                results.append(res)
                if checked % 500 == 0 or checked == total:
                    alive_count = sum(1 for r in results if r.get("alive"))
                    log.info(f"  Progress: {checked}/{total} checked | {alive_count} alive")

    # ── SOCKS checker ──────────────────────────────────────────────────────
    async def check_socks_task(addr, ptype):
        nonlocal checked
        async with semaphore:
            res = await check_socks_proxy(addr, ptype)
            async with lock:
                checked += 1
                results.append(res)
                if checked % 500 == 0 or checked == total:
                    alive_count = sum(1 for r in results if r.get("alive"))
                    log.info(f"  Progress: {checked}/{total} checked | {alive_count} alive")

    tasks = []
    for addr, ptype in http_proxies:
        tasks.append(asyncio.create_task(check_http_task(addr, ptype)))
    for addr, ptype in socks_proxies:
        tasks.append(asyncio.create_task(check_socks_task(addr, ptype)))

    await asyncio.gather(*tasks)

    alive = [r for r in results if r.get("alive")]
    # Sort: socks5 dulu, lalu latency terendah
    type_order = {"socks5": 0, "socks4": 1, "https": 2, "http": 3}
    alive.sort(key=lambda x: (type_order.get(x["type"], 9), x.get("latency", 9999)))

    return alive


# ─────────────────────────────────────────────────────────────────────────────
# BAGIAN 4: OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
def save_raw(proxy_dict: dict):
    """Simpan semua proxy mentah."""
    with open(OUTPUT_RAW, "w", encoding="utf-8") as f:
        for addr, ptype in proxy_dict.items():
            f.write(f"{ptype}://{addr}\n")
    log.info(f"[SAVE] {len(proxy_dict)} proxy mentah -> {OUTPUT_RAW}")


def save_alive(alive: list):
    """Simpan proxy yang hidup ke TXT dan JSON."""
    # TXT (siap pakai, format: type://ip:port)
    with open(OUTPUT_ALIVE, "w", encoding="utf-8") as f:
        for p in alive:
            f.write(f"{p['type']}://{p['proxy']}\n")
    log.info(f"[SAVE] {len(alive)} proxy hidup -> {OUTPUT_ALIVE}")

    # JSON detail
    output = {
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
        json.dump(output, f, indent=2, ensure_ascii=False)
    log.info(f"[SAVE] Detail JSON -> {OUTPUT_JSON}")


def print_summary(proxy_dict: dict, alive: list):
    """Print tabel ringkasan."""
    total = len(proxy_dict)
    log.info("\n" + "=" * 65)
    log.info("  HASIL SCAN PROXY")
    log.info(f"  Waktu    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Scraped  : {total} proxy dari {len(PROXY_SOURCES)} sumber")
    log.info(f"  Alive    : {len(alive)} proxy")
    log.info(f"  Dead     : {total - len(alive)} proxy")
    if alive:
        log.info(f"\n  Breakdown berdasarkan tipe:")
        for ptype in ("socks5", "socks4", "https", "http"):
            count = sum(1 for p in alive if p["type"] == ptype)
            if count:
                log.info(f"    {ptype.upper():<8} : {count}")

        avg_lat  = sum(p["latency"] for p in alive) // len(alive)
        min_lat  = min(p["latency"] for p in alive)
        log.info(f"\n  Latency rata-rata : {avg_lat} ms")
        log.info(f"  Latency terbaik  : {min_lat} ms")

        anon_count = {}
        for p in alive:
            a = p.get("anon", "unknown")
            anon_count[a] = anon_count.get(a, 0) + 1
        log.info(f"\n  Anonimitas:")
        for level in ("elite", "anonymous", "transparent"):
            c = anon_count.get(level, 0)
            if c:
                log.info(f"    {level:<12} : {c}")

        log.info(f"\n  Top 10 Proxy Tercepat:")
        log.info(f"  {'TYPE':<8} {'PROXY':<25} {'LATENCY':>8}  {'ANON'}")
        log.info(f"  {'-'*8} {'-'*25} {'-'*8}  {'-'*12}")
        for p in alive[:10]:
            log.info(
                f"  {p['type'].upper():<8} {p['proxy']:<25} "
                f"{str(p['latency'])+'ms':>9}  {p.get('anon','?')}"
            )
    log.info("\n" + "=" * 65)
    log.info(f"  File output:")
    log.info(f"    {OUTPUT_RAW}    — semua proxy mentah")
    log.info(f"    {OUTPUT_ALIVE}  — proxy hidup (type://ip:port)")
    log.info(f"    {OUTPUT_JSON}   — detail JSON lengkap")
    log.info("=" * 65)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    log.info("=" * 65)
    log.info("  Hatcher Tools — Proxy Scraper + Scanner")
    log.info(f"  Sumber    : {len(PROXY_SOURCES)} sumber publik")
    log.info(f"  Concurrent: {CONCURRENT} thread async")
    log.info(f"  Timeout   : {TIMEOUT}s per proxy")
    log.info(f"  SOCKS     : {'aktif' if SOCKS_SUPPORT else 'nonaktif (install aiohttp-socks)'}")
    log.info("=" * 65)

    # STEP 1: Scrape
    t1 = time.perf_counter()
    proxy_dict = await scrape_all_sources()
    save_raw(proxy_dict)
    t_scrape = round(time.perf_counter() - t1, 1)
    log.info(f"[TIME] Scraping selesai dalam {t_scrape}s\n")

    if not proxy_dict:
        log.error("[ERR] Tidak ada proxy yang berhasil di-scrape!")
        return

    # STEP 2: Scan
    t2 = time.perf_counter()
    alive = await scan_proxies(proxy_dict)
    t_scan = round(time.perf_counter() - t2, 1)
    log.info(f"[TIME] Scanning selesai dalam {t_scan}s\n")

    # STEP 3: Simpan & Ringkasan
    save_alive(alive)
    print_summary(proxy_dict, alive)


if __name__ == "__main__":
    asyncio.run(main())
