"""Образцы договоров по всем ОКЭД на тестовых данных — для вычитки.

Запуск из каталога backend:  python -m app.selfemployed.render_samples [каталог]
Файлы никуда не коммитятся — это инструмент вычитки, а не часть модуля.
"""
import sys
from datetime import date
from pathlib import Path

from app.selfemployed.builder import check, filename, render
from app.selfemployed.profiles import ORDER

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
OUT.mkdir(parents=True, exist_ok=True)

base = dict(
    number="СЗ-014", contract_date=date(2026, 10, 6), valid_to=date(2026, 12, 31),
    amount=900000, payment_days=20, payment_method="cashless",
    customer=dict(org_form="ТОО", name="Ромашка Трейд", bin="210940012346", position="Директор",
                  head_name="Сейткалиева Айгерим Маратовна", basis_gen="Устава",
                  address="г. Алматы, пр. Абая, д. 150, офис 12", iik="KZ12722S000012345678",
                  bank="АО «Kaspi Bank»", bik="CASPKZKA", phone="+7 701 000 00 00"),
    executor=dict(full_name="Нурланов Ерлан Бакытович", iin="900515300127",
                  address="г. Алматы, мкр. Аксай-4, д. 21, кв. 5", iik="KZ45601A861000123456",
                  bank="АО «Народный Банк Казахстана»", bik="HSBKKZKX", phone="+7 777 111 22 33"),
)

for code in ORDER:
    d = dict(base, oked=code)
    if code == "68201":
        d.update(amount=350000, subject="жилое помещение (квартиру), расположенное по адресу: "
                                        "г. Алматы, ул. Жандосова, д. 58, кв. 34, общей площадью 54 кв. м")
    if code == "77290":
        d.update(amount=120000, subject="имущество согласно перечню: стулья складные — 40 шт., "
                                        "столы банкетные — 5 шт., в исправном состоянии")
    (OUT / filename(d)).write_bytes(render(d))
    print(code, check(d))
