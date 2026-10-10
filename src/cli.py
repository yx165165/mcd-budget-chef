#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦口味推荐官 —— 统一命令行入口
================================

四个子命令对应四个能力：

  flavors     查看口味图谱（可选按品类过滤）
  recommend   口味推荐（主功能）
              · --like "巨无霸"       → 我想吃和它类似的
              · --want "想吃点甜的"    → 按口味描述找我想要的
              · --history file.txt    → 从我的历史订单学偏好
  plan        完整方案 = 口味推荐 + 营养配餐 + 最优优惠
  simple      简洁点餐：一句话给一餐

示例
----
python src/cli.py flavors
python src/cli.py recommend --like "巨无霸" --top 5
python src/cli.py recommend --want "想吃甜的，要酥脆的，不要牛肉" --top 5
python src/cli.py plan --want "想吃辣的" --budget 35 --kcal 700 --min-protein 25
python src/cli.py simple "来一份辣的汉堡套餐，预算30块"
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flavor_profile import (  # noqa: E402
    DIM_CN, DIMENSIONS, FlavorLibrary, FlavorRecommender, TasteProfile,
    profile_from_history, profile_from_text,
)
from nutrition import (  # noqa: E402
    NutritionGoal, NutritionTable, format_totals, summarize,
)
from coupon_optimizer import PriceOptimizer, PriceTable  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CATEGORY_CN = {
    "burger": "汉堡", "side": "小食", "drink": "饮品",
    "dessert": "甜品", "breakfast": "早餐",
}
TEMP_CN = {"hot": "热", "cold": "冰", "room": "常温"}

# 品类意图词表：把「我想吃汉堡」这类说法映射到 category
CATEGORY_INTENT: Dict[str, tuple] = {
    "burger": ("汉堡", "堡", "巨无霸", "双吉", "麦香鸡", "麦香鱼", "安格斯"),
    "side": ("小食", "配菜", "薯条", "鸡块", "鸡翅", "鸡排", "派", "玉米"),
    "drink": ("饮料", "喝的", "饮品", "可乐", "雪碧", "芬达", "咖啡", "橙汁"),
    "dessert": ("甜点", "甜品", "冰淇淋", "甜筒", "圣代", "麦旋风", "蛋糕"),
    "breakfast": ("早餐", "麦满分", "油条", "香饼"),
}


# ---------------------------------------------------------------------------
# 输出helper
# ---------------------------------------------------------------------------

def bar(value: float, maxv: float = 5.0, width: int = 10) -> str:
    """把 0-5 的分数画成方块条。"""
    filled = int(round(value / maxv * width))
    return "█" * filled + "·" * (width - filled)


def flavor_line(flavor: dict) -> str:
    parts = []
    for d in DIMENSIONS:
        v = flavor.get(d, 0)
        if v > 0:
            parts.append(f"{DIM_CN[d]}{v}")
    return " ".join(parts) if parts else "无显著风味"


