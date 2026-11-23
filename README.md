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

## Biriktirish oqimi
Javobgar ombordan texnikalarni skanerlab oladi (`/`), tadbir joyida har bir xodimga `/assign/` sahifasida biriktiradi (kodlarni skanerlab, F.I.Sh. kiritiladi).

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
