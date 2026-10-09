import importlib.util, json, os, sqlite3, tempfile, time, pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

issuer=load('issuer',ROOT/'EBL/ebl_elite_account_link.py')
verify=load('verifier',ROOT/'ESL/esl_ebl_account_link.py')
KEY='independent-proof-key-very-long-and-test-only-0123456789'
os.environ['EBL_ELITE_ACCOUNT_LINK_SECRET']=KEY
os.environ['ELITE_EBL_ACCOUNT_LINK_SECRET']=KEY
with tempfile.TemporaryDirectory() as td:
    db=pathlib.Path(td)/'secure-link.db'
    def conn():
        c=sqlite3.connect(db);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
    c=conn();c.executescript('''
      CREATE TABLE users(id INTEGER PRIMARY KEY,status TEXT NOT NULL,email_verified INTEGER NOT NULL);
      CREATE TABLE sports(id INTEGER PRIMARY KEY,slug TEXT UNIQUE NOT NULL);
      CREATE TABLE sport_account_links(user_id INTEGER NOT NULL,sport_id INTEGER NOT NULL,external_user_id TEXT NOT NULL,external_username TEXT,sport_role TEXT,last_synced_at TEXT,UNIQUE(user_id,sport_id),UNIQUE(sport_id,external_user_id));
      CREATE TABLE user_sport_memberships(user_id INTEGER NOT NULL,sport_id INTEGER NOT NULL,role TEXT,last_active_at TEXT,UNIQUE(user_id,sport_id));
      INSERT INTO users VALUES (10,'ACTIVE',1),(11,'ACTIVE',1),(12,'EMAIL_UNVERIFIED',0);
      INSERT INTO sports VALUES (1,'baseball');
    ''');c.commit();c.close()
    def issue(uid,username='Rookie',role='PLAYER'):
        return issuer.issue({'id':uid,'username':username,'role':role})['proof']
    p=issue(123)
    claims,error=verify.verify(p);assert error is None and claims['uid']==123
    out,error=verify.link(conn,10,p);assert error is None and out['external_username']=='Rookie'
    print('PASS: legitimate EBL owner verified and linked')
    assert verify.link(conn,11,p)[1]=='EBL_ACCOUNT_ALREADY_CLAIMED'
    assert verify.link(conn,10,p)[1]=='LINK_PROOF_ALREADY_USED'
    print('PASS: proof replay and other-user takeover rejected')
    assert verify.link(conn,11,issue(123))[1]=='EBL_ACCOUNT_ALREADY_CLAIMED'
    assert verify.link(conn,10,issue(456))[1]=='ALREADY_LINKED_TO_DIFFERENT_EBL_ACCOUNT'
    print('PASS: new proof cannot reassign an existing identity')
    assert verify.link(conn,12,issue(789))[1]=='ELITE_ACCOUNT_NOT_VERIFIED'
    print('PASS: ESL account must be active and email-verified')
    first,second=p.split('.')
    bad=first+'.'+('A' if second[0]!='A' else 'B')+second[1:]
    assert verify.verify(bad)[1]=='INVALID_LINK_PROOF'
    assert verify.verify(first[:-1]+('A' if first[-1]!='A' else 'B')+'.'+second)[1]=='INVALID_LINK_PROOF'
    assert verify.verify('broken')[1]=='INVALID_LINK_PROOF'
    print('PASS: malformed and tampered proofs rejected')
    # Test expiry with a fresh valid signature over expired claims.
    import hmac,hashlib,base64
    obj=dict(claims);obj['iat']=int(time.time())-250;obj['exp']=int(time.time())-60;obj['nonce']='anewuniqueproofnonce0123456789012345'
    b=json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    token=lambda data:base64.urlsafe_b64encode(data).decode().rstrip('=')
    signature=hmac.new(KEY.encode(),verify.CONTEXT+b,hashlib.sha256).digest()
    assert verify.verify(token(b)+'.'+token(signature))[1]=='EXPIRED_OR_INVALID_LINK_PROOF'
    print('PASS: expired signed proof rejected')
    os.environ['ELITE_EBL_ACCOUNT_LINK_SECRET']='wrong-secret-still-long-enough-for-security'
    assert verify.verify(p)[1]=='INVALID_LINK_PROOF'
    del os.environ['ELITE_EBL_ACCOUNT_LINK_SECRET']
    assert verify.verify(p)[1]=='LINK_NOT_CONFIGURED'
    print('PASS: absent/mismatched secret fails closed')
    os.environ['ELITE_EBL_ACCOUNT_LINK_SECRET']=KEY
    q=issue(321,'Coach123','COACH');out,error=verify.link(conn,11,q)
    assert error is None and out['sport_role']=='COACH'
    c=conn();r=c.execute('SELECT role FROM user_sport_memberships WHERE user_id=11').fetchone();assert r['role']=='COACH';c.close()
    print('PASS: signed EBL role and membership recorded')
print('ALL SECURE ACCOUNT LINK TESTS PASSED')
