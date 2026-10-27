"""Hermetic CLI fixtures, not evidence of native vendor/runtime acceptance."""
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


NEVER_STARTED = "Thu Jan  1 00:00:00 1970"


@contextlib.contextmanager
def running():
    """A live process this test owns, for records naming a live pid."""
    other = subprocess.Popen(["sleep", "60"])
    try:
        yield other.pid
    finally:
        other.kill()
        other.wait()


def same_id_rebind(binding, bind, state):
    """A resumed session reuses its native ID; only a stale record is replaced."""
    bound = binding.read_bytes()
    record = json.loads(bound)

    def recorded(**proof):
        binding.write_text(json.dumps({**record, "proof": {**record["proof"], **proof}}))

    gone = subprocess.Popen(["true"])
    gone.wait()
    complete = state / ".session-start-complete"
    saved = complete.read_bytes()
    recorded(pid=gone.pid)
    complete.write_text("1")
    bind(1)  # Replacement still needs every current claimant proof.
    assert json.loads(binding.read_text())["proof"]["pid"] == gone.pid
    complete.write_bytes(saved)
    with running() as pid:
        # Process gone; pid alive with another start time.
        for proof in ({"pid": gone.pid}, {"pid": pid, "started": NEVER_STARTED}):
            recorded(**proof)
            bind(0)
            assert binding.read_bytes() == bound
        started = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="],
                                 capture_output=True, text=True, check=True).stdout.strip()
        recorded(pid=pid, started=started)
        bind(1)  # A live recorded process still refuses until revoke.
        assert json.loads(binding.read_text())["proof"]["pid"] == pid
    binding.write_bytes(bound)


