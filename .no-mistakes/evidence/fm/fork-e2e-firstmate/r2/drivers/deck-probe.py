import os,json,subprocess,datetime
from pathlib import Path
h=Path(os.environ['FM_HOME']);ops=[]
def run(script,*args,expected=0,data=None,external=False):
 env=dict(os.environ)
 if external:
  for k in list(env):
   if k.startswith(('CODEX_','CLAUDE_')) or k=='CLAUDECODE':env.pop(k,None)
 p=subprocess.run(['bash',str(h/'bin'/script),*args],text=True,input=data,capture_output=True,env=env)
 ops.append({'script':script,'args':args,'external':external,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 assert p.returncode==expected,ops[-1]
 return p.stdout
assert (h/'state/.session-start-complete').exists()
run('fm-captain-hold.sh','hold','deck-call','--title','Disposable captain question','--reason','Choose whether to continue the disposable lab')
snapshot=json.loads(run('fm-fleet-snapshot.sh','--json',external=True))
row=next(r for r in snapshot['backlog']['records'] if r.get('id')=='deck-call');assert row['captain_actionable'],row
identity=run('fm-captain-hold.sh','open','deck-call','--identity',external=True).strip()
run('fm-captain-hold.sh','answers','--source','isolated-deck-live','--expected-identity',identity,data='deck-call\tContinue the disposable lab\tCaptain answer\tdone\n',external=True)
run('fm-captain-hold.sh','resolved','deck-call','1',external=True)
rows=[json.loads(l) for l in (h/'consumer.jsonl').read_text().splitlines()]
assert len(rows)==2,rows
assert [r['payload']['firstmate_event']['state'] for r in rows]==['open','resolved'],rows
at=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
run('fm-agent-notify.sh','--home',str(h),'call','forged-service','1','open','--at',at,expected=1,external=True)
assert len((h/'consumer.jsonl').read_text().splitlines())==2
result={'provider':'codex','snapshot_row':row,'identity':identity,'notification_states':[r['payload']['firstmate_event']['state'] for r in rows],'external_forged_open_refused':True,'operations':ops}
(h/'probe-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