def print_recommendations(recs, profile, show_evidence: bool = False) -> None:
    if not recs:
        print("没有找到符合口味的餐品。")
        print("可能原因：排除条件过严（如要求『冰的』同时又指定了『热的』）。可以放宽条件再试。")
        return
    for i, r in enumerate(recs, 1):
        it = r.item
        cat = CATEGORY_CN.get(it.get("category", ""), it.get("category", ""))
        temp = TEMP_CN.get(it.get("temp", ""), it.get("temp", ""))
        print(f"  {i}. {r.name}  [{cat}·{temp}]   匹配度 {r.similarity:.0%}")
        print(f"     风味：{flavor_line(it.get('flavor', {}))}")
        if it.get("texture"):
            print(f"     口感：{'、'.join(it['texture'])}")
        for reason in r.reasons[:3]:
            print(f"     → {reason}")
        if show_evidence:
            print(f"     依据：{it.get('evidence', '无')}")
        print()


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_compare(args) -> int:
    """两款口味对比：并排口味条 + 差异表 + 一句人话结论。"""
    lib = FlavorLibrary.load(args.library)
    A = lib.find(args.a)
    B = lib.find(args.b)
    if not A:
        print(f"[错误] 口味库里没有「{args.a}」。可用 `flavors` 查看全部餐品。", file=sys.stderr)
        return 2
    if not B:
        print(f"[错误] 口味库里没有「{args.b}」。", file=sys.stderr)
        return 2
    if A["name"] == B["name"]:
        print("[错误] 请选两款不同的餐品。", file=sys.stderr)
        return 2

    print("=" * 66)
    print(f"  口味对比：{A['name']}  vs  {B['name']}")
    print("=" * 66)
    print()

    for it in (A, B):
        cat = CATEGORY_CN.get(it.get("category", ""), it.get("category", ""))
        temp = TEMP_CN.get(it.get("temp", ""), it.get("temp", ""))
        print(f"【{it['name']}】{cat}·{temp}　口感：{'、'.join(it.get('texture', []))}")
        for d in DIMENSIONS:
            va = it.get("flavor", {}).get(d, 0)
            print(f"    {DIM_CN[d]}  {bar(va)} {va}")
        print(f"    依据：{it.get('evidence', '')}")
        print()

    # 差异表
    print("-" * 66)
    print(f"  {'维度':<6}{'A':>6}{'B':>8}{'差异':>10}   说明")
    print("-" * 66)
    for d in DIMENSIONS:
        va = A.get("flavor", {}).get(d, 0)
        vb = B.get("flavor", {}).get(d, 0)
        diff = vb - va
        mark = "↑" if diff > 0 else ("↓" if diff < 0 else "=")
        note = ""
        if diff > 0:
            note = f"B 比 A 更{DIM_CN[d]}"
        elif diff < 0:
            note = f"B 比 A 少{DIM_CN[d]}"
        print(f"  {DIM_CN[d]:<6}{va:>6}{vb:>8}{mark + str(abs(diff)):>10}   {note}")
    print()

    # 结论
    max_d, max_abs = DIMENSIONS[0], 0
    for d in DIMENSIONS:
        v = abs(B.get("flavor", {}).get(d, 0) - A.get("flavor", {}).get(d, 0))
        if v > max_abs:
            max_d, max_abs = d, v

    if max_abs == 0:
        print("  ▸ 结论：两款口味完全一致。")
    else:
        dir_txt = "更" if B.get("flavor", {}).get(max_d, 0) > A.get("flavor", {}).get(max_d, 0) else "更少"
        same = [DIM_CN[d] for d in DIMENSIONS
                if abs(B.get("flavor", {}).get(d, 0) - A.get("flavor", {}).get(d, 0)) <= 1]
        print(f"  ▸ 结论：最大差别在 {DIM_CN[max_d]}度 —— {B['name']} 比 {A['name']} {dir_txt}{DIM_CN[max_d]}"
              f"（{B.get('flavor', {}).get(max_d, 0)} vs {A.get('flavor', {}).get(max_d, 0)}，差 {max_abs} 档）。")
        if same:
            print(f"     两者在 {'、'.join(same)} 上基本一致，"
                  f"所以这次替换{'会带来明显不同的风味体验' if max_abs >= 3 else '差别比较细微'}。")

        # 推荐"更 X 但不至于变味"的第三款
        other = "spicy" if max_d == "sweet" else "sweet"
        cands = [it for it in lib.items
                 if it["name"] not in (A["name"], B["name"])
                 and it.get("flavor", {}).get(max_d, 0) > A.get("flavor", {}).get(max_d, 0)
                 and abs(it.get("flavor", {}).get(other, 0) - A.get("flavor", {}).get(other, 0)) <= 1]
        if cands:
            cands.sort(key=lambda x: -x.get("flavor", {}).get(max_d, 0))
            print(f"     想要「{DIM_CN[max_d]}更突出但不至于变味」，可以试试："
                  + "、".join(c["name"] for c in cands[:3]))
    print()
    return 0


def cmd_flavors(args) -> int:
    lib = FlavorLibrary.load(args.library)
    items = lib.items
    if args.category:
        items = lib.by_category(args.category)

    print("=" * 66)
    print(f"  麦麦口味图谱   共 {len(items)} 款")
    print("=" * 66)
    print(f"  {lib.meta.get('disclaimer', '')}")

    order = ["burger", "side", "drink", "dessert", "breakfast"]
    for cat in order:
        group = [it for it in items if it.get("category") == cat]
        if not group:
            continue
        print(f"\n【{CATEGORY_CN.get(cat, cat)}】（{len(group)} 款）")
        for it in group:
            print(f"  {it.get('name',''):<30} {flavor_line(it.get('flavor', {}))}")
            if it.get("texture"):
                print(f"  {'':<30} 口感：{'、'.join(it['texture'])}")
    print()
    return 0


