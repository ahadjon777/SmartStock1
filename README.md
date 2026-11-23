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
