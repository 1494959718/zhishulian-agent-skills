#!/bin/bash
# exam_dir_check.sh · 技能库保管人 署名实写 · #16 training-camp-exam
# 功能：答卷目录存在/可写/探针三合一检查（§二 T-1h 建目录＋探针）
# 入参：$1 = 答卷目录绝对路径
# 出参：stdout 三行 JSON-like 状态 + exit code 0=全过 / 1=任一不及格
# 用法：bash exam_dir_check.sh "<答卷目录>"

set -euo pipefail

# 10.18 修正（成员F复验指正·缺口补齐）：本脚本原不支持 --help，
# 传 --help 会被当成路径去跑检查，报出一堆无意义的 FAIL，易被误读为"脚本坏了"。
case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
用法: bash exam_dir_check.sh <答卷绝对路径>
功能: 答卷目录存在性 / 可写性 / 探针计数 三合一检查
出参: stdout 三项状态；exit 0=全过 / 1=存在性或可写性不及格
示例: bash exam_dir_check.sh "<答卷目录>"
USAGE
    exit 0
    ;;
esac

TARGET_DIR="${1:?用法: bash exam_dir_check.sh <答卷绝对路径>（或 --help 查看用法）}"

# 时点戳（§六 时点差口径必带）
TS=$(date "+%Y-%m-%d %H:%M:%S")

echo "=== exam_dir_check.sh 启动 · 时点 ${TS} ==="

# 1. 存在性
if [ -d "${TARGET_DIR}" ]; then
  EXIST="PASS"
  EXIST_CODE=0
else
  EXIST="FAIL"
  EXIST_CODE=1
fi
echo "[1/3] 存在性: ${EXIST} (路径=${TARGET_DIR})"

# 2. 可写性（创建临时探针文件，删除）
PROBE_FILE="${TARGET_DIR}/.exam_dir_probe_$$"
if touch "${PROBE_FILE}" 2>/dev/null && rm -f "${PROBE_FILE}"; then
  WRITABLE="PASS"
  WRITABLE_CODE=0
else
  WRITABLE="FAIL"
  WRITABLE_CODE=1
  rm -f "${PROBE_FILE}" 2>/dev/null || true
fi
echo "[2/3] 可写性: ${WRITABLE} (探针已清理)"

# 3. 探针结果：当前答卷 .md 数量（不含 .md5）
MD_COUNT=$(find "${TARGET_DIR}" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
MD5_COUNT=$(find "${TARGET_DIR}" -maxdepth 1 -name "*.md5" 2>/dev/null | wc -l | tr -d ' ')
echo "[3/3] 探针结果: ${MD_COUNT} 件 .md 答卷 / ${MD5_COUNT} 件 .md5 侧车"

# 总评
TOTAL_CODE=$((EXIST_CODE + WRITABLE_CODE))
if [ ${TOTAL_CODE} -eq 0 ]; then
  echo "总评: PASS · 3/3 通过 · 时点 ${TS}"
  exit 0
else
  echo "总评: FAIL · 存在性或可写性不及格 · 时点 ${TS}"
  exit 1
fi