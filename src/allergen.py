#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦口味推荐官 —— 过敏原推导模块
================================

⚠️ 安全声明（必读）
-------------------
本模块输出的过敏原信息是**基于公开配料信息推导的参考值**，
**不是麦当劳中国大陆官方发布的过敏原数据**。原因：

  中国大陆麦当劳**未公开过敏原一览表**。目前已核实的官方过敏原矩阵
  均来自境外市场（英国、新西兰、澳大利亚、日本）或第三方平台
  （台北市食材登录平台），配方与国内不完全一致，不能直接套用。

因此本模块的处理策略是「**宁可说不知道，也不猜**」：

  三级判定
  --------
  CONFIRMED  配料描述中**明确写出**了含该过敏原的食材 → 输出「含」
  POSSIBLE   配料描述中出现**含义模糊**的食材（如「风味酱」「沙拉酱」）
             → 输出「可能含（需确认）」
  UNKNOWN    无配料描述，或描述中未涉及该过敏原 → 输出「—（未知）」

  UNKNOWN **不等于「不含」**。这是本模块最重要的设计约束。

  交叉污染提示：所有输出都附「厨房共线加工，无法保证完全不含任何过敏原」，
  这也是各市场官方文件的一致表述。

依据标准
--------
过敏原清单参照《食品安全国家标准 预包装食品标签通则》(GB 7718-2025)
规定的**八大类**强制性致敏物质：
  含麸质谷物及其制品、甲壳纲类动物及其制品、鱼类及其制品、蛋类及其制品、
  花生及其制品、大豆及其制品、乳及乳制品、坚果及其果仁类制品
另补充常见自愿标示项：芝麻、芥末。

数据来源
--------
配料描述来自 `data/flavor_tags.json` 的 `evidence` 字段。该字段有三级来源
（见 `_meta.source_breakdown`）：
  official_disclosure  麦当劳中国官方公示文件 → 推导可信度最高
  official_website     官网页面描述 → 可信度较高
  inferred             第三方/推断 → 仅作参考
本模块会在输出中标明来源等级，让用户知道这条过敏原信息的底气有多足。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIB = os.path.join(os.path.dirname(HERE), "data", "flavor_tags.json")

# 判定等级
CONFIRMED = "confirmed"
POSSIBLE = "possible"
UNKNOWN = "unknown"

LEVEL_CN = {
    CONFIRMED: "含",
    POSSIBLE: "可能含",
    UNKNOWN: "—",
}

# ---------------------------------------------------------------------------
# 过敏原定义（GB 7718-2025 八大类 + 常见自愿标示项）
# ---------------------------------------------------------------------------

ALLERGENS: List[Dict[str, str]] = [
    {"key": "gluten",      "cn": "含麸质谷物", "note": "小麦、黑麦、大麦、燕麦及其制品"},
    {"key": "milk",        "cn": "乳及乳制品", "note": "含乳糖"},
    {"key": "egg",         "cn": "蛋类",       "note": ""},
    {"key": "soy",         "cn": "大豆",       "note": ""},
    {"key": "fish",        "cn": "鱼类",       "note": ""},
    {"key": "crustacean",  "cn": "甲壳纲类",   "note": "虾、蟹等"},
    {"key": "peanut",      "cn": "花生",       "note": ""},
    {"key": "tree_nut",    "cn": "坚果",       "note": "杏仁、榛果、核桃、腰果等"},
    {"key": "sesame",      "cn": "芝麻",       "note": "自愿标示项"},
    {"key": "mustard",     "cn": "芥末",       "note": "自愿标示项"},
]

ALLERGEN_CN = {a["key"]: a["cn"] for a in ALLERGENS}

# ---------------------------------------------------------------------------
# 食材关键词 → 过敏原映射
# ---------------------------------------------------------------------------
# 只有在这里被列出的食材，才会参与推导。
# 关键设计：把食材分成「明确含某过敏原」与「含糊、只能算可能含」两类。

