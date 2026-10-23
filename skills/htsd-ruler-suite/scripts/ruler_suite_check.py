#!/usr/bin/env python3
# ruler_suite_check.py · 技能库保管人 自研 · 自研 Skill 第2号「四尺套装」
# 功能：统一自检四把尺子（sidecar_verify.sh / box_matrix.py / roll_matrix.py / exam_dir_check.sh）
#       —— 尺子自己先证明自己没坏：自建沙盘 fixture → 真跑四脚本 → 逐条断言
# 入参：--scripts <四脚本所在目录>   --out <自检 JSON 输出路径>   [--keep] 保留沙盘不删
# 出参：stdout JSON（cases 总数 / pass / fail / 分母断言）+ exit 0=全过 1=有失败
#
# 设计纪律（10-22 立）：
#   ① 每条断言必须能判 PASS/FAIL，不许"看起来对"就算过；
#   ② 反例必须**期望尺子报错**——尺子拦不住 = FAIL（这是尺子失灵，不是数据问题）；
#   ③ 分母动态算出并断言（件数×应投箱 == 应投格），禁写死；
#   ④ 团队侧车口径 = 33B 纯单行；**值同但尺寸不合 = 不合规**（size 维度独立判）。
#
# 用法：python3 ruler_suite_check.py --scripts ./scripts --out ./实跑证据/xxx.json

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

TEAM_SIDECAR_BYTES = 33  # 团队现行口径：33B 纯单行（32 位 md5 + 换行）


