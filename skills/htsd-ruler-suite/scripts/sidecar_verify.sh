#!/bin/bash
# sidecar_verify.sh · 技能库保管人 署名实写 · #16 training-camp-exam
# 功能：逐件正卷 md5 vs 侧车 md5 比对；空壳/不等/抄旧值三型拦截（§五 侧车规矩）
# 入参：$1 = 答卷目录绝对路径
# 出参：stdout 比对报告 + exit code 0=全等 / 1=任一异常
# 用法：bash sidecar_verify.sh "<答卷目录>"

set -euo pipefail

# 10.18 修正（成员F复验指正·缺口补齐）：本脚本原不支持 --help，
# 且传 --help 会在 basename 处触发 "illegal option -- -" 直接崩（set -e）。
case "${1:-}" in
  -h|--help)
    cat <<'USAGE'
用法: bash sidecar_verify.sh <答卷绝对路径>
功能: 逐件正卷 md5 vs 侧车 md5 比对；拦截 空壳 / 不等 / 抄旧值 三型
      侧车解析格式无关，兼容 33B 纯值型、48B GNU 含名型、53B BSD 型
出参: stdout 比对报告；exit 0=全等 / 1=任一异常
示例: bash sidecar_verify.sh "<答卷目录>"
USAGE
    exit 0
    ;;
esac

TARGET_DIR="${1:?用法: bash sidecar_verify.sh <答卷绝对路径>（或 --help 查看用法）}"
TS=$(date "+%Y-%m-%d %H:%M:%S")

echo "=== sidecar_verify.sh 启动 · 时点 ${TS} ==="
echo "目录: ${TARGET_DIR}"

# 计数器
TOTAL=0
EMPTY_SIDECAR=0
MISMATCH=0
OK=0
MISSING_SIDECAR=0

# 扫所有 .md（仅顶层）
for MD_FILE in "${TARGET_DIR}"/*.md; do
  # 跳过非答卷件（如 README.md / 模板.md）
  BASENAME=$(basename "${MD_FILE}")
  if [[ ! "${BASENAME}" =~ ^答卷_ ]]; then
    continue
  fi
  TOTAL=$((TOTAL + 1))

  MD5_FILE="${MD_FILE}.md5"

  # 1. 侧车存在性
  if [ ! -f "${MD5_FILE}" ]; then
    echo "❌ [${BASENAME}] 侧车缺失（${MD5_FILE##*/}）"
    MISSING_SIDECAR=$((MISSING_SIDECAR + 1))
    continue
  fi

  # 2. 侧车空壳拦截（0B / 仅换行 / 仅空格）
  SIDECAR_SIZE=$(wc -c < "${MD5_FILE}" | tr -d ' ')
  if [ "${SIDECAR_SIZE}" -lt 33 ]; then
    echo "❌ [${BASENAME}] 侧车空壳（${SIDECAR_SIZE}B < 33B）"
    EMPTY_SIDECAR=$((EMPTY_SIDECAR + 1))
    continue
  fi

  # 3. 解析侧车 md5（格式无关取 32 位十六进制串）
  #    10.18 实跑修正（N4）：原实现 awk '{print $1}' 只认「纯值型」，
  #    对 macOS/BSD 默认输出的「MD5 (文件名) = 哈希」型必然误判「格式异常」，
  #    属尺子自身缺陷（同一坑已于 10.07 在技能库保管人 本人侧车复扫时踩过一次）。
  #    改为整行提取首个 32 位 hex，令注释中的「两型并存」声明真正成立。
  SIDECAR_HASH=$(head -1 "${MD5_FILE}" | grep -oE '[0-9a-fA-F]{32}' | head -1 | tr '[:upper:]' '[:lower:]')
  if [ -z "${SIDECAR_HASH}" ]; then
    echo "❌ [${BASENAME}] 侧车格式异常（未提取到 32 位 md5）"
    EMPTY_SIDECAR=$((EMPTY_SIDECAR + 1))
    continue
  fi

  # 4. 实算正卷 md5 vs 侧车 md5 比对
  ACTUAL_HASH=$(md5 -q "${MD_FILE}")
  if [ "${ACTUAL_HASH}" = "${SIDECAR_HASH}" ]; then
    OK=$((OK + 1))
    echo "✅ [${BASENAME}] 全等 (md5=${ACTUAL_HASH:0:8}...)"
  else
    MISMATCH=$((MISMATCH + 1))
    echo "❌ [${BASENAME}] 不等！侧车=${SIDECAR_HASH:0:8}... 实算=${ACTUAL_HASH:0:8}..."
  fi
done

echo ""
echo "=== 总评 · 时点 ${TS} ==="
echo "扫描 .md 总数：${TOTAL}"
echo "✅ 全等：${OK}"
echo "❌ 不等：${MISMATCH}"
echo "❌ 侧车缺失：${MISSING_SIDECAR}"
echo "❌ 侧车空壳：${EMPTY_SIDECAR}"

if [ ${MISMATCH} -gt 0 ] || [ ${MISSING_SIDECAR} -gt 0 ] || [ ${EMPTY_SIDECAR} -gt 0 ]; then
  exit 1
fi
exit 0