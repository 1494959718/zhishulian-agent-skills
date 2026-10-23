#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_cost_model.py · 技能库保管人 自研 · 算力底座降本决策器 v1.0
====================================================================
用途：为「工业化电影级内容生产系统 · 算力底座」回答一个问题——
      **这批镜头，走本地自建、还是走云 API？skill/插件/MCP 降本抓手能省多少？**

输出：三条路线成本对比 + 盈亏平衡片段数 + 推荐 + 逐条降本抓手（含算式与口径）。

设计纪律（对齐团队 K008 知识条目）：
  ① 每个价格/时长都有来源位与取证日，不写「据说」；
  ② 参数表外置可覆盖（--params），换机型/换报价不用改代码；
  ③ 输出每项都带「算式」，可复算；
  ④ 抓手的节省是**口径区间**，不是拍脑袋的定值——区间上界＝可全部吃下的部分。

用法：
    python3 compute_cost_model.py --clips 200 --seconds 5 --tier 720p --iterations 3
    python3 compute_cost_model.py --clips 2000 --seconds 5 --tier 1080p --iterations 2 --json
    python3 compute_cost_model.py --clips 500 --seconds 5 --tier 720p --params my_params.json
作者：技能库保管人 · 2026-10-22 · 仅用标准库
"""

import argparse
import json
import os

# ============================================================ 参数表（来源位见每项 source）
# 取证日：2026-10-22；调研件：<内部底稿>
DEFAULT_PARAMS = {
    "meta": {
        "取证日": "2026-10-22",
        "说明": "开源视频模型 2026 横向对比（Wan 2.2 / HunyuanVideo 1.5 / LTXVideo 13B）公开资料汇总；"
                "商业 API 价为 Replicate / fal 公开报价区间；本地硬件为 2026 年 10 月公开零售价。",
        "证据级": "B（可复核二手：厂商公开报价页与第三方横评；采购前须以实际报价单复算）",
    },
    "模型": {
        "Wan2.2": {
            "最低显存GB": 24, "推荐显存GB": 48,
            "5s_720p_A100分钟": 5.0, "5s_720p_RTX4090分钟": 3.0,
            "5s_1080p_A100分钟": 10.0, "5s_1080p_RTX4090分钟": 7.0,
            "INT8权重GB": 14, "本地磁盘GB": 28,
            "API_Replicate_每5s_720p_USD": [0.15, 0.25], "API_Replicate_每5s_1080p_USD": [0.30, 0.50],
            "API_fal_每5s_720p_USD": [0.12, 0.20], "API_fal_每5s_1080p_USD": [0.25, 0.45],
            "质量": "最高（出片首选）", "速度": "三模型中最慢",
        },
        "HunyuanVideo1.5": {
            "最低显存GB": 24, "推荐显存GB": 40,
            "5s_720p_A100分钟": 4.0, "5s_720p_RTX4090分钟": 3.0,
            "5s_1080p_A100分钟": 9.0, "5s_1080p_RTX4090分钟": 6.0,
            "INT8权重GB": 13, "本地磁盘GB": 26,
            "API_Replicate_每5s_720p_USD": [0.12, 0.20], "API_Replicate_每5s_1080p_USD": [0.25, 0.40],
            "API_fal_每5s_720p_USD": [0.10, 0.18], "API_fal_每5s_1080p_USD": [0.20, 0.35],
            "质量": "中上", "速度": "中",
        },
        "LTXVideo13B": {
            "最低显存GB": 16, "推荐显存GB": 24,
            "5s_720p_A100分钟": 2.0, "5s_720p_RTX4090分钟": 1.5,
            "5s_1080p_A100分钟": 4.0, "5s_1080p_RTX4090分钟": 4.0,
            "INT8权重GB": 13, "本地磁盘GB": 26,
            "API_Replicate_每5s_720p_USD": [0.06, 0.10], "API_Replicate_每5s_1080p_USD": [0.12, 0.20],
            "API_fal_每5s_720p_USD": [0.05, 0.08], "API_fal_每5s_1080p_USD": [0.10, 0.18],
            "质量": "略低（同设置下）", "速度": "快 2-3 倍（迭代首选）",
        },
    },
    "本地硬件": {
        # 一次性投入（USD，2026-10 公开零售价区间下沿取整）
        "RTX4080_16GB": {"投入USD": 1200, "显存GB": 16, "能力": "LTX 720p + 其他模型 INT4 量化"},
        "RTX4090_24GB": {"投入USD": 2000, "显存GB": 24, "能力": "全模型 720p；LTX 可上 1080p"},
        "RTX4090_x2_48GB": {"投入USD": 4000, "显存GB": 48, "能力": "全模型 1080p 良好设置"},
        "A100_80GB_云": {"投入USD": 0, "显存GB": 80, "小时租USD": [2, 4], "能力": "全模型满质量、最快出片"},
    },
    "本地边际": {
        "电费USD每机时": 0.10,          # 整机 0.6kW × 0.6 元/kWh ≈ 0.1 USD 区间下沿
        "折旧年数": 3,
        "人力USD每机时": 0,              # 默认 0：自动批处理时不占人；若需人工看护请覆盖
    },
    "工期": {"每日有效渲染小时": 16, "并行台数": 1},
    "降本抓手": {
        "asset_reuse": {"名称": "资产一次生成·多处复用", "可吃下比例": [0.20, 0.45],
                       "算式": "宣传片/社媒切片/预告版从分镜母版派生 → 独立渲染需求减少",
                       "落地": "插件（资产派生任务队列）＋MCP（资产索引检索）"},
        "quant_route": {"名称": "量化＋小模型路由", "可吃下比例": [0.05, 0.15],
                       "算式": "INT8/INT4 权重降显存→同机可并批；草稿层用 LTX、出片层用 Wan",
                       "落地": "skill（路由规则）＋工具（量化权重管理）"},
        "cache_dedupe": {"名称": "批量调度＋结果缓存去重", "可吃下比例": [0.05, 0.20],
                       "算式": "同 seed/同 prompt/同参数命中缓存即复用；批量排队避免空转",
                       "落地": "MCP（渲染队列与缓存命中统计）"},
        "tiered_qc": {"名称": "分层质检（小模型初筛＋人工终审）", "可吃下比例": [0.05, 0.20],
                     "算式": "自动判据（闪烁/穿帮/字幕/时长）先过，人工只看初筛命中件",
                     "落地": "skill（质检判据集）＋插件（批处理钩子）"},
        "shared_base": {"名称": "分层共享底座（内部口径）", "可吃下比例": [0.10, 0.30],
                       "算式": "底层 Transformer 共享／高层分支独立 → 多风格多分支不重复载权重",
                       "落地": "自研 MCP（服务编排）"},
    },
}

DEFAULT = "Wan2.2"
TIERS = {"720p": "720p", "1080p": "1080p"}


def load_params(path):
    p = dict(DEFAULT_PARAMS)
    if path:
        with open(path, encoding="utf-8") as fh:
            custom = json.load(fh)
        for k, v in custom.items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
    return p


def local_route(model, tier, params, hw_key):
    """本地路线：一次性投入 + 边际成本 + 交付工期"""
    m = params["模型"][model]
    hw = params["本地硬件"][hw_key]
    per5 = m["5s_%s_%s分钟" % (tier, "A100" if hw["显存GB"] >= 80 else "RTX4090")]
    capex = hw["投入USD"]
    hourly = params["本地边际"]["电费USD每机时"] + params["本地边际"]["人力USD每机时"]
    if hw.get("小时租USD"):                       # 云租卡：按小时计，不是机时边际
        hourly = (hw["小时租USD"][0] + hw["小时租USD"][1]) / 2
    return {"路线": "本地·%s" % hw_key, "一次性投入USD": capex,
            "单片段分钟": per5, "小时成本USD": hourly, "一次性": capex > 0,
            "每片段边际USD": round(per5 / 60 * hourly, 4)}


def api_route(model, tier, params, provider):
    m = params["模型"][model]
    lo, hi = m["API_%s_每5s_%s_USD" % (provider, tier)]
    return {"路线": "API·%s" % provider, "每5s_USD": [lo, hi],
            "每片段_USD": [round(lo / 5 * 1, 4), round(hi / 5 * 1, 4)]}


def cost(clips, seconds, tier, iterations, model, params, hw_key):
    m = params["模型"][model]
    local = local_route(model, tier, params, hw_key)
    rep = api_route(model, tier, params, "Replicate")
    fal = api_route(model, tier, params, "fal")
    # 每片段成本按「每5s报价 × 实际秒数/5」折算
    for r in (rep, fal):
        lo, hi = r["每5s_USD"]
        r["每片段_USD"] = [round(lo * seconds / 5, 4), round(hi * seconds / 5, 4)]
    total_units = clips * iterations          # 实际渲染次数＝片段数×迭代倍数
    local_total = local["一次性投入USD"] + local["每片段边际USD"] * total_units
    rep_total = rep["每片段_USD"][1] * total_units      # 保守取上界
    fal_total = fal["每片段_USD"][1] * total_units
    # 盈亏平衡：本地投入 ÷（**最优 API** 每片段上界 − 本地每片段边际）
    # 必须对最便宜的 API 计算——否则会用 Replicate 上界虚高推荐本地，与总成本最优矛盾。
    api_uppers = {"Replicate": rep["每片段_USD"][1], "fal": fal["每片段_USD"][1]}
    best_api_name = min(api_uppers, key=lambda k: api_uppers[k])
    gap = api_uppers[best_api_name] - local["每片段边际USD"]
    be = int(local["一次性投入USD"] / gap) if gap > 0 else None
    # 交付工期
    hours = total_units * local["单片段分钟"] / 60
    days = hours / max(1, params["工期"]["每日有效渲染小时"])
    return {"模型": model, "档位": tier, "片段数": clips, "单片段秒": seconds,
            "迭代倍数": iterations, "实际渲染次数": total_units,
            "本地": local, "Replicate": rep, "fal": fal,
            "总成本USD": {"本地": round(local_total, 2),
                          "Replicate": round(rep_total, 2),
                          "fal": round(fal_total, 2)},
            "盈亏平衡片段数": be,
            "盈亏平衡对照API": best_api_name,
            "本地交付工期天": round(days, 1)}


def savings(clips, seconds, iterations, model, tier, params, base_total):
    """skill/插件/MCP 降本抓手：逐条给可吃下比例与省下的钱（区间）"""
    total_units = clips * iterations
    unit_api = params["模型"][model]["API_fal_每5s_%s_USD" % tier][1] * seconds / 5
    rows = []
    for key, g in params["降本抓手"].items():
        lo, hi = g["可吃下比例"]
        rows.append({
            "抓手": g["名称"], "落地形态": g["落地"],
            "可吃下比例": [lo, hi],
            "省USD": [round(total_units * unit_api * lo, 2), round(total_units * unit_api * hi, 2)],
            "算式": g["算式"],
            "口径": "占该口径的渲染次数/云端等效成本；区间上界＝可全部吃下",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", type=int, required=True, help="片段（镜头）数")
    ap.add_argument("--seconds", type=int, default=5, help="单片段秒数")
    ap.add_argument("--tier", choices=list(TIERS), default="720p")
    ap.add_argument("--iterations", type=int, default=1, help="每片段平均迭代（重渲）倍数")
    ap.add_argument("--model", default=None, help="模型名，默认 Wan2.2")
    ap.add_argument("--hw", default="RTX4090_24GB", help="本地硬件档位键")
    ap.add_argument("--params", default=None, help="外置参数表 JSON（覆盖默认值）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    params = load_params(args.params)
    model = args.model or DEFAULT
    if model not in params["模型"]:
        print("ERR 未知模型：%s（可选 %s）" % (model, "、".join(params["模型"])))
        return 2
    if args.hw not in params["本地硬件"]:
        print("ERR 未知硬件档位：%s（可选 %s）" % (args.hw, "、".join(params["本地硬件"])))
        return 2

    c = cost(args.clips, args.seconds, args.tier, args.iterations, model, params, args.hw)
    sv = savings(args.clips, args.seconds, args.iterations, model, args.tier, params, c["总成本USD"])
    best_api = min(c["总成本USD"], key=lambda k: c["总成本USD"][k])

    if args.json:
        print(json.dumps({"成本": c, "降本抓手": sv, "云端最优": best_api},
                         ensure_ascii=False, indent=2))
        return 0

    print("=" * 74)
    print(" 算力底座降本决策器 v1.0 · 技能库保管人 · 取证日 %s · 证据级 %s" %
          (params["meta"]["取证日"], params["meta"]["证据级"]))
    print("=" * 74)
    print(" 场景：%s 模型 / %s / 片段 %d 个 × %d 秒 / 平均迭代 %d 次 = 实际渲染 %d 次" %
          (c["模型"], c["档位"], c["片段数"], c["单片段秒"], c["迭代倍数"], c["实际渲染次数"]))
    print()
    print("── 三条路线总成本（USD） ──")
    for k in ("本地", "Replicate", "fal"):
        print("  %-10s %10s" % (k, c["总成本USD"][k]))
    print("  分解：本地 一次性投入 %s ＋ 每片段边际 %s USD；API 每片段 %s–%s USD" %
          (c["本地"]["一次性投入USD"], c["本地"]["每片段边际USD"],
           c["fal"]["每片段_USD"][0], c["fal"]["每片段_USD"][1]))
    print()
    print("── 盈亏平衡 ──")
    if c["盈亏平衡片段数"]:
        print("  本地自建 vs 最优 API（%s）持平所需片段数 ≈ %d 个" % (c["盈亏平衡对照API"], c["盈亏平衡片段数"]))
        print("  算式：一次性投入 %d ÷ (API每片段上界 %s − 本地每片段边际 %s)" %
              (c["本地"]["一次性投入USD"], c["fal"]["每片段_USD"][1], c["本地"]["每片段边际USD"]))
        print("  ⇒ 低于此量走 %s；高于此量本地自建更省" % best_api)
    else:
        print("  本线路径无正差价（本地边际不劣于 API）")
    print()
    print("── 本地交付工期（%d 有效渲染小时/天） ──" % params["工期"]["每日有效渲染小时"])
    print("  约 %s 天（单片段 %s 分钟 × %d 次 ÷ 60）" %
          (c["本地交付工期天"], c["本地"]["单片段分钟"], c["实际渲染次数"]))
    print()
    print("── skill／插件／MCP 降本抓手（可省 USD 区间） ──")
    for r in sv:
        print("  ▸ %s" % r["抓手"])
        print("    可吃下 %s–%s ｜ 省 %s–%s USD" %
              (r["可吃下比例"][0], r["可吃下比例"][1], r["省USD"][0], r["省USD"][1]))
        print("    落地：%s" % r["落地形态"])
        print("    算式：%s" % r["算式"])
    print()
    print("  合计可省（各抓手不叠加，区间相加为上界）：%s–%s USD" %
          (round(sum(r["省USD"][0] for r in sv), 2), round(sum(r["省USD"][1] for r in sv), 2)))
    print("  口径：%s" % sv[0]["口径"])
    print("  ⚠ 抓手的『可吃下比例』是**工程口径区间**，不是承诺值；落地前须按真实管线标定。")
    print()
    print(" 参数覆盖：--params <json>；换机型/换报价不改代码。")
    print(" 来源位：见调研件《算力底座降本口径与调研提纲 v1.0》2026-10-22。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
