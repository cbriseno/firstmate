import os,sys,json,subprocess,shutil,time,shlex
from pathlib import Path
r=Path.cwd();s=r/'.test-validation-tmp';h=s/'dispatch';e=Path('/home/bri/.no-mistakes/evidence/01M5ZT3KVT2CC9WSJ8XY2KA747/r2');env=dict(os.environ,FM_HERDR_LAB_STATE_DIR=str(s/'herdr'))
helper=str(r/'bin/fm-herdr-lab.sh')
def lab(*args,check=True):
 p=subprocess.run([helper,*args],env=env,capture_output=True,text=True)
 if check and p.returncode:raise RuntimeError(str(args)+p.stderr+p.stdout)
 return p
session=lab('name','local-base').stdout.strip();prepared=False
try:
 lab('provision',session);prepared=True
 subprocess.run([str(r/'bin/fm-lab-home.sh'),'create',str(h)],check=True)
 (h/'tmp').mkdir();(h/'config/supervision-host-off').touch();(h/'state/.last-watcher-beat').touch()
 project=h/'projects/sample';project.mkdir()
 git_env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid')
 def git(path,*args):return subprocess.run(['git','-C',str(path),*args],env=git_env,text=True,capture_output=True,check=True).stdout.strip()
 git(project,'init','-q','-b','main');(project/'treehouse.toml').write_text('root = '+json.dumps(str(h/'pool'))+'\n');(project/'README.md').write_text('initial\n');git(project,'add','.');git(project,'commit','-qm','initial')
 origin=h/'origin.git';git(h,'clone','-q','--bare',str(project),str(origin));git(project,'remote','add','origin',str(origin));git(project,'fetch','-q','origin');git(project,'remote','set-head','origin','main')
 (project/'landed.txt').write_text('previous local landing\n');git(project,'add','.');git(project,'commit','-qm','local landing');local=git(project,'rev-parse','HEAD')
 publisher=h/'publisher';git(h,'clone','-q',str(origin),str(publisher));(publisher/'upstream.txt').write_text('unsynced upstream change\n');git(publisher,'add','.');git(publisher,'commit','-qm','upstream advance');git(publisher,'push','-q','origin','main');upstream=git(publisher,'rev-parse','HEAD')
 (h/'data/projects.md').write_text('- sample [local-only] - disposable lab (added 2026-10-27)\n')
 clean=dict(os.environ)
 for k in list(clean):
  if k.startswith(('FM_','CODEX_','CLAUDE_','TASKS_AXI','AGENT_NOTIFY')) or k in ('NO_MISTAKES_GATE','CLAUDECODE'):clean.pop(k,None)
 clean.update(FM_HOME=str(h),TMPDIR=str(h/'tmp'),HERDR_SESSION=session,TREEHOUSE_ROOT=str(h/'pool'),DISABLE_AUTOUPDATER='1',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid')
 for task,scout in [('live-base-ship',False),('live-base-scout',True)]:
  args=['bash',str(r/'bin/fm-brief.sh'),task,'sample','--herdr-lab']+(['--scout'] if scout else ['--project',str(project),'--mode','local-only'])
  p=subprocess.run(args,env=clean,text=True,capture_output=True);assert not p.returncode,p.stderr
  brief=h/'data'/task/'brief.md';t=brief.read_text().replace('{TASK}','Verify the inherited local landing is present and upstream.txt is absent; report the result without editing or publishing anything.').replace('{FIRSTMATE_SPEC}','This is disposable validation. Read the two files and report ready in branch. Do not run no-mistakes, commit, push, or use any external service.');brief.write_text(t)
  workspace=json.loads(lab('run',session,'workspace','create','--cwd',str(r),'--label',task,'--no-focus').stdout)
  def pick(o,k):
   if isinstance(o,dict):
    if k in o:return o[k]
    for v in o.values():
     a=pick(v,k)
     if a:return a
   if isinstance(o,list):
    for v in o:
     a=pick(v,k)
     if a:return a
  pane=pick(workspace,'pane_id');assert pane,workspace
  command=['env']
  for k in os.environ:
   if k.startswith(('FM_','CODEX_','CLAUDE_','TASKS_AXI','AGENT_NOTIFY')) or k in ('NO_MISTAKES_GATE','CLAUDECODE'):command+=['-u',k]
  for k in ['FM_HOME','TMPDIR','TREEHOUSE_ROOT','DISABLE_AUTOUPDATER','GIT_CONFIG_NOSYSTEM','GIT_CONFIG_GLOBAL','GIT_AUTHOR_NAME','GIT_AUTHOR_EMAIL','GIT_COMMITTER_NAME','GIT_COMMITTER_EMAIL']:command += [k+'='+clean[k]]
  command+=['bash',str(r/'bin/fm-spawn.sh'),task,str(project),'--backend','herdr','--harness','codex']+(['--scout'] if scout else ['--mode','local-only','--yolo','off'])
  log=h/(task+'.log');done=h/(task+'.exit')
  shell=shlex.join(command)+' > '+shlex.quote(str(log))+' 2>&1; printf "%s" "$?" > '+shlex.quote(str(done))
  lab('run',session,'pane','run',pane,shell)
  for tick in range(100):
   time.sleep(2)
   if done.exists():break
  text=log.read_text() if log.exists() else 'no log'
  result={'task':task,'exit':done.read_text() if done.exists() else 'timeout','local_main':local,'origin_main':upstream,'spawn_output':text}
  meta=h/'state'/(task+'.meta')
  if meta.exists():
   data=dict(line.split('=',1) for line in meta.read_text().splitlines() if '=' in line);wt=Path(data['worktree']);result.update(metadata=data,worker_head=git(wt,'rev-parse','HEAD'),landed_file=(wt/'landed.txt').exists(),upstream_file=(wt/'upstream.txt').exists())
  (e/(task+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
  assert result['exit']=='0' and result['worker_head']==local and result['landed_file'] and not result['upstream_file'],result
  assert local in text and upstream in text and 'operator syncs' in text,text
  if not scout:
   # Materialize a completed branch inside the disposable project, then exercise
   # the real approved local landing interface. No remote publication occurs.
   git(wt,'checkout','-B',data['branch'])
   (wt/'validated.txt').write_text('Disposable requested result.\n')
   git(wt,'add','validated.txt');git(wt,'commit','-qm','disposable completed ship')
   ship_head=git(wt,'rev-parse','HEAD')
   merge_log=h/'merge.log';merge_done=h/'merge.exit'
   merge_command=command[:command.index('bash')]+['bash',str(r/'bin/fm-merge-local.sh'),task]
   lab('run',session,'pane','run',pane,shlex.join(merge_command)+' > '+shlex.quote(str(merge_log))+' 2>&1; printf "%s" "$?" > '+shlex.quote(str(merge_done)))
   for _ in range(60):
    time.sleep(1)
    if merge_done.exists():break
   landing={'exit':merge_done.read_text() if merge_done.exists() else 'timeout','output':merge_log.read_text(),'ship_head':ship_head,'local_main':git(project,'rev-parse','HEAD'),'result_present':(project/'validated.txt').exists(),'upstream_present':(project/'upstream.txt').exists()}
   (e/'local-landing.json').write_text(json.dumps(landing,indent=2));print(json.dumps(landing,indent=2),flush=True)
   assert landing['exit']=='0' and landing['local_main']==ship_head and landing['result_present'] and not landing['upstream_present'],landing
   local=ship_head

finally:
 if prepared:
  p=lab('teardown',session,check=False);(e/'dispatch-lab-teardown.log').write_text(p.stdout+p.stderr+'exit='+str(p.returncode)+'\n');print('TEARDOWN',p.returncode,p.stderr,flush=True)
 if h.exists():
  for base,dirs,files in os.walk(h):os.chmod(base,0o700)
  shutil.rmtree(h)
