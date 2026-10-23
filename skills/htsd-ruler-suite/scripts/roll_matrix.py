#!/usr/bin/env python3
# roll_matrix.py · 技能库保管人 署名实写 · #16 training-camp-exam
# 功能：应得矩阵（人头×场次）+ 空格清单（§四 逐人点验，禁以扫盘代盯人）
# 入参：
#   --roster <名单md路径>     名单列 9 名学员（含别名/箱别名）
#   --papers <答卷目录>       答卷目录（递归扫描 .md + .md5）
#   --out <输出矩阵md路径>    应得矩阵 + 空格清单输出
# 出参：stdout JSON + 落盘 md
# 用法：python3 roll_matrix.py --roster 9人名单.md --papers ./答卷 --out ./应得矩阵.md

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="训练营考核 应得矩阵生成")
    ap.add_argument("--roster", required=True, help="9 人名单 md 路径（含学员 + 应考场次）")
    ap.add_argument("--papers", required=True, help="答卷目录绝对路径")
    ap.add_argument("--out", required=True, help="应得矩阵 md 输出路径")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    roster_path = Path(args.roster)
    papers_path = Path(args.papers)
    out_path = Path(args.out)

    if not roster_path.is_file():
        sys.exit(f"FAIL: 名单不存在 {roster_path}")
    if not papers_path.is_dir():
        sys.exit(f"FAIL: 答卷目录不存在 {papers_path}")

    # 1. 解析名单（人头=去重 + 别名合并）
    roster_text = roster_path.read_text(encoding="utf-8")
    # 简化解析：每行 "姓名\t场次1\t场次2"
    roster = {}  # canonical_name -> [场次列表]
    name_aliases = {}  # alias -> canonical
    for line in roster_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s+|\t+", line)
        if len(parts) < 2:
            continue
        canonical = parts[0].strip()
        sessions = [p.strip() for p in parts[1:] if p.strip()]
        roster[canonical] = sessions
        # 别名映射（例：技能库保管人(成员B) → base 名也注册）
        name_aliases[canonical] = canonical
        base = canonical.split("(")[0].strip()
        if base and base != canonical:
            name_aliases[base] = canonical
        for alias in re.findall(r"\(([^)]+)\)", canonical):
            name_aliases[alias] = canonical

    # 2. 扫描答卷目录（仅顶层 .md）
    papers = {}  # canonical -> {场次 -> md文件名}
    for md_file in sorted(papers_path.glob("*.md")):
        # 答卷_技能库保管人_进阶_20260914.md 或 答卷_成员D_C区双件专卷_20260914.md
        m = re.match(r"答卷_(\S+?)_(进阶|甲批|C区双件(?:专卷)?)_(\d{8})\.md$", md_file.name)
        if not m:
            continue
        name_raw = m.group(1)
        session_raw = m.group(2)
        # 归一化场次名（C区双件专卷 → C区双件）
        session = "C区双件" if session_raw.startswith("C区双件") else session_raw
        canonical = name_aliases.get(name_raw, name_raw)
        papers.setdefault(canonical, {})[session] = md_file.name

    # 3. 生成应得矩阵 + 空格清单
    matrix_lines = [
        f"# 应得矩阵 · #16 training-camp-exam · 时点 {ts}",
        "",
        f"**人头**：{len(roster)} 人（按人不按箱，别名合并）",
        f"**答卷目录**：`{papers_path}`",
        "",
        "## 应得矩阵（人头 × 场次）",
        "",
        "| 人头 | 应考场次 | 答卷 .md | 侧车 .md5 | 状态 |",
        "|:--|:--|:--|:--|:--|",
    ]

    gap_count = 0
    ok_count = 0
    noside_count = 0
    miss_count = 0
    gap_lines = ["", "## 空格清单（逐人点名催交）", "", "| 人头 | 缺考场次 | 状态 |", "|:--|:--|:--|"]

    for name, sessions in roster.items():
        for session in sessions:
            md_name = papers.get(name, {}).get(session, "—")
            md5_name = md_name + ".md5" if md_name != "—" else "—"
            md5_path = papers_path / md5_name if md5_name != "—" else None
            md5_status = "✅" if md5_path and md5_path.is_file() else ("❌" if md5_name != "—" else "—")

            if md_name == "—":
                status = "❌ 缺卷"
                gap_count += 1
                miss_count += 1
                gap_lines.append(f"| {name} | {session} | 缺卷催交 |")
            elif md5_status == "❌":
                status = "⚠️ 无侧车"
                gap_count += 1
                noside_count += 1
                gap_lines.append(f"| {name} | {session} | 侧车缺 |")
            else:
                status = "✅ 已交齐"
                ok_count += 1

            matrix_lines.append(f"| {name} | {session} | {md_name} | {md5_name} | {status} |")

    matrix_lines.append("")
    matrix_lines.append(f"## 总评")
    matrix_lines.append(f"- 应得总数：{sum(len(s) for s in roster.values())} 卷")
    matrix_lines.append(f"- 已交齐：{ok_count} 卷")
    matrix_lines.append(f"- 缺侧车：{noside_count} 卷")
    matrix_lines.append(f"- 缺卷：{miss_count} 卷")
    matrix_lines.append(f"- 校验：{ok_count} ＋ {noside_count} ＋ {miss_count} = {ok_count + noside_count + miss_count} 卷 ＝ 应得 {sum(len(x) for x in roster.values())} 卷")
    matrix_lines.append(f"- 时点：{ts}")

    out_path.write_text("\n".join(matrix_lines), encoding="utf-8")

    result = {
        "ts": ts,
        "roster_count": len(roster),
        "expected": sum(len(s) for s in roster.values()),
        "delivered": ok_count,
        "missing_sidecar": noside_count,
        "missing_paper": miss_count,
        "gap_count": gap_count,
        "out": str(out_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if gap_count == 0 else 1)  # N1改：有缺卷/缺侧车即非0，可被自动闸捕获


if __name__ == "__main__":
    main()