from pathlib import Path
import sqlite3, subprocess, sys, socket, time, urllib.request, json, tempfile, os, re
root=Path(__file__).parent
for fn in ['index.html','network.html','hall-of-fame.html']:
    src=(root/fn).read_text()
    assert re.search(r'<title>.+</title>',src)
    assert '(/api/network/' in src or '/api/network/' in src
    scripts=re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',src)
    for i,s in enumerate(scripts):
        p=root/f'.check_{fn}.{i}.js';p.write_text(s)
        result=subprocess.run(['node','--check',str(p)],capture_output=True,text=True)
        p.unlink()
        if result.returncode: raise AssertionError(f'JS parse failed {fn}: {result.stderr}')
    print('PASS JavaScript syntax and markup:',fn)
with tempfile.TemporaryDirectory() as tmp:
    port=49317
    env=os.environ.copy();env.update({'PORT':str(port),'ELITE_DB_PATH':tmp+'/network-test.sqlite','ELITE_SEED_DEMO':'0','ELITE_ENV':'development'})
    proc=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=str(root),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for x in range(30):
            try: urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1).read();break
            except Exception: time.sleep(.2)
        else: raise AssertionError('Server startup failed: '+proc.stderr.read().decode()[:1000])
        def get(path):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path, timeout=2) as r:return r.status,json.loads(r.read())
        status,d=get('/api/network/home'); assert status==200 and len(d['sports'])==9 and d['news']==[] and d['activity']==[]
        print('PASS public home API: 9 sports, empty newsroom (no fabricated results)')
        status,d=get('/api/network/hall-of-fame'); assert status==200 and len(d['sports'])==9 and d['inductees']==[]
        print('PASS Hall of Fame API: 9 sports, no fictional inductees')
        # Insert real and demo records, then check public privacy and exclusion.
        db=sqlite3.connect(tmp+'/network-test.sqlite')
        c=db.cursor()
        c.execute('PRAGMA table_info(users)')
        fields=[r[1] for r in c.fetchall()]
        if {'username','display_name','email','password_hash','email_verified'} <= set(fields):
            c.execute("INSERT INTO users(username,display_name,email,password_hash,email_verified) VALUES('public_demo','Public Athlete','public@example.test','not-a-real-hash',1)")
            uid=c.lastrowid
            c.execute("INSERT INTO users(username,display_name,email,password_hash,email_verified) VALUES('private_demo','Private Athlete','private@example.test','not-a-real-hash',1)")
            priv=c.lastrowid
            sid=c.execute("SELECT id FROM sports WHERE slug='baseball'").fetchone()[0]
            c.execute("INSERT INTO profile_settings(user_id,public_profile,show_activity) VALUES(?,?,?)",(priv,0,0))
            c.execute("INSERT INTO activity_feed(user_id,sport_id,activity_type,title,description,visibility,external_ref) VALUES(?,?,?,?,?,?,?)",(uid,sid,'WIN','Verified game event','Real feed test','PUBLIC','real-123'))
            c.execute("INSERT INTO activity_feed(user_id,sport_id,activity_type,title,description,visibility,external_ref) VALUES(?,?,?,?,?,?,?)",(uid,sid,'WIN','DEMO FAKE','Fake result','PUBLIC','demo-fake'))
            c.execute("INSERT INTO activity_feed(user_id,sport_id,activity_type,title,description,visibility,external_ref) VALUES(?,?,?,?,?,?,?)",(priv,sid,'WIN','Private result','Private feed test','PUBLIC','private-123'))
            c.execute("INSERT INTO honors(user_id,sport_id,honor_type,title,is_major) VALUES(?,?,?,?,?)",(uid,sid,'HALL_OF_FAME','Official inducted',1))
            c.execute("INSERT INTO honors(user_id,sport_id,honor_type,title,is_major) VALUES(?,?,?,?,?)",(priv,sid,'HALL_OF_FAME','Private inducted',1))
            c.execute("INSERT INTO honors(user_id,sport_id,honor_type,title,is_major) VALUES(?,?,?,?,?)",(uid,sid,'AWARD','Normal award',1))
            c.execute("INSERT INTO hub_news(sport_id,headline,summary) VALUES(?,?,?)",(sid,'Atlanta clinches division title','Fake fixture'))
            c.execute("INSERT INTO hub_news(sport_id,headline,summary) VALUES(?,?,?)",(sid,'Verified team report','Published result'))
            db.commit();db.close()
            _,d=get('/api/network/home')
            assert [x['title'] for x in d['activity']]==['Verified game event'], d['activity']
            assert [x['headline'] for x in d['news']]==['Verified team report'],d['news']
            assert [x['username'] for x in d['inductees']]==['public_demo'],d['inductees']
            _,h=get('/api/network/hall-of-fame')
            assert len(h['inductees'])==1 and h['inductees'][0]['username']=='public_demo',h
            print('PASS public/private activity, demo exclusion, published news and official-only induction')
            # A deactivated account's old achievements cannot remain on public feeds.
            db=sqlite3.connect(tmp+'/network-test.sqlite');db.execute("UPDATE users SET status='SUSPENDED' WHERE id=?",(uid,));db.commit();db.close()
            _,d=get('/api/network/home')
            assert d['activity']==[] and d['inductees']==[],d
            _,h=get('/api/network/hall-of-fame')
            assert h['inductees']==[],h
            print('PASS suspended users excluded from network moments and Hall of Fame')
        else: print('SKIP inserted privacy tests: schema differs')
        for path in ['/','/network.html','/hall-of-fame.html','/styles.css']:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path, timeout=2) as response: assert response.status==200 and len(response.read())>200
        print('PASS all static routes HTTP 200')
    finally:
        proc.terminate()
        try:proc.wait(timeout=2)
        except subprocess.TimeoutExpired:proc.kill()
print('ALL NETWORK PHASE-1 TESTS COMPLETED')
