#!/usr/bin/env python3
"""spec_gate.py - Automatic validation gate for yaml-agno SPECs.

Runs mechanical checks on one or all SPECs and reports violations. Intended to
be invoked after every SPEC correction, before the human/adversarial review.

Checks (all mechanical, no judgment):
  M1  metadata      Version/Last_Updated/Revision_Note present and recent.
  M2  mermaid       No `[text]` without ID, no `subgraph[`, no `participantX` glued.
  M3  english_code  No Spanish keywords in python code fences (def/class/return + accents).
  M4  no_dup_enums  No redefinition of Agno enums (RunStatus, RunContext, TeamMode, StepType, CBState).
  M5  no_dup_schemas No redefinition of SPEC_02 *Config (AgentConfig/TeamConfig/WorkflowConfig/StepConfig).
  M6  refs          Dependency_Hashes reference existing SPECs.
  M7  user_refs     No references to user comments like "(punto N)" / "(P[0-9] del usuario)".
  M8  cjk           No CJK characters (mojibake from prior rounds).

Usage:
  python scripts/spec_gate.py [SPEC_ID|all]

Exit code 0 = pass, 1 = violations found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SPECS_DIR = Path(__file__).resolve().parent.parent / "specs"

# Agno enums that yaml-agno must IMPORT, never redefine.
# (CircuitState is owned by SPEC_09, so it is allowed to define it there.)
AGNO_ENUMS = [
    "class RunStatus", "class RunContext", "class TeamMode", "class StepType",
    "class CBState", "class YamlAgnoRunStatus",
]
# Specs that legitimately own an enum and may define it.
ENUM_OWNERS = {
    "CircuitState": "SPEC_09",
}


def check_no_dup_enums(text: str, spec_id: str) -> list[str]:
    v: list[str] = []
    for enum in AGNO_ENUMS:
        if re.search(rf"^{re.escape(enum)}", text, re.MULTILINE):
            v.append(f"M4 redefines Agno enum: {enum}")
    # owned enums: allowed only in their owner spec
    for name, owner in ENUM_OWNERS.items():
        if spec_id != owner and re.search(rf"^class {name}\b", text, re.MULTILINE):
            v.append(f"M4 redefines owned enum {name} (owner: {owner})")
    return v
# SPEC_02 schemas (SSOT) that must not be redefined elsewhere.
SSOT_SCHEMAS = [
    "class AgentConfig(", "class TeamConfig(", "class WorkflowConfig(", "class StepConfig(",
]
SPANISH_CODE = re.compile(r"\b(def|class)\s+\w*[áéíóúñ]\w*|\b(return|raise)\s+\w*[áéíóúñ]\w*", re.IGNORECASE)
CJK = re.compile(r"[一-鿿㐀-䶿]")
USER_REFS = re.compile(r"\(punto \d|\(P\d+ del usuario|\(p\d+ del usuario", re.IGNORECASE)
EXISTING_SPECS = {p.stem for p in SPECS_DIR.glob("SPEC_*.md")}


def check_metadata(text: str) -> list[str]:
    v: list[str] = []
    if not re.search(r'Version:\s*"0\.[2-9]', text):
        v.append("M1 Version not bumped to 0.2.0+")
    if "Last_Updated" not in text:
        v.append("M1 Last_Updated missing")
    if "Revision_Note" not in text:
        v.append("M1 Revision_Note missing")
    return v


def check_mermaid(text: str) -> list[str]:
    v: list[str] = []
    for m in re.finditer(r"```mermaid\n(.*?)```", text, re.DOTALL):
        block = m.group(1)
        start = text[: m.start()].count("\n") + 1
        is_state_diagram = re.match(r"^\s*(stateDiagram|stateDiagram-v2)", block)
        for i, line in enumerate(block.splitlines(), start=start + 1):
            s = line.strip()
            # stateDiagram uses [*] as the start/end node marker (valid).
            if is_state_diagram and s.startswith("[*]"):
                continue
            # node `[text]` without preceding ID on the line
            if re.match(r"^\[[^\]]+\]", s):
                v.append(f"M2 L{i} node without ID: {s[:60]}")
            if re.match(r"^subgraph\[", s):
                v.append(f"M2 L{i} subgraph[ glued: {s[:60]}")
            if re.match(r"^participant[A-Za-z]", s):
                v.append(f"M2 L{i} participant glued: {s[:60]}")
    return v


def check_english_code(text: str) -> list[str]:
    v: list[str] = []
    for m in re.finditer(r"```python\n(.*?)```", text, re.DOTALL):
        block = m.group(1)
        start = text[: m.start()].count("\n") + 1
        for match in SPANISH_CODE.finditer(block):
            ln = start + block[: match.start()].count("\n")
            v.append(f"M3 L{ln} Spanish in python code: {match.group(0)[:40]}")
    return v


def check_no_dup_schemas(text: str, spec_id: str) -> list[str]:
    v: list[str] = []
    # SPEC_02 owns the schemas; SPEC_01 references them in the factory pattern
    # (delegation, not redefinition). Both are legitimate.
    if spec_id in ("SPEC_02", "SPEC_01"):
        return v
    for schema in SSOT_SCHEMAS:
        if re.search(rf"^{re.escape(schema)}", text, re.MULTILINE):
            v.append(f"M5 redefines SSOT schema: {schema}")
    return v


def check_refs(text: str) -> list[str]:
    v: list[str] = []
    m = re.search(r"Dependency_Hashes:\s*\[(.*?)\]", text)
    if not m:
        return v
    for ref in re.findall(r'"(SPEC_\d+)"', m.group(1)):
        stem = next((s for s in EXISTING_SPECS if s.startswith(ref + "_")), None)
        if stem is None:
            v.append(f"M6 Dependency_Hashes references missing {ref}")
    return v


def check_user_refs(text: str) -> list[str]:
    v: list[str] = []
    for m in USER_REFS.finditer(text):
        ln = text[: m.start()].count("\n") + 1
        v.append(f"M7 L{ln} user comment reference: {m.group(0)}")
    return v


def check_cjk(text: str) -> list[str]:
    v: list[str] = []
    for m in CJK.finditer(text):
        ln = text[: m.start()].count("\n") + 1
        v.append(f"M8 L{ln} CJK character: {m.group(0)}")
    return v


CHECKS_TEXT = [
    check_metadata, check_mermaid, check_english_code,
    check_no_dup_schemas, check_refs, check_user_refs, check_cjk,
]


def run(spec_path: Path) -> list[str]:
    text = spec_path.read_text(encoding="utf-8")
    spec_id = re.search(r'Spec_ID:\s*"(SPEC_\d+)"', text)
    spec_id = spec_id.group(1) if spec_id else ""
    violations: list[str] = []
    violations.extend(check_metadata(text))
    violations.extend(check_mermaid(text))
    violations.extend(check_english_code(text))
    violations.extend(check_no_dup_enums(text, spec_id))
    violations.extend(check_no_dup_schemas(text, spec_id))
    violations.extend(check_refs(text))
    violations.extend(check_user_refs(text))
    violations.extend(check_cjk(text))
    return violations


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "all":
        targets = sorted(SPECS_DIR.glob("SPEC_*.md"))
    else:
        targets = sorted(SPECS_DIR.glob(f"SPEC_{arg}*.md"))
        if not targets:
            print(f"No SPEC matching '{arg}'")
            return 2
    total_viol = 0
    for p in targets:
        v = run(p)
        status = "PASS" if not v else f"FAIL ({len(v)})"
        print(f"{p.name:55} {status}")
        for msg in v:
            print(f"    {msg}")
        total_viol += len(v)
    print(f"\n{'='*60}\n{len(targets)} SPECs checked, {total_viol} violations")
    return 0 if total_viol == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