INGREDIENT_MAP: Dict[str, List[str]] = {
    # ---- 含麸质谷物（小麦制品）----
    "gluten": [
        "面包", "面包糠", "英式松饼", "松饼", "面饼", "面粉", "小麦", "麦片",
        "裹粉", "脆浆", "酥皮", "派皮", "华夫筒", "曲奇", "饼干", "可颂",
        "热香饼", "油条", "麦满分", "汉堡", "堡", "卷", "蛋糕", "司康", "贝果", "泡芙",
    ],
    # ---- 乳及乳制品 ----
    "milk": [
        "芝士", "奶酪", "干酪", "切达", "高达", "牛奶", "奶油", "黄油", "鲜奶",
        "乳酪", "奶泡", "奶盖", "冰淇淋", "甜筒", "新地", "圣代", "麦旋风",
        "拿铁", "卡布", "玛奇朵", "摩卡", "奶茶", "热巧克力", "奶昔",
        "芝士蛋糕", "提拉米苏", "燕麦拿铁", "奶油奶酪", "马斯卡彭",
    ],
    # ---- 蛋类 ----
    # 注：「蛋黄酱/美乃滋/塔塔酱」按标准配方确实含蛋，判定为「含」；
    #     「沙拉酱」在国内有淀粉基底的无蛋版本，故归入「可能含」而非「含」。
    "egg": [
        "鸡蛋", "蛋饼", "蒸蛋", "炒蛋", "煎蛋", "蛋堡", "蛋", "蛋黄酱",
        "美乃滋", "塔塔酱", "蛋白", "欧姆蛋",
    ],
    # ---- 大豆（含大豆油、酱油等常见隐性来源）----
    "soy": [
        "大豆", "豆油", "酱油", "豆浆", "豆腐", "植物调和油", "沙拉油",
    ],
    # ---- 鱼类 ----
    "fish": ["鱼肉", "鳕鱼", "鲑鱼", "三文鱼", "金枪鱼", "狭鳕", "鱼排", "鱼"],
    # ---- 甲壳纲类 ----
    "crustacean": ["虾", "蟹", "龙虾"],
    # ---- 花生 ----
    "peanut": ["花生", "花生酱"],
    # ---- 坚果 ----
    "tree_nut": ["榛果", "杏仁", "核桃", "腰果", "开心果", "碧根果", "夏威夷果", "坚果"],
    # ---- 芝麻 ----
    "sesame": ["芝麻"],
    # ---- 芥末 ----
    "mustard": ["芥末", "黄芥末", "第戎"],
}

# 含义模糊、可能存在隐性过敏原的食材 —— 只标记为「可能含」，不下断言
#
# 关键：所有「复合酱料」都用**正则后缀**匹配，而不是精确词匹配。
# 因为酱料命名不统一（巨无霸酱 / 沙拉酱 / 风味酱 / 特制酱 / 烧烤酱 …），
# 只要出现「…酱」就说明是复合调味料，其配方国内不公开，
# 可能含蛋、芥末、大豆、芝麻等。宁可多提示，不可漏报。
AMBIGUOUS_PATTERNS: List[Tuple[str, str]] = [
    # (过敏原 key, 正则)
    ("egg",     r"[\u4e00-\u9fa5]{0,4}酱|沙拉"),
    ("mustard", r"[\u4e00-\u9fa5]{0,4}酱|沙拉"),
    ("soy",     r"[\u4e00-\u9fa5]{0,4}酱|沙拉|调味料|调味|裹粉|浆料"),
    ("milk",    r"[\u4e00-\u9fa5]{0,4}酱|奶香|奶酪风味"),
    ("gluten",  r"[\u4e00-\u9fa5]{0,4}酱|浆料"),
    ("sesame",  r"[\u4e00-\u9fa5]{0,4}酱|沙拉|浆料"),
]

# 需要从「可能含」判定中排除的、明确不含该过敏原的酱料名
SAUCE_EXCEPTIONS = {
    "egg": ["番茄酱"],
}