def md5q(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sidecar(path: Path, value: str, mode: str = "pure"):
    """按指定形态写侧车：pure=33B 纯单行 / gnu=48B 含名型 / stale=抄旧值 / shell=5B 空壳"""
    sc = Path(str(path) + ".md5")
    if mode == "pure":
        sc.write_text(value + "\n", encoding="utf-8")
    elif mode == "gnu":
        sc.write_text(value + "  " + path.name + "\n", encoding="utf-8")
    elif mode == "stale":
        sc.write_text("0" * 31 + "1\n", encoding="utf-8")
    elif mode == "shell":
        sc.write_text("\n\n", encoding="utf-8")
    return sc


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


class Suite:
    def __init__(self, scripts_dir: Path):
        self.scripts = scripts_dir
        self.cases = []
        self.root = Path(tempfile.mkdtemp(prefix="ruler_suite_"))

    def add(self, cid, kind, desc, expect, ok, detail=""):
        self.cases.append({
            "id": cid, "kind": kind, "desc": desc,
            "expect": expect, "result": "PASS" if ok else "FAIL",
            "detail": detail,
        })
        return ok

    # ---------- R1-R5：sidecar_verify.sh + 33B 团队口径独立双验 ----------
    def case_sidecar(self):
        d = self.root / "sidecar"
        d.mkdir(parents=True, exist_ok=True)
        good = d / "答卷_甲批_甲_20261022.md"
        good.write_text("# 甲\n正文甲\n", encoding="utf-8")
        write_sidecar(good, md5q(good), "pure")

        stale = d / "答卷_甲批_乙_20261022.md"
        stale.write_text("# 乙\n正文乙\n", encoding="utf-8")
        write_sidecar(stale, md5q(stale), "stale")  # 抄旧值 → 值断链

        noside = d / "答卷_甲批_丙_20261022.md"
        noside.write_text("# 丙\n正文丙\n", encoding="utf-8")

        shell = d / "答卷_甲批_丁_20261022.md"
        shell.write_text("# 丁\n正文丁\n", encoding="utf-8")
        write_sidecar(shell, md5q(shell), "shell")  # 2B 空壳

        gnu = d / "答卷_甲批_戊_20261022.md"
        gnu.write_text("# 戊\n正文戊\n", encoding="utf-8")
        write_sidecar(gnu, md5q(gnu), "gnu")  # 48B 含名型：值同但尺寸不合团队口径

        rc, out, err = run(["bash", str(self.scripts / "sidecar_verify.sh"), str(d)])
        text = out

        # v1.0 修正（10.22 首跑实抓）：v0.1 的 grab() 在全文里找关键词，
        # 抓到的是**逐件报告行**（如「✅ [答卷_…] 全等 (md5=…)」）而不是**总评汇总行**，
        # 于是 4 条断言全被自己的解析错误判成 FAIL —— 尺子没坏，是尺子的尺子（断言）坏了。
        # 修法：只切「=== 总评」之后的汇总段再取数。
        if "=== 总评" in text:
            summary = text.split("=== 总评", 1)[1]
        else:
            summary = text

        def grab(label):
            for line in summary.splitlines():
                if line.strip().startswith(("✅", "❌", "扫描")) and label in line:
                    return line.split("：")[-1].strip()
            return None

        total = grab("扫描 .md 总数")
        ok_n = grab("全等")
        mism = grab("不等")
        miss = grab("侧车缺失")
        empty = grab("侧车空壳")

        # v1.0：全等数应为 2 —— 甲（33B 正确）+ 戊（48B GNU 值同）。
        # sidecar_verify 只验**值**不验**尺寸**，故戊被计全等；这正是 R5 要用独立尺寸维度拦的。
        # 同时加尺子自身的分母断言：全等+不等+缺失+空壳 == 总数。
        self.add("R1", "正例", "sidecar_verify 计数自洽：全等=2（甲33B + 戊48B值同）+ 不等=1 + 缺失=1 + 空壳=1 == 总数 5",
                 "全等=2 不等=1 缺失=1 空壳=1 总数=5 且四项和==总数",
                 ok_n == "2" and mism == "1" and miss == "1" and empty == "1" and total == "5"
                 and (int(ok_n) + int(mism) + int(miss) + int(empty)) == int(total),
                 "全等=%s 不等=%s 缺失=%s 空壳=%s 总数=%s" % (ok_n, mism, miss, empty, total))

        self.add("R2", "反例", "sidecar_verify：侧车抄旧值（值断链）必须被拦成「不等」",
                 "不等=1 且 exit=1", mism == "1" and rc == 1,
                 "不等=%s exit=%s" % (mism, rc))

        self.add("R3", "反例", "sidecar_verify：缺侧车必须被拦成「侧车缺失」",
                 "侧车缺失=1", miss == "1", "侧车缺失=%s" % miss)

        self.add("R4", "反例", "sidecar_verify：空壳侧车必须被拦成「侧车空壳」",
                 "侧车空壳=1", empty == "1", "侧车空壳=%s" % empty)

        # R5：值同但 48B → 团队 33B 口径判不合规（size 维度独立判，不依赖 sidecar_verify）
        sc = Path(str(gnu) + ".md5")
        size = sc.stat().st_size
        val_ok = md5q(gnu) in sc.read_text(encoding="utf-8")
        self.add("R5", "反例", "值+尺寸双验：值同但 48B 含名型 → 按团队 33B 口径判不合规",
                 "值同=True 且尺寸=33 才合规；此处尺寸=%d ⇒ 不合规" % size,
                 (not (val_ok and size == TEAM_SIDECAR_BYTES)),
                 "size=%d value_match=%s" % (size, val_ok))

    # ---------- R6-R7：exam_dir_check.sh ----------
    def case_exam_dir(self):
        d = self.root / "examdir"
        d.mkdir(parents=True, exist_ok=True)
        rc, out, _ = run(["bash", str(self.scripts / "exam_dir_check.sh"), str(d)])
        ok_exist = "存在性: PASS" in out
        ok_write = "可写性: PASS" in out
        self.add("R6", "正例", "exam_dir_check：存在且可写目录 ⇒ 存在性/可写性双 PASS 且 exit=0",
                 "存在性 PASS + 可写性 PASS + exit=0",
                 ok_exist and ok_write and rc == 0,
                 "exist=%s write=%s exit=%s" % (ok_exist, ok_write, rc))

        missing = self.root / "examdir_missing"
        if missing.exists():
            shutil.rmtree(missing)
        rc2, out2, _ = run(["bash", str(self.scripts / "exam_dir_check.sh"), str(missing)])
        self.add("R7", "反例", "exam_dir_check：目录不存在 ⇒ 存在性 FAIL 且 exit=1",
                 "存在性 FAIL + exit=1",
                 ("存在性: FAIL" in out2) and rc2 == 1,
                 "exit=%s" % rc2)

    # ---------- R8-R10：box_matrix.py ----------
    def case_box_matrix(self):
        papers = self.root / "papers_ok"
        papers.mkdir(parents=True, exist_ok=True)
        p1 = papers / "答卷_甲批_甲_20261022.md"
        p1.write_text("# 甲\n", encoding="utf-8")
        write_sidecar(p1, md5q(p1), "pure")

        boxes = self.root / "boxes"
        bdir = boxes / "给箱甲" / "10月22日"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p1, bdir / p1.name)
        shutil.copy2(Path(str(p1) + ".md5"), bdir / (p1.name + ".md5"))

        out1 = self.root / "matrix_ok.md"
        rc, sout, _ = run([
            "python3", str(self.scripts / "box_matrix.py"),
            "--papers", str(papers), "--boxes", str(boxes),
            "--targets", "给箱甲", "--out", str(out1)])
        try:
            j1 = json.loads(sout)
        except Exception:
            j1 = {}
        self.add("R8", "正例", "box_matrix：件在「箱名/日期/件名」三层结构内 ⇒ gaps=0 publishable=True",
                 "gaps=0 且 publishable=True",
                 j1.get("gaps") == 0 and j1.get("publishable") is True,
                 "gaps=%s publishable=%s" % (j1.get("gaps"), j1.get("publishable")))

        # R9：件不在箱内 ⇒ 必须报缺件（尺子不许虚报零命中）
        papers2 = self.root / "papers_bad"
        papers2.mkdir(parents=True, exist_ok=True)
        p2 = papers2 / "答卷_甲批_乙_20261022.md"
        p2.write_text("# 乙\n", encoding="utf-8")
        write_sidecar(p2, md5q(p2), "pure")
        out2 = self.root / "matrix_bad.md"
        rc2, sout2, _ = run([
            "python3", str(self.scripts / "box_matrix.py"),
            "--papers", str(papers2), "--boxes", str(boxes),
            "--targets", "给箱甲", "--out", str(out2)])
        try:
            j2 = json.loads(sout2)
        except Exception:
            j2 = {}
        self.add("R9", "反例", "box_matrix：件不在箱内 ⇒ 必须报缺件 gaps≥1 publishable=False（不虚报零命中）",
                 "gaps≥1 且 publishable=False",
                 (j2.get("gaps") or 0) >= 1 and j2.get("publishable") is False,
                 "gaps=%s publishable=%s" % (j2.get("gaps"), j2.get("publishable")))

        # R10：分母断言 —— 应投格 = 件数 × 应投箱数（动态算出，不写死）
        self.add("R10", "正例", "分母断言：cells == papers × targets（R8 动态值）",
                 "cells == papers × targets",
                 j1.get("cells") == (j1.get("papers") or 0) * (j1.get("targets") or 0),
                 "cells=%s papers=%s targets=%s" % (j1.get("cells"), j1.get("papers"), j1.get("targets")))

    # ---------- R11-R12：roll_matrix.py ----------
    def case_roll(self):
        rp = self.root / "roll_papers"
        rp.mkdir(parents=True, exist_ok=True)
        pa = rp / "答卷_甲_甲批_20261022.md"
        pa.write_text("# 甲\n", encoding="utf-8")
        write_sidecar(pa, md5q(pa), "pure")

        roster = self.root / "roster.md"
        roster.write_text("# 人头 场次\n甲\t甲批\n乙\t甲批\n", encoding="utf-8")

        outp = self.root / "roll_out.md"
        rc, sout, _ = run([
            "python3", str(self.scripts / "roll_matrix.py"),
            "--roster", str(roster), "--papers", str(rp), "--out", str(outp)])
        try:
            j = json.loads(sout)
        except Exception:
            j = {}
        self.add("R11", "反例", "roll_matrix：1 人交齐 1 人缺卷 ⇒ gap_count=1、expected=2（分母动态）",
                 "expected=2 gap_count=1 missing_paper=1 exit=1",
                 j.get("expected") == 2 and j.get("gap_count") == 1
                 and j.get("missing_paper") == 1 and rc == 1,
                 "expected=%s gap=%s miss=%s exit=%s" % (
                     j.get("expected"), j.get("gap_count"), j.get("missing_paper"), rc))

        roster2 = self.root / "roster_full.md"
        roster2.write_text("# 人头 场次\n甲\t甲批\n", encoding="utf-8")
        outp2 = self.root / "roll_out_full.md"
        rc2, sout2, _ = run([
            "python3", str(self.scripts / "roll_matrix.py"),
            "--roster", str(roster2), "--papers", str(rp), "--out", str(outp2)])
        try:
            j2 = json.loads(sout2)
        except Exception:
            j2 = {}
        # v1.0 修正（10.22 首跑实抓）：v0.1 此处断言误取**首跑**的 j（gap=1）而非二跑的 j2，
        # 属"我调错了尺子"（参数口径不对），不是尺子坏了 —— 与 R1-R4 的解析错是两回事。
        self.add("R12", "正例", "roll_matrix：全部交齐 ⇒ gap_count=0 exit=0",
                 "gap_count=0 exit=0", j2.get("gap_count") == 0 and rc2 == 0,
                 "gap=%s exit=%s" % (j2.get("gap_count"), rc2))

    def run_all(self):
        self.case_sidecar()
        self.case_exam_dir()
        self.case_box_matrix()
        self.case_roll()

        total = len(self.cases)
        passed = sum(1 for c in self.cases if c["result"] == "PASS")
        failed = total - passed
        pos = sum(1 for c in self.cases if c["kind"] == "正例")
        neg = sum(1 for c in self.cases if c["kind"] == "反例")
        neg_pass = sum(1 for c in self.cases if c["kind"] == "反例" and c["result"] == "PASS")
        result = {
            "tool": "ruler_suite_check.py",
            "version": "v1.0",
            "author": "技能库保管人",
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cases": total, "pass": passed, "fail": failed,
            "pos_cases": pos, "neg_cases": neg, "neg_pass": neg_pass,
            "denominator_assertion": {
                "cases_total_equals_sum": total == pos + neg,
                "neg_cases_at_least_1": neg >= 1,
                "all_neg_passed": neg_pass == neg,
            },
            "cases_detail": self.cases,
        }
        result["all_pass"] = (failed == 0
                              and result["denominator_assertion"]["cases_total_equals_sum"]
                              and result["denominator_assertion"]["all_neg_passed"])
        return result


def main():
    ap = argparse.ArgumentParser(description="四尺套装统一自检（正例 + 反例）")
    ap.add_argument("--scripts", required=True, help="四脚本所在目录")
    ap.add_argument("--out", required=True, help="自检 JSON 输出路径")
    ap.add_argument("--keep", action="store_true", help="保留沙盘（调试用）")
    args = ap.parse_args()

    s = Suite(Path(args.scripts))
    try:
        res = s.run_all()
    finally:
        if not args.keep:
            shutil.rmtree(s.root, ignore_errors=True)
        else:
            res_keep = str(s.root)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["all_pass"] else 1)


if __name__ == "__main__":
    main()
