import os,json,sys,subprocess,time
from pathlib import Path
h=Path(os.environ['FM_HOME'])
cli=subprocess.Popen(['claude','-p','--input-format','stream-json','--output-format','stream-json','--verbose','--setting-sources','project','--dangerously-skip-permissions','--effort','low'],stdin=subprocess.PIPE,text=True)
try:
 cli.stdin.write(json.dumps({'type':'user','message':{'role':'user','content':sys.argv[1]}})+'\n');cli.stdin.flush()
 for _ in range(120):
  time.sleep(2)
  if (h/'probe-result.json').exists() and (h/'state/agent-notify/root.json').exists():
   (h/'native-stop-retry.json').write_text(json.dumps({'root':json.loads((h/'state/agent-notify/root.json').read_text()),'cli_pid':cli.pid,'cli_alive':cli.poll() is None}));break
finally:
 cli.stdin.close()
 try:cli.wait(timeout=15)
 except subprocess.TimeoutExpired:cli.terminate();cli.wait(timeout=15)