def _build_profile(args, lib) -> TasteProfile:
    """根据参数决定用哪种方式构建画像。"""
    if args.history:
        names = []
        with open(args.history, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    names.append(line)
        p = profile_from_history(names, lib)
        print(f"【从历史订单学偏好】{p.note}")
        return p
    if args.want:
        p = profile_from_text(args.want)
        print(f"【按口味描述】原文：「{args.want}」")
        return p
    if args.like:
        anchor = lib.find(args.like)
        if not anchor:
            print(f"[错误] 口味库里没有「{args.like}」。可用 `flavors` 子命令查看全部餐品。", file=sys.stderr)
            return None
        p = TasteProfile(
            target={d: float(anchor.get("flavor", {}).get(d, 0)) for d in DIMENSIONS},
            weights={d: 1.5 for d in DIMENSIONS},
            texture_pref=list(anchor.get("texture", [])),
            temp_pref=anchor.get("temp"),
            source="anchor", note=f"以「{anchor.get('name')}」为口味基准",
        )
        print(f"【找相似的】基准：{anchor.get('name')}（{flavor_line(anchor.get('flavor', {}))}）")
        return p
    print("[错误] 请指定 --like / --want / --history 之一。", file=sys.stderr)
    return None


def cmd_recommend(args) -> int:
    lib = FlavorLibrary.load(args.library)
    rec = FlavorRecommender(lib)
    p = _build_profile(args, lib)
    if p is None:
        return 2

    if p.source != "anchor":
        print(f"【你的口味画像】{p.describe()}")
    print("=" * 66)
    print(f"  口味推荐 Top {args.top}")
    print("=" * 66)

    cats = [c.strip() for c in args.category.split(",")] if args.category else None
    exclude = [args.like] if args.like else []
    # 历史模式：已经点过的不再推荐（要给它"下一餐吃什么"的答案，而不是复读历史）
    if args.history:
        with open(args.history, "r", encoding="utf-8") as f:
            exclude += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    recs = rec.recommend(p, top_k=args.top, categories=cats, exclude_names=exclude)
    print_recommendations(recs, p, show_evidence=args.evidence)

    if args.json:
        print(json.dumps({
            "profile": {"target": p.target, "weights": p.weights,
                        "describe": p.describe(), "source": p.source},
            "recommendations": [r.as_dict() for r in recs],
        }, ensure_ascii=False, indent=2))
    return 0


def cmd_plan(args) -> int:
    """完整方案：口味推荐 → 营养配餐 → 最优优惠。"""
    lib = FlavorLibrary.load(args.library)
    rec = FlavorRecommender(lib)
    p = _build_profile(args, lib)
    if p is None:
        return 2

    print(f"【你的口味画像】{p.describe()}")
    print()

    # ---- 第 1 步：口味推荐，得到候选池 ----
    candidates = rec.recommend(p, top_k=args.pool, categories=None)
    if not candidates:
        print("口味推荐无结果，无法继续。")
        return 1

    # 口味门槛：只保留相似度不低于最高分 cutoff 倍的候选。
    # 否则「口味不搭但便宜」的菜会混进最优方案，算出省钱却不对味的一餐。
    hi = candidates[0].similarity
    gated = [c for c in candidates if c.similarity >= hi * args.cutoff]
    if len(gated) < 3:
        gated = candidates[:3]      # 保底 3 款，避免候选太少凑不出组合
    candidates = gated

    print("=" * 66)
    print(f"  第 1 步 · 口味推荐（候选池 {len(candidates)} 款，已按口味门槛筛选）")
    print("=" * 66)
    print_recommendations(candidates[:5], p)
    cand_names = [r.name for r in candidates]

    # ---- 第 2 步：营养约束 + 最优优惠，联合求解 ----
    price_table = PriceTable.load(args.prices)
    nut_table = NutritionTable.load(args.nutrition)
    optimizer = PriceOptimizer(price_table)

    goal = NutritionGoal(
        calorie_budget=args.kcal,
        calorie_target=None,
        min_protein=args.min_protein,
        max_sodium=args.max_sodium,
    )

    def passes(names) -> bool:
        rep = summarize(names, nut_table, goal)
        return rep.passed

    print("=" * 66)
    print("  第 2 步 · 在候选池内求解「最省 + 营养达标」的组合")
    print("=" * 66)
    results = optimizer.optimize(
        candidates=cand_names,
        budget=args.budget,
        max_items=args.max_items,
        min_items=2,
        nutrition_filter=passes if (args.kcal or args.min_protein or args.max_sodium) else None,
        top_k=args.top,
    )

    if not results:
        print("在候选池内没找到满足条件的组合。")
        print("建议：放松营养约束、提高预算，或增大候选池（--pool）。")
        return 1

    # ---- 第 3 步：输出 ----
    print()
    for i, res in enumerate(results, 1):
        rep = summarize(res.names, nut_table, goal)
        print("=" * 66)
        print(f"  方案 {i}    实付 ¥{res.paid:.2f}"
              f"（原价 ¥{res.subtotal:.2f}，省 ¥{res.discount:.2f}）")
        print("=" * 66)
        for nm in res.names:
            c = price_table.cents(nm)
            print(f"    · {nm:<30} ¥{(c or 0)/100:.2f}")
        if res.coupon:
            print(f"    用券：{res.coupon.name}（-¥{res.discount:.2f}）")
        else:
            print("    用券：无可用券")
        print(f"    营养：{format_totals(rep.totals)}")
        for v in rep.verdicts:
            print(f"      {v}")
        print(f"    数据来源：营养＝{rep.source}｜价格＝demo 占位值（实际以 MCP calculate-price 为准）")
        print()

    if args.json:
        out = []
        for res in results:
            rep = summarize(res.names, nut_table, goal)
            d = res.as_dict()
            d["nutrition"] = rep.as_dict()
            out.append(d)
        print(json.dumps({"profile": p.describe(), "plans": out}, ensure_ascii=False, indent=2))
    return 0


def cmd_simple(args) -> int:
    """简洁点餐：一句话 → 一餐。"""
    text = args.text
    print("=" * 66)
    print("  简洁点餐模式")
    print("=" * 66)
    print(f"  你说：「{text}」")
    print()

    lib = FlavorLibrary.load(args.library)
    p = profile_from_text(text)

    # 从文本里再抓预算 / 热量数字（"预算30" "700大卡"）
    import re
    budget = args.budget
    kcal = args.kcal
    if budget is None:
        m = re.search(r"(?:预算|不超过|最多|控制在)\s*(\d+(?:\.\d+)?)\s*(?:元|块|rmb)?", text)
        if m:
            budget = float(m.group(1))
    if kcal is None:
        m = re.search(r"(\d{3,4})\s*(?:大卡|千卡|kcal|卡)", text)
        if m:
            kcal = float(m.group(1))

    print(f"  → 口味画像：{p.describe()}")
    print(f"  → 预算：{'¥%.0f' % budget if budget else '不限'}"
          f"｜热量上限：{'%.0f kcal' % kcal if kcal else '不限'}")
    print()

    rec = FlavorRecommender(lib)
    cands = rec.recommend(p, top_k=args.pool)
    if not cands:
        print("没听懂想吃什么。换个说法试试，比如「来个辣的汉堡，预算 30」。")
        return 1

    # 品类意图：「辣的汉堡」里的「汉堡」必须被满足，
    # 否则「最省」会把主食换成更便宜的小食，点出来不像一餐。
    must: List[str] = []
    for c, kws in CATEGORY_INTENT.items():
        if any(k in text for k in kws):
            same_cat = [r.name for r in cands if r.item.get("category") == c]
            if same_cat and same_cat[0] not in must:
                must.append(same_cat[0])
    if must:
        print(f"  → 识别到品类要求：{'、'.join(CATEGORY_CN.get(x, x) for x in
              [c for c in CATEGORY_INTENT if any(k in text for k in CATEGORY_INTENT[c])])}"
              f"  （已锁定：{'、'.join(must)}）")

    price_table = PriceTable.load(args.prices)
    nut_table = NutritionTable.load(args.nutrition)
    optimizer = PriceOptimizer(price_table)
    goal = NutritionGoal(calorie_budget=kcal)

    def passes(names) -> bool:
        return summarize(names, nut_table, goal).passed

    results = optimizer.optimize(
        candidates=[c.name for c in cands],
        budget=budget, max_items=3, min_items=2,
        must_include=must,
        nutrition_filter=passes if kcal else None, top_k=1,
    )

    if not results:
        print("这个预算下没凑出合适的一餐。")
        print("建议：把预算提高几块，或者换个主食品类。")
        return 1

    res = results[0]
    rep = summarize(res.names, nut_table, goal)
    print("  ┌─ 给你配好了 ─────────────────────────────")
    for nm in res.names:
        c = price_table.cents(nm)
        print(f"  │  {nm:<28} ¥{(c or 0)/100:.2f}")
    if res.coupon:
        print(f"  │  用券：{res.coupon.name}  省 ¥{res.discount:.2f}")
    print("  ├──────────────────────────────────────────")
    print(f"  │  实付 ¥{res.paid:.2f}    {format_totals(rep.totals)}")
    print("  └──────────────────────────────────────────")
    for v in rep.verdicts:
        print(f"     {v}")
    print()
    print("  （数据来源：口味库为公开配料推断；营养/价格为演示占位值，"
          "实际下单以麦当劳 MCP 实时结果为准）")
    return 0


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    # 公共参数挂到每个子命令上（用 parents），
    # 这样 `--json` / `--library` 放在子命令前后都能用，
    # 不需要用户记住 argparse 的"全局参数必须放前面"这条隐藏规则。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--library", default=os.path.join(ROOT, "data", "flavor_tags.json"))
    common.add_argument("--prices", default=os.path.join(ROOT, "data", "prices_demo.json"))
    common.add_argument("--nutrition", default=os.path.join(ROOT, "data", "nutrition_demo.json"))
    common.add_argument("--json", action="store_true", help="额外输出 JSON")

    ap = argparse.ArgumentParser(
        description="麦麦口味推荐官 —— 按口味找吃的，顺便把营养和券都算好")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("flavors", parents=[common], help="查看口味图谱")
    p1.add_argument("--category", choices=list(CATEGORY_CN.keys()))
    p1.set_defaults(func=cmd_flavors)

    p5 = sub.add_parser("compare", parents=[common], help="两款口味对比")
    p5.add_argument("a", help="餐品 A 名称")
    p5.add_argument("b", help="餐品 B 名称")
    p5.set_defaults(func=cmd_compare)

    p2 = sub.add_parser("recommend", parents=[common], help="口味推荐（主功能）")
    p2.add_argument("--like", help="以某餐品为基准，找相似的")
    p2.add_argument("--want", help="用自然语言描述想吃什么")
    p2.add_argument("--history", help="历史订单文件（每行一个餐品名）")
    p2.add_argument("--top", type=int, default=5)
    p2.add_argument("--category", help="限定品类，逗号分隔：burger,side,drink,dessert,breakfast")
    p2.add_argument("--evidence", action="store_true", help="显示配料依据")
    p2.set_defaults(func=cmd_recommend)

    p3 = sub.add_parser("plan", parents=[common], help="完整方案：口味+营养+优惠")
    p3.add_argument("--like"), p3.add_argument("--want"), p3.add_argument("--history")
    p3.add_argument("--budget", type=float, default=None, help="预算上限（元）")
    p3.add_argument("--kcal", type=float, default=None, help="热量上限（kcal）")
    p3.add_argument("--min-protein", type=float, default=None)
    p3.add_argument("--max-sodium", type=float, default=None)
    p3.add_argument("--pool", type=int, default=12, help="口味推荐候选池大小")
    p3.add_argument("--cutoff", type=float, default=0.7,
                    help="口味门槛：只保留相似度 ≥ 最高分×cutoff 的候选（默认 0.7）")
    p3.add_argument("--max-items", type=int, default=4)
    p3.add_argument("--top", type=int, default=2)
    p3.set_defaults(func=cmd_plan)

    p4 = sub.add_parser("simple", parents=[common], help="简洁点餐：一句话给一餐")
    p4.add_argument("text", help="一句话，如「来个辣的汉堡，预算30」")
    p4.add_argument("--budget", type=float, default=None)
    p4.add_argument("--kcal", type=float, default=None)
    p4.add_argument("--pool", type=int, default=10)
    p4.set_defaults(func=cmd_simple)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
