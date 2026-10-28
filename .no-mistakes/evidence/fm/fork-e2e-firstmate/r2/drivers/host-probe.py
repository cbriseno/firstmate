import os,json,subprocess
from pathlib import Path
h=Path(os.environ['FM_HOME']);p=h/'projects/check';p.mkdir()
env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='Lab',GIT_AUTHOR_EMAIL='lab@example.invalid',GIT_COMMITTER_NAME='Lab',GIT_COMMITTER_EMAIL='lab@example.invalid')
def run(a,cwd=h):return subprocess.run(a,cwd=cwd,env=env,text=True,capture_output=True,check=True).stdout.strip()
run(['git','init','-q','-b','main'],p);(p/'README.md').write_text('Completed disposable scout.\n');(p/'treehouse.toml').write_text('root = '+json.dumps(str(h/'pool'))+'\n');run(['git','add','.'],p);run(['git','commit','-qm','fixture'],p)
wt=run(['treehouse','--root',str(h/'pool'),'get','--lease'],p).splitlines()[-1]
(h/'data/final-scout').mkdir();(h/'data/final-scout/report.md').write_text('# Completed disposable scout\nThe local checkout was read successfully. No findings or captain decisions remain. This requested validation result is ready to report. Retire final-scout through bin/fm-teardown.sh final-scout, then record a visible captain outcome through bin/fm-branch-report.sh with --verdict captain --silent false --task final-scout. This is the requested captain deliverable and the captain is explicitly waiting for its result. Do not dispatch, modify projects, publish, or merge anything.\n')
(h/'state/final-scout.meta').write_text('project='+str(p)+'\nworktree='+wt+'\nkind=scout\nmode=scout\nharness=codex\nbackend=herdr\nwindow='+os.environ['LAB_SCOUT_TARGET']+'\nherdr_session='+os.environ['HERDR_SESSION']+'\nendpoint_task_id=final-scout\nherdr_workspace_id='+os.environ['LAB_SCOUT_WORKSPACE']+'\nherdr_tab_id='+os.environ['LAB_SCOUT_TAB']+'\nherdr_pane_id='+os.environ['LAB_SCOUT_PANE']+'\n')
(h/'state/final-scout.status').touch()
(h/'config/supervision-host-off').unlink(missing_ok=True);(h/'config/supervision-host').write_text('claude haiku\n')
(h/'handled.py').write_text('import os,json,subprocess\nfrom pathlib import Path\nh=Path(os.environ["FM_HOME"])\nr=subprocess.run(["bash",str(h/"bin/fm-wake-drain.sh")],text=True,capture_output=True)\n(h/"handback.json").write_text(json.dumps({"wake_drain":r.stdout,"stderr":r.stderr,"exit":r.returncode,"remaining_tasks":len(list((h/"state").glob("*.meta")))}))\nprint(r.stdout)\n')
(h/'setup-ready').touch();print('HOST_SETUP_READY')
