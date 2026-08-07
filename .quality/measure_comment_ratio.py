"""Measure comment ratio exactly like the audit: radon raw on src/."""
import json
import pathlib

from radon.raw import analyze

src_files = [p for p in pathlib.Path("src").rglob("*.py")]
tot = {"loc": 0, "comments": 0, "blank": 0}
for p in src_files:
    try:
        a = analyze(p.read_text(encoding="utf-8"))
    except Exception as e:  # metric tool: tolerate per-file parse failures
        print("ERR", p, e)
        continue
    tot["loc"] += a.loc
    tot["comments"] += a.comments
    tot["blank"] += a.blank

ratio = tot["comments"] / (tot["loc"] + tot["comments"])
print(json.dumps(tot))
print(f"comment_ratio={ratio:.1%}")
