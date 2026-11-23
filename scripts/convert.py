import re
import urllib.request
from pathlib import Path
from urllib.parse import quote

UPSTREAM_DIR = Path("upstream_repo")
OUTPUT_DIR = Path("Shadowrocket")
RAW_BASE = "https://raw.githubusercontent.com/Moli-X/Resources/main"

for sub in ("Loon", "QX", "Script", "External"):
    (OUTPUT_DIR / sub).mkdir(parents=True, exist_ok=True)

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
    "lths": "聊天话术VIP",
}

IGNORE_KEYWORDS = (
    "http", "github", "t.me", "仓库", "地址", "频道", "电报", "群组",
    "作者", "更新", "时间", "日期", "反馈", "交流", "禁止", "转载",
    "声明", "免责", "脚本", "项目", "主页", "整理", "收集", "tg"
)


def to_raw_url(url: str) -> str:
    """将 github.com/xxx/blob/ 链接转为 raw.githubusercontent.com 直链"""
    if "github.com/" in url and "/blob/" in url:
        return url.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")
    return url


def fetch_url(url: str) -> str:
    """下载远程文件内容，失败时返回空字符串"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"跳过无法下载的外链 {url}: {e}")
        return ""


def parse_readme() -> tuple[dict, list]:
    """解析 Readme.md：返回 (文件名->中文名映射, 外部链接列表)"""
    mapping = {}
    external_links = []
    seen_urls = set()

    readme = UPSTREAM_DIR / "Readme.md"
    if not readme.exists():
        return mapping, external_links

    text = readme.read_text(encoding="utf-8", errors="ignore")

    def process_cells(cells: list[str]):
        for i, cell in enumerate(cells):
            # 提取链接（兼容 Markdown [text](url) 和 HTML href="url"）
            url_m = re.search(r"(?:\]\(|href=[\"'])(https?://[^\"'\)\s]+)", cell)
            file_m = re.search(r"([A-Za-z0-9_\-\.]+\.(?:conf|plugin|snippet|js))", cell)
            if not file_m:
                continue

            fname = file_m.group(1)
            stem = Path(fname).stem.lower()
            desc = ""
            if i > 0:
                desc = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cells[i - 1])
                desc = re.sub(r"<[^>]+>", "", desc).strip()
                if desc and not desc.isdigit() and re.search(r"[\u4e00-\u9fff]", desc):
                    mapping[stem] = desc

            if url_m:
                raw_url = to_raw_url(url_m.group(1))
                # 仅收集指向外部仓库的链接（非 Moli-X/Resources 本仓库）
                if "Moli-X/Resources" not in raw_url and raw_url not in seen_urls:
                    seen_urls.add(raw_url)
                    external_links.append((desc or Path(fname).stem, fname, raw_url))

    for line in text.splitlines():
        if "|" in line:
            process_cells([c.strip() for c in line.strip("|").split("|")])

    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)
        if tds:
            process_cells([td.strip() for td in tds])

    return mapping, external_links


def extract_chinese_hint(content: str) -> str:
    for line in content.splitlines()[:30]:
        line = line.strip()
        if not line:
            continue
        if line.startswith(("#!name=", "#!desc=")):
            val = line.split("=", 1)[1].strip()
            if val and not any(k in val.lower() for k in IGNORE_KEYWORDS):
                return val
        if line.startswith(("#", "//", ";", "*", "/*")):
            text = line.lstrip("#/;=*- ").rstrip("=*-/ ").strip()
            if not text or not re.search(r"[\u4e00-\u9fff]", text):
                continue
            if any(k in text.lower() for k in IGNORE_KEYWORDS):
                continue
            return text[:35]
    return ""


def get_display_name(filename: str, content: str, readme_map: dict, meta_name: str = "") -> str:
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


def parse_qx(content: str, filename: str, readme_map: dict, custom_name: str = ""):
    rewrites, scripts, mitms = [], [], []
    script_idx = 1

    cn_name = custom_name or get_display_name(filename, content, readme_map)
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

    if not rewrites and not scripts:
        return None, None
    return cn_name, build_sgmodule(cn_name, desc, rewrites, scripts, mitms)


def parse_loon(content: str, filename: str, readme_map: dict, custom_name: str = ""):
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

    if not rewrites and not scripts and not rules:
        return None, None
    cn_name = custom_name or get_display_name(filename, content, readme_map, meta_name)
    return cn_name, build_sgmodule(cn_name, desc, rewrites, scripts, mitms, rules)


def parse_js_script(content: str, raw_js_url: str, filename: str, readme_map: dict, custom_name: str = ""):
    rewrites, scripts, mitms = [], [], []
    script_idx = 1

    for raw_line in content.splitlines()[:100]:
        line = raw_line.strip().lstrip("/*# ").strip()
        if not line:
            continue

        if re.match(r"^hostname\s*=", line, flags=re.I):
            hosts = line.split("=", 1)[1].strip()
            hosts = hosts.replace("%APPEND%", "").replace("%INSERT%", "").strip()
            if hosts:
                mitms.extend([h.strip() for h in hosts.split(",") if h.strip()])
            continue

        parts = line.split()
        if len(parts) >= 3 and parts[1] == "url":
            pattern, action = parts[0], parts[2].lower()
            stype_map = {
                "script-response-body": ("http-response", "1"),
                "script-request-body": ("http-request", "1"),
                "script-response-header": ("http-response", "0"),
                "script-request-header": ("http-request", "0"),
            }
            if action in stype_map:
                stype, req_body = stype_map[action]
                scripts.append(
                    f"{filename}_{script_idx} = type={stype}, pattern={pattern}, "
                    f"requires-body={req_body}, max-size=0, script-path={raw_js_url}"
                )
                script_idx += 1
            elif action in ("reject", "reject-200", "reject-img", "reject-dict", "reject-array"):
                rewrites.append(f"{pattern} - {action}")

    if not scripts and not rewrites:
        return None, None

    cn_name = custom_name or get_display_name(filename, content, readme_map)
    desc = f"来源: {raw_js_url}"
    return cn_name, build_sgmodule(cn_name, desc, rewrites, scripts, mitms)


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


def write_index(loon_items: list, qx_items: list, script_items: list, ext_items: list):
    lines = [
        "# Shadowrocket 模块中文目录",
        "",
        "点击对应模块进入文件页面后，点击右上角 **Raw** 即可复制订阅链接导入小火箭。",
        "",
    ]

    sections = [
        ("Readme 外链抓取模块（含 lths 等独立解锁）", "External", ext_items),
        ("Loon 转换模块", "Loon", loon_items),
        ("Quantumult X 转换模块", "QX", qx_items),
        ("本仓库 Script 目录模块", "Script", script_items),
    ]

    for title, folder, items in sections:
        if not items:
            continue
        lines.extend([f"## {title}", "", "| 中文功能 | 模块文件 |", "|---|---|"])
        for cn_name, fname in sorted(items, key=lambda x: x[1].lower()):
            lines.append(f"| {cn_name} | [{fname}](./{folder}/{fname}) |")
        lines.append("")

    (OUTPUT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    readme_map, external_links = parse_readme()
    loon_items, qx_items, script_items, ext_items = [], [], [], []

    # 1. 本地 Loon 目录
    loon_dir = UPSTREAM_DIR / "Loon"
    if loon_dir.exists():
        for file in loon_dir.rglob("*.plugin"):
            content = file.read_text(encoding="utf-8", errors="ignore")
            cn_name, out = parse_loon(content, file.stem, readme_map)
            if out:
                fname = f"{file.stem}.sgmodule"
                (OUTPUT_DIR / "Loon" / fname).write_text(out, encoding="utf-8")
                loon_items.append((cn_name, fname))

    # 2. 本地 Rewrite 目录
    qx_dir = UPSTREAM_DIR / "Rewrite"
    if qx_dir.exists():
        for ext in ("*.conf", "*.snippet"):
            for file in qx_dir.rglob(ext):
                content = file.read_text(encoding="utf-8", errors="ignore")
                cn_name, out = parse_qx(content, file.stem, readme_map)
                if out:
                    fname = f"{file.stem}.sgmodule"
                    (OUTPUT_DIR / "QX" / fname).write_text(out, encoding="utf-8")
                    qx_items.append((cn_name, fname))

    # 3. 本地 Script 目录
    script_dir = UPSTREAM_DIR / "Script"
    if script_dir.exists():
        for file in script_dir.rglob("*.js"):
            content = file.read_text(encoding="utf-8", errors="ignore")
            rel_path = file.relative_to(UPSTREAM_DIR)
            raw_url = f"{RAW_BASE}/{quote(rel_path.as_posix())}"
            cn_name, out = parse_js_script(content, raw_url, file.stem, readme_map)
            if out:
                fname = f"{file.stem}.sgmodule"
                (OUTPUT_DIR / "Script" / fname).write_text(out, encoding="utf-8")
                script_items.append((cn_name, fname))

    # 4. 抓取并转换 Readme.md 中的外部仓库链接
    for desc, orig_fname, raw_url in external_links:
        content = fetch_url(raw_url)
        if not content:
            continue
        stem = Path(orig_fname).stem
        suffix = Path(orig_fname).suffix.lower()

        if suffix == ".plugin":
            cn_name, out = parse_loon(content, stem, readme_map, desc)
        elif suffix in (".conf", ".snippet"):
            cn_name, out = parse_qx(content, stem, readme_map, desc)
        elif suffix == ".js":
            cn_name, out = parse_js_script(content, raw_url, stem, readme_map, desc)
        else:
            continue

        if out:
            fname = f"{stem}.sgmodule"
            (OUTPUT_DIR / "External" / fname).write_text(out, encoding="utf-8")
            ext_items.append((cn_name, fname))

    write_index(loon_items, qx_items, script_items, ext_items)


if __name__ == "__main__":
    main()
