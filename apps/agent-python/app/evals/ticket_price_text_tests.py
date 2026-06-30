"""Regression tests for shared ticket price text heuristics."""

from tools.ticket_price_text import (
    first_ticket_price_amount,
    first_ticket_price_mention,
    has_explicit_ticket_price_signal,
)


def test_ticket_price_text_extracts_chinese_adult_ticket():
    text = "那拉提景区 评分4.0/5 成人票95元起，儿童票48元。"

    assert has_explicit_ticket_price_signal(text)
    assert first_ticket_price_amount(text) == 95
    assert "成人票95元" in (first_ticket_price_mention(text) or "")


def test_ticket_price_text_extracts_window_sale_price():
    text = "门票售价 售票窗口购买:普通票(成人)80元/人,优惠票(学生)40元/人"

    assert has_explicit_ticket_price_signal(text)
    assert first_ticket_price_amount(text) == 80


def test_ticket_price_text_ignores_rating_review_count_and_hours():
    text = (
        "栖霞山门票预订_同程旅行: 景区评分：4.7/5分(4865条点评)"
        "开放时间05:30-21:00，售票大厅营业时间07:00-17:00，免门票入园时间05:30-07:00"
    )

    assert not has_explicit_ticket_price_signal(text)
    assert first_ticket_price_mention(text) is None
    assert first_ticket_price_amount(text) is None


def test_ticket_price_text_ignores_free_booking_quota():
    text = "2026南京金牛湖动物王国免费门票抢票流程，预约数量: 每日3750张，美团1500张。"

    assert not has_explicit_ticket_price_signal(text)


def test_ticket_price_text_ignores_login_free_prompt():
    text = "栖霞山门票预订，同程旅行，您好，请 登录 免费"

    assert not has_explicit_ticket_price_signal(text)


def test_ticket_price_text_accepts_free_admission_policy():
    text = "博物馆无需门票，免费开放，需提前预约。"

    assert has_explicit_ticket_price_signal(text)
    assert first_ticket_price_amount(text) == 0.0


def test_ticket_price_text_ignores_free_open_time_window():
    text = "栖霞山景区开放时间为7:00-17:00，景区每日7点前免费开放。"

    assert not has_explicit_ticket_price_signal(text)
    assert first_ticket_price_mention(text) is None
    assert first_ticket_price_amount(text) is None
