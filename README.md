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
Kamera brauzerda faqat HTTPS (yoki localhost) orqali ishlaydi. Skaner kutubxonasi (`html5-qrcode`) loyihaning o'ziga qo'shilgan, tashqi saytdan yuklanmaydi.

## Internetga chiqarishda (DEBUG=0)
`.env` da kamida shular bo'lsin: `DEBUG=0`, uzun tasodifiy `SECRET_KEY` (bo'lmasa dastur ishga tushmaydi), `ALLOWED_HOSTS=sizning-domen.uz`, `CSRF_TRUSTED_ORIGINS=https://sizning-domen.uz`.
HTTPS (cloudflared, ngrok, nginx) orqasida: `HTTPS=1` va `TRUST_X_FORWARDED_FOR=1`. Bu cookie'larni faqat HTTPS uchun yopadi.

## Ish oqimi
Har bir xodim o'z login'i bilan o'z telefonidan kiradi (login va F.I.Sh. `/panel/staff/` da admin tomonidan yaratiladi). F.I.Sh. har doim profildan avtomatik olinadi.
1. **Chiqarish** (`/out/`): javobgar ombordagi hamma texnikani ketma-ket skanerlaydi, hudud va tadbirni tanlab, bitta "Chiqarish" bosadi.
2. **Biriktirish** (`/take/`): tadbir joyida har bir xodim o'z telefonida o'ziga tegishli texnikalarni ketma-ket skanerlaydi (kamerani o'chirmasdan). Har bir kod darhol biriktiriladi, ovoz va tebranish bilan tasdiqlanadi. Texnika boshqa xodimga biriktirilgan bo'lsa, sahifaning o'zida «ko'chiraymi?» deb so'raydi. Adashib biriktirilganini «Bo'shatish» tugmasi bilan qaytarish mumkin. Internet uzilsa yoki sessiya tugasa, tushunarli xabar chiqadi.
3. **Jarayon** (`/progress/`): javobgar "20 tadan 14 tasi biriktirildi, 6 tasi qoldi" ni ko'radi (har 15 soniyada yangilanadi).
4. **Qaytarish** (`/in/`): hamma texnika skanerlanib, bitta "Qaytarish" bosiladi; qaytmagan texnikalar kimda ekani bilan ko'rsatiladi.

## Telegram admin bot
1. @BotFather orqali bot yarating, tokenni oling. O'z ID'ingizni bilish uchun botga `/start` yozing.
2. `.env` fayliga `TELEGRAM_BOT_TOKEN` va `TELEGRAM_ADMIN_IDS` ni yozing (`.env.example` ga qarang), so'ng:
```
python manage.py run_bot
```
Bot tugmali menyu bilan ishlaydi: `/start` yoki `/menu` bosing, qolganini tugmalar bajaradi (xabar o'z joyida yangilanadi, chat to'lib ketmaydi). Telegramning pastki chap burchagidagi **Menu** tugmasi ham buyruqlar ro'yxatini ochadi.

| Bo'lim | Nima qiladi |
|---|---|
| 📦 Tadbirda | Kim nima olgan, kimga biriktirilgan, qancha vaqtdan beri (sahifalab) |
| 📊 Statistika | Hudud bo'yicha o'rtacha ishlash vaqti: hafta/oy/chorak/yarim yil/yil tugmalari |
| 🔎 Qidirish | Texnika kodi, nomi yoki odam ismini yozing: karta, holati va so'nggi harakatlari chiqadi |
| 🏭 Omborlar | Har bir ombor bo'yicha tadbirda/jami |
| 🛡 Xavfsizlik | Hodisalar, lockdown (tasdiq bilan), bloklangan IP'larni ochish |

Oddiy xabar yozsangiz, bot uni qidiruv deb qabul qiladi. Eski buyruqlar ham ishlaydi: `/kim`, `/stat [hafta|oy|chorak|yarim|yil]`, `/find`, `/xavf`, `/bloklar`, `/lockdown on|off`.
Veb-dastur ham bir xil `.env` bilan ishga tushirilsa, texnika chiqarilganda, biriktirilganda va qaytarilganda adminlarga avtomatik xabar boradi (xabar sayt so'rovini sekinlashtirmaydi). `SITE_URL` berilsa, menyuda «🌐 Saytni ochish» tugmasi chiqadi.

## QR yorliqlarni chop etish
Admin sifatida kirib `/labels/` sahifasini oching: ombor yoki kod boshlanishi bo'yicha filtrlab, "Chop etish" bosiladi (bir sahifada 500 tagacha).

> **Muhim:** yorliqlar oddiy (standart) QR formatida yaratiladi. Avvalgi versiyada qisqa raqamli kodlar «Micro QR» bo'lib chiqqan, uni telefon kamerasi va brauzer skaneri o'qiy olmaydi (ayrim qo'l skanerlari o'qiydi). Eski yorliqlarni `/labels/` sahifasidan qayta chop eting.

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
