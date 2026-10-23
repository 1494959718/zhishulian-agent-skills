#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skillsmp_search.py — SkillsMP（Agent Skills 生态地图）检索与详情工具（技能库保管人 自研 v1.0）

为什么有它：
  公司「500 skill」目标不能靠一个个手写。SkillsMP 收录 GitHub 上公开 SKILL.md（官方口径 3M+，
  页面快照计数随 catalog 同步变动），带开放 REST API 与官方 MCP server。本工具把「查现成能力」
  这件事变成**一条可直调、可自证的命令**，让全组在动手自研之前先查一次，避免重复造轮子。

三条硬纪律（写进代码，不只写进文档）：
  ① 过滤自证：静默忽略的参数名是最坏的 API 坑。响应里的 filters.search 必须等于我发出去的 q，
     不等就**直接 exit 非零**，绝不把「未过滤的全量结果」当成「检索结果」交出去。
  ② 收录≠认证≠实时存在：SkillsMP 自己写明「只收录不认证」。返回的 githubUrl 是目录快照，
     实测 openclaw/openclaw 的 skills/video-frames 路径在 main 分支已不存在 ⇒ 必须回源核对路径。
  ③ 额度纪律：REST 匿名 50 次/日、10 次/分；MCP 匿名 10 次成功检索/小时/IP。
     空结果也算成功（消耗）；复用 JSON-RPC id 不省额度（每次调用都是新检索）。
     get_skill / list_categories / tools.list **不计检索额度** ⇒ 先取详情，别反复 search。

用法：
  python3 skillsmp_search.py search "ffmpeg" [--limit 10] [--sort stars|recent|relevance]
                                      [--language zh] [--category <slug>] [--json]
  python3 skillsmp_search.py detail <skill_id>          # MCP get_skill，不计检索额度
  python3 skillsmp_search.py categories [--domain <slug>] # MCP list_categories，不计检索额度
  python3 skillsmp_search.py quota                       # 看上次调用剩余额度（读响应头）
  python3 skillsmp_search.py self-test                   # 离线自检，不联网

归属：算力底座项目组（研发）｜公司技能/工具库 保管人：技能库保管人
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error

REST_SEARCH = "https://skillsmp.com/api/v1/skills/search"
MCP_URL = "https://skillsmp.com/mcp"
MCP_PROTOCOL_VERSION = "2025-06-18"
API_KEY_ENV = "SKILLSMP_API_KEY"          # 可选；匿名也可用（额度更小）

SORT_ENUM = ("stars", "recent", "relevance")
LIMIT_MIN, LIMIT_MAX = 1, 50

_LAST_QUOTA = {"daily_remaining": None, "daily_limit": None,
               "minute_remaining": None, "minute_limit": None,
               "daily_reset": None, "source": None}


# ---------------------------------------------------------------- 基础工具

