"""username → 角色 對照表（唯一事實來源）。

username 取自 memory（2026-06-01 已用 GitHub API 驗證真實存在）；
Task 10 動工前會再驗一次。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    code: str  # "R1".."R7"
    name: str  # 中文姓名


# 鍵一律小寫；插入順序即 R1..R7。
_BY_USERNAME: dict[str, Role] = {
    "hbb97tw-netizen": Role("R1", "郝家銘"),
    "wayneshc": Role("R2", "施惠棋"),
    "officehsieh-afk": Role("R3", "謝劼恩"),
    "holajennytw": Role("R4", "吳瑾瑜"),
    "arronyang0416": Role("R5", "楊宗勲"),
    "aa851115tw-tech": Role("R6", "黃俊維"),
    "angelali2026888-blip": Role("R7", "李靜雲"),
}

ROLES: list[Role] = list(_BY_USERNAME.values())  # 已依 R1..R7 排序


def role_for(username: str) -> Role | None:
    return _BY_USERNAME.get(username.lower())
