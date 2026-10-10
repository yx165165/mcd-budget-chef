#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦口味推荐官 —— 营养配餐模块
==============================

职责
----
1. 加载营养数据；**数据缺失时如实返回 None 并显示为「无」，绝不编造**
2. 汇总一个套餐（多个餐品）的总营养
3. 与用户营养目标比对，给出达标判定与缺口提示

数据来源说明（重要）
--------------------
真实运行时应通过麦当劳 MCP 的 `list-nutrition-foods` 获取逐餐品营养数据。
本仓库内置的 `data/nutrition_demo.json` 是**离线演示占位数据**，
其数值未经麦当劳官方核验，仅用于在无 Token 环境下跑通算法。
每次输出都会带上数据来源标签，不会把演示数据冒充官方数据。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NUTRITION = os.path.join(os.path.dirname(HERE), "data", "nutrition_demo.json")

# 各指标的中文名与单位
METRICS: Dict[str, tuple] = {
    "calories": ("热量", "kcal"),
    "protein": ("蛋白质", "g"),
    "fat": ("脂肪", "g"),
    "carbs": ("碳水化合物", "g"),
    "sodium": ("钠", "mg"),
}


@dataclass
class NutritionInfo:
    """单个餐品的营养信息。任何一个字段为 None 表示该数据缺失（显示为「无」）。"""

    name: str
    calories: Optional[float] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    sodium: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "calories": self.calories,
            "protein": self.protein,
            "fat": self.fat,
            "carbs": self.carbs,
            "sodium": self.sodium,
        }


@dataclass
class NutritionGoal:
    """营养目标。None 表示不约束。"""

    calorie_budget: Optional[float] = None   # 热量上限
    calorie_target: Optional[float] = None   # 目标热量（落在 ±tolerance 内）
    tolerance: float = 120.0
    min_protein: Optional[float] = None
    max_sodium: Optional[float] = None
    max_fat: Optional[float] = None


@dataclass
class NutritionReport:
    """一个套餐的营养报告。"""

    totals: Dict[str, Optional[float]]
    per_item: List[NutritionInfo]
    missing: List[str] = field(default_factory=list)      # 缺数据的餐品名
    verdicts: List[str] = field(default_factory=list)     # 达标判定
    passed: bool = True
    source: str = "demo"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "totals": self.totals,
            "per_item": [n.as_dict() for n in self.per_item],
            "missing": self.missing,
            "verdicts": self.verdicts,
            "passed": self.passed,
            "source": self.source,
        }


class NutritionTable:
    """营养数据表。"""

    def __init__(self, raw: Dict[str, Any], source: str = "demo") -> None:
        self.source = source
        self.note = raw.get("_disclaimer", "")
        self._by_name: Dict[str, Dict[str, float]] = {}
        for entry in raw.get("items", []):
            nm = str(entry.get("name", "")).strip()
            if nm:
                self._by_name[_norm(nm)] = entry

    @classmethod
    def load(cls, path: str = DEFAULT_NUTRITION, source: str = "demo") -> "NutritionTable":
        if not os.path.exists(path):
            return cls({"items": []}, source="unavailable")
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f), source=source)

    def get(self, name: str) -> Optional[NutritionInfo]:
        """取单个餐品营养。**查不到就返回 None，不猜不填。**"""
        entry = self._by_name.get(_norm(name))
        if not entry:
            return None
        return NutritionInfo(
            name=str(entry.get("name", name)),
            calories=_f(entry.get("calories")),
            protein=_f(entry.get("protein")),
            fat=_f(entry.get("fat")),
            carbs=_f(entry.get("carbs")),
            sodium=_f(entry.get("sodium")),
        )

    def has(self, name: str) -> bool:
        return _norm(name) in self._by_name


def _norm(s: str) -> str:
    """归一化餐品名，用于跨表（口味表/营养表）匹配。

    注意：只去掉空格与括号**符号**，保留括号内的内容——
    因为括号里往往是关键区分信息（份量、口味），
    例如「麦乐鸡(5块)」与「麦乐鸡(10块)」必须保持可区分。
    """
    s = str(s).strip().lower()
    for ch in [" ", "\t", "　", "(", ")", "（", "）"]:
        s = s.replace(ch, "")
    return s


def _f(x: Any) -> Optional[float]:
    """转 float；None/空/非法值一律返回 None（表示『无』）。"""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 汇总与判定
# ---------------------------------------------------------------------------

