import datetime, fcntl, io, json, os, pty, select, shutil, signal, struct, subprocess, tarfile, termios, time
from pathlib import Path

root = Path.cwd()
scratch = root / '.test-validation-tmp'
lab = scratch / 'codex-first-turn-live'
evidence = Path('/home/bri/.no-mistakes/evidence/01M5ZT3KVT2CC9WSJ8XY2KA747')
subprocess.run(['bash', str(root / 'bin/fm-lab-home.sh'), 'create', str(lab)], check=True, capture_output=True)
archive = subprocess.run(['git', 'archive', 'HEAD'], check=True, capture_output=True).stdout
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    bundle.extractall(lab)
shutil.copyfile(root / 'bin/fm-agent-notify.py', lab / 'bin/fm-agent-notify.py')
subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'init', '-q', '-b', 'main', str(lab)], check=True)
native = lab / 'native'
native.mkdir()
shutil.copyfile(Path.home() / '.codex/auth.json', native / 'auth.json')
(native / 'auth.json').chmod(0o600)
(native / 'config.toml').write_text('[projects.' + json.dumps(str(lab)) + ']\ntrust_level="trusted"\n')
(lab / 'tmp').mkdir()
(lab / 'config/supervision-host-off').touch()
(lab / 'consumer.py').write_text('''import json,os,sys
from pathlib import Path
home=Path(__file__).parent
binding=json.loads(Path(os.environ['AGENT_NOTIFY_FIRSTMATE_BINDING']).read_text())
with (home/'consumer.jsonl').open('a') as stream:
    stream.write(json.dumps({'provider':sys.argv[2], 'payload':json.load(sys.stdin), 'binding':binding})+'\\n')
''')
subprocess.run(['bash', str(lab / 'bin/fm-agent-notify.sh'), '--home', str(lab), 'initialize', '--consumer', str(lab / 'consumer.py')], check=True)
(lab / 'hook-info.py').write_text('''import json,os,sys
from pathlib import Path
payload=json.load(sys.stdin)
(Path(os.environ['FM_HOME'])/'hook-env.json').write_text(json.dumps({'event':payload.get('hook_event_name'), 'has_payload_session':bool(payload.get('session_id')), 'has_thread_env':bool(os.environ.get('CODEX_THREAD_ID')), 'has_session_env':bool(os.environ.get('CODEX_SESSION_ID'))}))
''')
hook_file = lab / '.codex/hooks.json'
hooks = json.loads(hook_file.read_text())
hooks['hooks']['SessionStart'].append({'hooks':[{'type':'command','command':'python3 hook-info.py'}]})
hook_file.write_text(json.dumps(hooks))
(lab / 'probe.py').write_text('''import datetime,json,os,subprocess
from pathlib import Path
home=Path(os.environ['FM_HOME']); state=home/'state/agent-notify'
assert (home/'state/.session-start-complete').exists(), 'tracked startup did not complete'
assert not (state/'root.json').exists(), 'expected skipped startup binding'
at=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(seconds=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
args=['bash',str(home/'bin/fm-agent-notify.sh'),'--home',str(home),'call','native-first-turn', '1','open','--at',at]
first=subprocess.run(args,text=True,capture_output=True)
assert first.returncode==0, first.stderr
root=json.loads((state/'root.json').read_text()); assert root['provider']=='codex'
rows=[json.loads(line) for line in (home/'consumer.jsonl').read_text().splitlines()]
assert len(rows)==1 and rows[0]['payload']['firstmate_event']['kind']=='captain_call'
assert rows[0]['binding']['session_id']==os.environ['CODEX_THREAD_ID']
assert rows[0]['binding']['role']=='firstmate'
assert not json.loads((home/'config/agent-notify.json').read_text())['root_stop_accepted']
subprocess.run(args,check=True)
assert len((home/'consumer.jsonl').read_text().splitlines())==1
result={'first_call_exit':first.returncode,'before_root':False,'after_root':root,'event_kind':rows[0]['payload']['firstmate_event']['kind'],'deduplicated':True,'root_stop_accepted':False,'startup':json.loads((home/'hook-env.json').read_text())}
(home/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
''')
env = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'CODEX_', 'CLAUDE_', 'TASKS_AXI', 'AGENT_NOTIFY')) and k not in ('NO_MISTAKES_GATE', 'CLAUDECODE')}
env.update(CODEX_HOME=str(native), FM_HOME=str(lab), TMPDIR=str(lab / 'tmp'), FM_BOOTSTRAP_DETECT_ONLY='1', DISABLE_AUTOUPDATER='1', TERM='xterm-256color')
prompt = 'You are an isolated test primary. Your only task after the tracked SessionStart hook is to execute `python3 probe.py` exactly once using the shell tool, then reply TEST_DONE. Do not delegate, run other commands, edit files, run validation pipelines, publish, or access other homes. The probe uses offline notification storage.'
args = ['codex', '--no-daemon', '--no-alt-screen', '--enable', 'hooks', '--dangerously-bypass-hook-trust', '--dangerously-bypass-approvals-and-sandbox', '-c', 'notify=[]', '-c', 'model_reasoning_effort="low"', prompt]
pid, terminal = pty.fork()
if pid == 0:
    os.chdir(lab)
    os.execvpe(args[0], args, env)
fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 160, 0, 0))
output = bytearray()
try:
    deadline = time.monotonic() + 220
    while time.monotonic() < deadline and not (lab / 'result.json').exists():
        ready, _, _ = select.select([terminal], [], [], 1)
        if ready:
            try:
                chunk = os.read(terminal, 65536)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
            if b'\x1b[6n' in chunk:
                os.write(terminal, b'\x1b[1;1R')
    (evidence / 'codex-first-turn-fixed-tui.log').write_bytes(output)
    assert (lab / 'result.json').exists(), 'native probe did not complete; inspect codex-first-turn-fixed-tui.log'
    result = json.loads((lab / 'result.json').read_text())
    assert result['startup'] == {'event':'SessionStart','has_payload_session':True,'has_thread_env':False,'has_session_env':False}, result
    (evidence / 'codex-first-turn-fixed.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
finally:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    os.waitpid(pid, 0)
    os.close(terminal)
    shutil.rmtree(lab)
