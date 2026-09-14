#!/usr/bin/env python3
from pathlib import Path
import shutil, sys, py_compile

target=Path(sys.argv[1] if len(sys.argv)>1 else "server.py").resolve()
backups=sorted(
    target.parent.glob(f"{target.stem}.pre_elite_*{target.suffix}"),
    key=lambda p:p.stat().st_mtime,
    reverse=True
)
if not backups:
    raise SystemExit("No pre-Elite backup found.")

backup=backups[0]
py_compile.compile(str(backup),doraise=True)
shutil.copy2(backup,target)
py_compile.compile(str(target),doraise=True)

print("Restored:",backup)
print("Syntax validation: PASS")
