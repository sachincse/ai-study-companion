#!/usr/bin/env python
"""Download openly licensed textbooks used as real sample notes and benchmark corpus.

Nothing here is fabricated: these are complete, Creative Commons licensed books
that map onto AKTU subjects. They are not committed to git (size); run this
script once and they land in ``data/sample_notes/``.

    python scripts/fetch_open_notes.py            # all books
    python scripts/fetch_open_notes.py ods dbdesign  # a subset
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "sample_notes"

BOOKS: dict[str, dict] = {
    "ods": {
        "file": "Open_Data_Structures_(Morin)_CC-BY-2.5.pdf",
        "title": "Open Data Structures (Edition 0.1G, pseudocode) - Pat Morin",
        "license": "CC BY 2.5",
        "subject": "BCS301 Data Structure / BCS503 Design and Analysis of Algorithm",
        "urls": [
            "https://opendatastructures.org/ods-python.pdf",
            "https://opendatastructures.org/versions/edition-0.1g/ods-python.pdf",
        ],
    },
    "dbdesign": {
        "file": "Database_Design_2nd_Edition_(Watt_Eng)_CC-BY-4.0.pdf",
        "title": "Database Design - 2nd Edition - Adrienne Watt & Nelson Eng (BCcampus)",
        "license": "CC BY 4.0",
        "subject": "BCS501 Database Management System",
        "urls": [
            "https://opentextbc.ca/dbdesign01/open/download?type=pdf",
            "https://yc-prod-openlibrary-repo.ecampusontario.ca/jspui/bitstream/123456789/247/16/Database-Design-2nd-Edition-1540829576.pdf",
        ],
    },
    "osm": {
        "file": "Operating_Systems_and_Middleware_(Hailperin)_CC-BY-SA-3.0.pdf",
        "title": "Operating Systems and Middleware: Supporting Controlled Interaction (rev 1.2) - Max Hailperin",
        "license": "CC BY-SA 3.0 (check the licence page inside the PDF)",
        "subject": "BCS401 Operating System",
        "urls": [
            "https://archive.org/download/osm-rev1.2/osm-rev1.2.pdf",
            "https://open.umn.edu/opentextbooks/formats/33",
            "https://gustavus.edu/mcs/max/os-book/osm-rev1.3.1.pdf",
        ],
    },
    "dmoi": {
        "file": "Discrete_Mathematics_An_Open_Introduction_3e_(Levin)_CC-BY-SA-4.0.pdf",
        "title": "Discrete Mathematics: An Open Introduction (3rd ed.) - Oscar Levin",
        "license": "CC BY-SA 4.0",
        "subject": "BCS303 Discrete Structures and Theory of Logic",
        "urls": [
            "https://discrete.openmathbooks.org/pdfs/dmoi3-tablet.pdf",
            "https://discrete.openmathbooks.org/pdfs/dmoi-tablet.pdf",
            "https://pld.cs.luc.edu/courses/163/now/levin.pdf",
        ],
    },
}


def download(url: str, target: Path) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AI Study Companion sample fetcher)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        print(f"   failed: {url} ({exc})")
        return False
    if not data.startswith(b"%PDF"):
        print(f"   not a PDF: {url}")
        return False
    target.write_bytes(data)
    print(f"   saved {target.name} ({len(data) / 1e6:.1f} MB)")
    return True


def main(argv: list[str]) -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    wanted = [a for a in argv if a in BOOKS] or list(BOOKS)
    failures = 0
    for key in wanted:
        book = BOOKS[key]
        target = DEST / book["file"]
        print(f"- {book['title']} [{book['license']}]")
        if target.exists() and target.stat().st_size > 100_000:
            print(f"   already present ({target.stat().st_size / 1e6:.1f} MB)")
            continue
        if not any(download(u, target) for u in book["urls"]):
            failures += 1
    print("\nAttribution and licence details: data/sample_notes/SOURCES.md")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
