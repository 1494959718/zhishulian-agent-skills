---
name: skillsmp-research
description: SkillsMP（Agent Skills 生态地图）检索与复用决策器。输入关键词（ffmpeg／TTS／成本测算／质检／PDF／专利撰写…），返回公开 SKILL.md 目录的匹配技能，含作者、star、内容语言、GitHub 来源路径，并自动折叠多语言副本、自证「服务端真的按我的词过滤了」、回显额度余额。当需要回答「这个能力别人写过没有／现成的 skill 从哪找／复用还是自研／公司 500 skill 目标怎么找增量」时调用本 skill。也用于对拟复用的外部 skill 做「收录≠认证」的回源核对清单。
---

# SkillsMP 检索与复用决策器（技能库保管人 自研 v1.0 · 2026-10-23）

**为什么需要它**：公司「500 skill」目标如果全靠手写，是把可复用的东西重造一遍。SkillsMP 把 GitHub 上公开的 SKILL.md 收成一张可检索的地图（官方口径 3M+，页面快照计数随 catalog 同步变动，**引用时必须写「官方口径」而不是把页面数字当精确值**）。本 skill 把「先查一次再动手」变成一条**可直调、可自证**的命令。

**归属**：算力底座·设备筹备调研组（B 线：成员B 主责用 skill/插件/MCP 做降本创新）｜公司技能/工具库 保管人：技能库保管人

---

## 快速开始

```bash
cd ~/.minimax/skills/skillsmp-research

# 1) 离线自检（不联网，先证明尺子没坏）
python3 skillsmp_search.py self-test

# 2) 关键词检索（会打印过滤自证与额度余额）
python3 skillsmp_search.py search "ffmpeg" --limit 8

# 3) 取单个 skill 详情（MCP，不消耗检索额度）
python3 skillsmp_search.py detail openclaw-openclaw-skills-video-frames-skill-md

# 4) 取分类/领域清单（MCP，不消耗检索额度）
python3 skillsmp_search.py categories --domain development

# 5) 看上次调用剩余额度
python3 skillsmp_search.py quota
```

---

## 三条硬纪律（写进了代码，不只写在这里）

### ① 过滤自证：静默忽略的参数名是最坏的 API 坑
实测：`GET /api/skills?q=ffmpeg` **返回 200 且有数据**，但服务端 `filters.search` 是空串 —— **完全没过滤**，返回的是按 star 排的全量目录；而同一份数据用 `?search=ffmpeg` 才真过滤。**「有数据」不等于「按你要的过滤了」。**

处置：本工具每次检索后**回读 `filters.search` 并与发出的 `q` 比对**，不等就 `GuardError` 直接退出非零 —— 绝不把「未过滤的全量」当「检索结果」交出去。
> 这与 K015 是同一个病根：**尺子自己测不出尺子默认值的荒谬**，所以要有专验该项的守卫。

### ② 收录 ≠ 认证 ≠ 实时存在
SkillsMP 自己写明：*「it does not certify that every skill is safe or high quality… only install what you understand」*，且**与 Anthropic/OpenAI 无关联**。
**实证**：目录里 `openclaw/openclaw → skills/video-frames` 的 `githubUrl`，在 openclaw 仓库 main 分支上**已不存在**（GitHub 原话：*The main branch of openclaw does not contain the path skills/video-frames*）⇒ 目录是**快照**，路径会漂移。

⇒ **复用前三件套**：① 回源 GitHub 核对路径真实存在 ② 读 SKILL.md 全文与附带脚本/权限 ③ 判断许可与是否与公司口径冲突。**目录只用来「找」，不用来「信」。**

### ③ 额度纪律（官方口径，来自 `https://skillsmp.com/api/llms.txt` 与 `openapi.json`）
| 通道 | 匿名额度 | 带 key 额度 |
|:--|:--|:--|
| REST `/api/v1/skills/search` | **50 次/UTC 日 ＋ 10 次/分** | Free 100/日；Standard 5,000/月；Professional 25,000/月（另有 30 次/分保护） |
| MCP `/mcp` | **10 次成功检索/小时/IP** | 与 REST 共用同一份账号额度 |

- **空结果也算成功**（消耗额度）；**复用 JSON-RPC id 不省额度**（每次调用都是一次新检索）。
- `get_skill` / `list_categories` / `tools.list` / `initialize` **不计检索额度** ⇒ **先取详情，别反复 search**。
- `totalIsExact=false` ⇒ `total` **不是精确总数**，不要当精确统计写进申报册。
- 错误码：`RATE_LIMITED` / `DAILY_QUOTA_EXCEEDED`（带 `remaining`/`resetAt`/`retryAfter`）/`SEARCH_COMPLETION_UNCERTAIN`（**可能已计费，停止自动重试，先查用量**）。
- 可选 key：环境变量 `SKILLSMP_API_KEY`（`Authorization: Bearer sk_live_…`）。**key 不得写进 URL、日志或任何交付件。**

---

## 输出解读

| 字段 | 含义 | 注意 |
|:--|:--|:--|
| `filters.search` | 服务端实际用的过滤词 | **与发出的 q 不等 = 守卫已拦** |
| `raw_count` / `deduped_count` | 原始条数 / 折叠后条数 | 差额＝**同一 skill 的多语言副本**（zh/ja/en 各占一条） |
| `total` / `totalIsExact` | 候选数 / 是否精确 | 官方明示 **候选数≠全库匹配数**，且常非精确 |
| `githubUrl` | 目录快照里的源路径 | **可能已失效，必须回源** |
| `stars` | 仓库 star | 热度信号，不等于质量 |

**去重规则**：按 `(name, author, 归一路径)` 折叠，其中归一化会抹掉 `docs/<locale>/` 这一层 —— 否则同一个 skill 的中/日/英三份会把结果数虚高三倍。

---

## 对公司的直接用法（这才是重点）

1. **自研前先查**：任何「我正要写一个 X 能力」的念头，先 `search "X"` 一次 —— 查得到就**评估复用**（省的是研发工时，不是钱），查不到再自研，并在件里写明「已检索未发现」。
2. **公司 500 skill 目标的增量来源**：SkillsMP 是**外部现成能力的检索入口**，配合团队自己的 skill 库做「内部复用优先 → 外部成熟能力次之 → 自研兜底」三级取用。
3. **体例学习**：对照高星 SKILL.md 的写法（frontmatter 触发词写法、渐进披露、references/ scripts/ 分层），反哺自研 skill 的触发准确率。
4. **反哺自研率口径**：本工具检索的是**外部**能力，**不计入公司自研率**（K005：自研率按 `author` 字段判定，外部 author 一律不算）。

---

## 边界（不做什么）

- **不做**自动安装、不做自动改写公司 skill、不替我做「能不能用」的最终判断（那是回源核对与团队决策的事）。
- **不提供** SKILL.md 正文（`get_skill` 只给目录元数据）—— 正文回源 GitHub；本机 `curl` 直连 GitHub 在当前网络不通，需走 `web_fetch` 或浏览器。
- **不承诺** SkillsMP 收录内容的质量、安全性或时效性 —— 它是地图，不是认证。

—— 技能库保管人 · 2026-10-23 · 算力底座·设备筹备调研组 副组长（B 线）＋ 公司技能/工具库建设保管人
