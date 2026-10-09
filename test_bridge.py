"""Local end-to-end tests, no actual production apps or secrets accessed."""
import hashlib,hmac,json,os,sqlite3,subprocess,sys,tempfile,time,urllib.request,urllib.error,socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler

root=Path(__file__).parent
sys.path.insert(0,str(root))
import ebl_esl_publisher as pub
SECRET="not-real-ELITE-test-key-very-long-1234567890"

def json_post(url, data, key=SECRET, timestamp=None, sport="baseball", altered_sig=None):
    body=json.dumps(data,separators=(",", ":")).encode();timestamp=str(int(time.time()) if timestamp is None else timestamp)
    sig=hmac.new(key.encode(),(timestamp+'.').encode()+body,hashlib.sha256).hexdigest()
    req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json','X-ESL-Sport':sport,'X-ESL-Timestamp':timestamp,'X-ESL-Signature':'sha256='+(altered_sig or sig)},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())

def get(url):
    with urllib.request.urlopen(url,timeout=5) as r:return json.loads(r.read())

with tempfile.TemporaryDirectory() as tmp:
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
    env=os.environ.copy();env.update({'PORT':str(port),'ELITE_DB_PATH':tmp+'/esl.sqlite','ELITE_NETWORK_BASEBALL_SECRET':SECRET,'ELITE_SEED_DEMO':'0','ELITE_ENV':'development'})
    server=subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        base=f'http://127.0.0.1:{port}'
        for _ in range(50):
            try:get(base+'/api/health');break
            except Exception:time.sleep(.1)
        else:raise AssertionError('Core startup failed')
        report={'event_id':'game:test-fixture-1','type':'GAME_FINAL','headline':'Club A 2, Club B 3 — Final',
                'summary':'Season 1 · League Day 1 · Final score','occurred_at':'2026-10-08 16:00:00',
                'details':{'away':'Club A','home':'Club B','away_runs':2,'home_runs':3,'season':1,'league_day':1}}
        url=base+'/api/network/ingest'
        assert json_post(url,report,key='incorrect-secret-with-lots-of-characters')[0]==401
        assert json_post(url,report,timestamp=int(time.time())-1000)[0]==401
        invalid={**report,'event_id':'demo:test'}
        assert json_post(url,invalid)[0]==400
        status,d=json_post(url,report);assert status==201 and d['created'] is True,(status,d)
        status,d=json_post(url,report);assert status==200 and d['duplicate'] is True,(status,d)
        board=get(base+'/api/network/home');assert len(board['scoreboard'])==1 and board['scoreboard'][0]['details']['home_runs']==3
        status_api=get(base+'/api/network/status')
        baseball=next(s for s in status_api['sports'] if s['slug']=='baseball')
        assert status_api['confirmed_reports']==1 and baseball['report_count']==1
        assert baseball['last_received_at'] is not None
        assert 'secret' not in json.dumps(status_api).lower()
        print('PASS Core: authenticated receipt status, no secrets or guessed connectivity')
        print('PASS Core: signed reports, invalid signature, timestamp, demo rejection, idempotency, verified score API')

        ebl_path=tmp+'/ebl.sqlite'
        def conn():
            c=sqlite3.connect(ebl_path);c.row_factory=sqlite3.Row;return c
        c=conn()
        c.executescript('''
            CREATE TABLE league_state(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT,payload_json TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE news(id INTEGER PRIMARY KEY AUTOINCREMENT,season INT,league_day INT,category TEXT,headline TEXT,body TEXT,importance INT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE award_history(id INTEGER PRIMARY KEY AUTOINCREMENT,season INT,period TEXT,award_code TEXT,award_name TEXT,player_id INT,franchise_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE games(id TEXT PRIMARY KEY,season INT,league_day INT,away_id TEXT,home_id TEXT,away_runs INT,home_runs INT,status TEXT);
            CREATE TABLE franchises(id TEXT PRIMARY KEY,name TEXT);
            CREATE TABLE franchise_branding(franchise_id TEXT PRIMARY KEY,display_name TEXT);
            CREATE TABLE players(id INTEGER PRIMARY KEY,name TEXT);
            INSERT INTO franchises VALUES('A','Alabama Arrows'),('B','Birmingham Bears');
            INSERT INTO players VALUES(1,'Sam Example');
            INSERT INTO games VALUES('past-game',1,1,'A','B',0,3,'FINAL');
            INSERT INTO news(season,league_day,category,headline,body,importance) VALUES(1,1,'LEAGUE','Past fixture','should not publish',3);
            INSERT INTO transactions(event_type,payload_json) VALUES('CONTRACT_SIGNED','{"player_id":1,"franchise_id":"A"}');
        ''');c.commit();c.close()
        os.environ['EBL_ESL_CORE_URL']=base;os.environ['EBL_ESL_NETWORK_SECRET']=SECRET;os.environ['EBL_ESL_PUBLISH_ENABLED']='1'
        assert pub.bootstrap(conn)
        assert pub.tick(conn)==0
        # Clubless retirements still matter to the player and to league history.
        row={'id':100,'event_type':'PLAYER_RETIRED','payload_json':json.dumps({'player_id':1,'player_name':'Sam Example','franchise_id':None}),'created_at':'2026-10-09 09:00:00'}
        rconn=conn();retirement=pub._report_tx(rconn,row);rconn.close()
        assert retirement and retirement['type']=='RETIREMENT' and 'Sam Example' in retirement['headline']
        print('PASS EBL: first activation skips old history, unsigned-team retirement supported')
        c=conn();c.executescript('''
            INSERT INTO transactions(event_type,payload_json) VALUES('CONTRACT_SIGNED','{"player_id":1,"franchise_id":"B"}');
            INSERT INTO award_history(season,period,award_code,award_name,player_id,franchise_id) VALUES(1,'REGULAR_SEASON','MVP','Most Valuable Player',1,'B');
            INSERT INTO news(season,league_day,category,headline,body,importance) VALUES(1,2,'LEAGUE','League announces milestone','This is a committed verified note',4);
            INSERT INTO games VALUES('game-two',1,2,'A','B',4,5,'FINAL');
        ''');c.commit();c.close()
        assert pub.tick(conn)==4
        assert pub.tick(conn)==0
        d=get(base+'/api/network/home'); types=[x['report_type'] for x in d['news'] if 'report_type' in x]
        assert set(types)=={'SIGNING','AWARD','LEAGUE_NEWS','GAME_FINAL'},types
        assert len(d['scoreboard'])==2, 'Prior test fixture plus 1 newly published final'
        diag=get(base+'/api/network/status')
        assert diag['confirmed_reports']==5,diag
        assert next(s for s in diag['sports'] if s['slug']=='baseball')['report_count']==5
        print('PASS Network status: confirmed five signed events, no phantom activity')
        assert not any(x.get('headline')=='Past fixture' for x in d['news'])
        print('PASS EBL→ESL: signing, award, news, final score delivered exactly once, no history flood')
    finally:
        server.terminate()
        try:server.wait(timeout=3)
        except subprocess.TimeoutExpired:server.kill()
print('ALL PHASE-2 END-TO-END TESTS PASSED')
