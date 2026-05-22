# Hatcher.host Automation Scripts

Referral code: `28deea96`

---

## 📁 Struktur File

```
.
├── email.txt                 ← INPUT: daftar email (satu per baris)
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

## 📝 Isi email.txt

```
# Satu email per baris
hariyantipohang7128@gmail.com
budisantoso99@gmail.com
sitinurhaliza2024@yahoo.com
```

> **Username** di-generate otomatis dari nama email (angka di belakang dibuang):
> `hariyantipohang7128@gmail.com` → username: `hariyantipohang`
>
> **Password** di-generate acak (huruf besar+kecil+angka+simbol).
> Semua data disimpan ke `registered_accounts.json`.

---

## 🚀 Alur Penggunaan

### STEP 1 — Auto Register
```bash
python auto_register.py
```
- Baca email dari `email.txt`
- Generate username otomatis dari nama email
- Generate password acak yang kuat
- Validasi referral code `28deea96`
- Cek ketersediaan email & username via API
- Jika username sudah dipakai → otomatis cari alternatif
- Register semua akun
- Hasil (email + username + password) disimpan ke `registered_accounts.json`

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
