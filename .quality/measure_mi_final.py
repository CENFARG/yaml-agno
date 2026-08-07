"""Final MI + max CC per refactored file (radon 6.0.1 API)."""
import pathlib

from radon.complexity import cc_visit
from radon.metrics import h_visit, mi_compute
from radon.raw import analyze

for f in [
    r"src\yaml_agno\factories\workflow_factory.py",
    r"src\yaml_agno\factories\agentos_factory.py",
    r"src\yaml_agno\di\provider_factory.py",
    r"src\yaml_agno\workflows\condition_evaluator.py",
    r"src\yaml_agno\tools\registry.py",
]:
    src = pathlib.Path(f).read_text(encoding="utf-8")
    raw = analyze(src)
    blocks = cc_visit(src)
    max_cc = max(b.complexity for b in blocks)
    halstead = h_visit(src)
    mi = mi_compute(halstead.total.volume, max_cc, raw.sloc, raw.comments)
    print(f"{f}: MI={mi:.1f} max_cc={max_cc} sloc={raw.sloc}")
