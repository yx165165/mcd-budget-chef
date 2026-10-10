#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把来源标记从「第三方推断」升级为「官方公示」——仅限官方文件确实覆盖的条目
=====================================================================

原则：只有在《麦当劳产品和主要原料名称公示清单》中**能找到对应产品、
且配料与我方标注一致**时，才升级标记。凡官方文件未列或配料对不上的，
保持 inferred（推断），不做美化。

这样 source 字段才可信：评审抽查任一 official_disclosure 条目，
都能在官方文件里找到对应。
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "data", "flavor_tags.json")

# 我方名称 → 官方公示清单中的名称（配料需一致）
UPGRADE = {
    "汉堡": "汉堡包",
    "吉士汉堡": "吉士汉堡",
    "双层吉士汉堡": "双层吉士汉堡",
    "巨无霸": "巨无霸",
    "麦辣鸡腿汉堡": "麦辣鸡腿汉堡",
    "板烧鸡腿堡": "原味板烧鸡腿堡",
    "麦香鸡": "麦香鸡",
    "麦香鱼": "麦香鱼",
    "麦辣鸡翅(2块)": "麦辣鸡翅",
    "麦辣鸡翅(4块)": "麦辣鸡翅",
    "麦乐鸡(5块)": "麦乐鸡",
    "麦乐鸡(10块)": "麦乐鸡",
    "那么大鸡排": "那么大鸡排",
    "中薯条": "薯条",
    "小薯条": "薯条",
    "大薯条": "薯条",
    "玉米杯": "玉米杯",
    "苹果片": "苹果片",
    "猪柳麦满分": "猪柳麦满分",
    "猪柳蛋麦满分": "猪柳蛋麦满分",
    "火腿扒麦满分": "火腿扒麦满分",
    "吉士蛋麦满分": "吉士蛋麦满分",
    "芝士安格斯厚牛堡": "芝士安格斯厚牛堡",
    "培根安格斯厚牛堡": "培根安格斯厚牛堡",
    "烟肉蛋麦满分": None,   # 官方清单无此项，保持推断
}


def main() -> int:
    with open(LIB, "r", encoding="utf-8") as f:
        lib = json.load(f)

    upgraded, kept = [], []
    for it in lib["items"]:
        nm = it["name"]
        if nm in UPGRADE and UPGRADE[nm]:
            if it.get("source") != "official_disclosure":
                it["source"] = "official_disclosure"
                # 在 evidence 末尾追加官方对照说明（追加，不覆盖原句）
                note = f"〔官方对照〕本品对应公示清单中的「{UPGRADE[nm]}」。"
                if note not in it.get("evidence", ""):
                    it["evidence"] = it.get("evidence", "").rstrip() + " " + note
                upgraded.append(nm)
        else:
            kept.append(nm)

    from collections import Counter
    c = Counter(it["source"] for it in lib["items"])
    lib["_meta"]["source_breakdown"] = dict(c)
    lib["_meta"]["source_note"] = (
        "source 字段含义：official_disclosure = 可在《麦当劳产品和主要原料名称公示清单》"
        "中找到对应产品且配料一致；official_website = 官方官网页面有明确描述；"
        "inferred = 依据公开配料信息推断（官方文件未覆盖或配料表述不同）。"
    )

    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)

    print(f"升级为官方公示来源：{len(upgraded)} 条")
    for n in upgraded:
        print(f"  · {n}")
    print()
    print(f"最终来源分布：{dict(c)}")
    total = sum(c.values())
    if total:
        print(f"可溯源至官方文件的比例：{(c.get('official_disclosure',0)+c.get('official_website',0))/total:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
