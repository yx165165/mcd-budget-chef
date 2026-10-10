#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦口味推荐官 —— 口味画像与相似度推荐引擎
==========================================

职责
----
1. 加载口味标签库（data/flavor_tags.json）
2. 把「用户输入」或「历史订单」转成口味画像 TasteProfile
3. 在口味向量空间里做加权相似度检索，返回 Top-K 推荐

为什么用「口味向量 + 加权相似度」而不是关键词匹配
------------------------------------------------
关键词匹配只能处理「我说了辣就推辣的」，无法处理：
  - 「我平时爱点巨无霸和麦辣鸡翅」→ 需要从多个历史样本**归纳**出偏好方向
  - 「想吃点甜的但别太腻」→ 需要在甜度上找**中间值**而不是极值
  - 「上次那个挺好吃」→ 需要判断哪些菜品在口味空间里**离它近**
口味向量把每种餐品映射到 6 维空间（甜/咸/辣/酸/苦/鲜），
用户偏好也是一个点（或带权重的方向），推荐就变成「找最近的邻居」——
这样上述三种场景都能用同一套机制处理。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DIMENSIONS: List[str] = ["sweet", "salty", "spicy", "sour", "bitter", "umami"]
DIM_CN: Dict[str, str] = {
    "sweet": "甜", "salty": "咸", "spicy": "辣",
    "sour": "酸", "bitter": "苦", "umami": "鲜",
}
MAX_SCORE: float = 5.0

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIB = os.path.join(os.path.dirname(HERE), "data", "flavor_tags.json")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class TasteProfile:
    """用户口味画像。

    target:  目标口味向量，每维 0-5，表示「想吃多甜/多辣」的期望值
    weights: 各维度权重，0 表示不在乎该维度，数值越大越在乎
    texture_pref:  偏好的口感列表（命中则加分）
    temp_pref:     偏好温度 hot/cold/room，None 表示不限
    exclude_keywords: 排除关键词（如「不要辣」写入 ["辣"]）
    """

    target: Dict[str, float] = field(default_factory=lambda: {d: 0.0 for d in DIMENSIONS})
    weights: Dict[str, float] = field(default_factory=lambda: {d: 1.0 for d in DIMENSIONS})
    texture_pref: List[str] = field(default_factory=list)
    temp_pref: Optional[str] = None
    exclude_keywords: List[str] = field(default_factory=list)
    source: str = "manual"          # manual / history / text
    note: str = ""

    def describe(self) -> str:
        """把画像翻译成一句人话。

        按 source 决定"哪些维度值得描述"：
          - text:   只看用户显式提到的维度（权重已被调高），避免把"没提到的"误报成偏好
          - history: 看全部维度，按归纳出的口味重心判断
          - anchor: 由调用方给出基准说明
        """
        if self.source == "anchor":
            return self.note or "以指定餐品为口味基准"

        if self.source == "text":
            consider = [d for d in DIMENSIONS if self.weights.get(d, 0) >= 1.5]
        else:  # history / manual
            consider = list(DIMENSIONS)

        parts: List[str] = []
        for d in consider:
            t = self.target.get(d, 0.0)
            if t >= 3.5:
                parts.append(f"偏{DIM_CN[d]}")
            elif t <= 1.5 and d in [x for x in consider if self.weights.get(x, 0) >= 1.5]:
                parts.append(f"要少{DIM_CN[d]}")
        if self.texture_pref:
            parts.append("爱" + "、".join(self.texture_pref))
        if self.temp_pref:
            parts.append({"hot": "要热的", "cold": "要冰的", "room": "常温"}[self.temp_pref])
        if self.exclude_keywords:
            parts.append("排除" + "、".join(self.exclude_keywords))
        return "、".join(parts) if parts else "无明显偏好（按均衡推荐）"


@dataclass
class Recommendation:
    """一条推荐结果。"""

    item: Dict[str, Any]
    similarity: float
    reasons: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.item.get("name", ""))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.item.get("category"),
            "similarity": round(self.similarity, 4),
            "flavor": self.item.get("flavor", {}),
            "texture": self.item.get("texture", []),
            "temp": self.item.get("temp"),
            "reasons": self.reasons,
            "evidence": self.item.get("evidence", ""),
        }


# ---------------------------------------------------------------------------
# 库加载与检索
# ---------------------------------------------------------------------------