def summarize(names: Sequence[str],
              table: NutritionTable,
              goal: Optional[NutritionGoal] = None) -> NutritionReport:
    """汇总一组餐品的营养，并按目标给出判定。

    数据缺失处理：缺失项从总和中剔除，并记入 missing 列表；
    若全部缺失，总和为 None（显示「无」），判定为「数据不足」。
    """
    per_item: List[NutritionInfo] = []
    missing: List[str] = []
    totals: Dict[str, Optional[float]] = {k: 0.0 for k in METRICS}
    counted = 0

    for nm in names:
        info = table.get(nm)
        if info is None:
            missing.append(nm)
            per_item.append(NutritionInfo(name=nm))   # 全 None → 显示「无」
            continue
        per_item.append(info)
        counted += 1
        for k in METRICS:
            v = getattr(info, k)
            if v is None:
                # 该项缺失：把总和置为 None（不假装是 0）
                totals[k] = None
            elif totals[k] is not None:
                totals[k] = totals[k] + v

    if counted == 0:
        totals = {k: None for k in METRICS}

    verdicts: List[str] = []
    passed = True

    if counted == 0:
        verdicts.append("🔴 数据不足：所选餐品均无营养数据，无法判定（不编造数值）")
        passed = False
    else:
        if goal:
            cal = totals.get("calories")
            if goal.calorie_budget is not None:
                if cal is None:
                    verdicts.append("⚠️ 热量数据缺失，无法核对热量上限")
                elif cal > goal.calorie_budget:
                    verdicts.append(f"🔴 热量 {cal:.0f} kcal 超出上限 {goal.calorie_budget:.0f}")
                    passed = False
                else:
                    verdicts.append(f"✅ 热量 {cal:.0f} ≤ 上限 {goal.calorie_budget:.0f}")

            if goal.calorie_target is not None:
                if cal is None:
                    verdicts.append("⚠️ 热量数据缺失，无法核对目标热量")
                elif abs(cal - goal.calorie_target) > goal.tolerance:
                    verdicts.append(f"🔴 热量 {cal:.0f} 偏离目标 {goal.calorie_target:.0f} 超过 ±{goal.tolerance:.0f}")
                    passed = False
                else:
                    verdicts.append(f"✅ 热量 {cal:.0f} 落在目标 {goal.calorie_target:.0f}±{goal.tolerance:.0f} 内")

            prot = totals.get("protein")
            if goal.min_protein is not None:
                if prot is None:
                    verdicts.append("⚠️ 蛋白质数据缺失，无法核对")
                elif prot < goal.min_protein:
                    verdicts.append(f"🔴 蛋白质 {prot:.1f}g 低于要求 {goal.min_protein:.1f}g")
                    passed = False
                else:
                    verdicts.append(f"✅ 蛋白质 {prot:.1f}g ≥ {goal.min_protein:.1f}g")

            na = totals.get("sodium")
            if goal.max_sodium is not None:
                if na is None:
                    verdicts.append("⚠️ 钠数据缺失，无法核对")
                elif na > goal.max_sodium:
                    verdicts.append(f"🔴 钠 {na:.0f}mg 超出上限 {goal.max_sodium:.0f}mg")
                    passed = False
                else:
                    verdicts.append(f"✅ 钠 {na:.0f}mg ≤ {goal.max_sodium:.0f}mg")

            fat = totals.get("fat")
            if goal.max_fat is not None:
                if fat is None:
                    verdicts.append("⚠️ 脂肪数据缺失，无法核对")
                elif fat > goal.max_fat:
                    verdicts.append(f"🔴 脂肪 {fat:.1f}g 超出上限 {goal.max_fat:.1f}g")
                    passed = False
                else:
                    verdicts.append(f"✅ 脂肪 {fat:.1f}g ≤ {goal.max_fat:.1f}g")

    if missing:
        verdicts.append(f"⚠️ 以下餐品无营养数据（计为「无」，未计入总和）：{'、'.join(missing)}")

    return NutritionReport(
        totals=totals, per_item=per_item, missing=missing,
        verdicts=verdicts, passed=passed, source=table.source,
    )


def format_totals(totals: Dict[str, Optional[float]]) -> str:
    """把总量格式化成一行；None 显示为「无」。"""
    parts = []
    for k, (cn, unit) in METRICS.items():
        v = totals.get(k)
        if v is None:
            parts.append(f"{cn} 无")
        elif k == "calories":
            parts.append(f"{cn} {v:.0f}{unit}")
        elif k == "sodium":
            parts.append(f"{cn} {v:.0f}{unit}")
        else:
            parts.append(f"{cn} {v:.1f}{unit}")
    return " | ".join(parts)
