import re
from pathlib import Path

UPSTREAM_DIR = Path("upstream_repo")
OUTPUT_DIR = Path("Shadowrocket")

# 清理旧文件并重建输出目录
(OUTPUT_DIR / "Loon").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "QX").mkdir(parents=True, exist_ok=True)


def parse_qx(content: str, filename: str) -> str:
    """将 Quantumult X 重写 (.conf / .snippet) 转换为 Shadowrocket .sgmodule"""
    rewrites, scripts, mitms = [], [], []
    script_idx = 1

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue

        # 提取 hostname
        if line.lower().startswith("hostname"):
            hosts = line.split("=", 1)[1].strip()
            hosts = hosts.replace("%APPEND%", "").replace("%INSERT%", "").strip()
            if hosts:
                mitms.extend([h.strip() for h in hosts.split(",") if h.strip()])
            continue

        parts = line.split()
        if len(parts) < 3 or parts[1] != "url":
            continue

        pattern = parts[0]
        action = parts[2].lower()

        # 1. URL 拒绝类规则
        if action in ("reject", "reject-200", "reject-img", "reject-dict", "reject-array"):
            rewrites.append(f"{pattern} - {action}")

        # 2. URL 重定向类规则
        elif action in ("302", "307") and len(parts) >= 4:
            rewrites.append(f"{pattern} {parts[3]} {action}")

        # 3. 脚本类规则
        elif action.startswith("script-") and len(parts) >= 4:
            script_url = parts[3]
            if action == "script-response-body":
                stype, req_body = "http-response", "1"
            elif action == "script-request-body":
                stype, req_body = "http-request", "1"
            elif action == "script-response-header":
                stype, req_body = "http-response", "0"
            elif action == "script-request-header":
                stype, req_body = "http-request", "0"
            else:
                # 跳过 script-echo-response 等不直接兼容的语法
                continue

            scripts.append(
                f"{filename}_{script_idx} = type={stype}, pattern={pattern}, "
                f"requires-body={req_body}, max-size=0, script-path={script_url}"
            )
            script_idx += 1

    return build_sgmodule(filename, f"Converted from QX: {filename}", rewrites, scripts, mitms)


def parse_loon(content: str, filename: str) -> str:
    """将 Loon 插件 (.plugin) 转换为 Shadowrocket .sgmodule"""
    name = filename
    desc = f"Converted from Loon: {filename}"
    rewrites, scripts, mitms, rules = [], [], [], []
    section = ""
    script_idx = 1

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # 提取元信息
        if line.startswith("#!name="):
            name = line.split("=", 1)[1].strip()
            continue
        if line.startswith("#!desc="):
            desc = line.split("=", 1)[1].strip()
            continue
        if line.startswith(("#", ";", "//")):
            continue

        # 识别区块头
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue

        if section == "[rewrite]":
            parts = line.split()
            if len(parts) >= 2:
                pattern = parts[0]
                action = parts[1].lower()
                if action in ("reject", "reject-200", "reject-img", "reject-dict", "reject-array"):
                    rewrites.append(f"{pattern} - {action}")
                elif action in ("302", "307") and len(parts) >= 3:
                    rewrites.append(f"{pattern} {parts[2]} {action}")

        elif section == "[script]":
            # 匹配 Loon 脚本格式: http-response ^regex script-path=..., tag=...
            m = re.match(r"^(http-request|http-response)\s+(\S+)\s+(.*)$", line)
            if m:
                stype, pattern, params = m.groups()
                # 统一布尔值格式并提取 tag 作为脚本名
                params = params.replace("requires-body=true", "requires-body=1")
                params = params.replace("requires-body=false", "requires-body=0")
                tag_match = re.search(r"tag\s*=\s*([^,]+)", params)
                tag = tag_match.group(1).strip() if tag_match else f"{filename}_{script_idx}"
                # 移除 tag 字段，改为 Surge/Shadowrocket 键值对格式
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

    return build_sgmodule(name, desc, rewrites, scripts, mitms, rules)


def build_sgmodule(name, desc, rewrites, scripts, mitms, rules=None) -> str:
    """组装标准 Shadowrocket .sgmodule 内容"""
    lines = [f"#!name={name}", f"#!desc={desc}", ""]

    if rules:
        lines.append("[Rule]")
        lines.extend(rules)
        lines.append("")

    if rewrites:
        lines.append("[URL Rewrite]")
        lines.extend(rewrites)
        lines.append("")

    if scripts:
        lines.append("[Script]")
        lines.extend(scripts)
        lines.append("")

    if mitms:
        unique_hosts = list(dict.fromkeys(mitms))
        lines.append("[MITM]")
        lines.append(f"hostname = %APPEND% {', '.join(unique_hosts)}")
        lines.append("")

    return "\n".join(lines)


def main():
    # 1. 转换 Loon 插件
    loon_dir = UPSTREAM_DIR / "Loon"
    if loon_dir.exists():
        for file in loon_dir.rglob("*.plugin"):
            content = file.read_text(encoding="utf-8", errors="ignore")
            out = parse_loon(content, file.stem)
            (OUTPUT_DIR / "Loon" / f"{file.stem}.sgmodule").write_text(out, encoding="utf-8")

    # 2. 转换 Quantumult X 重写
    qx_dir = UPSTREAM_DIR / "Rewrite"
    if qx_dir.exists():
        for ext in ("*.conf", "*.snippet"):
            for file in qx_dir.rglob(ext):
                content = file.read_text(encoding="utf-8", errors="ignore")
                out = parse_qx(content, file.stem)
                (OUTPUT_DIR / "QX" / f"{file.stem}.sgmodule").write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
