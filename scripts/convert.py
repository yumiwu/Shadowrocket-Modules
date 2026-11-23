import re
from pathlib import Path

UPSTREAM_DIR = Path("upstream_repo")
OUTPUT_DIR = Path("Shadowrocket")

(OUTPUT_DIR / "Loon").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "QX").mkdir(parents=True, exist_ok=True)


def load_readme_map() -> dict:
    """从源仓库 Readme.md 的表格中提取 文件名 -> 中文功能 的映射"""
    mapping = {}
    readme = UPSTREAM_DIR / "Readme.md"
    if not readme.exists():
        return mapping

    for line in readme.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        for i, cell in enumerate(cells):
            # 匹配表格中的文件名，如 [ADBlock.conf](...) 或 Spotify.plugin
            m = re.search(r"([A-Za-z0-9_\-\.]+\.(?:conf|plugin|snippet|js))", cell)
            if m and i > 0:
                stem = Path(m.group(1)).stem
                desc = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cells[i - 1]).strip()
                desc = re.sub(r"<[^>]+>", "", desc).strip()
                if desc and not desc.isdigit():
                    mapping[stem.lower()] = desc
    return mapping


def extract_chinese_hint(content: str) -> str:
    """从文件前 15 行注释中提取中文说明作为兜底"""
    for line in content.splitlines()[:15]:
        line = line.strip()
        if line.startswith(("#!name=", "#!desc=")):
            val = line.split("=", 1)[1].strip()
            if val:
                return val
        if line.startswith(("#", "//", ";")):
            text = line.lstrip("#/; ").strip()
            # 过滤掉纯链接、作者信息或无意义符号，保留包含中文的说明
            if re.search(r"[\u4e00-\u9fff]", text) and not text.startswith(("http", "作者", "更新", "时间", "脚本")):
                return text[:40]
    return ""


def parse_qx(content: str, filename: str, readme_map: dict):
    rewrites, scripts, mitms = [], [], []
    script_idx = 1

    cn_name = readme_map.get(filename.lower()) or extract_chinese_hint(content) or filename
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
    name = ""
    desc = f"来源: Loon ({filename})"
    rewrites, scripts, mitms, rules = [], [], [], []
    section = ""
    script_idx = 1

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#!name="):
            name = line.split("=", 1)[1].strip()
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

    cn_name = name or readme_map.get(filename.lower()) or extract_chinese_hint(content) or filename
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
    """在 Shadowrocket/README.md 生成中文模块索引表"""
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
    for cn_name, fname in sorted(loon_items, key=lambda x: x[0]):
        lines.append(f"| {cn_name} | [{fname}](./Loon/{fname}) |")

    lines.extend([
        "",
        "## Quantumult X 转换模块",
        "",
        "| 中文功能 | 模块文件 |",
        "|---|---|",
    ])
    for cn_name, fname in sorted(qx_items, key=lambda x: x[0]):
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
