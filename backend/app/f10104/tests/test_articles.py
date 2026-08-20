"""Резолвер текстов статей Налогового кодекса.

Статья хранится и отдаётся целиком: резать норму по подпунктам скриптом —
верный способ получить обрезанную на полфразы цитату в документе, который
пойдёт в налоговый регистр. Нужный пункт подсвечивает интерфейс.
"""
from app.f10104.rules import get_articles, resolve_article


def test_reference_with_point_resolves_to_whole_article():
    a = resolve_article("ст. 682 п. 1 пп. 5)")

    assert a["found"] is True
    assert a["kind"] == "nk"
    assert a["number"] == 682
    assert "Ставки подоходного налога" in a["title"]
    assert len(a["text"]) > 500          # текст целиком, а не обрезок


def test_convention_reference_never_goes_to_the_tax_code():
    """«Ст. 10 конвенции» и «ст. 10 НК» — разные нормы. Подменить одну другой
    значит показать бухгалтеру не тот текст под видом обоснования."""
    a = resolve_article("ст. 706 + ст. 10/11/12 конвенции")

    assert a["found"] is False
    assert a["kind"] == "treaty"
    assert "международн" in a["message"]


def test_other_code_reference_is_not_reported_as_missing():
    """Ст. 243 — Социальный кодекс, ст. 647 — утративший силу НК-2017.
    Ответ «текст не загружен» был бы неверным: их тут и не должно быть."""
    for ref in ("ст. 243 Социального кодекса", "ст. 647 НК-2017"):
        a = resolve_article(ref)
        assert a["kind"] == "other_code", ref
        assert a["found"] is False


def test_missing_article_is_honest_not_silent():
    a = resolve_article("ст. 999")

    assert a["found"] is False
    assert a["kind"] == "missing"
    assert "не загружен" in a["message"]


def test_unparsable_reference_does_not_crash():
    assert resolve_article("белиберда")["kind"] == "unparsed"
    assert resolve_article("")["found"] is False


def test_every_article_cited_by_the_engine_has_a_text():
    """Все нормы действующего кодекса, на которые ссылается движок, должны
    разрешаться в текст. Если тест покраснел — в справочник добавили ссылку
    на статью, текста которой нет."""
    import glob
    import io
    import re

    cited = set()
    for path in glob.glob("app/f10104/*.py"):
        source = io.open(path, encoding="utf-8").read()
        cited.update(int(m) for m in re.findall(r"ст\.\s*(\d+)", source))

    # Статьи конвенций и других кодексов сюда не относятся.
    cited -= {7, 10, 11, 12, 243, 647}
    have = {a["number"] for a in get_articles()["articles"].values()}

    assert not (cited - have), f"нет текстов: {sorted(cited - have)}"
