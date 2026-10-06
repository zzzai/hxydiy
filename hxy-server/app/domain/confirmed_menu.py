"""User-confirmed installation template; live prices always come from PriceBook."""

from copy import deepcopy
from pydantic import ValidationError
from app.schemas.catalog import ServiceSpec


MENU_VERSION = "menu-20261001"
RETIRED_CODES = {"hxy-oil-back-30", "hxy-cupping-scraping-1"}
# Code, name, category, duration, store/group/member cents, flow.
MENU = [
    ("hxy-qiqing-30", "现煮草本泡", "bath", None, (2990, 2790, 2590),
     "体质检测＋现煮草本泡脚＋养生茶饮"),
    ("hxy-xiangxiang-60", "精选草本泡", "bath", 60, (8900, 7900, 6900),
     "养生茶饮＋现煮草本泡脚＋手臂按摩＋刮脚＋搓盐（50分钟）＋热敷（10分钟）"),
    ("hxy-xiaoqi-90", "招牌草本泡", "bath", 90, (12900, 9900, 8900),
     "养生茶饮＋现煮草本泡脚＋足部按摩＋肩颈背按摩＋腹部按摩＋腿部按摩＋刮脚＋搓盐（75分钟）＋草本热敷（15分钟）"),
    ("hxy-nvshen-60", "女神草本足护", "bath", 60, (10900, 8900, 7900),
     "养生茶饮＋现煮草本泡脚＋按摩＋祛角质＋养护＋足膜＋润足"),
    ("hxy-tuina-70", "荷小推", "balance", 70, (12900, 9900, 8900),
     "全身推拿（60分钟）＋热敷（10分钟）＋养生茶饮＋养生小吃"),
    ("hxy-spa-60", "舒压精油SPA", "care", 60, (12900, 9900, 8900),
     "清脚＋高端精油SPA（45分钟）＋头部按摩（15分钟）＋经络梳＋养生茶饮＋养生小吃"),
    ("hxy-spa-90", "安神精油SPA", "care", 90, (17900, 15900, 13900),
     "清脚＋高端精油SPA（75分钟）＋头部按摩（15分钟）＋经络梳＋养生茶饮＋养生小吃"),
    ("hxy-caier-30", "采耳", "small", 30, (8900, 6900, 5900), "耳部清洁＋耳部按摩"),
    ("hxy-head-30", "头疗", "small", 30, (7900, 5900, 4900), "头面耳按摩30分钟＋经络梳＋眼罩/眼贴"),
    ("hxy-jubu-30", "局部推拿", "local-strength", 30, (7900, 5900, 4900), "肩颈、腰臀、腿部、腹部、足部任选其一"),
    ("hxy-foot-refine-1", "足部精修", "small", None, (5900, 3900, 3900), "现煮草本泡脚＋脚部精修"),
    ("hxy-baguan-1", "拔罐", "small", None, (5900, 3900, 2900), "拔竹罐＋草本功效膏贴"),
    ("hxy-guasha-1", "刮痧", "small", None, (5900, 3900, 2900), "刮痧＋草本功效膏贴"),
    ("hxy-taoke-60", "功夫调理", "kit", 60, (98000, None, None), "活络油20分钟＋工具20分钟＋热敷20分钟；10次/套"),
]
GIFT_CODES = {"hxy-tuina-70", "hxy-spa-60", "hxy-spa-90"}


def menu_spec(row):
    code, _, _, duration, _, flow = row
    return {
        "version": MENU_VERSION,
        "flow_steps": flow.split("＋"),
        "sale_unit": "package" if code == "hxy-taoke-60" else "service",
        "services_per_unit": 10 if code == "hxy-taoke-60" else 1,
        "service_duration_min": duration,
        "included_services": [{"code": "hxy-qiqing-30", "name": "现煮草本泡", "quantity": 1}]
        if code in GIFT_CODES else [],
    }


def project_service_spec(project):
    for module in project.detail_modules or []:
        if isinstance(module, dict) and module.get("type") == "service_contract":
            try:
                return ServiceSpec.model_validate(module.get("spec")).model_dump()
            except ValidationError:
                return {}
    return {}


def contract_modules(existing, spec):
    return [deepcopy(module) for module in existing or []
            if not isinstance(module, dict) or module.get("type") != "service_contract"] + [
        {"type": "service_contract", "spec": deepcopy(spec)},
    ]


def visible_modules(modules):
    return [deepcopy(module) for module in modules or []
            if not isinstance(module, dict) or module.get("type") != "service_contract"]
