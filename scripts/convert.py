import re
from pathlib import Path

UPSTREAM_DIR = Path("upstream_repo")
OUTPUT_DIR = Path("Shadowrocket")

(OUTPUT_DIR / "Loon").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "QX").mkdir(parents=True, exist_ok=True)

# 常见缩写兜底词典（防止注释和 Readme 都没写清）
COMMON_NAMES = {
    "collections": "莫离合集（会员解锁）",
    "adblock": "莫离去广告",
    "bdy": "百度网盘",
    "bdpanadblock": "百度网盘去广告",
    "baiducloud": "百度网盘倍速",
    "mgtv": "芒果TV",
    "ximalaya": "喜马拉雅",
    "xmly": "喜马拉雅",
    "xmlyadblock": "喜马拉雅去广告",
    "saomiao": "扫描全能王",
    "smqnw": "扫描全能王VIP",
    "spotify": "Spotify会员解锁",
    "weibo": "微博去广告",
    "video": "视频去广告/解锁",
    "xhs": "小红书去广告",
    "xiaohongshu": "小红书去广告",
    "mtxiuxiu": "美图秀秀VIP",
    "search": "Safari超级搜索",
    "wps": "WPS会员解锁",
    "youtube": "YouTube去广告+画中画",
    "bilibili": "B站去广告/解锁",
    "bilibilivip": "B站去广告+1080P高码率",
    "zhihu_plus": "知乎去广告",
    "amap": "高德地图去广告",
    "douban": "豆瓣电影网页优化",
    "netease": "网易云音乐去广告",
    "qidian": "起点读书去广告",
    "pinduoduo": "拼多多去广告",
    "cainiao": "菜鸟裹裹去广告",
}

# 注释中需要跳过的垃圾信息关键词
IGNORE_KEYWORDS = (
    "http", "github", "t.me", "仓库", "地址", "频道", "电报", "群组",
    "作者", "更新", "时间", "日期", "反馈", "交流", "禁止", "转载",
    "声明", "免责", "脚本", "项目", "主页", "整理", "收集", "tg"
)


def load_readme_map() -> dict:
    """从源仓库 Readme.md（兼容 Markdown 和 HTML 表格）提取 文件名 -> 中文功能"""
    mapping = {}
    readme = UPSTREAM_DIR / "Readme.md"
    if not readme.exists():
        return mapping

    text = readme.read_text(encoding="utf-8", errors="ignore")

    # 1. 解析 Markdown 表格行
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        for i, cell in enumerate(cells):
            m = re.search(r"([A-Za-z0-9_\-\.]+\.(?:conf|plugin|snippet|js))", cell)
            if m and i > 0:
                stem = Path(m.group(1)).stem.lower()
                desc = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cells[i - 1])
                desc = re.sub(r"<[^>]+>", "", desc).strip()
                if desc and not desc.isdigit() and re.search(r"[\u4e00-\u9fff]", desc):
                    mapping[stem] = desc

    # 2. 解析 HTML 表格行 (<tr><td>功能</td><td>链接</td></tr>)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)
        for i, td in enumerate(tds):
            m = re.search(r"([A-Za-z0-9_\-\.]+\.(?:conf|plugin|snippet|js))", td)
            if m and i > 0:
                stem = Path(m.group(1)).stem.lower()
                desc = re.sub(r"<[^>]+>", "", tds[i - 1]).strip()
                if desc and not desc.isdigit() and re.search(r"[\u4e00-\u9fff]", desc):
                    mapping[stem] = desc

    return mapping


def extract_chinese_hint(content: str) -> str:
    """从文件前 25 行注释中提取真正的中文功能说明，过滤仓库链接等垃圾行"""
    for line in content.splitlines()[:25]:
        line = line.strip()
        if not line:
            continue

        # 优先取标准元信息里的 #!name= 或 #!desc=
        if line.startswith(("#!name=", "#!desc=")):
            val = line.split("=", 1)[1].strip()
            if val and not any(k in val.lower() for k in IGNORE_KEYWORDS):
                return val

        if line.startswith(("#", "//", ";")):
            text = line.lstrip("#/;=*- ").rstrip("=*- ").strip()
            if not text or not re.search(r"[\u4e00-\u9fff]", text):
                continue
            # 只要包含垃圾关键词就跳过
            if any(k in text.lower() for k in IGNORE_KEYWORDS):
                continue
            return text[:35]

    return ""


def get_display_name(filename: str, content: str, readme_map: dict, meta_name: str = "") -> str:
    """按优先级确定最终中文名：插件自带name > Readme表格 > 常见词典 > 有效注释 > 原文件名"""
    key = filename.lower()
    if meta_name and not any(k in meta_name.lower() for k in IGNORE_KEYWORDS):
        return meta_name
    if key in readme_map:
        return readme_map[key]
    if key in COMMON_NAMES:
        return COMMON_NAMES[key]
    hint = extract_chinese_hint(content)
    if hint:
        return hint
    return filename


