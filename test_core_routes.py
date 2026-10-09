"""Local HTTP integration for a reviewed ESL source tree, not live production.

Usage: ESL_REPO_ROOT=/path/to/patched/esl python tests/test_core_routes.py
"""
import os,sys,json,socket,subprocess,tempfile,time,urllib.request,urllib.error,http.cookiejar,sqlite3
from pathlib import Path

root=Path(os.environ['ESL_REPO_ROOT'])
assert (root/'server.py').is_file() and (root/'esl_ebl_account_link.py').is_file(), 'Need patched repo'
with socket.socket() as s:
    s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='esl_link_route_test_') as td:
    env=dict(os.environ,PORT=str(port),ELITE_ENV='development',ELITE_DB_PATH=str(Path(td)/'test.db'),ELITE_PUBLIC_REGISTRATION='1',ELITE_SEED_DEMO='0',ELITE_EBL_ACCOUNT_LINK_SECRET='independent-proof-key-very-long-and-test-only-0123456789')
    p=subprocess.Popen([sys.executable,'server.py'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        url=f'http://127.0.0.1:{port}'
        jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        def ask(path,data=None,headers=None):
            body=None if data is None else json.dumps(data).encode()
            req=urllib.request.Request(url+path,data=body,headers={'Content-Type':'application/json',**(headers or {})})
            try:
                with opener.open(req,timeout=3) as resp:return resp.status,json.loads(resp.read())
            except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
        for _ in range(60):
            try:
                status,_=ask('/api/health');
                if status==200:break
            except Exception:time.sleep(.1)
        else:raise AssertionError('Core did not start')
        status,d=ask('/api/auth/register',{'username':'proof_tester','email':'proof@example.test','password':'secure-testing-1234','accept_terms':True,'accept_privacy':True,'accept_community_rules':True})
        assert status==201,(status,d)
        status,d2=ask('/api/auth/verify-email',{'token':d['dev_verification_token']});assert status==200,(status,d2)
        csrf=next(c.value for c in jar if c.name=='elite_csrf')
        headers={'X-CSRF-Token':csrf}
        status,d=ask('/api/integrations/baseball/link',{'external_user_id':'101','external_username':'victim','role':'PLAYER'},headers)
        assert status==401 and d['error']=='INVALID_LINK_PROOF',(status,d)
        status,d=ask('/api/gateway/link-external',{'sport':'baseball','external_user_id':'101'})
        assert status==410 and d['error']=='SPORT_OWNERSHIP_PROOF_REQUIRED',(status,d)
        print('PASS legacy raw-ID and gateway-ticket linking blocked over HTTP')
        # A proof from a simulated signed-in EBL user's server-side issuer succeeds.
        import importlib.util
        proof_path=Path(__file__).resolve().parent.parent/'EBL/ebl_elite_account_link.py'
        spec=importlib.util.spec_from_file_location('issuer',proof_path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        os.environ['EBL_ELITE_ACCOUNT_LINK_SECRET']=env['ELITE_EBL_ACCOUNT_LINK_SECRET']
        proof=mod.issue({'id':789,'username':'RealBallplayer','role':'PLAYER'})['proof']
        status,d=ask('/api/integrations/baseball/link',{'proof':proof},headers)
        assert status==200 and d['link']['external_user_id']=='789',(status,d)
        status,d=ask('/api/integrations/baseball/status')
        assert status==200 and d['connected'] is True and d['link']['external_user_id']=='789',(status,d)
        print('PASS EBL-signed proof links account and hub status reflects connection')
        status,d=ask('/api/integrations/baseball/link',{'proof':proof},headers)
        assert status==409 and d['error']=='LINK_PROOF_ALREADY_USED',(status,d)
        c=sqlite3.connect(env['ELITE_DB_PATH']);cnt=c.execute('SELECT COUNT(*) FROM sport_account_links').fetchone()[0];c.close()
        assert cnt==1
        print('PASS replay rejected at HTTP route; database link unchanged')
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
print('ALL LOCAL ESL HTTP LINK ROUTE TESTS PASSED')