def _http(url, headers=None, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, dict(e.headers or {}), body


def _record_quota(headers):
    """把 x-ratelimit-* 头记进 _LAST_QUOTA（供 quota 子命令回看）。"""
    for k, v in (headers or {}).items():
        lk = k.lower()
        if lk == "x-ratelimit-daily-limit":
            _LAST_QUOTA["daily_limit"] = _int(v)
        elif lk == "x-ratelimit-daily-remaining":
            _LAST_QUOTA["daily_remaining"] = _int(v)
        elif lk == "x-ratelimit-daily-reset":
            _LAST_QUOTA["daily_reset"] = _int(v)
        elif lk == "x-ratelimit-minute-limit":
            _LAST_QUOTA["minute_limit"] = _int(v)
        elif lk == "x-ratelimit-minute-remaining":
            _LAST_QUOTA["minute_remaining"] = _int(v)
    if headers:
        _LAST_QUOTA["source"] = "x-ratelimit-* 响应头"
    _save_quota()


def _quota_state_path():
    """额度状态落盘位置（跨进程可读 —— quota 子命令单独跑时才有意义）。"""
    return os.path.join(os.path.expanduser("~"), ".cache", "skillsmp", "quota.json")


def _save_quota():
    """额度是辅助信息，写不进去不影响主流程。"""
    try:
        d = os.path.dirname(_quota_state_path())
        if d:
            os.makedirs(d, exist_ok=True)
        with open(_quota_state_path(), "w", encoding="utf-8") as f:
            json.dump(_LAST_QUOTA, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def _load_quota():
    """读回上次调用记下的额度（跨进程）。"""
    try:
        with open(_quota_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if k in _LAST_QUOTA:
                    _LAST_QUOTA[k] = v
    except Exception:
        pass


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


class GuardError(RuntimeError):
    """守卫失败：宁可报错，也不把不可信的返回交出去。"""


# ---------------------------------------------------------------- 去重

# docs/zh-CN/ docs/ja-JP/ ... （注意路径可能不以 "/" 开头，故用 (^|/) 锚定）
_LOCALE_DIR = re.compile(r"(^|/)docs/[a-zA-Z]{2}(-[A-Za-z]{2,4})?/")
# 上游有时把同一个 skill 同时放在 .agents/skills/ 与 skills/ 两处（打包约定），也算同一条
_AGENTS_DIR = re.compile(r"(^|/)\.agents/skills/")


def _repo_path(github_url):
    """从 tree URL 里抽出仓库内路径，作为去重键的一部分。"""
    if not github_url:
        return ""
    m = re.search(r"/tree/[^/]+/(.*)$", github_url)
    return (m.group(1) if m else github_url).rstrip("/")


def norm_skill_path(github_url):
    """归一化：抹掉 docs/<locale>/ 与 .agents/ 这两层，让同一 skill 的多语言/双路径副本折叠成一条。"""
    p = _repo_path(github_url)
    p = _LOCALE_DIR.sub(r"\1", p)
    p = _AGENTS_DIR.sub(r"\1skills/", p)
    return p


def assert_filter_applied(filters, query):
    """纪律①的守卫本体：服务端真的按我发的词过滤了吗？

    不等（或者服务端压根没回 filters.search）就抛 GuardError —— 宁可报错，
    也不把「未过滤的全量目录」当成「检索结果」交出去。
    """
    applied = (filters.get("search") or "").strip()
    if applied.lower() != query.strip().lower():
        raise GuardError(
            "守卫失败：服务端 filters.search=%r ≠ 我发出的 q=%r —— 该参数被静默忽略，"
            "返回的是未过滤的全量结果，不能当检索结果用。" % (applied, query))
    return applied


def dedupe_skills(skills):
    """同一 (name, author, 归一路径) 只留一条；多语言副本折叠。

    返回 (去重后列表, 被折叠条数)。
    """
    seen, out, folded = {}, [], 0
    for s in skills:
        key = (s.get("name"), s.get("author"), norm_skill_path(s.get("githubUrl")))
        if key in seen:
            folded += 1
            # 保留信息更全的那条（描述更长者优先）
            prev = seen[key]
            if len(s.get("description") or "") > len(prev.get("description") or ""):
                out[out.index(prev)] = s
                seen[key] = s
            continue
        seen[key] = s
        out.append(s)
    return out, folded


# ---------------------------------------------------------------- 检索

def search(query, limit=20, sort="stars", language=None, category=None, api_key=None):
    """REST 关键词检索。返回 dict。

    守卫：响应 filters.search 必须等于 query，否则抛 GuardError。
    """
    if not query or not query.strip():
        raise GuardError("query 不能为空")
    limit = max(LIMIT_MIN, min(LIMIT_MAX, int(limit)))
    if sort not in SORT_ENUM:
        raise GuardError("sort 只能是 %s（官方枚举），收到：%r" % ("|".join(SORT_ENUM), sort))

    params = {"q": query, "limit": limit, "sortBy": sort}
    if language:
        params["language"] = language
    if category:
        params["category"] = category
    url = REST_SEARCH + "?" + urllib.parse.urlencode(params)

    headers = {"Accept": "application/json", "User-Agent": "laowu-l5-skillsmp/1.0"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    status, rh, body = _http(url, headers=headers)
    _record_quota(rh)
    if status != 200:
        raise GuardError("HTTP %s：%s" % (status, body[:300]))

    try:
        payload = json.loads(body)
    except ValueError:
        raise GuardError("返回不是 JSON：%s" % body[:200])

    if not payload.get("success", False):
        raise GuardError("success=false：%s" % json.dumps(payload.get("meta") or {}, ensure_ascii=False)[:300])

    data = payload.get("data") or {}
    skills = data.get("skills") or []
    filters = data.get("filters") or {}
    pagination = data.get("pagination") or {}

    # —— 纪律①：过滤自证。filters.search 必须与我发出去的 query 一致。
    assert_filter_applied(filters, query)

    deduped, folded = dedupe_skills(skills)
    return {
        "query": query,
        "filters_applied": filters,
        "pagination": pagination,
        "raw_count": len(skills),
        "deduped_count": len(deduped),
        "folded_duplicates": folded,
        "total_is_exact": pagination.get("totalIsExact"),
        "quota": dict(_LAST_QUOTA),
        "skills": deduped,
    }


# ---------------------------------------------------------------- MCP

def _mcp(tool, arguments, api_key=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        "User-Agent": "laowu-l5-skillsmp/1.0",
    }
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    status, rh, raw = _http(MCP_URL, headers=headers, data=body)
    _record_quota(rh)
    if status != 200:
        raise GuardError("MCP HTTP %s：%s" % (status, raw[:300]))
    try:
        d = json.loads(raw)
    except ValueError:
        raise GuardError("MCP 返回不是 JSON：%s" % raw[:200])
    # JSON-RPC 错误可能挂在 HTTP 200 上 —— 必须读 error.data
    if isinstance(d, dict) and d.get("error"):
        raise GuardError("MCP error: %s" % json.dumps(d["error"], ensure_ascii=False)[:400])
    result = (d.get("result") or {})
    chunks = result.get("content") or []
    for c in chunks:
        if c.get("type") == "text":
            try:
                return json.loads(c.get("text") or "{}")
            except ValueError:
                return {"_raw_text": c.get("text")}
    return result


def detail(skill_id, api_key=None):
    """MCP get_skill —— 不计检索额度。"""
    if not skill_id:
        raise GuardError("skill_id 不能为空")
    return _mcp("get_skill", {"id": skill_id}, api_key=api_key)


def categories(domain=None, api_key=None):
    """MCP list_categories —— 不计检索额度。"""
    data = _mcp("list_categories", {}, api_key=api_key)
    if domain:
        doms = data.get("domains") or []
        data = {"domains": [d for d in doms if d.get("domain") == domain]}
    return data


# ---------------------------------------------------------------- 输出

def _trunc(s, n):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def print_search(res):
    pg = res.get("pagination") or {}
    fl = res.get("filters_applied") or {}
    q = res.get("quota") or {}
    print("检索词：%s" % res["query"])
    print("服务端过滤自证：filters.search=%r  sortBy=%r  （相等才算真过滤）"
          % (fl.get("search"), fl.get("sortBy")))
    print("返回 %d 条 → 去重后 %d 条（折叠多语言副本 %d 条）｜total=%s（totalIsExact=%s，计数非精确）"
          % (res["raw_count"], res["deduped_count"], res["folded_duplicates"],
             pg.get("total"), res.get("total_is_exact")))
    if q.get("daily_remaining") is not None:
        print("额度：日剩余 %s/%s ｜ 分钟剩余 %s/%s"
              % (q.get("daily_remaining"), q.get("daily_limit"),
                 q.get("minute_remaining"), q.get("minute_limit")))
    print("-" * 108)
    print("%-28s %-20s %8s %-5s %s" % ("NAME", "AUTHOR", "STARS", "LANG", "GITHUB"))
    for s in res["skills"]:
        print("%-28s %-20s %8s %-5s %s"
              % (_trunc(s.get("name"), 28), _trunc(s.get("author"), 20),
                 s.get("stars"), s.get("contentLanguage") or "-",
                 s.get("githubUrl") or "-"))
        desc = s.get("description")
        if desc:
            print("    └ %s" % _trunc(desc, 100))
    print("-" * 108)
    print("提醒：收录≠认证≠实时存在 —— 复用前必须回源 GitHub 核对路径与内容。")


def print_detail(d):
    sk = d.get("skill") or d
    for k in ("id", "name", "author", "description", "contentLanguage",
              "stars", "forks", "updatedAt", "githubUrl", "skillUrl"):
        if k in sk:
            print("%-16s %s" % (k + ":", sk[k]))
    if not sk:
        print(json.dumps(d, ensure_ascii=False, indent=2)[:1500])
    print("提醒：get_skill 只给目录元数据，**不含 SKILL.md 正文**；正文回源 GitHub 读。")


# ---------------------------------------------------------------- 自检

def self_test():
    """离线自检：不联网。尺子自己先证明自己没坏。"""
    fails = []

    def ck(name, cond, detail_txt=""):
        if cond:
            print("  PASS  %s" % name)
        else:
            print("  FAIL  %s  %s" % (name, detail_txt))
            fails.append(name)

    print("== 1. 多语言副本折叠 ==")
    dup = [
        {"name": "video-editing", "author": "a", "githubUrl": "https://github.com/a/r/tree/main/skills/video-editing", "description": "x"},
        {"name": "video-editing", "author": "a", "githubUrl": "https://github.com/a/r/tree/main/docs/zh-CN/skills/video-editing", "description": "zh"},
        {"name": "video-editing", "author": "a", "githubUrl": "https://github.com/a/r/tree/main/docs/ja-JP/skills/video-editing", "description": "ja"},
    ]
    out, folded = dedupe_skills(dup)
    ck("zh/ja/en 三份折叠成 1 条", len(out) == 1 and folded == 2, "got %d/%d" % (len(out), folded))
    ck("折叠后保留描述最长者", out[0]["description"] == "zh", out[0]["description"])

    print("== 2. 不同 skill 不误折叠 ==")
    two = [
        {"name": "a", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/skills/a"},
        {"name": "b", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/skills/b"},
    ]
    out2, folded2 = dedupe_skills(two)
    ck("2 条不同 skill 保持 2 条", len(out2) == 2 and folded2 == 0)

    print("== 3. 同名不同路径不误折叠 / 同仓双路径会折叠 ==")
    three = [
        {"name": "a", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/skills/a"},
        {"name": "a", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/.agents/skills/a"},
    ]
    out3, folded3 = dedupe_skills(three)
    ck("同仓 .agents/skills 与 skills 折叠成 1 条", len(out3) == 1 and folded3 == 1,
       "got %d/%d" % (len(out3), folded3))
    two_paths = [
        {"name": "a", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/skills/a"},
        {"name": "b", "author": "x", "githubUrl": "https://github.com/x/y/tree/main/skills/b"},
    ]
    out4, _ = dedupe_skills(two_paths)
    ck("不同 skill 保持 2 条", len(out4) == 2)

    print("== 4. 过滤自证守卫（行为测，不测源码字符串）==")
    try:
        assert_filter_applied({"search": "ffmpeg"}, "ffmpeg")
        ck("匹配时放行", True)
    except GuardError:
        ck("匹配时放行", False, "不该抛错")
    for bad, why in (({"search": ""}, "未过滤（全量）"),
                     ({"search": "video"}, "服务端用词≠我发的词"),
                     ({}, "缺 filters.search 字段")):
        try:
            assert_filter_applied(bad, "ffmpeg")
            ck("不匹配时拦截：%s" % why, False, "未抛 GuardError")
        except GuardError:
            ck("不匹配时拦截：%s" % why, True)
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    ck("守卫被 search() 真正调用（非孤立函数）",
       "assert_filter_applied(filters, query)" in src)

    print("== 5. 参数校验 ==")
    try:
        search("x", sort="updated")
        ck("非法 sortBy 被拒", False, "未抛错")
    except GuardError:
        ck("非法 sortBy 被拒", True)
    except Exception as e:
        ck("非法 sortBy 被拒", False, "抛了非 GuardError: %r" % e)
    try:
        search("")
        ck("空 query 被拒", False, "未抛错")
    except GuardError:
        ck("空 query 被拒", True)
    except Exception as e:
        ck("空 query 被拒", False, "抛了非 GuardError: %r" % e)

    print("== 6. limit 夹取到 1..50 ==")
    import inspect
    sig = inspect.getsource(search)
    ck("limit 上限夹取存在", "LIMIT_MAX" in sig and "min(" in sig)

    print("== 7. MCP 协议头 ==")
    ck("带 MCP-Protocol-Version 头", "MCP-Protocol-Version" in src)
    ck("读 HTTP 200 上的 JSON-RPC error", 'd.get("error")' in src)

    print("== 8. 额度自省（读头 + 跨进程落盘）==")
    _record_quota({"x-ratelimit-daily-limit": "50", "x-ratelimit-daily-remaining": "49",
                   "x-ratelimit-minute-limit": "10", "x-ratelimit-minute-remaining": "9",
                   "x-ratelimit-daily-reset": "1792713600"})
    ck("日额度读入", _LAST_QUOTA["daily_remaining"] == 49)
    ck("分钟额度读入", _LAST_QUOTA["minute_remaining"] == 9)
    _LAST_QUOTA["daily_remaining"] = None
    _load_quota()
    ck("额度跨进程读回", _LAST_QUOTA["daily_remaining"] == 49,
       "got %r" % _LAST_QUOTA["daily_remaining"])

    print("== 9. 端点常量 ==")
    ck("REST v1 端点正确", REST_SEARCH == "https://skillsmp.com/api/v1/skills/search")
    ck("MCP 端点正确", MCP_URL == "https://skillsmp.com/mcp")

    print("")
    if fails:
        print("自检结果：%d 条 FAIL —— %s" % (len(fails), ", ".join(fails)))
        return 1
    print("自检结果：全部 PASS（%d 组断言）" % 9)
    return 0


# ---------------------------------------------------------------- CLI

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    api_key = os.environ.get(API_KEY_ENV)

    def opt(flag, cast=str):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                return cast(argv[i + 1])
        return None

    try:
        if cmd == "self-test":
            return self_test()

        if cmd == "search":
            q = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else opt("--q")
            if not q:
                print("用法：search <query> [--limit N] [--sort ...] [--language zh] [--category slug]")
                return 2
            res = search(q, limit=opt("--limit", int) or 20, sort=opt("--sort") or "stars",
                         language=opt("--language"), category=opt("--category"), api_key=api_key)
            if "--json" in argv:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print_search(res)
            return 0

        if cmd == "detail":
            if len(argv) < 2:
                print("用法：detail <skill_id>")
                return 2
            d = detail(argv[1], api_key=api_key)
            if "--json" in argv:
                print(json.dumps(d, ensure_ascii=False, indent=2))
            else:
                print_detail(d)
            return 0

        if cmd == "categories":
            d = categories(domain=opt("--domain"), api_key=api_key)
            if "--json" in argv:
                print(json.dumps(d, ensure_ascii=False, indent=2))
                return 0
            for dom in d.get("domains") or []:
                print("[%s] %s" % (dom.get("domain"), dom.get("domainName")))
                for c in dom.get("categories") or []:
                    print("   %-28s %-30s %s" % (c.get("slug"), c.get("name"), c.get("count")))
            return 0

        if cmd == "quota":
            _load_quota()
            print(json.dumps(_LAST_QUOTA, ensure_ascii=False, indent=2))
            if _LAST_QUOTA["daily_remaining"] is None:
                print("（还没有调用过；跑一次 search 才会拿到 x-ratelimit-* 头并落盘）")
            else:
                print("（数据来自上次真实调用的响应头，落盘于 %s）" % _quota_state_path())
            return 0

    except GuardError as e:
        print("守卫失败：%s" % e, file=sys.stderr)
        return 3
    except Exception as e:
        print("错误：%r" % e, file=sys.stderr)
        return 4

    print("未知命令：%s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
