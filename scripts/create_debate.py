import json, urllib.request, sys
url='http://127.0.0.1:8000/api/debates'
payload={'topic':'AI will replace software engineers','rounds':1,'stance_style':'balanced'}
data=json.dumps(payload).encode('utf-8')
req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as f:
    resp=f.read().decode()
    print(resp)
