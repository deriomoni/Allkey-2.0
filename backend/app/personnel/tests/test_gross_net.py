"""Пересчёт оклада на руки ↔ к начислению (ставки 2026)."""
from app.personnel.gross_net import net_from_gross, gross_from_net, convert_salary
from app.personnel.rates import get_rates

R = get_rates()  # 2026: mrp=4325, mzp=85000, opv 10%, vosms 2%, ipn 10%, base 30 МРП


def test_net_from_gross_with_base_deduction():
    b = net_from_gross(500_000, apply_base_deduction=True, rates=R)
    assert b.opv == 50_000
    assert b.vosms == 10_000
    assert b.base_deduction == 30 * 4325       # 129 750
    assert b.taxable == 500_000 - 50_000 - 10_000 - 129_750  # 310 250
    assert b.ipn == 31_025
    assert b.net == 500_000 - 50_000 - 10_000 - 31_025       # 408 975


def test_net_from_gross_without_base_deduction():
    b = net_from_gross(500_000, apply_base_deduction=False, rates=R)
    assert b.base_deduction == 0
    assert b.taxable == 440_000
    assert b.ipn == 44_000
    assert b.net == 396_000


def test_gross_from_net_inverts():
    for gross in (250_000, 347_850, 500_000, 1_234_567):
        for apply in (True, False):
            net = net_from_gross(gross, apply, R).net
            back = gross_from_net(net, apply, R)
            # округление удержаний может дать сдвиг в считанные тенге, но не больше
            assert abs(back.gross - gross) <= 2, (gross, apply, back.gross)
            assert back.net == net


def test_low_salary_taxable_floored_at_zero():
    b = net_from_gross(100_000, apply_base_deduction=True, rates=R)
    assert b.taxable == 0          # вычет больше базы
    assert b.ipn == 0
    assert b.net == 88_000         # только ОПВ+ВОСМС
    assert gross_from_net(88_000, True, R).gross == 100_000


def test_convert_salary_modes():
    g = convert_salary(500_000, "gross", True)
    assert g.net == 408_975
    n = convert_salary(408_975, "net", True)
    assert n.gross == 500_000
