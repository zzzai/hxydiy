"""Immutable versions of the daily store inspection checklist."""

BASE_AREAS = {
    "restroom": "卫生间",
    "water_room": "打水房",
    "cashier": "收银台",
    "rest_area": "休息区",
    "foot_area": "足疗区",
}
STANDARD_AREAS = {**BASE_AREAS, "herbal_prep": "煮药区"}
HUAFU_SPA_ROOMS = {
    "spa_banxia": "半夏",
    "spa_rendong": "忍冬",
    "spa_duruo": "杜若",
    "spa_qingdai": "青黛",
}
CHECKLISTS = {
    1: BASE_AREAS,
    2: STANDARD_AREAS,
    3: {**STANDARD_AREAS, "warehouse": "仓库", "shower_room": "淋浴间", **HUAFU_SPA_ROOMS},
}


def new_checklist_version(store_code: str) -> int:
    return 3 if store_code == "hxy-anyang-huafu-002" else 2
