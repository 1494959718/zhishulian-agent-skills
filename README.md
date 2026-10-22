# 南京智枢联 · 自研 Agent Skills 与交付方法库

> Self-developed Agent Skills and delivery-methodology notes — Nanjing Zhishulian Information Technology Co., Ltd.

本仓库收录本团队**自研**的 Agent Skill 与配套交付方法条目，面向「工业化电影级内容生产系统·算力底座」
以及一般的软件／内容交付场景。全部条目均可脱离公司环境独立运行。

**English summary** — A collection of self-developed Agent Skills (SKILL.md + runnable scripts) and
distilled delivery-methodology notes. Every skill ships with runnable scripts and a self-test entry
point. External skills discovered via [SkillsMP](https://skillsmp.com) are **not** included here and
are **not** counted as self-developed.

## 目录结构 / Layout

```
  skillsmp-research           # 外部技能生态检索与复用决策器（SkillsMP）
MANIFEST.md                    # 每件文件的字节数 + md5（值+尺寸双验）
```

## 安装 / Install

把需要的 skill 目录整体拷入你的 skills 目录（MiniMax Code 默认 `~/.minimax/skills/`，其他运行时同理）：

```bash
cp -R skills/<skill-name> ~/.minimax/skills/
```

每个 skill 的 `SKILL.md` 头部是 YAML frontmatter（`name` / `description`），运行时可直接发现并加载。

## 用法 / Usage

```bash
# SkillsMP 检索：先查一次现成能力，再决定自研
python3 skills/skillsmp-research/skillsmp_search.py search "ffmpeg" --limit 8
python3 skills/skillsmp-research/skillsmp_search.py self-test     # 离线自检
```

## 方法论体例 / Methodology

本仓库当前为**试水发布**：先发 1 件 skill 验证「公开仓库 → SkillsMP 收录」链路是否打通，
打通后按同一发布树构建器放量。方法条目统一采用**六步体例**（采/验/算/疑/落/用）。

## 边界 / Scope

- 本仓库只收录**自研**条目。经 SkillsMP 检索到的外部 skill **一律不计入自研率**，
  按 `author` 字段判定；收录 ≠ 认证 ≠ 实时存在，复用前必须回源核对。
- 条目中出现的算力与成本结论均为**口径化测算**，非承诺值；未实测处已标注。
- 联系方式与内部代号在公开版本中已脱敏。

## 说明 / Notes

内容由团队成员在 AI 辅助下撰写并逐条实跑校验；每条结论均附可复算证据。
仓库内条目遵循与本地交付件一致的「值+尺寸双验」纪律，清单见 `MANIFEST.md`。

## License

内部研发用途。未经书面授权，不得用于对外商业交付或再分发。
