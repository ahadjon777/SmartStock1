# SmartStock

Ishxona texnikasini QR-kod bilan tadbirga chiqarish/qaytarish va ishlash vaqti hisobi dasturi (Django).

## Imkoniyatlar
- Telefon kamerasi bilan QR skanerlash (chiqarish va qaytarish avtomatik almashadi)
- Kim bergan, kim olgani, hudud, sana va vaqt yoziladi
- Ishlash vaqti = chiqish-qaytish vaqtining yarmi, admin panelda qo'lda o'zgartirish mumkin
- Statistika: hafta, oy, chorak, yarim yil, yil; hududlar bo'yicha o'rtacha
- Excel'dan import

## Ishga tushirish (Windows)
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
Skaner: http://127.0.0.1:8000/ , statistika: `/stats/`, admin: `/admin/`

## Excel import
Birinchi qator sarlavha, ustunlar: `kod | nomi | ombor`
```
python manage.py import_excel texnikalar.xlsx
```

## Eslatma
Kamera brauzerda faqat HTTPS (yoki localhost) orqali ishlaydi.

## Ish oqimi
Har bir xodim o'z login'i bilan o'z telefonidan kiradi (login va F.I.Sh. `/panel/staff/` da admin tomonidan yaratiladi). F.I.Sh. har doim profildan avtomatik olinadi.
1. **Chiqarish** (`/out/`): javobgar ombordagi hamma texnikani ketma-ket skanerlaydi, hudud va tadbirni tanlab, bitta "Chiqarish" bosadi.
2. **Biriktirish** (`/take/`): tadbir joyida har bir xodim o'z telefonida o'ziga tegishli 2-4 ta texnikani skanerlaydi. Texnika boshqa xodimga biriktirilgan bo'lsa, ko'chirishni so'raydi.
3. **Jarayon** (`/progress/`): javobgar "20 tadan 14 tasi biriktirildi, 6 tasi qoldi" ni ko'radi (har 15 soniyada yangilanadi).
4. **Qaytarish** (`/in/`): hamma texnika skanerlanib, bitta "Qaytarish" bosiladi; qaytmagan texnikalar kimda ekani bilan ko'rsatiladi.

## Telegram admin bot
1. @BotFather orqali bot yarating, tokenni oling. O'z ID'ingizni bilish uchun botga `/start` yozing.
2. Windows'da (PowerShell):
```
$env:TELEGRAM_BOT_TOKEN="123:ABC"
$env:TELEGRAM_ADMIN_IDS="111111111,222222222"
python manage.py run_bot
```
Buyruqlar: `/kim` (kim jami olgan va kimga biriktirilgan), `/stat [hafta|oy|chorak|yarim|yil]`.
Veb-dastur ham bir xil o'zgaruvchilar bilan ishga tushirilsa, texnika chiqarilganda va biriktirilganda adminlarga avtomatik xabar boradi.

## QR yorliqlarni chop etish
Admin sifatida kirib `/labels/` sahifasini oching: ombor yoki kod boshlanishi bo'yicha filtrlab, "Chop etish" bosiladi (bir sahifada 500 tagacha).

## Admin panel (`/panel/`)
- **Bosh sahifa:** jami texnika, hozir tadbirda, bugungi chiqish/qaytish, omborlar kesimi, so'nggi harakatlar
- **Tadbirda:** kim jami olgan, kimga biriktirilgan, hudud, qancha vaqtdan beri (qidiruv bilan)
- **Texnika:** qidirish/filtr, qo'shish, tahrirlash, Excel yuklash, QR yorliqlar
- **Omborlar** va **Xodimlar** (faqat admin): yaratish, mas'ul biriktirish, parol, faollik

Rollar: *Admin* (`is_staff`) hamma narsani ko'radi; *Ombor mas'uli* faqat o'z omborlarini ko'radi va faqat shu ombor texnikasini skanerlay oladi; oddiy *xodim* faqat skaner va biriktirishdan foydalanadi.
Yangilanishdan keyin: `git pull`, `pip install -r requirements.txt`, `python manage.py migrate`.

## Xavfsizlik monitoringi
Dastur o'ziga qilingan hujumni aniqlaydi, Telegram'ga ogohlantirish yuboradi va xabar ostidagi tugmalar bilan choralar ko'riladi.

**Nimani aniqlaydi:**
- Parol tanlash (bitta IP'dan 5 daqiqada 5+ xato) va bitta akkauntga turli IP'lardan urinishlar (10 daqiqada 8+)
- Admin akkauntiga yangi IP'dan kirish
- Skanerlash (bitta IP'dan 1 daqiqada 30+ mavjud bo'lmagan/taqiqlangan sahifa)

**Tugmalar:** 🚫 IP'ni bloklash, 🔒 akkauntni qulflash, 🛑 Lockdown (faqat superuserlar ishlay oladi), ✅ ko'rib chiqdim.
**Bot buyruqlari:** `/xavf` (so'nggi hodisalar), `/bloklar` (bloklangan IP'lar, ochish tugmasi bilan), `/lockdown on|off`.

**Xavfsizlik himoyalari:** yagona faol superuser qulflanmaydi; `SECURITY_ALLOWLIST_IPS` dagi IP'lar bloklanmaydi.
**O'zingizni bloklab qo'ysangiz:** `python manage.py unblock_ip all` yoki `python manage.py lockdown off`.
**Sinash:** `python manage.py simulate_attack` soxta hujum yaratadi (haqiqiy odamga tegmaydi).

**Sozlamalar (ixtiyoriy):** `SECURITY_ALLOWLIST_IPS`, `SECURITY_FAIL_LIMIT`, `SECURITY_USER_FAIL_LIMIT`, `SECURITY_SCAN_LIMIT`.
Proksi (nginx, cloudflared, ngrok) orqasida ishlasangiz `TRUST_X_FORWARDED_FOR=1` qo'ying, aks holda hamma so'rov bitta IP'dan ko'rinadi. Proksisiz bu o'zgaruvchini yoqmang.
