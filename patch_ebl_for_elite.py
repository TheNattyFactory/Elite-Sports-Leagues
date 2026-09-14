#!/usr/bin/env python3
from pathlib import Path
import datetime, py_compile, shutil, sys

AUTH_ROUTES = {
    "/api/register",
    "/api/login",
    "/api/account/recover",
    "/api/account/verify-email",
    "/api/account/request-password-reset",
    "/api/account/reset-password",
    "/api/account/resend-verification",
}

def compile_check(path):
    py_compile.compile(str(path), doraise=True)

def stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def patch_text(text):
    changes=[]

    if "from urllib.parse import urlparse, parse_qs" not in text:
        anchor="from urllib.parse import urlparse"
        if anchor not in text:
            raise RuntimeError("Missing urllib.parse anchor")
        text=text.replace(anchor,"from urllib.parse import urlparse, parse_qs",1)
        changes.append("parse_qs import")

    bridge_import="from ebl_elite_bridge import complete_elite_handoff, ELITE_AUTH_MODE, elite_core_status"
    if bridge_import not in text:
        anchor="from urllib.error import HTTPError, URLError"
        if anchor not in text:
            raise RuntimeError("Missing urllib.error anchor")
        text=text.replace(anchor,anchor+"\n"+bridge_import,1)
        changes.append("Elite bridge import")

    if 'if p=="/auth/elite":' not in text:
        anchors=[
            '    def do_GET(self):\n        p=urlparse(self.path).path\n\n        if p.startswith("/api/"):\n',
            '    def do_GET(self):\n        p = urlparse(self.path).path\n\n        if p.startswith("/api/"):\n'
        ]
        use=next((a for a in anchors if a in text),None)
        if not use:
            raise RuntimeError("Missing H.do_GET anchor")

        p_line="        p=urlparse(self.path).path\n" if "p=urlparse" in use else "        p = urlparse(self.path).path\n"
        route=(
            "    def do_GET(self):\n"
            +p_line+
            "\n"
            '        if p=="/auth/elite":\n'
            "            qs=parse_qs(urlparse(self.path).query)\n"
            '            token=(qs.get("elite_token") or [""])[0].strip()\n'
            "            if not token:\n"
            '                return self.out({"error":"MISSING_ELITE_TOKEN"},400)\n'
            "            result,err,status=complete_elite_handoff(self,token,conn,pwhash,new_session)\n"
            "            if err:\n"
            '                return self.out({"error":err},status)\n'
            "            self.send_response(302)\n"
            '            self.send_header("Location","/")\n'
            '            self.send_header("Set-Cookie",f"sid={result[\'sid\']}; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000")\n'
            "            self.end_headers()\n"
            "            return\n\n"
            '        if p.startswith("/api/"):\n'
        )
        text=text.replace(use,route,1)
        changes.append("/auth/elite route")

    if 'p=="/api/elite/status"' not in text:
        anchor='        if p=="/api/me":return self.out({"user":u})\n'
        if anchor not in text:
            raise RuntimeError("Missing /api/me anchor")
        addition=(
            anchor+
            '        if p=="/api/elite/status":\n'
            "            core=elite_core_status()\n"
            '            return self.out({"ok":True,"auth_mode":ELITE_AUTH_MODE,"elite_core":core,"bridge_version":"1.1"})\n'
        )
        text=text.replace(anchor,addition,1)
        changes.append("/api/elite/status")

    if "USE_ELITE_CORE_AUTH" not in text:
        anchor="    def api_post(self,p):\n"
        if anchor not in text:
            raise RuntimeError("Missing api_post anchor")
        guard=(
            anchor+
            "        if ELITE_AUTH_MODE==\"core_only\" and p in "+repr(AUTH_ROUTES)+":\n"
            '            return self.out({"error":"USE_ELITE_CORE_AUTH","elite_core":True},410)\n'
        )
        text=text.replace(anchor,guard,1)
        changes.append("core_only guard")

    return text,changes

def main():
    path=Path(sys.argv[1] if len(sys.argv)>1 else "server.py").resolve()
    bridge=path.with_name("ebl_elite_bridge.py")

    if not path.exists():
        raise SystemExit(f"Not found: {path}")
    if not bridge.exists():
        raise SystemExit("ebl_elite_bridge.py must be beside server.py")

    compile_check(path)
    original=path.read_text(encoding="utf-8")
    patched,changes=patch_text(original)

    if patched==original:
        print("EBL server is already patched. No changes needed.")
        compile_check(path)
        compile_check(bridge)
        return

    backup=path.with_name(f"{path.stem}.pre_elite_{stamp()}{path.suffix}")
    shutil.copy2(path,backup)

    try:
        path.write_text(patched,encoding="utf-8")
        compile_check(path)
        compile_check(bridge)
    except Exception:
        shutil.copy2(backup,path)
        raise

    print("Elite bridge patch complete.")
    print("Backup:",backup)
    for c in changes:
        print(" -",c)
    print("Syntax validation: PASS")

if __name__=="__main__":
    main()
