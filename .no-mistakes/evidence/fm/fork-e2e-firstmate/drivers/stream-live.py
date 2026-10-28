import os,sys,json,subprocess,shutil,time,shlex,tarfile,io
from pathlib import Path
root=Path.cwd(); scratch=root/'.test-validation-tmp'; evidence=Path('/home/bri/.no-mistakes/evidence/01M5ZT3KVT2CC9WSJ8XY2KA747')
env=dict(os.environ,FM_HERDR_LAB_STATE_DIR=str(scratch/'herdr'))
helper=str(root/'bin/fm-herdr-lab.sh')
def lab(*args,check=True):
 p=subprocess.run([helper,*args],env=env,text=True,capture_output=True)
 if p.returncode and check: raise RuntimeError(str(args)+p.stderr+p.stdout)
 return p
session=lab('name','native-parity').stdout.strip(); (scratch/'session-name').write_text(session)
prepared=False
try:
 prepared=True
 lab('provision',session)
 for provider in ('claude',):
  home=scratch/('primary-a' if provider=='claude' else 'primary-b')
  subprocess.run([str(root/'bin/fm-lab-home.sh'),'create',str(home)],check=True,stdout=subprocess.DEVNULL)
  archive=subprocess.run(['git','archive','HEAD'],check=True,capture_output=True).stdout
  with tarfile.open(fileobj=io.BytesIO(archive)) as tar: tar.extractall(home)
  subprocess.run(['git','init','-q','-b','main',str(home)],check=True)
  (home/'tmp').mkdir(); (home/'config/supervision-host-off').touch()
  # The consumer is the external boundary only: the real bridge proves and sends
  # its real protocol to an offline recorder, never the operator's ntfy store.
  (home/'consumer.py').write_text('import json,os,sys\nfrom pathlib import Path\np=Path(__file__).parent\nb=Path(os.environ["AGENT_NOTIFY_FIRSTMATE_BINDING"])\nr={"provider":sys.argv[2],"payload":json.load(sys.stdin),"binding":json.loads(b.read_text())}\nwith (p/"consumer.jsonl").open("a") as f: f.write(json.dumps(r)+"\\n")\n')
  subprocess.run(['bash',str(home/'bin/fm-agent-notify.sh'),'--home',str(home),'initialize','--consumer',str(home/'consumer.py')],check=True)
  shutil.copyfile(scratch/'producer-probe.py',home/'probe.py')
  shutil.copyfile(scratch/'stream-primary.py',home/'stream-primary.py')
  tab=json.loads(lab('run',session,'workspace','create','--cwd',str(home),'--label',provider+'-primary','--no-focus').stdout)
  (evidence/(provider+'-lab-tab.json')).write_text(json.dumps(tab,indent=2))
  def pick(obj,key):
   if isinstance(obj,dict):
    if key in obj:return obj[key]
    for v in obj.values():
     r=pick(v,key)
     if r:return r
   if isinstance(obj,list):
    for v in obj:
     r=pick(v,key)
     if r:return r
  pane=pick(tab,'pane_id'); assert pane,tab
  unsets=[k for k in os.environ if k.startswith(('FM_','CODEX_','CLAUDE_','TASKS_AXI','AGENT_NOTIFY')) or k in ('NO_MISTAKES_GATE','CLAUDECODE')]
  command=['env']
  for k in unsets:command+=['-u',k]
  command += ['NATIVE_FIXTURE_PROVIDER='+provider,'FM_HOME='+str(home),'TMPDIR='+str(home/'tmp'),'DISABLE_AUTOUPDATER=1','FM_BOOTSTRAP_DETECT_ONLY=1']
  prompt='This is an isolated validation primary. Follow any session-start context already delivered, then use your Bash/shell tool to execute exactly `python3 probe.py`. Do not delegate, edit files, run no-mistakes, publish, or access other homes. After it returns, reply NATIVE_PROBE_DONE and stop. All fixture operations and offline notification storage belong to this marked disposable home.'
  if provider=='claude':
   command+=['CODEX_THREAD_ID=inherited-foreign-thread','python3','stream-primary.py',prompt]
  else:
   command+=['CLAUDECODE=1','codex','--no-alt-screen','--disable','hooks','--dangerously-bypass-approvals-and-sandbox','-c','notify=[]','-c','model_reasoning_effort="low"',prompt]
  shell=shlex.join(command)+' > '+shlex.quote(str(home/'native-output.log'))+' 2>&1; printf NATIVE_EXIT=%s \"$?\"'
  print('START',provider,session,pane,flush=True)
  lab('run',session,'pane','run',pane,shell)
  for tick in range(120):
   time.sleep(2)
   if (home/'probe-result.json').exists():break
   if tick%15==0:
    capture=lab('run',session,'pane','read',pane,'--source','recent-unwrapped','--lines','40',check=False)
    print('WAIT',provider,tick*2,capture.stdout,flush=True)
    if 'Do you trust' in capture.stdout:lab('run',session,'pane','send-keys',pane,'enter')
  for _ in range(20):
   if (home/'native-stop-retry.json').exists():break
   time.sleep(2)
  if (home/'state/agent-notify/root.json').exists():
   (evidence/'claude-stop-retry-root.json').write_text((home/'state/agent-notify/root.json').read_text())
  for filename in ('probe-result.json','native-output.log','consumer.jsonl','native-stop-retry.json'):
   if (home/filename).exists():shutil.copyfile(home/filename,evidence/(provider+'-'+filename))
  state=home/'state/agent-notify'
  if state.exists():shutil.copytree(state,evidence/(provider+'-notification-state'),dirs_exist_ok=True)
  capture=lab('run',session,'pane','read',pane,'--source','recent-unwrapped','--lines','80',check=False)
  (evidence/(provider+'-pane.json')).write_text(capture.stdout+capture.stderr)
  print('RESULT',provider,(home/'probe-result.json').read_text() if (home/'probe-result.json').exists() else 'NO RESULT; '+(home/'native-output.log').read_text()[-4000:],flush=True)
finally:
 if prepared:
  result=lab('teardown',session,check=False)
  (evidence/'native-lab-teardown.log').write_text(result.stdout+result.stderr+'exit='+str(result.returncode)+'\n')
  print('TEARDOWN',result.returncode,result.stdout,result.stderr,flush=True)
 for provider in ('claude','codex'):
  if (scratch/('primary-a' if provider=='claude' else 'primary-b')).exists():shutil.rmtree(scratch/('primary-a' if provider=='claude' else 'primary-b'))