class FlavorLibrary:
    """口味标签库的封装。"""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.meta: Dict[str, Any] = raw.get("_meta", {})
        self.items: List[Dict[str, Any]] = raw.get("items", [])
        self._index: Dict[str, Dict[str, Any]] = {}
        for it in self.items:
            for key in [it.get("name", "")] + list(it.get("aliases") or []):
                if key:
                    self._index[_norm(key)] = it

    @classmethod
    def load(cls, path: str = DEFAULT_LIB) -> "FlavorLibrary":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def __len__(self) -> int:
        return len(self.items)

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        """按名称或别名精确查找。"""
        return self._index.get(_norm(name))

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """按关键词模糊查找（子串命中）。"""
        k = _norm(keyword)
        out = []
        for it in self.items:
            hay = _norm(it.get("name", "")) + "".join(_norm(a) for a in (it.get("aliases") or []))
            if k and k in hay:
                out.append(it)
        return out

    def by_category(self, category: str) -> List[Dict[str, Any]]:
        return [it for it in self.items if it.get("category") == category]


def _norm(s: str) -> str:
    """归一化：去掉空格与括号符号，但**保留括号内内容**。

    括号里常是关键区分信息（份量/口味），如「麦乐鸡(5块)」与
    「麦乐鸡(10块)」必须能区分，故不能把括号连同内容一起删掉。
    """
    s = str(s).strip().lower()
    for ch in [" ", "\t", "　", "(", ")", "（", "）"]:
        s = s.replace(ch, "")
    return s


# ---------------------------------------------------------------------------
# 画像构建
# ---------------------------------------------------------------------------

# 文本 → 口味维度的关键词表。值表示该关键词把对应维度推到多高。
# 注意：这里只放「口味词」，不放「食材词」——
# 食材（牛/猪/鱼）的排除逻辑单独在 MEAT_TERMS 里处理，
# 否则「不要牛肉」会被误解成「要少鲜味」。
FLAVOR_KEYWORDS: Dict[str, Dict[str, float]] = {
    "sweet": {"甜": 5, "嗜甜": 5, "甜品": 4, "甜的": 5, "sweet": 5, "甜口": 5},
    "salty": {"咸": 5, "重口": 5, "咸香": 4, "咸的": 5, "salty": 4},
    "spicy": {"辣": 5, "香辣": 4, "麻辣": 5, "辣的": 5, "spicy": 4, "重辣": 5},
    "sour":  {"酸": 5, "酸的": 5, "开胃": 3, "sour": 4},
    "bitter": {"苦": 5, "bitter": 4},
    "umami": {"鲜": 4, "肉香": 4, "umami": 4},
}

# 食材类别 → 用于匹配的餐品名关键词。支持「不要牛肉」这类忌口。
MEAT_TERMS: Dict[str, tuple] = {
    "牛肉": ("牛", "安格斯"),
    "猪肉": ("猪柳", "培根", "烟肉", "火腿"),
    "鱼": ("鱼",),
    "咖啡": ("咖啡", "拿铁", "卡布", "摩卡", "玛奇朵", "美式"),
    "鸡肉": ("鸡",),
}

NEG_PATTERNS = ["不要", "不吃", "不想吃", "别吃", "忌", "过敏"]

TEXTURE_KEYWORDS: Dict[str, str] = {
    "酥脆": "酥脆", "脆": "酥脆", "脆的": "酥脆",
    "软": "软嫩", "嫩": "软嫩", "软的": "软嫩",
    "多汁": "多汁", "爆汁": "多汁",
    "绵密": "绵密", "奶昔": "绵密", "细腻": "绵密",
    "爽脆": "爽脆", "清脆": "爽脆",
    "嚼劲": "有嚼劲", "有嚼头": "有嚼劲",
}

NEGATION_PREFIX = ["不", "别", "不要", "不吃", "不太", "少", "无"]

TEMP_KEYWORDS = {
    "热": "hot", "热的": "hot", "暖": "hot",
    "冰": "cold", "冷的": "cold", "冰的": "cold", "凉": "cold",
    "常温": "room",
}