# 中文宽度对齐：CJK 字符与全角标点算 2 列
def _w(s: str) -> int:
    return sum(2 if _is_wide(c) else 1 for c in s)


def _is_wide(c: str) -> bool:
    o = ord(c)
    return (0x1100 <= o <= 0x115F or 0x2E80 <= o <= 0xA4CF
            or 0xAC00 <= o <= 0xD7A3 or 0xF900 <= o <= 0xFAFF
            or 0xFE30 <= o <= 0xFE6F or 0xFF00 <= o <= 0xFF60
            or 0xFFE0 <= o <= 0xFFE6 or 0x3000 <= o <= 0x303F)


def _pad(s: str, width: int) -> str:
    """按显示宽度补空格。"""
    d = width - _w(s)
    return s + " " * max(d, 0)


# ---------------------------------------------------------------------------
# 结果模型
# ---------------------------------------------------------------------------

@dataclass
class AllergenReport:
    """单个餐品的过敏原报告。"""

    name: str
    levels: Dict[str, str] = field(default_factory=dict)      # key -> confirmed/possible/unknown
    hits: Dict[str, List[str]] = field(default_factory=dict)  # key -> 触发该判定的食材
    source: str = "inferred"
    evidence: str = ""
    has_ingredient_text: bool = False

    @property
    def source_cn(self) -> str:
        return {
            "official_disclosure": "麦当劳中国官方公示文件",
            "official_website": "麦当劳中国官网",
            "inferred": "第三方/推断（仅供参考）",
        }.get(self.source, self.source)

    def confirmed_list(self) -> List[str]:
        return [ALLERGEN_CN[k] for k in ALLERGEN_CN if self.levels.get(k) == CONFIRMED]

    def possible_list(self) -> List[str]:
        return [ALLERGEN_CN[k] for k in ALLERGEN_CN if self.levels.get(k) == POSSIBLE]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "source_cn": self.source_cn,
            # has_ingredient_text=False 表示「无数据」；
            # True 且 confirmed/possible 全空 表示「有数据、未发现」
            "has_ingredient_text": self.has_ingredient_text,
            "verdict": ("no_data" if not self.has_ingredient_text
                        else ("none_found" if not (self.confirmed_list() or self.possible_list())
                              else "found")),
            "levels": self.levels,
            "levels_cn": {ALLERGEN_CN[k]: LEVEL_CN[v] for k, v in self.levels.items()},
            "hits": self.hits,
            "confirmed": self.confirmed_list(),
            "possible": self.possible_list(),
        }


# ---------------------------------------------------------------------------
# 推导引擎
# ---------------------------------------------------------------------------

