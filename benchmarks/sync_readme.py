#!/usr/bin/env python
"""Copy the summary tables from benchmarks/RESULTS.md into README.md.

README.md contains two markers:
    <!-- BENCHMARK:START --> ... <!-- BENCHMARK:END -->
Everything between them is replaced with the tables from the latest run, so the
front page never drifts from the numbers that were actually measured.

    python benchmarks/sync_readme.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
RESULTS = ROOT / "benchmarks" / "RESULTS.md"
START, END = "<!-- BENCHMARK:START -->", "<!-- BENCHMARK:END -->"


def extract_block(results_md: str) -> str:
    lines = results_md.splitlines()
    keep: list[str] = []
    header_line = next((ln for ln in lines if ln.startswith("Last run:")), "")
    if header_line:
        keep.append(header_line.replace("Last run:", "Latest run:"))
        keep.append("")
    in_table = False
    for ln in lines:
        if ln.startswith("## "):
            keep.append(f"**{ln[3:].strip()}**")
            keep.append("")
            in_table = False
            continue
        if ln.startswith("|"):
            keep.append(ln)
            in_table = True
        elif in_table and not ln.strip():
            keep.append("")
            in_table = False
    return "\n".join(keep).strip() + "\n"


def main() -> None:
    if not RESULTS.exists():
        raise SystemExit("benchmarks/RESULTS.md not found - run the benchmark first")
    block = extract_block(RESULTS.read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(readme):
        raise SystemExit("README.md is missing the BENCHMARK markers")
    readme = pattern.sub(f"{START}\n{block}{END}", readme)
    README.write_text(readme, encoding="utf-8")
    print("README benchmark section updated")


if __name__ == "__main__":
    main()
