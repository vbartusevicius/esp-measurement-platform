"""Fix the KiCad 10 fp-lib-table by removing quotes (kinet2pcb 1.1.4 bug workaround).

KiCad 10's fp-lib-table template uses quoted attribute values like
  (lib (name "Audio_Module") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/..."))
but kinet2pcb 1.1.4's regex-based parser doesn't strip quotes before the
type comparison, so '"KiCad"' != 'kicad' and every stock library is skipped.
This script removes the quotes so the parser finds all 156 stock libraries.
"""
import re

PATHS = [
    "/root/.config/kicad/fp-lib-table",
    "/root/.config/kicad/10.0/fp-lib-table",
]

for path in PATHS:
    try:
        with open(path) as f:
            tbl = f.read()
    except OSError:
        continue
    # Remove quotes around individual attribute values: (name "X") -> (name X)
    tbl = re.sub(r'\(name\s+"([^"]+)"\)', r'(name \1)', tbl)
    tbl = re.sub(r'\(type\s+"([^"]+)"\)', r'(type \1)', tbl)
    tbl = re.sub(r'\(uri\s+"([^"]+)"\)', r'(uri \1)', tbl)
    tbl = re.sub(r'\(options\s+"([^"]*)"\)', r'(options \1)', tbl)
    tbl = re.sub(r'\(descr\s+"([^"]+)"\)', r'(descr \1)', tbl)
    with open(path, "w") as f:
        f.write(tbl)
    print(f"Fixed {path}")
