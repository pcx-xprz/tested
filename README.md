# Hatcher.host Automation Scripts

Referral code: `28deea96`

---

## 📁 Struktur File

```
.
├── accounts.txt              ← INPUT: daftar akun (email|username|password)
├── auto_register.py          ← Script 1: auto registrasi
├── check_coins.py            ← Script 2: cek coin balance & status
├── registered_accounts.json  ← OUTPUT: hasil register (auto-dibuat)
├── coins_report.json         ← OUTPUT: laporan coins (auto-dibuat)
├── register.log              ← Log register
├── checker.log               ← Log checker
└── requirements.txt
```

---

## ⚙️ Setup

```bash
pip install -r requirements.txt
```

---

## 📝 Isi accounts.txt

```
# Format: email|username|password
email1@gmail.com|username1|P@ssw0rd1!
email2@gmail.com|username2|P@ssw0rd2!
```

---

## 🚀 Alur Penggunaan

### STEP 1 — Auto Register
```bash
python auto_register.py
```
- Memvalidasi referral code `28deea96`
- Cek ketersediaan email & username via API
- Register semua akun dari `accounts.txt`
- Hasil disimpan ke `registered_accounts.json`

### STEP 2 — Verifikasi Email (MANUAL)
- Buka inbox masing-masing email
- Klik link konfirmasi dari Hatcher
- Harus dilakukan per akun sebelum bisa login

### STEP 3 — Buat 1 Agent (MANUAL atau via Dashboard)
- Login ke https://hatcher.host
- Buat minimal 1 agent (Chat-to-Hatch)
- Ini yang men-trigger **500 coin referral reward** ke akun referrer

### STEP 4 — Cek Coin Balance
```bash
python check_coins.py
```
- Login semua akun
- Cek balance coin / kredit
- Cek referral stats
- Cek jumlah agent
- Output ke `coins_report.json`

---

## 📊 API Endpoints yang Digunakan

| Method | Endpoint | Fungsi |
|--------|----------|--------|
| GET | `/auth/session` | Cek session aktif |
| GET | `/referrals/validate/{code}` | Validasi referral code |
| GET | `/auth/check-availability?email=` | Cek ketersediaan email |
| GET | `/auth/check-availability?username=` | Cek ketersediaan username |
| POST | `/auth/register` | Registrasi akun baru |
| POST | `/auth/login` | Login & dapat JWT token |
| GET | `/auth/me` | Data profil + balance |
| GET | `/referrals/stats` | Statistik referral |
| GET | `/agents` | List agent milik akun |

---

## ⚠️ Catatan Penting

- **500 coin** masuk ke akun referrer **HANYA** setelah referral membuat 1 agent
- Email verifikasi **wajib** dilakukan secara manual
- Gunakan delay antar request untuk menghindari rate-limiting
- Jangan share file `registered_accounts.json` (berisi password)