def profile_from_text(text: str) -> TasteProfile:
    """把一句自然语言翻译成口味画像。

    例：「想吃点甜的，但别太腻，要酥脆的」
      → target{sweet:5, ...}, texture_pref=['酥脆']
    """
    p = TasteProfile(source="text", note=text)
    # 未提到的维度给**很低**的权重（0.15）而非 0.5：
    #   - 不能给 0：否则所有「甜5」的候选同分，排序没有区分度
    #   - 不能给 1.0：否则会把「没提到咸」误解成「要少咸」，拉低所有候选
    # 0.15 的效果是"锦上添花"：主维度决定大方向，次要维度做细微区分。
    for d in DIMENSIONS:
        p.weights[d] = 0.15
    hit_dims: List[str] = []

    for dim, kws in FLAVOR_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                # 判断是否被否定：「不辣」「不要甜」
                idx = text.find(kw)
                head = text[max(0, idx - 2):idx]
                negated = any(head.endswith(n) for n in NEGATION_PREFIX)
                if negated:
                    p.weights[dim] = 2.0
                    p.target[dim] = 0.0
                    p.exclude_keywords.append(DIM_CN[dim])
                else:
                    p.weights[dim] = 2.0
                    p.target[dim] = max(p.target[dim], kws[kw])
                    hit_dims.append(dim)
                break

    # 口感
    for kw, tex in TEXTURE_KEYWORDS.items():
        if kw in text and tex not in p.texture_pref:
            p.texture_pref.append(tex)

    # 忌口（食材类否定）：「不要牛肉」→ 排除牛肉类餐品
    for label, tokens in MEAT_TERMS.items():
        hit = False
        for tk in (label,) + tuple(tokens):
            if any(f"{neg}{tk}" in text for neg in NEG_PATTERNS):
                hit = True
                break
        if hit and label not in p.exclude_keywords:
            p.exclude_keywords.append(label)

    # 温度
    for kw, t in TEMP_KEYWORDS.items():
        if kw in text:
            p.temp_pref = t
            break

    # 「清淡」「不腻」「少油」→ 整体降强度
    if any(w in text for w in ["清淡", "不腻", "少油", "轻食", "健康"]):
        for d in DIMENSIONS:
            p.target[d] = min(p.target.get(d, 0.0), 2.0)
            p.weights[d] = 1.5
        p.note += "（已按清淡口味收敛）"

    return p


def profile_from_history(ordered_names: Sequence[str],
                         library: FlavorLibrary,
                         recency_weight: bool = True) -> TasteProfile:
    """从历史订单学偏好。

    做法：把每次点过的餐品口味向量按「时间加权平均」——
    越近的订单权重越高（近因效应），得到用户口味的重心。
    """
    p = TasteProfile(source="history")
    vecs: List[Tuple[Dict[str, float], float]] = []

    n = len(ordered_names)
    for i, name in enumerate(ordered_names):
        item = library.find(name)
        if not item:
            continue
        w = (i + 1) / n if recency_weight else 1.0
        vecs.append((item.get("flavor", {}), w))

    if not vecs:
        p.note = "历史订单为空，或其中的餐品均不在口味库中，改用均衡权重"
        p.target = {d: 3.0 for d in DIMENSIONS}
        return p

    total_w = sum(w for _, w in vecs)
    for d in DIMENSIONS:
        p.target[d] = sum(v.get(d, 0.0) * w for v, w in vecs) / total_w

    # 口味方差大的维度权重调低（说明用户在该维度上不挑），方差小的维度说明稳定偏好
    for d in DIMENSIONS:
        vals = [v.get(d, 0.0) for v, _ in vecs]
        mean = sum(vals) / len(vals)
        var = sum((x - mean) ** 2 for x in vals) / len(vals)
        p.weights[d] = 1.0 + 1.0 / (1.0 + var)   # 越稳定权重越高，上限 2

    # 口感偏好：出现频次最高的前两个
    counter: Dict[str, int] = {}
    for nm in ordered_names:
        it = library.find(nm)
        if it:
            for t in it.get("texture", []):
                counter[t] = counter.get(t, 0) + 1
    p.texture_pref = [t for t, _ in sorted(counter.items(), key=lambda x: -x[1])[:2]]
    p.note = f"基于 {len(vecs)} 条历史订单归纳（近因加权）"
    return p


# ---------------------------------------------------------------------------
# 推荐
# ---------------------------------------------------------------------------

