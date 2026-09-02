from app.seed import PLANS


def test_membership_seed_matches_approved_offline_benefits() -> None:
    plans = {code: (name, price_cents, benefits) for code, name, price_cents, benefits in PLANS}

    assert set(plans) == {"annual", "monthly"}
    annual_name, annual_price, annual_benefits = plans["annual"]
    assert annual_name == "年度权益卡"
    assert annual_price == 9900
    assert any("会员日" in benefit and "门店价 6.8 折" in benefit and "不与其他优惠叠加" in benefit for benefit in annual_benefits)
    assert any("门店价 99 元以下项目" in benefit and "仅赠送一次" in benefit and "不与其他优惠叠加" in benefit for benefit in annual_benefits)
