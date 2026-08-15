"""种子数据：从业务定稿（2026-08-01）导入开发环境测试数据。

仅 local/test 环境使用；生产数据必须通过管理后台配置发布。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Addon, CouponTemplate, MemberPlan, PriceBook, Product, Project, Store, UserCoupon, User,
)

STORE = {
    "store_code": "hxy-anyang-ziwei-001",
    "name": "荷小悦草本泡脚（紫薇壹号店）",
    "city": "河南安阳",
    "address": "河南省安阳市文峰区紫薇壹号B区西门南60米",
    "phone": "",
    "business_hours": "10:00-23:00",
    "location_lat": 36.101277,
    "location_lng": 114.410409,
    "status": "preparing",
}

# code, category, mark, name, duration, summary, store/group/member 价格（分）, image, label
# 试用基线来自《荷小悦项目单-无系列.xlsx》2026-08-09 版本；名称仍可通过后台继续核定。
PROJECTS = [
    ("hxy-qiqing-30", "bath", "泡", "草本泡脚", 30,
     "体质辩证+五行茶饮+现熬草本汤泡脚+艾灸贴/修脚（二选一）+搓盐",
     3990, 2990, 2990, "/assets/services/service-foot-bath.jpg", "草本现煮"),
    ("hxy-xiangxiang-60", "bath", "泡", "草本沐足", 60,
     "现熬草本汤泡脚+局部放松（20分钟）+修脚/搓盐（二选一）+足底按摩（30分钟）",
     8900, 7900, 6900, "/assets/services/service-foot-bath.jpg", "基础款"),
    ("hxy-xiaoqi-90", "bath", "泡", "招牌草本沐足", 90,
     "草本泡脚+肩颈放松+足底按摩+走竹罐+腰肾/肠胃调理（二选一）+腿部按摩+草本热敷",
     12900, 9900, 8900, "/assets/services/service-foot-bath.jpg", "招牌"),
    ("hxy-tuina-70", "balance", "调", "荷小推", 70,
     "五行茶饮+对证推拿+热敷包+草本功效膏贴+养生小吃",
     13900, 11900, 9900, "/assets/services/service-tuina.jpg", "主力款"),
    ("hxy-spa-90", "care", "SPA", "精油SPA", 90,
     "五行茶饮+高端精油SPA+养生小吃",
     19900, 16900, 13900, "/assets/spa-scene.jpg", "主力款"),
    ("hxy-taoke-60", "kit", "盒", "功夫调理", 60,
     "痛症调理：活络油20分钟+工具20分钟+热敷20分钟，10次每套",
     128000, None, 98000, "/assets/products/family-relax-card.png", "利润款"),
    ("hxy-caier-30", "small", "小", "采耳", 30,
     "耳部清洁+耳部按摩", 7900, 6900, 5900, "/assets/products/daily-care-pack.png", "小项"),
    ("hxy-baguan-1", "small", "小", "拔罐", None,
     "拔竹罐+草本功效膏贴", 5900, 4900, 3900, "/assets/ip-paopao-running-bucket.png", "小项"),
    ("hxy-guasha-1", "small", "小", "刮痧", None,
     "刮痧+草本功效膏贴", 5900, 4900, 3900, "/assets/products/home-relax-gift.png", "小项"),
    ("hxy-head-30", "small", "小", "头疗", 30,
     "头部按摩+眼罩/眼贴", 6900, 5900, 4900, "/assets/products/daily-care-pack.png", "小项"),
    ("hxy-jubu-30", "local-strength", "加", "局部调理", 30,
     "肩颈、腰臀、腿部、腹部、足部（任选其一）+精油/活络油（二选一）", 6900, 5900, 4900,
     "/assets/products/herbal-heat-pack.png", "加强项"),
]

ADDONS = [
    ("hxy-addon-hotpack", "草本热敷", 15, 1900),
    ("hxy-addon-extra", "加按", 15, 2900),
    ("hxy-addon-head", "头部放松", 15, 2900),
    ("hxy-addon-tool", "工具放松", 20, 3900),
    ("hxy-addon-moxa", "艾灸温热体验", 20, 3900),
]

PLANS = [
    ("annual", "年度权益卡", 9900,
     ["消费享受会员价", "会员日每周二 6.8 折", "赠送门店价值 89 元项目一次"]),
    ("stored", "储值会员", 50000, ["可退（须到店线下办理）"]),
    ("monthly", "泡脚月卡", 49900, ["30 天内不限次泡脚，仅限本人"]),
]

NEW_USER_COUPON = {
    "code": "new-user-2999",
    "name": "新客泡脚券",
    "coupon_type": "fixed",
    "amount_cents": 2999,
    "min_spend_cents": 2990,
    "validity_days": 30,
    "auto_grant_new_user": True,
}

# 营销券模板（领券中心/分享有礼）
MARKETING_COUPONS = [
    # 每日放松券：每天可领 1 张（培养到店习惯）
    {
        "code": "daily-relax-500",
        "name": "每日放松券",
        "coupon_type": "fixed",
        "amount_cents": 500,
        "min_spend_cents": 4900,
        "validity_days": 1,
        "auto_grant_new_user": False,
        "is_claimable": True,
        "claim_limit": 1,
        "daily_claimable": True,
    },
    # 分享有礼券：分享小程序得券（24h 限 1 次，服务端发放）
    {
        "code": "share-gift-300",
        "name": "分享有礼券",
        "coupon_type": "fixed",
        "amount_cents": 300,
        "min_spend_cents": 0,
        "validity_days": 7,
        "auto_grant_new_user": False,
        "is_claimable": False,
        "claim_limit": 1,
        "daily_claimable": False,
    },
    # 全场满减活动：满 99 减 9（结算自动立减，无需领券）
    {
        "code": "auto-99-9",
        "name": "满减活动（满99减9）",
        "coupon_type": "fixed",
        "amount_cents": 900,
        "min_spend_cents": 9900,
        "validity_days": 30,
        "auto_grant_new_user": False,
        "is_claimable": False,
        "claim_limit": 0,
        "daily_claimable": False,
        "auto_apply": True,
    },
    # 老带新券：邀请人被邀首单后邀请人得券
    {
        "code": "invite-reward-500",
        "name": "老带新券",
        "coupon_type": "fixed",
        "amount_cents": 500,
        "min_spend_cents": 4900,
        "validity_days": 30,
        "auto_grant_new_user": False,
        "is_claimable": False,
        "claim_limit": 0,
        "daily_claimable": False,
    },
]

# 商城商品（价格 9.9 暂定，待门店复核）
PRODUCTS = [
    ("hxy-p-foot-ai", "艾草草本泡脚包", "门店同源草本香，适合日常泡一泡。", "10 包 / 袋", "foot", 990,
     "/assets/products/herbal-foot-bath-bag.png"),
    ("hxy-p-foot-chenpi", "桂艾陈皮泡脚包", "香气更有记忆点，家庭装 10 包。", "10 包 / 袋", "foot", 990,
     "/assets/products/chenpi-foot-bath-pouch.png"),
    ("hxy-p-heat-ai", "艾草热敷袋", "肩颈、腰背日常热敷放松。", "1 只 / 袋", "heat", 990,
     "/assets/products/herbal-heat-pack.png"),
    ("hxy-p-heat-film", "一次性泡脚桶膜", "家用干净方便，20 片装。", "20 片 / 包", "heat", 990,
     "/assets/products/daily-care-pack.png"),
    ("hxy-p-gift-home", "家门口放松礼盒", "泡脚包、热敷袋、到店券组合。", "组合礼袋", "gift", 990,
     "/assets/products/home-relax-gift.png"),
    ("hxy-p-gift-family", "爸妈常来礼卡", "到店项目券 + 草本包，适合送家人。", "礼卡 1 张", "gift", 990,
     "/assets/products/family-relax-card.png"),
]


def seed(db: Session) -> None:
    if db.scalar(select(Store).limit(1)):
        return  # 已初始化

    store = Store(**STORE)
    db.add(store)
    db.flush()

    for code, cat, mark, name, dur, summary, store_p, group_p, member_p, img, label in PROJECTS:
        proj = Project(
            store_id=store.id, code=code, category=cat, category_mark=mark, name=name,
            duration_min=dur, summary=summary, image_url=img, price_label=label,
            tags=[label], publication_status="published",
            content_version="final-20260801",
        )
        db.add(proj)
        db.flush()
        if store_p is not None:
            db.add(PriceBook(project_id=proj.id, price_type="store", amount_cents=store_p))
        if group_p is not None:
            db.add(PriceBook(project_id=proj.id, price_type="group", amount_cents=group_p))
        db.add(PriceBook(project_id=proj.id, price_type="member", amount_cents=member_p))

    for code, name, dur, price in ADDONS:
        db.add(Addon(store_id=store.id, code=code, name=name, duration_min=dur,
                     price_cents=price, publication_status="published"))

    for code, name, price, benefits in PLANS:
        db.add(MemberPlan(code=code, name=name, price_cents=price, benefits=benefits,
                          status="published"))

    tpl = CouponTemplate(**NEW_USER_COUPON, status="published")
    db.add(tpl)

    for m in MARKETING_COUPONS:
        db.add(CouponTemplate(**m, status="published"))

    for code, name, desc, spec, ptype, price, img in PRODUCTS:
        db.add(Product(
            store_id=store.id, code=code, name=name, desc=desc, spec=spec,
            product_type=ptype, price_cents=price, image_url=img,
            publication_status="published",
        ))
    db.commit()
