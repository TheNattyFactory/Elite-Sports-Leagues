import base64,hashlib,hmac,json,secrets,time
SECRET="test-secret"
def enc(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def dec(s): return base64.urlsafe_b64decode(s+"="*((4-len(s)%4)%4))
p={"typ":"external-link","uid":4,"sid":1,"exp":int(time.time())+300,"nonce":secrets.token_urlsafe(8)}
raw=json.dumps(p,separators=(",",":"),sort_keys=True).encode()
ticket=enc(raw)+"."+enc(hmac.new(SECRET.encode(),raw,hashlib.sha256).digest())
a,b=ticket.split(".",1);raw2=dec(a);sig=dec(b)
assert hmac.compare_digest(sig,hmac.new(SECRET.encode(),raw2,hashlib.sha256).digest())
assert json.loads(raw2)["uid"]==4
print("external link ticket test PASS")
