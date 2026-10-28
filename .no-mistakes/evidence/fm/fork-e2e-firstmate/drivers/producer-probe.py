import json,os,subprocess,datetime,time,sys
from pathlib import Path
h=Path(os.environ['FM_HOME']); state=h/'state/agent-notify';out={'provider':'claude'}
def run(args,expected=0,data=None,extra=None):
 r=subprocess.run(args,input=data,env={**os.environ,**(extra or {})},text=True,capture_output=True)
 row={'args':args[4:] if 'fm-agent-notify.sh' in str(args) else args[-2:],'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 out.setdefault('operations',[]).append(row);assert r.returncode==expected,row
 return r
def bridge(*a,**kw):return run(['bash',str(h/'bin/fm-agent-notify.sh'),'--home',str(h),*map(str,a)],**kw)
def clear():
 if (state/'root.json').exists():
  root=json.loads((state/'root.json').read_text());(state/(root['provider']+'-'+root['session_id']+'.json')).unlink(missing_ok=True);(state/'root.json').unlink()
def fresh(*a,**kw):
 clear();bridge(*a,**kw);assert (state/'root.json').exists()
at=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
out['harness']=run(['bash',str(h/'bin/fm-harness.sh')]).stdout.strip();out['before_root']=(state/'root.json').exists()
run(['bash',str(h/'bin/fm-tasks-axi.sh'),'add','native-result','Native requested outcome'])
fresh('call','native-first-turn',1,'open','--at',at)
fresh('call','native-first-turn',1,'resolved','--at',at)
fresh('response','native-response','req1','open','--at',at)
fresh('response','native-response','req1','resolved','--at',at)
fresh('designate','native-result','native-outcome')
fresh('initiative','native-initiative','--requires','native-outcome')
fresh('landed','native-result',data=json.dumps({'state':'done','structured':True,'completion':{'verb':'done'},'local_note':'local main'}))
fresh('complete','native-initiative')
count=len((h/'consumer.jsonl').read_text().splitlines());bridge('complete','native-initiative');assert len((h/'consumer.jsonl').read_text().splitlines())==count
out['delivered_kinds']=[json.loads(l)['payload']['firstmate_event']['kind'] for l in (h/'consumer.jsonl').read_text().splitlines()]
root=json.loads((state/'root.json').read_text());binding=state/(root['provider']+'-'+root['session_id']+'.json');saved=binding.read_bytes();record=json.loads(saved)
# The claimant remains a real native session. Only its persisted prior-process
# record is corrupted, as after a resume of that same native session ID.
gone=subprocess.Popen(['true']);gone.wait();binding.write_text(json.dumps({**record,'proof':{**record['proof'],'pid':gone.pid}}));bridge('bind','claude');assert binding.read_bytes()==saved
with subprocess.Popen(['sleep','60']) as other:
 try:
  started=subprocess.run(['ps','-p',str(other.pid),'-o','lstart='],text=True,capture_output=True,check=True).stdout.strip()
  binding.write_text(json.dumps({**record,'proof':{**record['proof'],'pid':other.pid,'started':started}}));bridge('bind','claude',expected=1);assert json.loads(binding.read_text())['proof']['pid']==other.pid
 finally:other.terminate()
binding.write_bytes(saved)
for file,bad in [('.lock-session','foreign-session'),('.session-start-complete','1')]:
 p=h/'state'/file;before=p.read_bytes();p.write_text(bad)
 try:bridge('response','forged','req-guard','open','--at',at,expected=1)
 finally:p.write_bytes(before)
bridge('response','forged','req-guard','open','--at',at,expected=1,extra={'CLAUDE_CODE_SESSION_ID':'forged-id'})
bridge('response','forged','req-guard','open','--at',at,expected=1,extra={'FM_TASK_ID':'worker-cannot-own-root'})
assert len((h/'consumer.jsonl').read_text().splitlines())==count
out['guards']='stale binding rebinds; live binding refuses replacement; wrong lock session/start completion/native ID/worker role refuse without event delivery'
clear();out['stop_retry_requested']=True
(h/'probe-result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