class AllergenEngine:
    """从配料描述推导过敏原。"""

    # 引用式描述的识别：「同X，仅份量不同」「同X，仅容量不同」
    # 这类条目的配料完全等同于被引用的那条，必须跟随解析，
    # 否则会被误判为「无配料描述」→ 明明是已知成分却说不知道，属漏报。
    _REF_RE = re.compile(r"^\s*同\s*([^，,。；;]+)[，,。；;]")

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.items: List[Dict[str, Any]] = raw.get("items", [])
        self._by_name = {_norm(i["name"]): i for i in self.items}
        self._cache: Dict[str, AllergenReport] = {}

    @classmethod
    def load(cls, path: str = DEFAULT_LIB) -> "AllergenEngine":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    # -- 单条推导 ---------------------------------------------------------
    def analyze(self, name: str) -> Optional[AllergenReport]:
        """推导单个餐品的过敏原。查不到该餐品返回 None。"""
        return self._analyze(name, depth=0)

    def _analyze(self, name: str, depth: int) -> Optional[AllergenReport]:
        key = _norm(name)
        if key in self._cache:
            return self._cache[key]
        item = self._by_name.get(key)
        if not item:
            return None
        rep = self._derive(item, depth=depth)
        if rep is not None:
            self._cache[key] = rep
        return rep

    def _resolve_reference(self, item: Dict[str, Any], depth: int) -> Optional[Dict[str, Any]]:
        """若本条是「同X…」的引用式描述，返回被引用的条目。"""
        if depth > 3:          # 防循环
            return None
        m = self._REF_RE.match(str(item.get("evidence", "")).strip())
        if not m:
            return None
        ref_name = m.group(1).strip()
        # 允许「同侧食薯饼」这种带修饰的写法：先精确查，再模糊查
        ref = self._by_name.get(_norm(ref_name))
        if ref is None:
            for k, v in self._by_name.items():
                if ref_name and ref_name in v.get("name", ""):
                    ref = v
                    break
        return ref

    def _derive(self, item: Dict[str, Any], depth: int = 0) -> Optional[AllergenReport]:
        evidence = str(item.get("evidence", ""))
        # 只取「配料描述」部分参与推导：
        # evidence 里可能含「〔官方对照〕…」等我们后来追加的说明文字，
        # 那些不是配料，混进来会误判。
        ingredient_text = _ingredient_part(evidence)
        has_text = _has_ingredient_text(ingredient_text)

        # 引用式描述 → 跟随被引用条目解析其配料
        if not has_text:
            ref = self._resolve_reference(item, depth)
            if ref is not None:
                ref_rep = self._analyze(ref["name"], depth + 1)
                if ref_rep is not None and ref_rep.has_ingredient_text:
                    # 复用被引用条目的判定，但名称与自身 evidence 用本条
                    return AllergenReport(
                        name=item["name"],
                        levels=dict(ref_rep.levels),
                        hits={k: [f"{h}（同「{ref['name']}」）" for h in v]
                              for k, v in ref_rep.hits.items()},
                        source=item.get("source", "inferred"),
                        evidence=evidence,
                        has_ingredient_text=True,
                    )

        levels: Dict[str, str] = {a["key"]: UNKNOWN for a in ALLERGENS}
        hits: Dict[str, List[str]] = {a["key"]: [] for a in ALLERGENS}

        if has_text:
            # 1) 明确配料 → 判定为「含」
            for ak, kws in INGREDIENT_MAP.items():
                for kw in kws:
                    if kw in ingredient_text:
                        levels[ak] = CONFIRMED
                        if kw not in hits[ak]:
                            hits[ak].append(kw)
            # 2) 模糊/复合配料 → 判定为「可能含」（不覆盖已确认的）
            for ak, pattern in AMBIGUOUS_PATTERNS:
                for m in re.finditer(pattern, ingredient_text):
                    kw = m.group(0)
                    if kw in SAUCE_EXCEPTIONS.get(ak, []):
                        continue          # 如「番茄酱」明确不含蛋
                    if levels[ak] == UNKNOWN:
                        levels[ak] = POSSIBLE
                    if kw not in hits[ak]:
                        hits[ak].append(kw)

        # 3) 「乳及乳制品」的特殊处理：
        #    咖啡类饮品即便配料未写明「牛奶」，只要产品名含拿铁/卡布/摩卡等，
        #    默认含奶（这些品类的标准做法就是加奶）。
        #    但这是**推断**，所以标 possible 而非 confirmed。
        nm = item.get("name", "")
        for kw in ("拿铁", "卡布", "玛奇朵", "摩卡", "奶茶", "奶昔", "热巧克力"):
            if kw in nm and levels["milk"] == UNKNOWN:
                levels["milk"] = POSSIBLE
                hits["milk"].append(f"产品名含「{kw}」，该类饮品通常含乳")
                break

        # 4) 含肉产品的重组肉提示 → 可能涉及大豆蛋白等辅料
        if any(k in ingredient_text for k in ("牛肉", "鸡肉", "猪肉", "混合肉片")):
            if levels["soy"] == UNKNOWN:
                levels["soy"] = POSSIBLE
                hits["soy"].append("肉制品常含大豆蛋白作粘合剂（配方未公开）")

        return AllergenReport(
            name=item["name"],
            levels=levels,
            hits=hits,
            source=item.get("source", "inferred"),
            evidence=evidence,
            has_ingredient_text=has_text,
        )

    # -- 批量筛选 ---------------------------------------------------------
    def filter_safe(self, avoid: Sequence[str], names: Optional[Sequence[str]] = None
                    ) -> Tuple[List[str], List[str], List[str]]:
        """给定要避开的过敏原，把候选餐品分成三类。

        返回 (安全, 风险, 未知)
          - 安全：所有要避开的过敏原都判定为 UNKNOWN 且**有配料描述**
            （即配料里确实没提到，而不是"没数据"）
          - 风险：任一要避开项为 confirmed 或 possible
          - 未知：无配料描述，无法判断

        注意：「安全」也**不等于绝对不含**——厨房交叉污染无法排除。
        """
        avoid_keys = [k for k in avoid if k in ALLERGEN_CN]
        pool = names if names is not None else [i["name"] for i in self.items]

        safe, risk, unknown = [], [], []
        for nm in pool:
            rep = self.analyze(nm)
            if rep is None:
                continue
            if not rep.has_ingredient_text:
                unknown.append(nm)
                continue
            level_set = {rep.levels.get(k, UNKNOWN) for k in avoid_keys}
            if CONFIRMED in level_set or POSSIBLE in level_set:
                risk.append(nm)
            else:
                safe.append(nm)
        return safe, risk, unknown


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = str(s).strip().lower()
    for ch in [" ", "\t", "　", "(", ")", "（", "）"]:
        s = s.replace(ch, "")
    return s


