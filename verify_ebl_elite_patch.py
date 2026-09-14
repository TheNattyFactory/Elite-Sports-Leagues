#!/usr/bin/env python3
from pathlib import Path
import sys, py_compile

path=Path(sys.argv[1] if len(sys.argv)>1 else "server.py").resolve()
bridge=path.with_name("ebl_elite_bridge.py")

checks={
    "server exists":path.exists(),
    "bridge exists":bridge.exists()
}

if path.exists():
    text=path.read_text(encoding="utf-8")
    checks.update({
        "parse_qs import":"parse_qs" in text,
        "bridge import":"from ebl_elite_bridge import" in text,
        "Elite handoff route":'if p=="/auth/elite":' in text,
        "Elite status endpoint":'p=="/api/elite/status"' in text,
        "core_only guard":"USE_ELITE_CORE_AUTH" in text
    })
    try:
        py_compile.compile(str(path),doraise=True)
        checks["server syntax"]=True
    except Exception:
        checks["server syntax"]=False

if bridge.exists():
    try:
        py_compile.compile(str(bridge),doraise=True)
        checks["bridge syntax"]=True
    except Exception:
        checks["bridge syntax"]=False

for name,ok in checks.items():
    print(("PASS" if ok else "FAIL"),"-",name)

if not all(checks.values()):
    raise SystemExit(1)
