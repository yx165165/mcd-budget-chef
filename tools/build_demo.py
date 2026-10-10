#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成零 Token 在线演示页（docs/index.html）
==========================================

把口味图谱、价格、营养三份数据内嵌进 HTML，并用 JS 重写一遍推荐算法，
使得任何人**无需 MCP Token、无需安装**，点开链接就能体验核心功能。

之所以要独立重写一份 JS 而不是调 Python：
GitHub Pages 只能托管静态文件，跑不了 Python。所以演示页是算法的
「镜像实现」，与 Python 版保持同一套评分公式。两者若有出入，以 Python 版为准。

用法：
    python tools/build_demo.py
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "docs")


def load(name: str) -> dict:
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>麦麦口味推荐官 · 在线演示</title>
<meta name="description" content="告诉它你想吃什么味，它从 67 款麦当劳餐品的口味图谱里帮你找。零 Token、打开即玩。">
<style>
  :root{
    --navy:#002060;
    --navy-2:#1b3b7a;
    --gold:#FFC000;
    --ink:#1a1a1a;
    --ink-2:#5a6270;
    --line:#e3e7ee;
    --bg:#ffffff;
    --bg-2:#f7f9fc;
    --ok:#1a7f4b;
    --warn:#b06a00;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{-webkit-text-size-adjust:100%}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Roboto,sans-serif;
    background:var(--bg);color:var(--ink);line-height:1.65;
    font-size:16px;
  }
  .wrap{max-width:760px;margin:0 auto;padding:0 18px 72px}

  /* ---------- Hero ---------- */
  header{
    background:var(--navy);color:#fff;
    padding:40px 18px 34px;margin-bottom:0;
  }
  header .inner{max-width:760px;margin:0 auto}
  h1{font-size:29px;font-weight:800;letter-spacing:.5px;line-height:1.3}
  h1 .accent{color:var(--gold)}
  .sub{margin-top:12px;font-size:16px;color:#cfd8ea;line-height:1.7}
  .meta{margin-top:18px;font-size:13px;color:#93a4c4}
  .tagbar{margin-top:16px;display:flex;flex-wrap:wrap;gap:8px}
  .tagbar span{
    font-size:13px;padding:4px 11px;border-radius:20px;
    background:rgba(255,192,0,.16);color:var(--gold);font-weight:600;
  }

  /* ---------- Section ---------- */
  section{margin-top:34px}
  h2{
    font-size:20px;font-weight:800;color:var(--navy);
    padding-left:12px;border-left:5px solid var(--gold);
    margin-bottom:6px;line-height:1.3;
  }
  .hint{font-size:14px;color:var(--ink-2);margin:10px 0 16px}

  /* ---------- Tabs ---------- */
  .tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
  .tab{
    font-size:15px;font-weight:600;padding:9px 17px;border-radius:9px;
    border:1.5px solid var(--line);background:#fff;color:var(--ink-2);
    cursor:pointer;transition:.15s;
  }
  .tab:hover{border-color:var(--navy-2);color:var(--navy)}
  .tab.on{background:var(--navy);border-color:var(--navy);color:#fff}

  /* ---------- Input ---------- */
  .row{display:flex;gap:10px;flex-wrap:wrap}
  input[type=text]{
    flex:1 1 240px;font-size:16px;padding:13px 15px;border-radius:9px;
    border:1.5px solid var(--line);outline:none;font-family:inherit;
    background:#fff;color:var(--ink);
  }
  input[type=text]:focus{border-color:var(--navy-2)}
  button.go{
    font-size:16px;font-weight:700;padding:13px 26px;border-radius:9px;
    border:none;background:var(--gold);color:var(--navy);cursor:pointer;
    transition:.15s;white-space:nowrap;
  }
  button.go:hover{filter:brightness(.94)}
  .chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
  .chip{
    font-size:14px;padding:6px 13px;border-radius:20px;cursor:pointer;
    background:var(--bg-2);border:1px solid var(--line);color:var(--ink-2);
    transition:.15s;
  }
  .chip:hover{background:#eef3fb;border-color:var(--navy-2);color:var(--navy)}

  /* ---------- Result ---------- */
  .profile{
    margin:18px 0 4px;padding:13px 16px;border-radius:9px;
    background:var(--bg-2);border-left:4px solid var(--gold);
    font-size:15px;
  }
  .profile b{color:var(--navy)}
  .card{
    border:1.5px solid var(--line);border-radius:12px;padding:17px 18px;
    margin-top:13px;background:#fff;transition:.15s;
  }
  .card:hover{border-color:#c8d3e6;box-shadow:0 3px 14px rgba(0,32,96,.07)}
  .card-top{display:flex;align-items:baseline;gap:11px;flex-wrap:wrap}
  .rank{
    font-size:13px;font-weight:800;color:var(--navy);background:var(--gold);
    width:23px;height:23px;border-radius:6px;display:inline-flex;
    align-items:center;justify-content:center;flex-shrink:0;
  }
  .name{font-size:18px;font-weight:800;color:var(--navy)}
  .cat{font-size:13px;color:var(--ink-2);background:var(--bg-2);
       padding:2px 9px;border-radius:5px}
  .score{margin-left:auto;font-size:16px;font-weight:800;color:var(--ok)}
  .bars{margin-top:13px;display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:7px 14px}
  .bar{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--ink-2)}
  .bar .lb{width:17px;flex-shrink:0;font-weight:600}
  .bar .track{flex:1;height:7px;background:#edf0f5;border-radius:4px;overflow:hidden}
  .bar .fill{height:100%;background:var(--navy-2);border-radius:4px}
  .tex{margin-top:12px;font-size:14px;color:var(--ink-2)}
  .why{margin-top:11px;font-size:14px;color:var(--ok)}
  .why div{padding-left:15px;position:relative}
  .why div:before{content:"→";position:absolute;left:0;color:var(--gold);font-weight:800}
  .ev{margin-top:11px;font-size:13px;color:var(--ink-2);background:var(--bg-2);
      padding:10px 13px;border-radius:7px;line-height:1.6}
  .ev b{color:var(--navy);font-weight:700}

  /* ---------- Combo ---------- */
  .combo{border:2px solid var(--navy);border-radius:12px;padding:19px;margin-top:16px;background:#fff}
  .combo-line{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
              border-bottom:1px dashed var(--line);font-size:15px}
  .combo-line:last-of-type{border-bottom:none}
  .combo-total{
    margin-top:14px;padding-top:14px;border-top:2px solid var(--navy);
    display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;
  }
  .combo-total .pay{font-size:25px;font-weight:800;color:var(--navy)}
  .combo-total .save{font-size:14px;color:var(--ok);font-weight:700}
  .nut{margin-top:12px;font-size:14px;color:var(--ink-2);
       background:var(--bg-2);padding:11px 14px;border-radius:8px;line-height:1.7}
  .nut .none{color:var(--warn);font-weight:700}

  /* ---------- Map / footer ---------- */
  details.map{margin-top:20px;border:1.5px solid var(--line);border-radius:11px;overflow:hidden}
  details.map summary{
    cursor:pointer;padding:14px 18px;font-weight:700;color:var(--navy);
    background:var(--bg-2);font-size:16px;
  }
  details.map .body{padding:6px 18px 18px}
  .mrow{display:flex;align-items:center;gap:12px;padding:1px 0;font-size:13.5px;
        color:var(--ink-2)}
  .mname{width:178px;flex-shrink:0;color:var(--ink);font-weight:600;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mfl{flex:1;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:var(--navy-2)}

  footer{
    margin-top:44px;padding-top:22px;border-top:1px solid var(--line);
    font-size:13px;color:var(--ink-2);line-height:1.8;
  }
  footer b{color:var(--navy)}
  footer a{color:var(--navy-2)}
  .err{color:#b3261e;font-size:15px;padding:14px;background:#fdf1f0;
       border-radius:9px;margin-top:14px}
  .empty{color:var(--ink-2);font-size:15px;padding:14px;background:var(--bg-2);
         border-radius:9px;margin-top:14px}
</style>
</head>
<body>
<header>
  <div class="inner">
    <h1>麦麦<span class="accent">口味</span>推荐官</h1>
    <p class="sub">告诉它你想吃什么味，它从 67 款麦当劳餐品的口味图谱里帮你找——
       再顺手把营养和优惠券都算好。</p>
    <div class="tagbar">
      <span>零 Token</span><span>打开即玩</span><span>67 款口味图谱</span><span>每条附配料依据</span>
    </div>
    <div class="meta">麦当劳程序员创意开发大赛参赛作品 · 非麦当劳官方产品</div>
  </div>
</header>

<div class="wrap">

  <section>
    <h2>开始找吃的</h2>
    <p class="hint">三种方式任选。<b>不知道想吃啥</b>就点下面的快捷标签。</p>
    <div class="tabs">
      <button class="tab on" data-mode="want">我想吃…</button>
      <button class="tab" data-mode="like">和这个类似</button>
      <button class="tab" data-mode="surprise">随便给我一个</button>
    </div>

    <div class="row">
      <input type="text" id="q" placeholder="例如：想吃甜的，要酥脆的，不要牛肉">
      <button class="go" id="run">推荐</button>
    </div>
    <div class="chips" id="chips"></div>
  </section>

  <section id="resultSec" style="display:none">
    <h2>推荐结果</h2>
    <div id="profile"></div>
    <div id="cards"></div>

    <div style="margin-top:26px">
      <h2>顺手配一餐</h2>
      <p class="hint">在上面推荐到的餐品里，帮你凑一份最省的一餐，并自动选最划算的券。</p>
      <div class="row">
        <input type="text" id="budget" placeholder="预算（元），例如 30" value="30">
        <button class="go" id="combo">配一餐</button>
      </div>
      <div id="comboOut"></div>
    </div>
  </section>

  <section>
    <h2>口味图谱（全部 67 款）</h2>
    <p class="hint">这是我给每款餐品标注的口味。每条都附配料依据，可逐条溯源。</p>
    <details class="map">
      <summary>展开查看 · 点击任意一行可拿它当推荐基准</summary>
      <div class="body" id="mapBody"></div>
    </details>
  </section>

  <footer>
    <p><b>数据说明（请务必阅读）</b></p>
    <p>· 口味标签为<b>基于公开配料信息的结构化推断</b>，非麦当劳官方数据，附配料依据可溯源；</p>
    <p>· 价格与营养为<b>离线演示占位数据</b>，未与官方核验，仅用于跑通算法；</p>
    <p>· 真实运行时，菜单/营养/价格/优惠券通过<b>麦当劳官方 MCP</b> 实时获取，
       并用官方 calculate-price 复核金额；</p>
    <p>· 输出仅供参考，<b>不构成医疗、营养或其他专业建议</b>；
       餐品信息、价格及供应状态以麦当劳官方渠道的实时结果为准。</p>
    <p style="margin-top:12px">
      源码与完整文档：<a href="https://github.com/yx165165/mcd-flavor-scout">github.com/yx165165/mcd-flavor-scout</a>
    </p>
  </footer>
</div>

<script>
/* ===================================================================
   数据（内嵌，与仓库 data/ 目录同源）
   =================================================================== */
const LIB = __LIB__;
const PRICES = __PRICES__;
const NUTRI = __NUTRI__;

const DIMS = ["sweet","salty","spicy","sour","bitter","umami"];
const DIM_CN = {sweet:"甜",salty:"咸",spicy:"辣",sour:"酸",bitter:"苦",umami:"鲜"};
const CAT_CN = {burger:"汉堡",side:"小食",drink:"饮品",dessert:"甜品",breakfast:"早餐"};
const TEMP_CN = {hot:"热",cold:"冰",room:"常温"};
const MAXS = 5;

/* 口味词表（与 Python 版 FLAVOR_KEYWORDS 对应） */
const FLAVOR_KW = {
  sweet:{甜:5,嗜甜:5,甜品:4,sweet:5,甜口:5},
  salty:{咸:5,重口:5,咸香:4,salty:4},
  spicy:{辣:5,香辣:4,麻辣:5,spicy:4,重辣:5},
  sour:{酸:5,开胃:3,sour:4},
  bitter:{苦:5,bitter:4},
  umami:{鲜:4,肉香:4,umami:4}
};
const TEXTURE_KW = {酥脆:"酥脆",脆:"酥脆",软:"软嫩",嫩:"软嫩",多汁:"多汁",爆汁:"多汁",
  绵密:"绵密",奶昔:"绵密",细腻:"绵密",爽脆:"爽脆",清脆:"爽脆",嚼劲:"有嚼劲"};
const MEAT_TERMS = {
  "牛肉":["牛","安格斯"],"猪肉":["猪柳","培根","烟肉","火腿"],
  "鱼":["鱼"],"咖啡":["咖啡","拿铁","卡布","摩卡","玛奇朵","美式"],"鸡肉":["鸡"]
};
const NEGS = ["不要","不吃","不想吃","别吃","忌","过敏"];
const TEMP_KW = {热:"hot",暖:"hot",冰:"cold",冷:"cold",凉:"cold",常温:"room"};
const CAT_INTENT = {
  burger:["汉堡","堡","巨无霸","双吉","安格斯"],
  side:["小食","配菜","薯条","鸡块","鸡翅","鸡排","派","玉米"],
  drink:["饮料","喝的","饮品","可乐","雪碧","芬达","咖啡","橙汁"],
  dessert:["甜点","甜品","冰淇淋","甜筒","圣代","麦旋风","蛋糕"],
  breakfast:["早餐","麦满分","油条","香饼"]
};

/* ===================================================================
   工具
   =================================================================== */
const norm = s => String(s||"").trim().toLowerCase().replace(/[\\s()（）　]/g,"");

function find(name){
  const k = norm(name);
  for (const it of LIB.items){
    if (norm(it.name)===k) return it;
    for (const a of (it.aliases||[])) if (norm(a)===k) return it;
  }
  return null;
}
function priceOf(name){
  const k = norm(name);
  for (const it of PRICES.items) if (norm(it.name)===k) return it.price;
  return null;
}
function nutriOf(name){
  const k = norm(name);
  for (const it of NUTRI.items) if (norm(it.name)===k) return it;
  return null;
}

/* ===================================================================
   画像构建
   =================================================================== */
function profileFromText(text){
  const p = {target:{}, weights:{}, texture:[], temp:null, exclude:[], source:"text"};
  DIMS.forEach(d => { p.target[d]=0; p.weights[d]=0.15; });

  for (const d in FLAVOR_KW){
    for (const kw in FLAVOR_KW[d]){
      if (text.includes(kw)){
        const i = text.indexOf(kw);
        const head = text.slice(Math.max(0,i-2), i);
        const neg = NEGS.some(n => head.endsWith(n));
        if (neg){ p.weights[d]=2.0; p.target[d]=0; p.exclude.push(DIM_CN[d]); }
        else { p.weights[d]=2.0; p.target[d]=Math.max(p.target[d], FLAVOR_KW[d][kw]); }
        break;
      }
    }
  }
  for (const kw in TEXTURE_KW){
    const t = TEXTURE_KW[kw];
    if (text.includes(kw) && !p.texture.includes(t)) p.texture.push(t);
  }
  for (const label in MEAT_TERMS){
    let hit=false;
    for (const tk of [label,...MEAT_TERMS[label]]){
      if (NEGS.some(n => text.includes(n+tk))){ hit=true; break; }
    }
    if (hit && !p.exclude.includes(label)) p.exclude.push(label);
  }
  for (const kw in TEMP_KW){ if (text.includes(kw)){ p.temp=TEMP_KW[kw]; break; } }
  if (["清淡","不腻","少油","轻食","健康"].some(w => text.includes(w))){
    DIMS.forEach(d => { p.target[d]=Math.min(p.target[d],2.0); p.weights[d]=1.5; });
  }
  return p;
}
function profileFromAnchor(name){
  const a = find(name);
  if (!a) return null;
  const p = {target:{}, weights:{}, texture:[...(a.texture||[])], temp:a.temp,
             exclude:[], source:"anchor", note:a.name};
  DIMS.forEach(d => { p.target[d]=a.flavor[d]||0; p.weights[d]=1.5; });
  return p;
}
function describe(p){
  if (p.source==="anchor") return "以「"+p.note+"」为口味基准";
  const want = p.source==="text"
    ? DIMS.filter(d => p.weights[d]>=1.5)
    : DIMS.slice();
  const parts=[];
  want.forEach(d=>{
    const t=p.target[d];
    if (t>=3.5) parts.push("偏"+DIM_CN[d]);
    else if (t<=1.5 && p.weights[d]>=1.5) parts.push("要少"+DIM_CN[d]);
  });
  if (p.texture.length) parts.push("爱"+p.texture.join("、"));
  if (p.temp) parts.push({hot:"要热的",cold:"要冰的",room:"常温"}[p.temp]);
  if (p.exclude.length) parts.push("排除"+p.exclude.join("、"));
  return parts.length?parts.join("、"):"无明显偏好（按均衡推荐）";
}

/* ===================================================================
   相似度与检索
   =================================================================== */
function excluded(it, p){
  const name = it.name;
  for (const kw of p.exclude){
    for (const d in DIM_CN){
      if (kw===DIM_CN[d] && (it.flavor[d]||0)>=3) return true;
    }
    if (kw==="牛肉" && (name.includes("牛")||name.includes("安格斯"))) return true;
    if (kw==="猪肉" && ["猪柳","培根","烟肉","火腿"].some(x=>name.includes(x))) return true;
    if (kw==="鱼" && name.includes("鱼")) return true;
    if (kw==="鸡肉" && (name.includes("鸡")||name.includes("翅"))) return true;
  }
  if (p.temp && it.temp!==p.temp) return true;
  return false;
}
function similarity(it, p){
  let num=0, den=0;
  DIMS.forEach(d=>{
    const w=p.weights[d]||0;
    if (w<=0.1) return;
    num += w*(1-Math.abs((p.target[d]||0)-(it.flavor[d]||0))/MAXS);
    den += w;
  });
  const base = den? num/den : 0;
  let tex=0; const reasons=[];
  (it.texture||[]).forEach(t=>{ if (p.texture.includes(t)){ tex+=0.05;
    reasons.push("口感「"+t+"」符合你的偏好"); } });
  tex = Math.min(tex,0.10);
  let tmp=0;
  if (p.temp && it.temp===p.temp){ tmp=0.05; reasons.push("温度符合"); }
  DIMS.slice().sort((a,b)=>{
    const sa=p.weights[a]*(1-Math.abs((p.target[a]||0)-(it.flavor[a]||0))/MAXS);
    const sb=p.weights[b]*(1-Math.abs((p.target[b]||0)-(it.flavor[b]||0))/MAXS);
    return sb-sa;
  }).slice(0,2).forEach(d=>{
    if ((p.weights[d]||0)>1.5 && Math.abs((p.target[d]||0)-(it.flavor[d]||0))<=1)
      reasons.unshift(DIM_CN[d]+"度对得上（你 "+(p.target[d]||0).toFixed(1)+
                      " / 它 "+(it.flavor[d]||0).toFixed(1)+"）");
  });
  return {score:Math.min(base*0.85+tex+tmp,1), reasons};
}
function recommend(p, topK, excludeNames){
  const ex = new Set((excludeNames||[]).map(norm));
  const out=[];
  for (const it of LIB.items){
    if (ex.has(norm(it.name))) continue;
    if (excluded(it,p)) continue;
    const r = similarity(it,p);
    out.push({item:it, score:r.score, reasons:r.reasons});
  }
  out.sort((a,b)=>b.score-a.score);
  return out.slice(0, topK||5);
}

/* ===================================================================
   组合 × 券 联合求解
   =================================================================== */
const CENTS = x => Math.round(x*100);
function couponOff(cp, names, sub){
  if (cp.kind==="threshold") return sub>=CENTS(cp.threshold)? Math.min(CENTS(cp.amount),sub):0;
  if (cp.kind==="item"){
    for (const n of names) if (n===cp.targetName)
      return Math.min(CENTS(cp.amount), CENTS(priceOf(n)||0));
    return 0;
  }
  if (cp.kind==="discount"){
    let off = Math.round(sub*(1-cp.rate));
    if (cp.maxOff!=null) off=Math.min(off,CENTS(cp.maxOff));
    return Math.max(off,0);
  }
  return 0;
}
function combos(pool, budget){
  const items = pool.filter(n=>priceOf(n)!=null);
  // 候选池本身覆盖几个品类：用于判断"要不要跨品类"
  const cats = new Set(items.map(n=>{ const i=find(n); return i?i.category:null; }).filter(Boolean));
  const needCross = cats.size >= 2;
  let best=null;
  const n = items.length;
  for (let m=1; m<(1<<n); m++){
    const names=[];
    for (let i=0;i<n;i++) if (m&(1<<i)) names.push(items[i]);
    // 一餐至少两样，最多三样 —— 只给一份鸡块不算一餐
    if (names.length<2 || names.length>3) continue;

    const sub = names.reduce((a,x)=>a+CENTS(priceOf(x)),0);
    let cp=null, bestOff=0;
    for (const c of PRICES.coupons){
      const o=couponOff(c,names,sub);
      if (o>bestOff){ bestOff=o; cp=c; }
    }
    const paid = Math.max(sub-bestOff,0);
    if (budget!=null && paid>CENTS(budget)) continue;

    // 若池子里有多种品类，组合就必须跨品类 ——
    // 否则"最省"会选出两份同类的小食凑数，不像一餐。
    if (needCross){
      const got = new Set(names.map(x=>{ const i=find(x); return i?i.category:null; }).filter(Boolean));
      if (got.size < 2) continue;
    }
    // 同分时优先"含主食"的组合
    const hasMain = names.some(x=>{ const i=find(x); return i && i.category==="burger"; });
    const score = paid - (hasMain?1:0);   // 微小偏好，不改变"更省优先"的大方向
    if (!best || score<best._s){
      best={names,sub,off:bestOff,paid,cp,_s:score};
    }
  }
  if (best) delete best._s;
  return best;
}

/* ===================================================================
   UI
   =================================================================== */
let MODE="want", LAST=null;
const $ = id => document.getElementById(id);

const CHIPS = {
  want:["想吃甜的，要酥脆的","想吃辣的","清淡一点，不要油炸","想吃甜的，不要牛肉","想来点带咖啡味的"],
  like:["巨无霸","麦辣鸡腿汉堡","中薯条","奥利奥麦旋风","芝士蛋糕"],
  surprise:["给我个惊喜","随便，要热的"]
};
function renderChips(){
  $("chips").innerHTML = CHIPS[MODE].map(c=>'<span class="chip">'+c+'</span>').join("");
  $("chips").querySelectorAll(".chip").forEach(el=>{
    el.onclick = ()=>{
      if (MODE==="surprise"){ $("q").value=""; doSurprise(); }
      else { $("q").value = el.textContent; run(); }
    };
  });
}
document.querySelectorAll(".tab").forEach(t=>{
  t.onclick = ()=>{
    document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
    t.classList.add("on");
    MODE = t.dataset.mode;
    $("q").placeholder = MODE==="like" ? "输入一个你爱吃的餐品名，例如：巨无霸"
                       : MODE==="surprise" ? "点下面的标签，或直接按「推荐」"
                       : "例如：想吃甜的，要酥脆的，不要牛肉";
    $("q").value="";
    renderChips();
    $("resultSec").style.display="none";
  };
});

const catTag = it => (CAT_CN[it.category]||it.category)+"·"+(TEMP_CN[it.temp]||it.temp);

function cardHTML(r,i){
  const it=r.item;
  const bars = DIMS.filter(d=>(it.flavor[d]||0)>0).map(d=>
    '<div class="bar"><span class="lb">'+DIM_CN[d]+'</span>'+
    '<span class="track"><span class="fill" style="width:'+((it.flavor[d]/5)*100)+'%"></span></span>'+
    '<span>'+it.flavor[d]+'</span></div>').join("");
  const why = r.reasons.slice(0,3).map(x=>"<div>"+x+"</div>").join("");
  return '<div class="card">'+
    '<div class="card-top"><span class="rank">'+(i+1)+'</span>'+
    '<span class="name">'+it.name+'</span>'+
    '<span class="cat">'+catTag(it)+'</span>'+
    '<span class="score">'+Math.round(r.score*100)+'%</span></div>'+
    '<div class="bars">'+bars+'</div>'+
    (it.texture&&it.texture.length?'<div class="tex">口感：'+it.texture.join("、")+'</div>':"")+
    (why?'<div class="why">'+why+'</div>':"")+
    '<div class="ev"><b>配料依据：</b>'+it.evidence+'</div>'+
  '</div>';
}

function show(p, title, excludeNames){
  const recs = recommend(p, 5, excludeNames);
  LAST = p;
  $("resultSec").style.display="block";
  $("profile").innerHTML = '<div class="profile">'+title+'<br><b>你的口味画像：</b>'+describe(p)+'</div>';
  $("cards").innerHTML = recs.length
    ? recs.map(cardHTML).join("")
    : '<div class="empty">没有符合的餐品。可能排除条件过严（例如同时要求「要冰的」和「要热的」），放宽试试。</div>';
  $("comboOut").innerHTML="";
  $("resultSec").scrollIntoView({behavior:"smooth",block:"start"});
}

function run(){
  const v = $("q").value.trim();
  if (MODE==="like"){
    if (!v){ alert("请输入一个餐品名，例如：巨无霸"); return; }
    const a = find(v);
    if (!a){ alert("口味图谱里没有「"+v+"」\\n可以在下方【口味图谱】里找一个存在的名字。"); return; }
    show(profileFromAnchor(a.name), '找相似的 · 基准是「'+a.name+'」', [a.name]);
  } else if (MODE==="surprise"){
    doSurprise();
  } else {
    if (!v){ alert("说一句你想吃什么味，例如：想吃甜的，要酥脆的"); return; }
    show(profileFromText(v), '按口味描述 · 原文「'+v+'」');
  }
}
function doSurprise(){
  const pool = ["想吃甜的","想吃辣的","想清淡点","想来点咸香的","想吃冰的甜品","想吃酥脆的"];
  const t = pool[Math.floor(Math.random()*pool.length)];
  $("q").value = t;
  show(profileFromText(t), "随便给你一个 · 抽到「"+t+"」");
}
$("run").onclick = run;
$("q").addEventListener("keydown", e=>{ if(e.key==="Enter") run(); });

$("combo").onclick = ()=>{
  if (!LAST){ alert("先在上面做一次推荐"); return; }
  const b = parseFloat($("budget").value);
  const pool = recommend(LAST, 8).map(r=>r.item.name);
  const best = combos(pool, isNaN(b)?null:b);
  if (!best){
    $("comboOut").innerHTML = '<div class="empty">这个预算下没凑出组合。'+
      '把预算调高几块试试。</div>';
    return;
  }
  let lines="";
  best.names.forEach(n=>{ lines += '<div class="combo-line"><span>'+n+
    '</span><span>¥'+(priceOf(n)).toFixed(2)+'</span></div>'; });

  let nut="", missing=[];
  const tot={calories:0,protein:0,fat:0,carbs:0,sodium:0};
  const has={calories:false,protein:false,fat:false,carbs:false,sodium:false};
  best.names.forEach(n=>{
    const nu = nutriOf(n);
    if (!nu){ missing.push(n); return; }
    ["calories","protein","fat","carbs","sodium"].forEach(k=>{
      if (nu[k]==null) return;
      tot[k]+=nu[k]; has[k]=true;
    });
  });
  const f=(k,dec)=> has[k]? tot[k].toFixed(dec) : '<span class="none">无</span>';
  nut = "热量 "+f("calories",0)+" kcal ｜ 蛋白质 "+f("protein",1)+" g ｜ 脂肪 "+
        f("fat",1)+" g ｜ 碳水 "+f("carbs",1)+" g ｜ 钠 "+f("sodium",0)+" mg";
  if (missing.length) nut += '<br><span class="none">⚠️ 以下餐品无营养数据（计为「无」，未计入总和）：'+
    missing.join("、")+'</span>';

  $("comboOut").innerHTML = '<div class="combo">'+lines+
    '<div class="combo-total"><div>实付 <span class="pay">¥'+(
      best.paid/100).toFixed(2)+'</span></div>'+
    '<div class="save">原价 ¥'+(best.sub/100).toFixed(2)+
      (best.off>0? ' ｜ 用「'+best.cp.name+'」省 ¥'+(best.off/100).toFixed(2) : ' ｜ 无可用券')+
    '</div></div>'+
    '<div class="nut">'+nut+'</div></div>';
};

/* 图谱 */
(function(){
  const order=["burger","side","drink","dessert","breakfast"];
  let h="";
  order.forEach(c=>{
    const g = LIB.items.filter(i=>i.category===c);
    if (!g.length) return;
    h += '<div style="margin:16px 0 7px;font-weight:800;color:#002060;font-size:15px">'+
         (CAT_CN[c]||c)+'（'+g.length+' 款）</div>';
    g.forEach(it=>{
      const fl = DIMS.filter(d=>(it.flavor[d]||0)>0)
        .map(d=>DIM_CN[d]+it.flavor[d]).join(" ");
      h += '<div class="mrow"><span class="mname" title="'+it.name+'">'+it.name+
           '</span><span class="mfl">'+(fl||"—")+'</span></div>';
    });
  });
  $("mapBody").innerHTML = h;
  $("mapBody").querySelectorAll(".mname").forEach(el=>{
    el.style.cursor="pointer";
    el.onclick = ()=>{
      document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));
      document.querySelector('.tab[data-mode="like"]').classList.add("on");
      MODE="like"; $("q").value=el.textContent; renderChips(); run();
    };
  });
})();

renderChips();
/* 首次进入自动跑一个示例，避免空白页 */
$("q").value = "想吃甜的，要酥脆的，不要牛肉";
run();
</script>
</body>
</html>
"""


def main() -> int:
    lib = load("flavor_tags.json")
    prices = load("prices_demo.json")
    nutri = load("nutrition_demo.json")

    html = (HTML_TEMPLATE
            .replace("__LIB__", json.dumps(lib, ensure_ascii=False, separators=(",", ":")))
            .replace("__PRICES__", json.dumps(prices, ensure_ascii=False, separators=(",", ":")))
            .replace("__NUTRI__", json.dumps(nutri, ensure_ascii=False, separators=(",", ":"))))

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"已生成 {out}  ({len(html):,} 字符, {len(html.encode('utf-8')):,} 字节)")
    print(f"  口味图谱 {len(lib.get('items', []))} 款")
    print(f"  价格 {len(prices.get('items', []))} 条 / 优惠券 {len(prices.get('coupons', []))} 张")
    print(f"  营养 {len(nutri.get('items', []))} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