# evidence 中属于「配料描述」的前缀标记
_ING_MARKERS = [
    "主要原料为", "主要原料：", "配料：", "配料:", "原料：",
    # 以下为非「配料：」格式但同样含配料信息的写法
    "官网产品信息：", "官网产品信息:", "官网原文", "官网热点更新",
    "麦当劳台湾官网原文：", "麦当劳台湾官网原文:",
]

# 需要从配料描述中剔除的、我们后来追加的说明性文字
_STRIP_PATTERNS = [
    r"〔官方对照〕[^。]*。?",
    r"依据《[^》]*》[：:]?",
]


def _has_ingredient_text(text: str) -> bool:
    """判断这段文字是否**真的包含配料信息**（而非只是口味评论）。

    判据（满足其一即可）：
      1. 含配料标记词（配料：/ 主要原料为 / 官网产品信息：…）
      2. 命中 ≥2 个已知食材关键词

    为什么需要这个判断：evidence 字段里既有配料清单，也有纯口味描述
    （例如「燕麦奶替代牛奶，甜度略高」）。后者虽提到「牛奶」二字，
    但那是**比较对象**而非**配料声明**，不能据此认定"含乳"。
    """
    t = text or ""
    if any(m in t for m in _ING_MARKERS):
        return True
    hits = 0
    for kws in INGREDIENT_MAP.values():
        for kw in kws:
            if kw in t:
                hits += 1
                break
    return hits >= 2


def _ingredient_part(evidence: str) -> str:
    """从 evidence 中抽出参与过敏原扫描的正文。

    刻意**宁可广、不可漏**：返回清理后的整段文本，而不是只取某个标记后的
    第一句。原因是有过一次真实漏报——

        麦乐鸡的 evidence 为：
          「麦当劳台湾官网原文：『鷄肉於調味裹層後…』。**裹粉**调味含少量胡椒（辣1）。」
        若只取「官网原文：」后的第一句，就会漏掉第二句里的「裹粉」，
        从而误判为「未发现含麸质谷物」——而裹粉是明确的小麦制品。

    所以只剔除**我们后来追加的说明性文字**（〔官方对照〕…、依据《…》），
    它们不含真实配料信息。
    """
    text = evidence or ""
    for pat in _STRIP_PATTERNS:
        text = re.sub(pat, "", text)
    return text.strip()
    """从 evidence 中抽出「含配料信息的正文」。

    这里刻意**宁可广、不可漏**：返回清理后的整段文本，而不是只取某个标记后的
    第一句。原因是有过一次真实漏报——

        麦乐鸡的 evidence 为：
          「麦当劳台湾官网原文：『鷄肉於調味裹層後…』。**裹粉**调味含少量胡椒（辣1）。」
        若只取「官网原文：」后的第一句，就会漏掉第二句里的「裹粉」，
        从而误判为「未发现含麸质谷物」——而裹粉是明确的小麦制品。

    所以策略改为：整段参与扫描，只剔除**我们自己后来追加的说明性文字**
    （〔官方对照〕…、依据《…》 这类），因为它们不含真实配料信息。
    """
    text = evidence or ""
    for pat in _STRIP_PATTERNS:
        text = re.sub(pat, "", text)
    return text.strip()