def launch():
    code, tmp = map(Path, sys.argv[1:3])
    # An executable symlink gives the fixture an actual codex-named ancestor.
    # It executes Python fixtures, never the installed model CLI.
    native = tmp / "codex"
    native.symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ("FM_", "CODEX_", "CLAUDE_", "TASKS_AXI", "AGENT_NOTIFY"))}
    env["HOME"] = str(tmp)
    # A sibling fixture service models Deck: no root environment or native
    # root ancestor. Pipes keep this hermetic without any polling/service use.
    service = subprocess.Popen([sys.executable, __file__, "service", str(code), str(tmp)],
                               env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        subprocess.run([str(native), __file__, "driver", str(code), str(tmp),
                        str(service.stdin.fileno()), str(service.stdout.fileno())],
                       pass_fds=(service.stdin.fileno(), service.stdout.fileno()), env=env, check=True)
    finally:
        service.stdin.close()
        assert service.wait(timeout=15) == 0
        service.stdout.close()
    for mode in ("shared", "claude", "claude-metadata"):
        binary = native
        if mode.startswith("claude"):
            binary = tmp / "claude"
            if not binary.exists():
                binary.symlink_to(sys.executable)
        subprocess.run([str(binary), __file__, mode, str(code), str(tmp), "app-server" if mode == "shared" else "cli"],
                       env=env, check=True)
    routing_launch(code, tmp)


def routing_launch(code, tmp):
    """Focused entry: routing-check <code> <temporary-directory>."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ("FM_", "CODEX_", "CLAUDE_", "HERDR_", "AGENT_NOTIFY"))}
    env["HOME"] = str(tmp)
    for mode in ("cli", "app-server", "claude"):
        binary = tmp / ("claude" if mode == "claude" else "codex")
        if not binary.exists():
            binary.symlink_to(sys.executable)
        subprocess.run([str(binary), __file__, "routing", str(code), str(tmp), mode],
                       env=env, check=True)


def routing():
    code, tmp = map(Path, sys.argv[2:4])
    mode = sys.argv[4]
    provider = "claude" if mode == "claude" else "codex"
    home = tmp / ("routing-" + mode)
    (home / "state").mkdir(parents=True)
    for name in (".lock", ".session-start-complete"):
        (home / "state" / name).write_text(str(os.getpid()))
    sid = "routing-" + mode
    env = dict(os.environ, FM_HOME=str(home))
    payload = {"session_id": sid, "hook_event_name": "Stop", "last_assistant_message": "PRIVATE_FIXTURE_TEXT"}
    if provider == "codex":
        env.update(CODEX_THREAD_ID=sid, CODEX_SESSION_ID=sid, CODEX_HOME=str(home / "native"))
        (home / "native/sessions").mkdir(parents=True)
        (home / "native/sessions" / (sid + ".jsonl")).write_text(json.dumps({"type": "session_meta", "payload": {
            "id": sid, "cwd": str(home), "source": "vscode" if mode == "app-server" else "cli"}}) + "\n")
    else:
        env.update(CLAUDE_CODE_SESSION_ID=sid, CLAUDE_PID=str(os.getpid()))
        (home / "state/.lock-session").write_text(sid)
        transcript = home / (sid + ".jsonl")
        transcript.write_text(json.dumps({"sessionId": sid, "cwd": str(home)}) + "\n")
        payload["transcript_path"] = str(transcript)
    # This consumer has no imports or code for DB/network/audio or publication.
    consumer = home / "consumer.py"
    consumer.write_text('''import json,os,sys
from pathlib import Path
home=Path(__file__).parent
data=json.load(sys.stdin)
binding=os.environ.get('AGENT_NOTIFY_FIRSTMATE_BINDING')
with (home/'consumer.jsonl').open('a') as f:
    f.write(json.dumps({'binding':bool(binding), 'hook':data.get('hook_event_name')})+'\\n')
if (home/'fail-consumer').exists(): sys.exit(7)
''')

    def cmd(*args, data=None, expected=0):
        result = subprocess.run(["bash", str(code / "bin/fm-agent-notify.sh"), "--home", str(home), *map(str, args)],
                                input=json.dumps(payload if data is None else data), env=env, text=True, capture_output=True)
        assert result.returncode == expected, (mode, args, result.stderr)
        return result

    def hook(data=None, expected=0):
        return cmd("hook", provider, "--consumer", consumer, data=data, expected=expected)

    state = home / "state/agent-notify"
    directory = state / "hooks"
    receipt_path = directory / (provider + "-" + sid + "-Stop.json")
    config_path = home / "config/agent-notify.json"
    cmd("initialize", "--consumer", consumer)
    config_before = config_path.read_bytes()
    hook()  # Unbound personal sessions retain routing and create no receipt.
    assert not directory.exists()
    cmd("bind", provider)
    binding_path = state / (provider + "-" + sid + ".json")
    binding_before = binding_path.read_bytes()
    if mode == "app-server":
        env.pop("CODEX_THREAD_ID")
        env.pop("CODEX_SESSION_ID")  # Shared hook runtime needs only the genuine payload's already-bound SID.
    before = time.time()
    hook()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["started_at"] >= before and receipt["finished_at"] >= receipt["started_at"]
    assert receipt["provider"] == provider and receipt["session_id"] == sid
    assert receipt["home"] == str(home) and receipt["task_id"] == "supervisor" and receipt["role"] == "firstmate"
    assert receipt["proof_pid"] == os.getpid() and receipt["proof_started"]
    assert receipt["binding_fingerprint"] == hashlib.sha256(
        json.dumps(json.loads(binding_before), sort_keys=True).encode()).hexdigest()
    assert receipt["root_stop_accepted"] is False and receipt["binding_forwarded"] is False
    assert receipt["consumer_returncode"] == 0
    assert json.loads((home / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is False
    assert config_path.read_bytes() == config_before and binding_path.read_bytes() == binding_before
    assert set(receipt) == {"version", "provider", "session_id", "home", "role", "task_id", "hook_event_name",
                            "binding_fingerprint", "proof_pid", "proof_started", "root_stop_accepted",
                            "binding_forwarded", "started_at", "finished_at", "consumer_returncode"}
    original = receipt_path.read_bytes()
    for data in ({**payload, "session_id": "foreign"}, {"hook_event_name": "Stop"},
                 {**payload, "hook_event_name": "PRIVATE_FIXTURE_TEXT"}):
        hook(data)
        assert receipt_path.read_bytes() == original and len(list(directory.iterdir())) == 1
    for path, replacement in ((home / "state/.session-start-complete", "0"),
                              (state / "root.json", json.dumps({"provider": provider, "session_id": "foreign"}))):
        saved = path.read_bytes()
        path.write_text(replacement)
        hook()
        assert receipt_path.read_bytes() == original
        path.write_bytes(saved)
    # A verified worker is still forwarded, without recording worker hooks.
    meta = home / "state/worker.meta"
    meta.write_text(f"endpoint_task_id=worker\nkind=ship\nharness={provider}\nspawn_gen=fixture-generation\n")
    binding = json.loads(binding_before)
    binding.update(role="ship", task_id="worker")
    binding["proof"].update(meta=str(meta), generation="fixture-generation")
    binding_path.write_text(json.dumps(binding))
    hook()
    assert receipt_path.read_bytes() == original
    assert json.loads((home / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is True
    binding_path.write_bytes(binding_before)
    # Only the existing native root acceptance command can switch this route.
    if mode == "app-server":
        env.update(CODEX_THREAD_ID=sid, CODEX_SESSION_ID=sid)
    cmd("accept-root")
    accepted_config = config_path.read_bytes()
    hook()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["root_stop_accepted"] is True and receipt["binding_forwarded"] is True
    assert json.loads((home / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is True
    assert len(list(directory.iterdir())) == 1  # Replaces, never appends an unbounded journal.
    (home / "fail-consumer").touch()
    hook(expected=1)
    assert json.loads(receipt_path.read_text())["consumer_returncode"] == 7
    (home / "fail-consumer").unlink()
    # Refuse a symlinked destination without touching it or breaking routing.
    receipt_path.unlink()
    directory.rmdir()
    outside = home / "outside"
    outside.mkdir()
    directory.symlink_to(outside, target_is_directory=True)
    assert "receipt could not be written" in hook().stderr
    assert not list(outside.iterdir())
    directory.unlink()
    directory.write_text("not a directory")
    assert "receipt could not be written" in hook().stderr
    assert config_path.read_bytes() == accepted_config and binding_path.read_bytes() == binding_before
    print("ok - root hook receipts, retained fallback, accepted forwarding, privacy and failure isolation:", mode)


def service():
    code, tmp = map(Path, sys.argv[2:4])
    env = dict(os.environ, FM_HOME=str(tmp / "home"))
    assert not any(key.startswith(("CODEX_", "CLAUDE_")) for key in env)
    ancestors = []
    pid = os.getpid()
    while pid > 1:
        ancestors.append(pid)
        pid = int(subprocess.check_output(["ps", "-p", str(pid), "-o", "ppid="], text=True))
    for line in sys.stdin:
        request = json.loads(line)
        assert request["root_pid"] not in ancestors
        script = code / "bin" / ("fm-captain-hold.sh" if request["owner"] == "hold" else "fm-agent-notify.sh")
        args = [] if request["owner"] == "hold" else ["--home", str(tmp / "home")]
        completed = subprocess.run(["bash", str(script), *args, *request["args"]],
                                   env=env, text=True, capture_output=True)
        print(json.dumps({"returncode": completed.returncode, "stderr": completed.stderr,
                          "stdout": completed.stdout, "root_ancestor": False}), flush=True)


def additional():
    mode = sys.argv[1]
    code, tmp = map(Path, sys.argv[2:4])
    home = tmp / (mode + "-home")
    home.mkdir()
    (home / "state").mkdir()
    for name in (".lock", ".session-start-complete"):
        (home / "state" / name).write_text(str(os.getpid()))
    consumer = tmp / "consumer.py"
    env = dict(os.environ, FM_HOME=str(home))
    sid = "fixture-" + mode
    provider = "codex" if mode == "shared" else "claude"
    payload = {"session_id": sid}
    if mode == "shared":
        env.update(CODEX_THREAD_ID=sid, CODEX_HOME=str(home / "provider"))
        sessions = home / "provider/sessions"
        sessions.mkdir(parents=True)
        (sessions / (sid + ".jsonl")).write_text(json.dumps({"type": "session_meta", "payload":
            {"id": sid, "cwd": str(home), "source": "vscode"}}) + "\n")
    else:
        env.update(CLAUDE_CODE_SESSION_ID=sid, CLAUDE_PID=str(os.getpid()))
        (home / "state/.lock-session").write_text(sid)
        transcript = home / (sid + ".jsonl")
        transcript.write_text(json.dumps({"sessionId": sid, "cwd": str(home)}) + "\n")
        payload["transcript_path"] = str(transcript)

    def cmd(*args, expected=0, data=None):
        completed = subprocess.run(["bash", str(code / "bin/fm-agent-notify.sh"), "--home", str(home), *map(str, args)],
                                  input=json.dumps(data or payload), env=env, text=True, capture_output=True)
        assert completed.returncode == expected, (mode, args, completed.stderr)
        return completed.stdout

    cmd("initialize", "--consumer", consumer)
    if mode == "shared":
        cmd("bind", provider, expected=1)  # A shared PID plus one inherited ID is insufficient.
        env["CODEX_SESSION_ID"] = sid
    cmd("bind", provider)
    cmd("hook", provider, "--consumer", consumer, data={**payload, "hook_event_name": "Stop"})
    assert json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is None
    cmd("accept-root")
    if mode == "shared":
        # Native hook session identity is independent of a shared process's
        # tool environment, which is needed to claim, not to select a binding.
        env.pop("CODEX_THREAD_ID")
        env.pop("CODEX_SESSION_ID")
    cmd("hook", provider, "--consumer", consumer, data={**payload, "hook_event_name": "Stop"})
    record = json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])
    assert record["binding"]["session_id"] == sid
    if mode == "shared":
        # An inherited foreign binding cannot classify a different/absent SID.
        env["AGENT_NOTIFY_FIRSTMATE_BINDING"] = str(home / "state/agent-notify" / (provider + "-" + sid + ".json"))
        for other in ({"session_id": "another-thread"}, {}):
            cmd("hook", provider, "--consumer", consumer, data={**other, "hook_event_name": "Stop"})
            assert json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is None
        encoded = subprocess.run(["bash", str(code / "bin/fm-operational-input.sh"), "encode", "watcher"],
                                 input="fixture wake", text=True, capture_output=True, check=True).stdout
        cmd("hook", provider, "--consumer", consumer,
            data={**payload, "hook_event_name": "UserPromptSubmit", "prompt": encoded})
        assert json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])["payload"]["firstmate_input"] == "operational"
        (home / "state/.session-start-complete").write_text("0")
        cmd("hook", provider, "--consumer", consumer, data={**payload, "hook_event_name": "Stop"})
        assert json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is None
        (home / "state/.session-start-complete").write_text(str(os.getpid()))
        env.update(CODEX_THREAD_ID=sid, CODEX_SESSION_ID=sid)
        at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        cmd("response", "initiative", "real-answer", "open", "--at", at)
        record = json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])
        assert record["binding"]["session_id"] == sid
        worktree = tmp / "shared-worker"
        worktree.mkdir()
        worker_sid = "unbound-shared-worker"
        (sessions / (worker_sid + ".jsonl")).write_text(json.dumps({"type": "session_meta", "payload":
            {"id": worker_sid, "cwd": str(worktree), "source": "vscode"}}) + "\n")
        (home / "state/shared-worker.meta").write_text(f"endpoint_task_id=shared-worker\nkind=ship\nharness=codex\nspawn_gen=generation-1\nworktree={worktree}\n")
        env.update(FM_TASK_ID="shared-worker", FM_TASK_INBOX=str(home / "state/shared-worker.inbox"),
                   FM_NOTIFY_SPAWN_GEN="generation-1", CODEX_THREAD_ID=worker_sid, CODEX_SESSION_ID=worker_sid)
        cmd("hook", provider, "--consumer", consumer, data={"session_id": worker_sid, "hook_event_name": "Stop"})
        assert json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])["binding"] is None
        print("ok - shared native payload selects proven binding; other/missing SID and unbound shared worker retain fallback")
    else:
        cmd("hook", provider, "--consumer", consumer, data={**payload, "hook_event_name": "PermissionRequest"})
        record = json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])
        assert record["payload"]["hook_event_name"] == "PermissionRequest" and record["binding"]["role"] == "firstmate"
        env["CLAUDE_CODE_SESSION_ID"] = "foreign"
        cmd("bind", provider, expected=1)
        worktree = tmp / "claude-worker"
        worktree.mkdir()
        worker_sid = "fixture-claude-worker"
        transcript = home / (worker_sid + ".jsonl")
        # Current Claude Code leads with a cwd-less record; adoption must skip it.
        transcript.write_text(json.dumps({"type": "last-prompt", "sessionId": worker_sid}) + "\n"
                              + json.dumps({"sessionId": worker_sid, "cwd": str(worktree)}) + "\n")
        (home / "state/claude-worker.meta").write_text(f"endpoint_task_id=claude-worker\nkind=ship\nharness=claude\nspawn_gen=generation-1\nworktree={worktree}\n")
        env.update(FM_TASK_ID="claude-worker", FM_TASK_INBOX=str(home / "state/claude-worker.inbox"),
                   FM_NOTIFY_SPAWN_GEN="generation-1")
        # A genuine native hook, not inherited tool-session text, selects the
        # session. Native PID/transcript and launch ownership remain mandatory.
        env.pop("CLAUDE_CODE_SESSION_ID")
        cmd("hook", provider, "--consumer", consumer,
            data={"session_id": worker_sid, "transcript_path": str(transcript), "hook_event_name": "Stop"})
        record = json.loads((tmp / "consumer.jsonl").read_text().splitlines()[-1])
        assert record["binding"]["role"] == "ship" and record["binding"]["session_id"] == worker_sid
        print("ok - Claude native process/transcript/lock and automatic worker hook adoption without manual bind")


def claude_metadata():
    """Current Claude transcripts lead with records that carry no cwd."""
    code, tmp = map(Path, sys.argv[2:4])
    home = tmp / "claude-metadata-home"
    (home / "state").mkdir(parents=True)
    (home / "bin").mkdir()
    (home / "AGENTS.md").write_text("fixture\n")
    subprocess.run(["git", "init", "-q", str(home)], check=True)
    for name in (".lock", ".session-start-complete"):
        (home / "state" / name).write_text(str(os.getpid()))
    sid = "fixture-claude-metadata"
    (home / "state/.lock-session").write_text(sid)
    store = tmp / "claude-config"
    project = store / "projects" / "-fixture-project"
    project.mkdir(parents=True)
    transcript = project / (sid + ".jsonl")
    consumer = tmp / "metadata-consumer.py"
    log = tmp / "metadata-consumer.jsonl"
    consumer.write_text('''import json,os,sys
from pathlib import Path
binding = Path(os.environ['AGENT_NOTIFY_FIRSTMATE_BINDING'])
row = {'provider': sys.argv[2], 'payload': json.load(sys.stdin),
       'binding': json.loads(binding.read_text())}
with Path(__file__).with_suffix('.jsonl').open('a') as stream:
    stream.write(json.dumps(row) + '\\n')
''')
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FM_", "CODEX_", "CLAUDE_"))}
    env.update(FM_HOME=str(home), FM_ROOT_OVERRIDE=str(home), CLAUDE_CODE_SESSION_ID=sid,
               CLAUDE_PID=str(os.getpid()), CLAUDE_CONFIG_DIR=str(store))
    # Shapes observed on Claude Code 2.1.309-2.1.311, without any content.
    lead = [{"type": "last-prompt", "leafUuid": "fixture-leaf", "sessionId": sid},
            {"type": "permission-mode", "permissionMode": "default", "sessionId": sid},
            {"type": "file-history-snapshot", "messageId": "fixture-message", "snapshot": {}}]
    conversation = {"type": "attachment", "sessionId": sid, "cwd": str(home), "uuid": "fixture-uuid"}
    state = home / "state/agent-notify"
    binding = state / ("claude-" + sid + ".json")
    hook_payload = {"session_id": sid, "transcript_path": str(transcript), "hook_event_name": "Stop"}
    fresh = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    call = ("call", "first-turn-call", 1, "open", "--at", fresh)

    def records(*rows, path=transcript):
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def run(args, data="", expected=0, **extra):
        completed = subprocess.run(args, input=data if isinstance(data, str) else json.dumps(data),
                                   env={**env, **extra}, text=True, capture_output=True, timeout=30)
        assert completed.returncode == expected, (args, completed.returncode, completed.stderr)
        return completed

    def bridge(*args, **kwargs):
        return run(["bash", str(code / "bin/fm-agent-notify.sh"), "--home", str(home), *map(str, args)], **kwargs)

    def register(data=hook_payload, **extra):
        completed = run(["bash", str(code / "bin/fm-agent-notify-register.sh")], data=data, **extra)
        assert completed.stdout == "" and completed.stderr == "", completed
        return completed

    def refused(reason, producer=True, **kwargs):
        assert reason in bridge("bind", "claude", expected=1, **kwargs).stderr
        if producer:
            assert reason in bridge(*call, expected=1, **kwargs).stderr
        assert not binding.exists() and not (state / "root.json").exists()
        assert not log.exists() and not list((state / "events").glob("*.json"))

    register()  # Unconfigured homes stay inert.
    assert not state.exists()
    bridge("initialize", "--consumer", consumer)
    # Fresh startup: SessionStart runs before Claude writes any transcript.
    refused("no unique native Claude transcript")
    records(*lead)
    refused("has no working directory")
    for wrong in ([{**lead[0], "sessionId": "another-session"}, conversation],
                  [*lead, {key: value for key, value in conversation.items() if key != "sessionId"}],
                  [*lead, {**conversation, "sessionId": "another-session"}]):
        records(*wrong)
        refused("session metadata mismatch")
    records(*lead, conversation)
    duplicate = store / "projects/-another-project" / transcript.name
    duplicate.parent.mkdir()
    duplicate.write_text(transcript.read_text())
    refused("no unique native Claude transcript")
    duplicate.unlink()
    # Skipping cwd-less records leaves every supervisor proof in force.
    refused("native hook and tool session disagree", producer=False,
            data={**hook_payload, "session_id": "another-session"})
    refused("no unique native Claude transcript", CLAUDE_CODE_SESSION_ID="another-session")
    refused("no trusted Claude process ancestor", CLAUDE_PID=str(os.getppid()))
    for path, replacement, reason in ((home / "state/.lock", "1", "does not own completed supervisor startup"),
                                      (home / "state/.session-start-complete", "1", "does not own completed supervisor startup"),
                                      (home / "state/.lock-session", "another-session", "lock session mismatch")):
        saved = path.read_bytes()
        path.write_text(replacement)
        refused(reason)
        path.write_bytes(saved)
    records(*lead, {**conversation, "cwd": str(tmp)})
    refused("not this primary supervisor")
    records(*lead, conversation)
    (home / ".fm-secondmate-home").touch()
    refused("not this primary supervisor")
    (home / ".fm-secondmate-home").unlink()
    bridge(*call, expected=1, FM_TASK_ID="worker")
    assert not binding.exists() and not (state / "root.json").exists() and not log.exists()

    (home / "data").mkdir()
    (home / ".tasks.toml").write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 20\n')
    (home / "data/backlog.md").write_text("## In flight\n\n## Queued\n\n## Done\n")
    run(["bash", str(code / "bin/fm-tasks-axi.sh"), "add", "first-turn-result", "first turn result"])

    def first_turn(*args, **kwargs):
        assert not binding.exists() and not (state / "root.json").exists()
        bridge(*args, **kwargs)
        assert json.loads(binding.read_text())["proof"]["transcript_path"] == str(transcript)
        assert json.loads((state / "root.json").read_text()) == {"provider": "claude", "session_id": sid}
        assert json.loads((home / "config/agent-notify.json").read_text())["root_stop_accepted"] is False
        binding.unlink()
        (state / "root.json").unlink()

    first_turn(*call, CODEX_THREAD_ID="inherited-thread")
    first_turn("call", "first-turn-call", 1, "resolved", "--at", fresh)
    first_turn("response", "first-turn-response", "request-1", "open", "--at", fresh)
    first_turn("response", "first-turn-response", "request-1", "resolved", "--at", fresh)
    first_turn("designate", "first-turn-result", "first-turn-outcome")
    assert json.loads((home / "data/agent-notify/designate/first-turn-result.json").read_text())["outcome"] == "first-turn-outcome"
    first_turn("initiative", "first-turn-initiative", "--requires", "first-turn-outcome")
    first_turn("landed", "first-turn-result", data={"state": "done", "structured": True,
               "completion": {"verb": "done"}, "local_note": "local main"})
    first_turn("complete", "first-turn-initiative")
    delivered = [json.loads(line) for line in log.read_text().splitlines()]
    assert [row["payload"]["firstmate_event"]["kind"] for row in delivered] == [
        "captain_call", "captain_call", "response_required", "response_required",
        "deliverable_landed", "initiative_completed"]
    assert [row["payload"]["firstmate_event"].get("state") for row in delivered[:4]] == ["open", "resolved", "open", "resolved"]
    assert all(row["provider"] == "claude" and row["payload"]["hook_event_name"] == "FirstmateEvent"
               and row["binding"]["session_id"] == sid and row["binding"]["role"] == "firstmate"
               and row["binding"]["proof"]["pid"] == os.getpid() for row in delivered)
    persisted = [json.loads(path.read_text()) for path in (state / "events").glob("*.json")]
    assert len(persisted) == 4 and all(row["accepted"] for row in persisted)
    bridge(*call)
    bridge("complete", "first-turn-initiative")
    assert len(log.read_text().splitlines()) == len(delivered)
    binding.unlink()
    (state / "root.json").unlink()
    print("ok - first-turn Claude producers establish root before declarations/events; all proofs enforced; isolated delivery and dedup")
    # In-session bind with empty stdin resolves the session's own transcript.
    assert bridge("bind", "claude").stdout.strip() == str(binding)
    assert json.loads(binding.read_text())["proof"]["transcript_path"] == str(transcript)
    assert json.loads((state / "root.json").read_text()) == {"provider": "claude", "session_id": sid}
    bridge("accept-root")  # current_root revalidates through the recorded transcript.
    same_id_rebind(binding, lambda expected: bridge("bind", "claude", expected=expected), home / "state")
    saved = (home / "state/.lock-session").read_bytes()
    proof = json.loads(binding.read_text())
    with running() as pid:
        binding.write_text(json.dumps({**proof, "proof": {**proof["proof"], "pid": pid, "started": NEVER_STARTED}}))
        (home / "state/.lock-session").write_text("another-session")
        assert "lock session mismatch" in bridge("bind", "claude", expected=1).stderr
        assert json.loads(binding.read_text())["proof"]["pid"] == pid
        (home / "state/.lock-session").write_bytes(saved)
        bridge("bind", "claude")
    assert json.loads(binding.read_text()) == proof
    bridge("accept-root")
    bridge("revoke", "claude")
    assert not binding.exists()
    bridge("bind", "claude")
    print("ok - Claude transcript metadata skips cwd-less leading records; store lookup; stale resume rebinds; proofs kept")

    # The Stop retry binds once the transcript exists and is otherwise inert.
    def unbind():
        binding.unlink()
        (state / "root.json").unlink()

    unbind()
    register({**hook_payload, "cursor_version": "fixture"})
    register(FM_ROOT_OVERRIDE=str(tmp))
    register(CLAUDE_CODE_SESSION_ID="")
    saved = (home / "state/.lock-session").read_bytes()
    (home / "state/.lock-session").write_text("another-session")
    register()
    assert not binding.exists()
    (home / "state/.lock-session").write_bytes(saved)
    register()
    bound = binding.read_bytes()
    assert json.loads(bound)["proof"]["transcript_path"] == str(transcript)
    assert json.loads((state / "root.json").read_text()) == {"provider": "claude", "session_id": sid}
    # A resumed session's stale same-ID binding is replaced; a valid one is kept.
    with running() as pid:
        binding.write_text(json.dumps({**json.loads(bound), "proof": {**json.loads(bound)["proof"],
                                                                       "pid": pid, "started": NEVER_STARTED}}))
        register()
    assert binding.read_bytes() == bound
    kept = {**json.loads(bound), "proof": {**json.loads(bound)["proof"], "transcript_path": str(tmp / "kept.jsonl")}}
    binding.write_text(json.dumps(kept))
    assert bridge("bind", "claude", "--unless-valid", data=hook_payload).stdout.strip() == str(binding)
    assert "revoke first" in bridge("bind", "claude", data=hook_payload, expected=1).stderr
    register()
    assert json.loads(binding.read_text()) == kept
    binding.write_bytes(bound)
    assert run(["bash", str(code / "bin/fm-agent-notify-register.sh"), "--help"]).stdout.startswith("Usage:")
    run(["bash", str(code / "bin/fm-agent-notify-register.sh"), "manual"], expected=2)
    print("ok - Claude Stop registration retry binds an unbound or stale root silently; inert unconfigured/foreign/out of scope/validly bound")

    # Startup registration tries each present provider; only the lock owner wins.
    script = '. "$1/bin/fm-agent-notify-lib.sh"; fm_notify_register'
    unbind()
    completed = run(["bash", "-c", script, "notify-test", str(code)], CODEX_THREAD_ID="inherited-thread")
    assert completed.stderr == "" and binding.exists()
    unbind()
    transcript.unlink()
    completed = run(["bash", "-c", script, "notify-test", str(code)], CODEX_THREAD_ID="inherited-thread")
    assert "; codex: " in completed.stderr, completed.stderr
    assert "claude: no unique native Claude transcript" in completed.stderr and not binding.exists()
    print("ok - startup registration tries each present provider and names every refusal")


def driver():
    code, tmp = map(Path, sys.argv[2:4])
    bridge = code / "bin/fm-agent-notify.sh"
    home = tmp / "home"
    home.mkdir()
    for dirname in ("state", "data", "config"):
        (home / dirname).mkdir()
    (home / ".tasks.toml").write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 20\n')
    (home / "data/backlog.md").write_text("## In flight\n\n## Queued\n\n## Done\n")
    consumer = tmp / "consumer.py"
    log = tmp / "consumer.jsonl"
    # This subprocess has no DB/network code and no imports capable of sending.
    consumer.write_text('''import json,os,sys
from pathlib import Path
root=Path(__file__).parent
assert sys.argv[1] == 'hook'
if (root/'fail-consumer').exists(): sys.exit(7)
binding=os.environ.get('AGENT_NOTIFY_FIRSTMATE_BINDING')
row={'provider':sys.argv[2], 'payload':json.load(sys.stdin),
     'task':os.environ.get('FM_TASK_ID'), 'inbox':os.environ.get('FM_TASK_INBOX'),
     'binding':json.loads(Path(binding).read_text()) if binding else None}
with (root/'consumer.jsonl').open('a') as f: f.write(json.dumps(row)+'\\n')
''')
    env = dict(os.environ, FM_HOME=str(home), CODEX_HOME=str(tmp / "codex-home"),
               CODEX_THREAD_ID="fixture-root", CODEX_SESSION_ID="fixture-root")
    session_dir = Path(env["CODEX_HOME"]) / "sessions"
    session_dir.mkdir(parents=True)

    def session(sid, cwd):
        env["CODEX_THREAD_ID"] = env["CODEX_SESSION_ID"] = sid
        (session_dir / ("rollout-" + sid + ".jsonl")).write_text(json.dumps(
            {"type": "session_meta", "payload": {"id": sid, "cwd": str(cwd), "source": "cli"}}) + "\n")

    def cmd(*args, payload=None, expected=0, more_env=None):
        completed = subprocess.run(["bash", str(bridge), "--home", str(home), *map(str, args)],
            input=json.dumps(payload or {}), capture_output=True, text=True,
            env={**env, **(more_env or {})})
        assert completed.returncode == expected, (args, completed.returncode, completed.stdout, completed.stderr)
        return completed.stdout.strip()

    def records():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def hook(event="Stop", sid=None, **kwargs):
        cmd("hook", "codex", "--consumer", consumer,
            payload={"session_id": sid or env["CODEX_THREAD_ID"], "hook_event_name": event, **kwargs})
        return records()[-1]

    def tasks(*args):
        return subprocess.run(["bash", str(code / "bin/fm-tasks-axi.sh"), *args],
                              capture_output=True, text=True, env=env, check=True).stdout

    def call(task, count, state, at):
        cmd("call", task, count, state, "--at", at)

    service_in = os.fdopen(os.dup(int(sys.argv[4])), "w", buffering=1)
    service_out = os.fdopen(os.dup(int(sys.argv[5])), "r")

    def external(owner, *args, expected=0):
        service_in.write(json.dumps({"owner": owner, "args": list(map(str, args)), "root_pid": os.getpid()}) + "\n")
        result = json.loads(service_out.readline())
        assert result["returncode"] == expected, result
        assert result["root_ancestor"] is False
        return result

    now = datetime.datetime.now(datetime.timezone.utc)
    fresh = (now + datetime.timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    session("fixture-root", home)
    assert hook()["binding"] is None  # Missing config still forwards.
    cmd("initialize", "--consumer", consumer)
    initial = json.loads((home / "config/agent-notify.json").read_text())
    cmd("initialize", "--consumer", consumer)
    assert json.loads((home / "config/agent-notify.json").read_text()) == initial
    cmd("bind", "codex", expected=1)  # cwd/native session alone cannot own root.
    for name in (".lock", ".session-start-complete"):
        (home / "state" / name).write_text(str(os.getpid()) + "\n")
    assert hook("SessionStart")["binding"] is None
    cmd("accept-root", expected=1)  # A hook never auto-claims a supervisor.
    binding_path = Path(cmd("bind", "codex"))
    assert json.loads(binding_path.read_text())["role"] == "firstmate"
    assert hook()["binding"] is None  # Root Stop filter not accepted.
    cmd("accept-root")
    assert hook()["binding"]["session_id"] == "fixture-root"
    assert hook(sid="foreign-thread", firstmate_input="operational")["binding"] is None
    assert "firstmate_input" not in records()[-1]["payload"]
    assert hook("UserPromptSubmit", prompt="Human question?")["payload"].get("firstmate_input") is None
    encoded = subprocess.run(["bash", str(code / "bin/fm-operational-input.sh"), "encode", "watcher"],
                             input="fixture wake", text=True, capture_output=True, check=True).stdout
    assert hook("UserPromptSubmit", prompt=encoded)["payload"]["firstmate_input"] == "operational"
    assert hook(sid="unknown", firstmate_event={"kind": "initiative_completed"})["binding"] is None
    assert "firstmate_event" not in records()[-1]["payload"]
    assert hook(sid="invalid/id")["binding"] is None
    print("ok - native process/session plus supervisor ownership; unknown/personal fallback; operational input")

    same_id_rebind(binding_path, lambda expected: cmd("bind", "codex", expected=expected), home / "state")
    assert hook()["binding"]["session_id"] == "fixture-root"
    print("ok - resumed Codex root replaces only a stale same-ID binding after every proof; a live one refuses")

    before = len(records())
    call("seeded", 1, "open", old)
    assert len(records()) == before
    call("question", 1, "open", fresh)
    call("question", 1, "open", fresh)
    assert len(records()) == before + 1
    call("question", 1, "resolved", fresh)
    call("question", 1, "open", fresh)
    call("question", 1, "resolved", fresh)
    assert len(records()) == before + 2
    call("answered-first", 1, "resolved", fresh)
    call("answered-first", 1, "open", fresh)
    assert records()[-1]["payload"]["firstmate_event"]["state"] == "resolved"
    assert len(records()) == before + 3
    (tmp / "fail-consumer").touch()
    cmd("call", "retry", 1, "open", "--at", fresh, expected=1)
    cmd("call", "retry", 1, "resolved", "--at", fresh, expected=1)
    (tmp / "fail-consumer").unlink()
    call("retry", 1, "open", fresh)  # Tombstone prevents stale open.
    call("retry", 1, "resolved", fresh)  # Failed resolution can be retried.
    assert records()[-1]["payload"]["firstmate_event"]["state"] == "resolved"
    cmd("response", "main", "answer-request-1", "open", "--at", fresh)
    cmd("response", "main", "answer-request-1", "resolved", "--at", fresh)
    print("ok - stable call identity, historical seed, retry, dedup and resolve-before-open")

    for task in ("result-a", "result-b", "internal", "already-done"):
        tasks("add", task, task)
    tasks("done", "already-done", "--note", "local main")
    cmd("designate", "already-done", "old-result", expected=1)
    cmd("designate", "result-a", "outcome-a")
    cmd("designate", "result-a", "outcome-a")
    cmd("designate", "result-b", "outcome-a", expected=1)
    cmd("designate", "result-b", "outcome-b")
    cmd("initiative", "main-initiative", "--requires", "outcome-a", "outcome-b")
    cmd("complete", "legacy-task", expected=1)
    cmd("complete", "main-initiative", expected=1)
    before = len(records())
    row = {"state": "done", "structured": True, "kind": "ship", "completion": {"verb": "done"}, "local_note": "local main"}
    cmd("landed", "internal", payload=row)
    assert len(records()) == before
    for bad in ({**row, "local_note": None}, {**row, "hold_kind": "captain"}, {**row, "state": "in_flight"}):
        cmd("landed", "result-a", payload=bad, expected=1)
    cmd("landed", "result-a", payload=row)
    cmd("landed", "result-a", payload=row)
    cmd("complete", "main-initiative", expected=1)
    cmd("landed", "result-b", payload=row)
    assert len(records()) == before + 2
    cmd("complete", "main-initiative")
    cmd("complete", "main-initiative")
    event = records()[-1]["payload"]["firstmate_event"]
    assert event["kind"] == "initiative_completed" and event["task_id"] == event["initiative_id"]
    cmd("revoke", "codex")
    session("replacement-root", home)
    cmd("bind", "codex")
    cmd("landed", "result-a", payload=row)
    cmd("complete", "main-initiative")
    assert len(records()) == before + 3
    print("ok - explicit deliverables and main requirements, artifact eligibility, no Any-Done/backfill, session replacement dedup")

    # Presentation augments a proven event; it does not enable root Stop
    # filtering, designate an outcome, or accept a URL from report prose.
    config_path = home / "config/agent-notify.json"
    configured = json.loads(config_path.read_text())
    configured["root_stop_accepted"] = False
    config_path.write_text(json.dumps(configured))
    tasks("add", "presentation", "Deck móvil data/presentation/report.md")
    detail = "Las tarjetas muestran el resultado y abren el resumen correcto."
    cmd("designate", "presentation", "presentation-outcome", "--detail", detail)
    cmd("designate", "presentation", "presentation-outcome", "--detail", "another result", expected=1)
    before = len(records())
    cmd("landed", "presentation", payload=row, more_env={"FM_DATA_OVERRIDE": str(tmp / "unrelated-data")})
    event = records()[-1]["payload"]["firstmate_event"]
    context = event["context"]
    assert context == {"version": 1, "task_label": "Deck móvil", "home_label": "Firstmate",
                       "detail": detail, "target": {"view": "delivery", "id": event["artifact_id"]}}
    assert event["summary"] == detail and "presentation" not in event
    assert not any(key in event for key in ("click_url", "home", "home_id"))
    assert json.loads(config_path.read_text()) == configured
    cmd("landed", "presentation", payload=row)
    assert len(records()) == before + 1
    for bad in ("bad\nheader", "x" * 401, "token=private", "/private/report.md", "a" * 64):
        cmd("response", "presentation", "invalid-presentation", "open", "--at", fresh,
            "--detail", bad, expected=1)
    cmd("response", "presentation", "explicit-question", "open", "--at", fresh,
        "--task-label", "Decidir la entrega móvil", "--detail", "¿Publicar esta versión local?")
    event = records()[-1]["payload"]["firstmate_event"]
    assert event["context"]["target"] == {"view": "question", "id": "explicit-question"}
    assert event["context"]["detail"] == "¿Publicar esta versión local?"
    cmd("response", "presentation", "explicit-question", "resolved", "--at", fresh)
    assert records()[-1]["payload"]["firstmate_event"]["context"] == event["context"]
    # Restore the fixture hook mode for the existing native-worker regressions.
    configured["root_stop_accepted"] = True
    config_path.write_text(json.dumps(configured))
    print("ok - bounded canonical context, immutable result prose, exact question/artifact targets; no URL/path, root acceptance or replay")

    worktree = tmp / "worktree"
    worktree.mkdir()
    session("fixture-worker", worktree)
    env.update(FM_TASK_ID="worker", FM_TASK_INBOX=str(home / "state/worker.inbox"), FM_NOTIFY_SPAWN_GEN="generation-1")
    meta = home / "state/worker.meta"
    def worker_meta(kind="ship", generation="generation-1"):
        meta.write_text(f"endpoint_task_id=worker\nkind={kind}\nharness=codex\nspawn_gen={generation}\nworktree={worktree}\n")
    worker_meta()
    # Drive the actual installed wrapper path, never the manual bind command.
    # A fresh launch receives this exact generation; pre-existing processes do
    # not. Native hook session identity need not inherit tool-local markers.
    env.pop("CODEX_THREAD_ID")
    env.pop("CODEX_SESSION_ID")
    config = home / "config/agent-notify.json"
    disabled = config.with_suffix(".disabled")
    config.rename(disabled)
    assert hook("UserPromptSubmit", sid="fixture-worker", prompt="first native prompt")["binding"] is None
    disabled.rename(config)
    env.pop("FM_NOTIFY_SPAWN_GEN")
    assert hook(sid="fixture-worker")["binding"] is None  # Legacy launch is not retroactively promoted.
    env["FM_NOTIFY_SPAWN_GEN"] = "generation-1"
    assert hook("UserPromptSubmit", sid="fixture-worker", prompt="first native prompt")["binding"]["role"] == "ship"
    env.update(CODEX_THREAD_ID="fixture-worker", CODEX_SESSION_ID="fixture-worker")
    assert records()[-1]["task"] == "worker"
    cmd("designate", "result-a", "outcome-a", expected=1)
    cmd("call", "worker-forgery", 1, "open", "--at", fresh, expected=1)
    worker_meta(generation="generation-2")
    assert hook()["binding"] is None
    assert records()[-1]["task"] is None and records()[-1]["inbox"] is None
    cmd("bind", "codex", expected=1)
    worker_meta()
    cmd("revoke", "codex")
    worker_meta(kind="scout")
    assert hook("PermissionRequest")["binding"]["role"] == "scout"
    cmd("revoke", "codex")
    worker_meta(kind="secondmate")
    env.pop("FM_TASK_ID")  # Persistent secondmate launches intentionally omit it.
    assert hook()["binding"]["role"] == "secondmate"
    env["FM_TASK_ID"] = "worker"
    assert hook(sid="unbound-worker-thread")["binding"] is None
    cmd("bind", "codex", more_env={"FM_TASK_INBOX": str(tmp / "foreign/state/worker.inbox")}, expected=1)
    assert not (tmp / "foreign").exists()
    print("ok - ordinary hooks auto-adopt ship/scout/secondmate with exact launch proof; absent config/legacy/stale/foreign stay unclassified")

    # Authoritative hold and backlog-close integrations, using fixture tasks-axi.
    for key in ("FM_TASK_ID", "FM_TASK_INBOX", "FM_NOTIFY_SPAWN_GEN"):
        env.pop(key, None)
    session("replacement-root", home)
    env["FM_CAPTAIN_HOLD_NOW"] = fresh
    def hold(*args):
        completed = subprocess.run(["bash", str(code / "bin/fm-captain-hold.sh"), *args],
                                   text=True, capture_output=True, env=env)
        assert completed.returncode == 0, completed.stderr
        return completed.stdout
    before = len(records())
    hold("hold", "actual-call", "--title", "actual call", "--reason", "explicit captain answer")
    assert len(records()) == before + 1, records()[-1]
    original = records()[-1]["payload"]["firstmate_event"]["context"]
    assert original == {"version": 1, "task_label": "actual call", "home_label": "Firstmate",
                        "detail": "explicit captain answer", "target": {"view": "question", "id": "hold:1"}}
    # Neither a worker nor a service may open a call or fabricate its answer.
    external("bridge", "call", "service-forgery", 1, "open", "--at", fresh, expected=1)
    external("bridge", "call", "actual-call", 1, "resolved", "--at", fresh, expected=1)
    assert len(records()) == before + 1
    answer = tmp / "answer.txt"
    answer.write_text("proceed")
    external("hold", "answer", "actual-call", "--decision-file", str(answer))
    assert len(records()) == before + 2
    assert records()[-1]["payload"]["firstmate_event"]["state"] == "resolved"
    assert records()[-1]["payload"]["firstmate_event"]["context"] == original
    assert records()[-1]["payload"]["firstmate_event"]["event_id"] == records()[-2]["payload"]["firstmate_event"]["event_id"]
    assert records()[-1]["binding"]["session_id"] == "replacement-root"
    external("hold", "answer", "actual-call", "--decision-file", str(answer))
    assert len(records()) == before + 2  # Canonical service retry stays consumed.
    call("worker-forgery", 1, "open", fresh)
    call("service-forgery", 1, "open", fresh)
    assert len(records()) == before + 4  # Failed unauthorized writes left no tombstones.
    external("bridge", "call", "actual-call", 2, "resolved", "--at", fresh, expected=1)
    assert len(records()) == before + 4  # Another occurrence is not this canonical answer.
    before = len(records())
    hold("hold", "deferred", "--title", "deferred call", "--reason", "later", "--until", "2099-01-01")
    assert len(records()) == before
    tasks("add", "transition-result", "transition result")
    cmd("designate", "transition-result", "transition-outcome")
    script = '. "$1/bin/fm-tasks-axi-lib.sh"; . "$1/bin/fm-backlog-transition-lib.sh"; fm_backlog_done "$FM_HOME/data" transition-result --note "local main"'
    completed = subprocess.run(["bash", "-c", script, "notify-test", str(code)], env=env, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    assert records()[-1]["payload"]["firstmate_event"]["task_id"] == "transition-result", completed.stderr
    print("ok - canonical service answer cancels through root without native ancestry; forged calls refused; lifecycle seams")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "routing-check":
        routing_launch(*map(Path, sys.argv[2:4]))
    elif len(sys.argv) > 1 and sys.argv[1] == "routing":
        routing()
    elif len(sys.argv) > 1 and sys.argv[1] == "driver":
        driver()
    elif len(sys.argv) > 1 and sys.argv[1] == "service":
        service()
    elif len(sys.argv) > 1 and sys.argv[1] in ("shared", "claude"):
        additional()
    elif len(sys.argv) > 1 and sys.argv[1] == "claude-metadata":
        claude_metadata()
    else:
        launch()
