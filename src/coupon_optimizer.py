#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦口味推荐官 —— 最优优惠模块
==============================

职责
----
在「候选餐品池」里找出实付最省、同时满足营养约束的组合，并把优惠券纳入同一次搜索。

为什么券必须和组合一起搜
------------------------
很多券是整单门槛型（如「满 30 减 6」）。如果先挑最便宜的单品、再看能不能用券，
就会漏掉「多花 3 元凑到门槛、反而实付更少」这类解。所以本模块对
「组合 × 券」做**联合枚举**，按实付金额排序。

价格用「分」为单位的整数参与计算，避免浮点误差累积（官方 calculate-price
同样以分为单位返回，便于对齐复核）。
"""

from __future__ import annotations

import itertools
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES = os.path.join(os.path.dirname(HERE), "data", "prices_demo.json")


def to_cents(yuan: float) -> int:
    """元 → 分（四舍五入到整数分）。"""
    return int(round(float(yuan) * 100))


def to_yuan(cents: int) -> float:
    return cents / 100.0


@dataclass
class Coupon:
    """优惠券。kind: threshold 满减 / item 单品 / discount 折扣"""

    code: str
    name: str
    kind: str = "threshold"
    threshold: float = 0.0        # 门槛（元）
    amount: float = 0.0           # 减免额（元）
    target_name: Optional[str] = None   # 单品券适用餐品名
    rate: float = 1.0             # 折扣率
    max_off: Optional[float] = None     # 折扣封顶

    def discount_cents(self, names: Sequence[str], subtotal_cents: int,
                       price_map: Dict[str, int]) -> int:
        if self.kind == "threshold":
            if subtotal_cents >= to_cents(self.threshold):
                return min(to_cents(self.amount), subtotal_cents)
            return 0
        if self.kind == "item":
            if self.target_name:
                for nm in names:
                    if nm == self.target_name:
                        return min(to_cents(self.amount), price_map.get(nm, 0))
            return 0
        if self.kind == "discount":
            off = int(round(subtotal_cents * (1.0 - self.rate)))
            if self.max_off is not None:
                off = min(off, to_cents(self.max_off))
            return max(off, 0)
        return 0


@dataclass
class PriceResult:
    """一个组合的价格结果。"""

    names: List[str]
    subtotal: float
    discount: float
    paid: float
    coupon: Optional[Coupon]
    coupons_considered: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "items": self.names,
            "subtotal": round(self.subtotal, 2),
            "discount": round(self.discount, 2),
            "paid": round(self.paid, 2),
            "coupon": self.coupon.name if self.coupon else None,
            "coupons_considered": self.coupons_considered,
        }


class PriceTable:
    """价格表（演示用；真实运行应从 MCP query-meals 获取）。"""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.note = raw.get("_disclaimer", "")
        self._cents: Dict[str, int] = {}
        self._coupons: List[Coupon] = []
        for e in raw.get("items", []):
            nm = str(e.get("name", "")).strip()
            if nm:
                self._cents[nm] = to_cents(e.get("price", 0))
        for c in raw.get("coupons", []):
            self._coupons.append(Coupon(
                code=str(c.get("code", "")),
                name=c.get("name", "优惠券"),
                kind=c.get("kind", "threshold"),
                threshold=float(c.get("threshold") or 0),
                amount=float(c.get("amount") or 0),
                target_name=c.get("targetName"),
                rate=float(c.get("rate") or 1.0),
                max_off=c.get("maxOff"),
            ))

    @classmethod
    def load(cls, path: str = DEFAULT_PRICES) -> "PriceTable":
        if not os.path.exists(path):
            return cls({"items": [], "coupons": []})
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def coupons(self) -> List[Coupon]:
        return self._coupons

    def cents(self, name: str) -> Optional[int]:
        return self._cents.get(name)


class PriceOptimizer:
    """在候选池里找实付最省的组合。"""

    # 一个「完整一餐」的槽位：主食必选，配菜/饮品选配
    def __init__(self, table: PriceTable) -> None:
        self.table = table

    def best_coupon(self, names: Sequence[str], subtotal_cents: int) -> Tuple[Optional[Coupon], int]:
        best, best_d = None, 0
        for cp in self.table.coupons:
            d = cp.discount_cents(names, subtotal_cents, self.table._cents)
            if d > best_d:
                best, best_d = cp, d
        return best, best_d

    def optimize(self,
                 candidates: Sequence[str],
                 budget: Optional[float] = None,
                 must_include: Sequence[str] = (),
                 max_items: int = 4,
                 min_items: int = 1,
                 nutrition_filter: Optional[callable] = None,
                 top_k: int = 3) -> List[PriceResult]:
        """枚举候选池的子集（含 must_include），返回实付最省的 top_k 个。

        nutrition_filter: 可选回调 (names) -> bool，用于叠加营养约束。
        """
        pool: List[str] = []
        for nm in candidates:
            if self.table.cents(nm) is not None and nm not in pool:
                pool.append(nm)

        must = [m for m in must_include if self.table.cents(m) is not None]
        optional = [p for p in pool if p not in must]

        results: List[PriceResult] = []
        budget_cents = to_cents(budget) if budget is not None else None
        n_coupons = len(self.table.coupons)

        # 枚举 optional 的任意子集，再并上 must
        for r in range(0, max(0, max_items - len(must)) + 1):
            for combo in itertools.combinations(optional, r):
                names = list(must) + list(combo)
                if len(names) < min_items or not names:
                    continue
                subtotal = sum(self.table.cents(nm) or 0 for nm in names)
                cp, disc = self.best_coupon(names, subtotal)
                paid = max(subtotal - disc, 0)
                if budget_cents is not None and paid > budget_cents:
                    continue
                if nutrition_filter is not None and not nutrition_filter(names):
                    continue
                results.append(PriceResult(
                    names=names,
                    subtotal=to_yuan(subtotal),
                    discount=to_yuan(disc),
                    paid=to_yuan(paid),
                    coupon=cp,
                    coupons_considered=n_coupons,
                ))

        # 去重（同一组餐品名只留一份）并按实付升序
        seen = set()
        uniq: List[PriceResult] = []
        for res in sorted(results, key=lambda x: (x.paid, -x.discount)):
            key = tuple(sorted(res.names))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(res)
        return uniq[:top_k]
