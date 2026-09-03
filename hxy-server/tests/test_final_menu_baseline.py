from app.seed import PROJECTS


def _project(code: str):
    return next(item for item in PROJECTS if item[0] == code)


def test_final_menu_contains_confirmed_projects_and_prices():
    expected = {
        "hxy-qiqing-30": ("草本泡脚", 30, 3990, 2990, 2990),
        "hxy-xiangxiang-60": ("草本沐足", 60, 8900, 7900, 6900),
        "hxy-xiaoqi-90": ("招牌草本沐足", 90, 12900, 9900, 8900),
        "hxy-tuina-70": ("荷小推", 70, 9900, 7900, 6900),
        "hxy-spa-60": ("舒享精油 SPA", 60, 11900, 9900, 8900),
        "hxy-spa-90": ("深享精油 SPA", 90, 17900, 15900, 13900),
        "hxy-taoke-60": ("功夫调理", 60, None, None, 98000),
        "hxy-caier-30": ("采耳", 30, 8900, 6900, 5900),
        "hxy-baguan-1": ("拔罐", None, 5900, 3900, 2900),
        "hxy-guasha-1": ("刮痧", None, 5900, 3900, 2900),
        "hxy-head-30": ("头疗", 30, 7900, 5900, 4900),
        "hxy-jubu-30": ("局部推拿", 30, 7900, 5900, 4900),
        "hxy-foot-refine-1": ("足部精修", None, 5900, 3900, 3900),
    }
    assert len(PROJECTS) == len(expected)
    for code, (name, duration, store, group, member) in expected.items():
        row = _project(code)
        assert row[3] == name
        assert row[4] == duration
        assert row[6:9] == (store, group, member)


def test_spa_60_uses_dedicated_project_visual():
    row = _project("hxy-spa-60")
    assert row[9] == "/assets/projects/hxy-spa-60.webp"
    assert row[9] != _project("hxy-spa-90")[9]


def test_final_menu_order_matches_spreadsheet_rows():
    assert [item[0] for item in PROJECTS] == [
        "hxy-qiqing-30",
        "hxy-xiangxiang-60",
        "hxy-xiaoqi-90",
        "hxy-tuina-70",
        "hxy-spa-60",
        "hxy-spa-90",
        "hxy-taoke-60",
        "hxy-caier-30",
        "hxy-baguan-1",
        "hxy-guasha-1",
        "hxy-head-30",
        "hxy-jubu-30",
        "hxy-foot-refine-1",
    ]


def test_counted_addons_are_marked_without_service_minutes():
    assert _project("hxy-baguan-1")[4] is None
    assert _project("hxy-guasha-1")[4] is None
    assert _project("hxy-foot-refine-1")[4] is None
