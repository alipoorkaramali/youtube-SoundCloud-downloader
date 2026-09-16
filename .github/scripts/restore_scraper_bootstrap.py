#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bootstrap: restores patched scraper.py (only-new + auto-limit). Run after checkout."""
import base64, zlib, sys
from pathlib import Path

# Data is loaded from companion file to keep this script small for git pushes
_CHUNK_DIR = Path(__file__).resolve().parent / "_scraper_payload"

def main():
    target = Path(__file__).resolve().parent / "scraper.py"
    parts = sorted(_CHUNK_DIR.glob("part_*.b64"))
    if not parts:
        print("❌ payload chunks not found", file=sys.stderr)
        sys.exit(1)
    b64 = "".join(p.read_text() for p in parts)
    raw = zlib.decompress(base64.b64decode(b64))
    target.write_bytes(raw)
    print(f"✅ scraper.py restored ({len(raw)} bytes) → {target}")

if __name__ == "__main__":
    main()