def format_report(rep: AllergenReport, width: int = 66) -> str:
    """把报告格式化成终端可读文本。"""
    out = []
    out.append("=" * width)
    out.append(f"  过敏原参考：{rep.name}")
    out.append("=" * width)
    out.append(f"  配料依据来源：{rep.source_cn}")
    if rep.evidence:
        ev = rep.evidence
        out.append(f"  原始依据：{ev[:width*3]}{'…' if len(ev) > width*3 else ''}")
    out.append("")

    if not rep.has_ingredient_text:
        out.append("  ⚠️ 该餐品**无配料描述**，无法推导过敏原。")
        out.append("     所有项均为「—（未知）」，这不等于「不含」。")
        out.append("")
    else:
        found = rep.confirmed_list() + rep.possible_list()
        if not found:
            out.append("  ℹ️ 已依据配料描述逐项核对，**未发现**八大类致敏物质。")
            out.append("     但这**不等于「绝对不含」**——见下方提示。")
        else:
            out.append(f"  ℹ️ 已识别：{'、'.join(rep.confirmed_list()) or '无'}"
                       + (f"（明确含）" if rep.confirmed_list() else "")
                       + (f"；{'、'.join(rep.possible_list())}（可能含）" if rep.possible_list() else ""))
        out.append("")

    out.append(f"  {_pad('过敏原', 14)}{_pad('判定', 12)}触发食材")
    out.append("  " + "-" * (width - 4))
    for a in ALLERGENS:
        k = a["key"]
        lv = rep.levels.get(k, UNKNOWN)
        if lv == UNKNOWN:
            # 区分「有配料描述但没提到」与「根本没配料数据」：
            # 前者是"核对过、未发现"，后者是"不知道"。语义完全不同。
            mark, txt = ("⚪", "未发现") if rep.has_ingredient_text else ("❔", "无数据")
        else:
            mark = {CONFIRMED: "🔴", POSSIBLE: "🟡"}[lv]
            txt = LEVEL_CN[lv]
        hit = "、".join(rep.hits.get(k, [])) or "—"
        if _w(hit) > 34:
            acc, out_s = 0, ""
            for ch in hit:
                acc += 2 if _is_wide(ch) else 1
                if acc > 31:
                    out_s += "…"
                    break
                out_s += ch
            hit = out_s
        out.append(f"  {_pad(a['cn'], 14)}{mark}{_pad(txt, 8)}{hit}")
    out.append("")
    out.append("  ⚠️ 重要提示")
    out.append("  · 本判定基于**公开配料信息推导**，**非麦当劳中国大陆官方过敏原数据**；")
    out.append("    中国大陆麦当劳未公开过敏原一览表。")
    out.append("  · 判定含义：🔴含 / 🟡可能含 / ⚪**未发现**（核对过配料、未提及）/")
    out.append("    ❔**无数据**（该餐品无配料描述，无法判断）。")
    out.append("    ⚪ 与 ❔ 都**不等于「不含」**。")
    out.append("  · 麦当劳厨房同时处理多种致敏食材，**无法保证任何餐品完全不含过敏原**。")
    out.append("  · 严重过敏者请**以下单时麦当劳官方渠道的说明为准**，并咨询医生。")
    return "\n".join(out)
