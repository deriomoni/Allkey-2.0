"""Ситуации из консультаций uchet.kz и «Параграфа» — заготовка под прогон.

Как добавлять. Одна строка на ситуацию, ожидания необязательны:

    ("ИД", "о чём консультация и откуда",
     case(country="TR", income="services", amount=50000),
     {"kpn.rate": 0.20}),

Помощник `case()` заполняет всё обязательное; переопределяются только те
ответы, которые в консультации названы. Короткие имена: country, income,
amount, rate, act, paid, currency. Остальные ключи как в анкете, точка
пишется подчёркиванием: S3_4, S5_5, S7_2.

Пути в ожиданиях — как в вердикте: `kpn.rate`, `kpn.amount_kzt`, `graphs.F`,
`date_rule.rule_id`, `vat.applicable`, `confidence`. Флаг — `flag:F-PE-RISK`.

Ниже шесть ситуаций из тех областей, которых нет в наших двадцати кейсах.
Ожидания намеренно НЕ проставлены: их ставит владелец по тексту консультации,
иначе мы сверяем помогайку с собственным представлением о правильном ответе.
"""

CASES = [
    ("ПУ-1", "Стройплощадка нерезидента, срок работ 8 месяцев",
     case(country="TR", income="services", S5_5="engineering",
          S3_1="yes", S3_2="head_office", S3_3="no", S3_4="construction",
          S6_1="kz", amount=50000.0, currency="USD", rate=500.0)),

    ("РОЯ-1", "Лицензия на ПО с неразделённой техподдержкой",
     case(country="RU", income="royalty", S5_6="yes", S5_7="no",
          amount=20000.0, currency="USD", rate=500.0)),

    ("БАРТ-1", "Расчёт встречной поставкой товаров резидента",
     case(country="UZ", income="services", S5_5="marketing",
          S2_1="counter_supply", amount=15000.0, currency="USD", rate=500.0)),

    ("НАЧ-1", "Доход начислен и отнесён на вычеты, оплаты не было",
     case(country="DE", income="services", S5_5="consulting",
          paid=None, S4_6={"deducted": True, "year": 2026},
          amount=30000.0, currency="EUR", rate=590.0)),

    ("ЕАЭС-1", "Услуги из Кыргызстана, место реализации по протоколу ЕАЭС",
     case(country="KG", income="services", S5_5="consulting", S6_1="outside",
          amount=8000.0, currency="USD", rate=500.0)),

    ("СТРАХ-1", "Страховая премия по договору перестрахования",
     case(country="GB", income="insurance", S5_10="reinsurance",
          amount=25000.0, currency="USD", rate=500.0)),
]