class FlavorRecommender:
    """基于口味向量的相似度推荐器。"""

    def __init__(self, library: FlavorLibrary) -> None:
        self.lib = library

    # -- 单个餐品对画像的相似度 -------------------------------------------
    def _similarity(self, item: Dict[str, Any], p: TasteProfile) -> Tuple[float, List[str]]:
        flavor = item.get("flavor", {})
        reasons: List[str] = []

        # 1) 口味维度：加权「接近度」= 1 - |目标 - 实际| / MAX
        #    只跳过权重极低（≤0.1）的维度。text 模式下未提及维度权重为 0.15，
        #    仍然参与计算以提供区分度，但不会主导排序。
        num = den = 0.0
        for d in DIMENSIONS:
            w = p.weights.get(d, 0.0)
            if w <= 0.1:
                continue
            diff = abs(p.target.get(d, 0.0) - flavor.get(d, 0.0))
            num += w * (1.0 - diff / MAX_SCORE)
            den += w
        base = num / den if den else 0.0

        # 记录贡献最大的维度作为推荐理由
        for d in sorted(DIMENSIONS, key=lambda x: -(p.weights.get(x, 0) *
                                                    (1 - abs(p.target.get(x, 0) - flavor.get(x, 0)) / MAX_SCORE)))[:2]:
            if p.weights.get(d, 0) > 1.5 and abs(p.target.get(d, 0) - flavor.get(d, 0)) <= 1.0:
                reasons.append(f"{DIM_CN[d]}度对得上（你 {p.target.get(d, 0):.1f} / 它 {flavor.get(d, 0):.1f}）")

        # 2) 口感加分：每个命中的偏好口感 +0.05（上限 +0.10）
        tex_bonus = 0.0
        for t in item.get("texture", []):
            if t in p.texture_pref:
                tex_bonus += 0.05
                reasons.append(f"口感「{t}」符合你的偏好")
        tex_bonus = min(tex_bonus, 0.10)

        # 3) 温度加分
        temp_bonus = 0.0
        if p.temp_pref and item.get("temp") == p.temp_pref:
            temp_bonus = 0.05
            reasons.append(f"温度符合（{p.temp_pref}）")

        # 归一化：口味接近度占 85%，口感最多 +10%，温度 +5%，总分封顶 100%
        score = base * 0.85 + tex_bonus + temp_bonus
        return min(score, 1.0), reasons

    def _excluded(self, item: Dict[str, Any], p: TasteProfile) -> bool:
        """硬排除：忌口 / 否定词 / 温度不符。"""
        name = str(item.get("name", ""))
        for kw in p.exclude_keywords:
            # 口味维度的排除：若该维度得分高则排除
            for d, cn in DIM_CN.items():
                if kw == cn and item.get("flavor", {}).get(d, 0) >= 3:
                    return True
            if kw == "牛肉" and ("牛" in name or "安格斯" in name):
                return True
            if kw == "猪肉" and any(x in name for x in ["猪柳", "培根", "烟肉", "火腿"]):
                return True
            if kw == "鱼" and "鱼" in name:
                return True
            if kw == "鸡肉" and ("鸡" in name or "翅" in name):
                return True
            if kw == "咖啡" and any(x in name for x in ["咖啡", "拿铁", "卡布", "摩卡", "玛奇朵", "美式"]):
                return True
        if p.temp_pref and item.get("temp") != p.temp_pref:
            return True
        return False

    def recommend(self,
                  profile: TasteProfile,
                  top_k: int = 5,
                  categories: Optional[Sequence[str]] = None,
                  exclude_names: Iterable[str] = ()) -> List[Recommendation]:
        """返回 Top-K 推荐。

        exclude_names 用于「已点过的不再推」，也支持"再来一份类似的"场景。
        """
        excluded_set = {_norm(x) for x in exclude_names}
        pool = self.lib.items
        if categories:
            cats = set(categories)
            pool = [it for it in pool if it.get("category") in cats]

        results: List[Recommendation] = []
        for it in pool:
            if _norm(it.get("name", "")) in excluded_set:
                continue
            if self._excluded(it, profile):
                continue
            sim, reasons = self._similarity(it, profile)
            results.append(Recommendation(item=it, similarity=sim, reasons=reasons))

        results.sort(key=lambda r: -r.similarity)
        return results[:top_k]

    def similar_to(self, name: str, top_k: int = 5) -> List[Recommendation]:
        """「我喜欢吃 X，推荐类似的」——把 X 的口味向量当作目标画像。"""
        anchor = self.lib.find(name)
        if not anchor:
            return []
        p = TasteProfile(
            target={d: float(anchor.get("flavor", {}).get(d, 0.0)) for d in DIMENSIONS},
            weights={d: 1.5 for d in DIMENSIONS},
            texture_pref=list(anchor.get("texture", [])),
            temp_pref=anchor.get("temp"),
            source="anchor",
            note=f"以「{anchor.get('name')}」为基准",
        )
        # 同品类优先但要能跨品类：不做 categories 限制
        return self.recommend(p, top_k=top_k, exclude_names=[anchor.get("name", "")])
