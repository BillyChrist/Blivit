"""Generate .clangd from PlatformIO c_cpp_properties.json for IDE diagnostics."""

from __future__ import annotations

import json
import re
from pathlib import Path

AVIONICS_ROOT = Path(__file__).resolve().parents[1]
CPP_PROPS = AVIONICS_ROOT / ".vscode" / "c_cpp_properties.json"
CLANGD_OUT = AVIONICS_ROOT / ".clangd"


def _strip_json_comments(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def main() -> None:
    raw = CPP_PROPS.read_text(encoding="utf-8")
    cfg = json.loads(_strip_json_comments(raw))
    conf = cfg["configurations"][0]

    flags: list[str] = ["-std=gnu++11", "-x", "c++"]
    for define in conf.get("defines", []):
        if define:
            flags.append(f"-D{define}")
    for include in conf.get("includePath", []):
        if include:
            flags.append(f"-I{include}")

    lines = ["CompileFlags:", "  Add:"]
    for flag in flags:
        lines.append(f"    - {json.dumps(flag)}")

    CLANGD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {CLANGD_OUT} ({len(flags)} flags)")


if __name__ == "__main__":
    main()