def parse_qx(content: str, filename: str, readme_map: dict):
    rewrites, scripts, mitms = [], [], []
    script_idx = 1

    cn_name = get_display_name(filename, content, readme_map)
    desc = f"来源: QX ({filename})"

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue

        if line.lower().startswith("hostname"):
            hosts = line.split("=", 1)[1].strip()
            hosts = hosts.replace("%APPEND%", "").replace("%INSERT%", "").strip()
            if hosts:
                mitms.extend([h.strip() for h in hosts.split(",") if h.strip()])
            continue

        parts = line.split()
        if len(parts) < 3 or parts[1] != "url":
            continue

        pattern, action = parts[0], parts[2].lower()

        if action in ("reject", "reject-200", "reject-img", "reject-dict", "reject-array"):
            rewrites.append(f"{pattern} - {action}")
        elif action in ("302", "307") and len(parts) >= 4:
            rewrites.append(f"{pattern} {parts[3]} {action}")
        elif action.startswith("script-") and len(parts) >= 4:
            script_url = parts[3]
            stype_map = {
                "script-response-body": ("http-response", "1"),
                "script-request-body": ("http-request", "1"),
                "script-response-header": ("http-response", "0"),
                "script-request-header": ("http-request", "0"),
            }
            if action not in stype_map:
                continue
            stype, req_body = stype_map[action]
            scripts.append(
                f"{filename}_{script_idx} = type={stype}, pattern={pattern}, "
                f"requires-body={req_body}, max-size=0, script-path={script_url}"
            )
            script_idx += 1

    return cn_name, build_sgmodule(cn_name, desc, rewrites, scripts, mitms)


def parse_loon(content: str, filename: str, readme_map: dict):
    meta_name = ""
    desc = f"来源: Loon ({filename})"
    rewrites, scripts, mitms, rules = [], [], [], []
    section = ""
    script_idx = 1

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#!name="):
            meta_name = line.split("=", 1)[1].strip()
            continue
        if line.startswith("#!desc="):
            desc = line.split("=", 1)[1].strip()
            continue
        if line.startswith(("#", ";", "//")):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue

        if section == "[rewrite]":
            parts = line.split()
            if len(parts) >= 2:
                pattern, action = parts[0], parts[1].lower()
                if action in ("reject", "reject-200", "reject-img", "reject-dict", "reject-array"):
                    rewrites.append(f"{pattern} - {action}")
                elif action in ("302", "307") and len(parts) >= 3:
                    rewrites.append(f"{pattern} {parts[2]} {action}")

        elif section == "[script]":
            m = re.match(r"^(http-request|http-response)\s+(\S+)\s+(.*)$", line)
            if m:
                stype, pattern, params = m.groups()
                params = params.replace("requires-body=true", "requires-body=1")
                params = params.replace("requires-body=false", "requires-body=0")
                tag_match = re.search(r"tag\s*=\s*([^,]+)", params)
                tag = tag_match.group(1).strip() if tag_match else f"{filename}_{script_idx}"
                params = re.sub(r",?\s*tag\s*=\s*[^,]+", "", params).strip(" ,")
                scripts.append(f"{tag} = type={stype}, pattern={pattern}, {params}")
                script_idx += 1

        elif section == "[mitm]":
            if line.lower().startswith("hostname"):
                hosts = line.split("=", 1)[1].strip()
                hosts = hosts.replace("%APPEND%", "").replace("%INSERT%", "").strip()
                if hosts:
                    mitms.extend([h.strip() for h in hosts.split(",") if h.strip()])

        elif section == "[rule]":
            rules.append(line)

    cn_name = get_display_name(filename, content, readme_map, meta_name)
    return cn_name, build_sgmodule(cn_name, desc, rewrites, scripts, mitms, rules)


def build_sgmodule(name, desc, rewrites, scripts, mitms, rules=None) -> str:
    lines = [f"#!name={name}", f"#!desc={desc}", ""]
    if rules:
        lines.extend(["[Rule]", *rules, ""])
    if rewrites:
        lines.extend(["[URL Rewrite]", *rewrites, ""])
    if scripts:
        lines.extend(["[Script]", *scripts, ""])
    if mitms:
        unique_hosts = list(dict.fromkeys(mitms))
        lines.extend(["[MITM]", f"hostname = %APPEND% {', '.join(unique_hosts)}", ""])
    return "\n".join(lines)


def write_index(loon_items: list, qx_items: list):
    lines = [
        "# Shadowrocket 模块中文目录",
        "",
        "点击对应模块进入文件页面后，点击右上角 **Raw** 即可复制订阅链接导入小火箭。",
        "",
        "## Loon 转换模块",
        "",
        "| 中文功能 | 模块文件 |",
        "|---|---|",
    ]
    for cn_name, fname in sorted(loon_items, key=lambda x: x[1].lower()):
        lines.append(f"| {cn_name} | [{fname}](./Loon/{fname}) |")

    lines.extend([
        "",
        "## Quantumult X 转换模块",
        "",
        "| 中文功能 | 模块文件 |",
        "|---|---|",
    ])
    for cn_name, fname in sorted(qx_items, key=lambda x: x[1].lower()):
        lines.append(f"| {cn_name} | [{fname}](./QX/{fname}) |")

    (OUTPUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    readme_map = load_readme_map()
    loon_items, qx_items = [], []

    loon_dir = UPSTREAM_DIR / "Loon"
    if loon_dir.exists():
        for file in loon_dir.rglob("*.plugin"):
            content = file.read_text(encoding="utf-8", errors="ignore")
            cn_name, out = parse_loon(content, file.stem, readme_map)
            fname = f"{file.stem}.sgmodule"
            (OUTPUT_DIR / "Loon" / fname).write_text(out, encoding="utf-8")
            loon_items.append((cn_name, fname))

    qx_dir = UPSTREAM_DIR / "Rewrite"
    if qx_dir.exists():
        for ext in ("*.conf", "*.snippet"):
            for file in qx_dir.rglob(ext):
                content = file.read_text(encoding="utf-8", errors="ignore")
                cn_name, out = parse_qx(content, file.stem, readme_map)
                fname = f"{file.stem}.sgmodule"
                (OUTPUT_DIR / "QX" / fname).write_text(out, encoding="utf-8")
                qx_items.append((cn_name, fname))

    write_index(loon_items, qx_items)


if __name__ == "__main__":
    main()
