#!/usr/bin/env python3
# box_matrix.py  v0.1 骨架 · 成员C 署名实写 · #16 training-camp-exam
# 功能：SKILL.md §四「件 × 箱勾验表（逐格 md5）」自动化防线
#       对应 9.14 三起投箱事故：甲批漏 1 / 教材零投 / C 区只投全员
# 入参：
#   --papers  <件正本文件 或 目录>     目录时取顶层 *.md（排除 .md5 / .bak）
#   --boxes   <投递箱根目录>
#   --targets "给全员,给成员F,..."      应投箱清单（声明的投递范围）；缺一格即告警
#   --out     <矩阵 md 输出路径>
#   --alias   "给成员B=给技能库保管人"        别名箱合并（可重复；§四「计数按人不按箱」）
#   --show-all                        非应投箱也列出（信息列，不计入空格）
# 出参：stdout JSON + 落盘 md；exit 0 = 应投格全 ✅ / 1 = 有空格或异常
#
# 格符号： ✅ 正卷 md5 全等＋侧车全等 ｜ 🟡 正卷全等但侧车缺/不等
#          ⚠️ 正卷在但 md5 不等      ｜ ❌ 缺件            ｜ — 非应投箱

import argparse, json, sys
from datetime import datetime
from pathlib import Path


def md5q(p):
    import hashlib
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="件 × 箱勾验表（#16 §四）")
    ap.add_argument("--papers", required=True, help="件正本文件或目录")
    ap.add_argument("--boxes", required=True, help="投递箱根目录")
    ap.add_argument("--targets", required=True, help="应投箱清单，逗号分隔")
    ap.add_argument("--out", required=True, help="矩阵 md 输出路径")
    ap.add_argument("--alias", action="append", default=[], help="别名箱合并 主箱=别名箱")
    ap.add_argument("--show-all", action="store_true", help="列出非应投箱（信息列）")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    boxes_root = Path(args.boxes)
    out_path = Path(args.out)
    if not boxes_root.is_dir():
        sys.exit("FAIL: 投递箱根目录不存在 " + str(boxes_root))

    pw = Path(args.papers)
    if pw.is_file():
        papers = [pw]
        papers_dir = pw.parent
    elif pw.is_dir():
        papers = sorted([p for p in pw.glob("*.md")
                         if not p.name.endswith(".md5") and not p.name.endswith(".bak")])
        papers_dir = pw
    else:
        sys.exit("FAIL: --papers 不存在 " + str(pw))
    if not papers:
        sys.exit("FAIL: --papers 未取到任何件")

    alias = {}
    for spec in args.alias:
        if "=" in spec:
            primary, aliasbox = spec.split("=", 1)
            alias[aliasbox.strip()] = primary.strip()

    def canon(b):
        return alias.get(b, b)

    targets = [canon(t.strip()) for t in args.targets.split(",") if t.strip()]
    onbox = sorted([d.name for d in boxes_root.iterdir()
                    if d.is_dir() and d.name.startswith("给")])
    cols = []
    for b in onbox:
        c = canon(b)
        if c not in cols:
            cols.append(c)
    if not args.show_all:
        cols = [c for c in cols if c in targets]
    else:
        cols = [c for c in targets if c in cols] + [c for c in cols if c not in targets]

    def group_dirs(c):
        return [d for d in onbox if canon(d) == c]

    rows, gaps, mism = [], [], []
    for p in papers:
        want = md5q(p)
        row = {"paper": p.name, "md5": want, "cells": {}}
        for c in cols:
            if c not in targets:
                row["cells"][c] = ("—", "")
                continue
            hit, bad, noside = None, None, []
            for d in group_dirs(c):
                # 10.18 实跑修正（P0）：投递箱真实结构是「箱名/日期/件名」，
                # 原实现只查 boxes_root/d/p.name 这一层，实测 16 份真件全落日期层、
                # 挂箱根 0 份 → 脚本会误报「14/17 空格」即凭空指控同事漏投。
                # 改为 rglob 递归命中（同箱同日多副本取首个），消除误报面。
                cands = [q for q in (boxes_root / d).rglob(p.name) if q.is_file()]
                if not cands:
                    continue
                f = cands[0]
                if md5q(f) == want:
                    side = Path(str(f) + ".md5")
                    ok = side.is_file() and md5q(side) == md5q(Path(str(p) + ".md5")) if Path(str(p) + ".md5").is_file() else False
                    if ok:
                        hit = d
                    else:
                        hit, noside = d, [d]
                else:
                    bad = d
            if hit:
                row["cells"][c] = ("🟡" if noside else "✅", hit)
                if noside:
                    gaps.append("%s → %s（侧车缺/不等）" % (p.name, c))
            elif bad:
                row["cells"][c] = ("⚠️", bad)
                mism.append("%s → %s（md5 不等）" % (p.name, c))
            else:
                row["cells"][c] = ("❌", "")
                gaps.append("%s → %s（缺件）" % (p.name, c))
        rows.append(row)

    L = ["# 件 × 箱 勾验表 · #16 training-camp-exam §四", "",
         "> box_matrix.py v0.1（成员C）｜时点 **%s**｜分发布：`%s`" % (ts, boxes_root),
         "> 规则：**应投箱逐格 md5，无空格才准发布**；别名箱已合并（§四 计数按人不按箱）。", "",
         "| 件（md5 前 8） | " + " | ".join(cols) + " |",
         "|:--|" + "|".join([":--:"] * len(cols)) + "|"]
    for r in rows:
        cells = []
        for c in cols:
            sym, src = r["cells"][c]
            cells.append(sym if not src or sym == "—" else sym + "·" + src.replace("给", ""))
        L.append("| %s.. | %s |" % (r["md5"][:8], " | ".join(cells)))
    L += ["", "## 空格清单（逐格点名）", ""]
    L += (["- " + g for g in gaps] if gaps else ["- **无空格**——应投箱逐格全 ✅"])
    L += ["", "## md5 不等清单", ""]
    L += (["- " + m for m in mism] if mism else ["- 无"])
    L += ["", "## 总评", "",
          "- 件数：**%d**｜应投箱：**%d**｜应投格：**%d**" % (len(rows), len(targets), len(rows) * len(targets)),
          "- ✅ %d｜🟡 %d｜⚠️ %d｜❌ %d" % (
              sum(1 for r in rows for c in cols if r["cells"][c][0] == "✅"),
              sum(1 for r in rows for c in cols if r["cells"][c][0] == "🟡"),
              sum(1 for r in rows for c in cols if r["cells"][c][0] == "⚠️"),
              sum(1 for r in rows for c in cols if r["cells"][c][0] == "❌")),
          "- 时点：%s" % ts]
    out_path.write_text("\n".join(L), encoding="utf-8")

    n_bad = len(gaps) + len(mism)
    print(json.dumps({
        "ts": ts, "papers": len(rows), "targets": len(targets),
        "cells": len(rows) * len(targets), "gaps": len(gaps), "mismatch": len(mism),
        "publishable": n_bad == 0, "out": str(out_path),
    }, ensure_ascii=False, indent=2))
    sys.exit(0 if n_bad == 0 else 1)


if __name__ == "__main__":
    main()
