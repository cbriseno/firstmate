#!/usr/bin/env python3
"""Opt-in, synchronous Firstmate -> Agent Notify producer (Unix).

No daemon, polling, transcript prose classifier, or alternate publisher.
The CLI is the schema/transition owner. All private records are version 1.

--home is always explicit and canonical. `initialize --consumer /abs/script.py`
creates config/agent-notify.json with a historical cutoff and root_stop_accepted
false. This is bridge activation only, not Agent Notify preferences. Initialization
is idempotent and never moves the cutoff. No historical scan or backfill occurs.

`bind codex|claude` runs inside the native session, after supervisor startup or
with spawn's exact task inbox/generation. It takes NO supplied native session ID.
Native metadata, process ancestry and launch/lock ownership must agree. A Codex
app-server tool-local claim additionally requires equal CODEX_THREAD_ID and
CODEX_SESSION_ID. Claude metadata is the first cwd-bearing record of the
session's own transcript: the hook payload's transcript_path, or for an
in-session command (empty stdin) the unique <sid>.jsonl in Claude's project
store. Leading metadata-only records are skipped; any naming another session
refuse. A fresh Claude startup writes that transcript only after its
SessionStart hook, so startup registration cannot prove it there. Codex
SessionStart may lack the tool-local session variables required by bind.
Native-root operations establish a missing or stale Codex or Claude root
through the same bind before producing declarations or events. Each present
provider is tried; only the native process owning completed startup can bind.
The tracked Claude Stop entry
bin/fm-agent-notify-register.sh also retries once the transcript exists;
`bind --unless-valid` keeps that retry inert while this session's
recorded binding is still valid. Each authorized native hook then uses its
genuine payload session_id to select and revalidate that exact binding,
including shared hook runtimes without tool-local environment. Unknown
sessions keep ordinary behavior.
Bindings in state/agent-notify/<provider>-<native-id>.json carry consumer fields
version/home/provider/session_id/role/task_id, plus revalidated producer proof.
A resumed session reuses its native ID: bind replaces a same-ID binding only
when its recorded proof process is gone or has another start time, and only
after the new claimant passes every proof above. A live recorded process still
refuses until `revoke <provider>`, which revokes the current native session
only. No pane or title is identity evidence.

With configuration present, the first existing native hook automatically binds
an unbound CLI worker using its genuine payload session_id, native metadata and
process ancestry plus the exact launch inbox/generation. No manual worker bind
or extra SessionStart registration is needed. A secondmate without FM_TASK_ID
must match the exact launch inbox and a secondmate record. Hook adoption NEVER
claims root. An unbound shared app-server worker cannot be assigned from its
shared hook alone; it needs an independently proven binding. Missing launch
generation or native Claude PID/transcript proof remains unclassified.

`accept-root` enables root hook filtering only after independent live acceptance.
Until then `hook <provider>` forwards ordinary root hooks without a binding.
For an already verified current root, each known hook atomically replaces
state/agent-notify/hooks/<provider>-<session>-<hook>.json with fixed routing
metadata: binding fingerprint/process incarnation, acceptance/forwarding state,
invocation times and consumer return code (null if no exit code was obtained).
No payload or text is retained. Unknown/stale/worker identities write no receipt.
Receipts attest this wrapper invocation, not consumer suppression, delivery,
frontend reload, acceptance or continuity. Receipt failures retain routing.
Hook installation must name this command and --home in place of the consumer's
existing hook, so the exact binding environment is set per invocation, including
shared hook runtimes. Unverified native payloads forward without a binding.
Typed operational prompts are checked by fm-operational-input.sh, never prose.

`call <task> <occurrence> open|resolved --at <UTC>` is called only by the captain
hold owner. Occurrence is its durable resolution count + 1 (the resolved count
on answer). Same-lifecycle retries deduplicate; resolve-before-open tombstones.
Calls older than initialize's cutoff are seeded consumed, never replayed.
An external answer service may resolve through the still-valid root binding
only after the hold owner's read-only `resolved` predicate confirms the exact
canonical occurrence has settled. This cannot create an opening or response.
`response <task> <request-id> open|resolved --at <UTC>` records the bound root's
explicit request for an answer, with its own durable lifecycle identity.
Technical blockers, dispatch and worker Stop are not producer events.

`designate <task> <outcome>` explicitly marks an as-yet-unlanded requested result.
The caller attests that designation is the user's requested outcome, not any Done.
`landed <task>` receives the artifact selected by the shell entry's canonical
landed rule, only from a successful lifecycle close. Each designation is immutable.
`initiative <id> --requires <outcome>...` records the explicit main scope and exact
required outcomes. `complete <id>` requires all those outcomes to have landed;
no relation or completion is inferred for legacy tasks. Each has its own identity.
Declarations in data/agent-notify survive task metadata teardown. Event records
in state/agent-notify/events retain lifecycle IDs across native session replacement.

Events invoke ONLY the configured consumer: python3 <consumer> hook <provider>
with FirstmateEvent JSON on stdin and the verified root binding environment.
No root means refusal, never a worker alert. Unacknowledged consumer failures are
durable and may be retried at the same transition; there is no replay service.
Consumer dedup, mute/pause, attention, delay, audio and human cancellation own
delivery. Accepted/consumed events never replay on restart or unmute.

Optional event.context v1 carries task_label (120), home_label (80), detail
(400), and target {view: question|delivery|task, id: existing stable identity}.
Text is bounded and single-line, never report bodies or worker status notes.
`designate`, `initiative`, `response` and `call` accept --task-label, --home-label
and --detail; declarations retain them immutably. Missing task labels come from
canonical tasks-axi show fields; call detail comes from decoded hold_reason,
with a bounded truthful delivery fallback from the canonical landed verb.
Context cannot designate or close an outcome. The consumer alone builds URLs
from its private firstmate_base_url plus binding home and event task identity;
no URL or filesystem home path is supplied by presentation. A call target is
its exact hold/request occurrence; a delivery target is its real artifact ID.
No notification setting, root acceptance or historical event is changed.
"""

import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

CODE = Path(__file__).resolve().parent
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
PRESENTATION = {"task_label": 120, "home_label": 80, "detail": 400}


def plain(value, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise ValueError("presentation must be bounded single-line text")
    # Paths, hashes and credentials are not phone presentation. Explicit callers
    # must provide a human summary instead of relying on silent redaction.
    if re.search(r"(?:^|\s)(?:/|~/|data/|state/|config/)|\b[0-9a-f]{32,}\b|"
                 r"\b(?:password|token|secret|api[_-]?key)\s*[:=]", value, re.I):
        raise ValueError("presentation must not contain paths, hashes or credentials")
    return value.strip()


def display(value, limit):
    """Canonical fields may be long or include legacy artifact links; omit those."""
    if not value:
        return None
    value = re.sub(r"(?:^|\s)(?:https?://|/|~/|data/|state/|config/)\S+", "", value)
    value = re.sub(r"\b[0-9a-f]{32,}\b", "", value, flags=re.I)
    value = " ".join(value.split())
    if len(value) > limit:
        value = value[:limit - 1].rstrip() + "…"
    try:
        return plain(value, limit)
    except ValueError:
        return None


def slug(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid stable identity")
    return value


def read(path):
    if path.is_symlink():
        raise ValueError("symlinked bridge record")
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".notify-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          timeout=15, **kwargs).stdout.strip()


def process(pid):
    return {key: run(["ps", "-p", str(pid), "-o", key + "="])
            for key in ("ppid", "comm", "args", "lstart")}


def ancestry():
    pid = os.getpid()
    for _ in range(64):
        if pid <= 1:
            return
        row = process(pid)
        yield pid, row
        pid = int(row["ppid"])


def stdin_payload():
    """An in-session command may receive no payload at all; that means {}."""
    text = "" if sys.stdin.isatty() else sys.stdin.read()
    payload = json.loads(text) if text.strip() else {}
    if not isinstance(payload, dict):
        raise ValueError("native payload must be a JSON object")
    return payload


def claude_transcript(sid, payload, worker_hook):
    # A hook payload names its own transcript. An in-session command has no
    # payload path, so it takes the unique <sid>.jsonl in Claude's own project
    # store, as Codex takes its unique session file.
    if worker_hook or "transcript_path" in payload:
        path = Path(payload.get("transcript_path", ""))
    else:
        store = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
        paths = list(store.glob("*/" + sid + ".jsonl")) if store.is_absolute() else []
        if len(paths) != 1:
            raise ValueError("no unique native Claude transcript")
        path = paths[0]
    if not path.is_absolute() or path.stem != sid or not path.is_file():
        raise ValueError("native Claude transcript required")
    return path


def claude_cwd(path, sid):
    # Claude Code writes metadata-only records (last-prompt, mode,
    # permission-mode, file-history-snapshot, ...) before its first
    # conversation record, and only conversation records carry cwd. Skip them
    # in a bounded leading read, but every record that names a session must
    # name this one, including the first cwd-bearing record.
    with path.open() as stream:
        for index, line in enumerate(stream):
            if index >= 256:
                break
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or record.get("sessionId", sid) != sid:
                raise ValueError("native Claude session metadata mismatch")
            if "cwd" in record:
                if "sessionId" not in record:
                    raise ValueError("native Claude session metadata mismatch")
                return record["cwd"]
    raise ValueError("native Claude session metadata has no working directory")


def native_sid(provider, payload, worker_hook=False):
    key = "CODEX_THREAD_ID" if provider == "codex" else "CLAUDE_CODE_SESSION_ID"
    sid = slug(payload.get("session_id", "") if worker_hook else os.environ.get(key, ""))
    if payload.get("session_id", sid) != sid:
        raise ValueError("native hook and tool session disagree")
    return sid


def live(binding):
    """The binding's proof process still runs as the recorded incarnation."""
    try:
        proof = binding["proof"]
        return process(proof["pid"])["lstart"] == proof["started"]
    except (KeyError, TypeError, OSError, ValueError, subprocess.SubprocessError):
        return False


def native(provider, home, payload, worker_hook=False):
    sid = native_sid(provider, payload, worker_hook)
    chain = list(ancestry())
    if provider == "codex":
        matches = [(p, r) for p, r in chain if Path(r["comm"]).name == "codex"]
        if not matches:
            raise ValueError("no native Codex process ancestor")
        pid, runtime = matches[0]
        provider_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        paths = list((provider_home / "sessions").glob("**/*" + sid + ".jsonl"))
        if len(paths) != 1:
            raise ValueError("native Codex session metadata is not unique")
        with paths[0].open() as stream:
            first = json.loads(stream.readline())
        meta = first.get("payload", {})
        if first.get("type") != "session_meta" or meta.get("id") != sid:
            raise ValueError("native Codex session metadata mismatch")
        if meta.get("source") not in ("cli", "vscode"):
            raise ValueError("unowned Codex source")
        cwd = Path(meta["cwd"]).resolve(strict=True)
        shared = "app-server" in runtime["args"].split()
        if shared and worker_hook:
            raise ValueError("shared hook alone cannot establish a new worker's launch ownership")
        if shared and os.environ.get("CODEX_SESSION_ID") != sid:
            raise ValueError("shared Codex runtime lacks matching tool-local session identity")
        transcript = None
    else:
        pid = int(os.environ.get("CLAUDE_PID", "0"))
        runtime = next((r for p, r in chain if p == pid), None)
        if not runtime or "claude" not in Path(runtime["comm"]).parts:
            # Native installer uses a version basename beneath a claude tree.
            if not runtime or "/claude/" not in runtime["args"].split()[0]:
                raise ValueError("no trusted Claude process ancestor")
        path = claude_transcript(sid, payload, worker_hook)
        cwd = Path(claude_cwd(path, sid)).resolve(strict=True)
        shared = False
        transcript = str(path)
    return sid, pid, runtime["lstart"], cwd, shared, transcript


class Bridge:
    def __init__(self, home):
        requested = Path(home)
        if not requested.is_absolute():
            raise ValueError("--home must be absolute")
        self.home = requested.resolve(strict=True)
        self.state = self.home / "state" / "agent-notify"
        self.data = self.home / "data" / "agent-notify"
        self.config_path = self.home / "config" / "agent-notify.json"
        for path in (self.state, self.data, self.config_path.parent):
            if path.resolve() != path:
                raise ValueError("bridge directories must belong to the canonical home")
        self.config = read(self.config_path) if self.config_path.exists() else None
        if self.config and (self.config.get("version") != 1 or
                            not Path(self.config.get("consumer", "")).is_absolute()):
            raise ValueError("invalid bridge configuration")

    @contextlib.contextmanager
    def locked(self):
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state / ".lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def binding_path(self, provider, sid):
        return self.state / (provider + "-" + slug(sid) + ".json")

    def bind(self, provider, payload, worker_hook=False, unless_valid=False):
        if unless_valid:
            existing = self.binding_path(provider, native_sid(provider, payload, worker_hook))
            if existing.exists() and self.valid_binding(read(existing)):
                return existing
        task = os.environ.get("FM_TASK_ID")
        secondmate_hook = worker_hook and not task
        if secondmate_hook:
            inbox = Path(os.environ.get("FM_TASK_INBOX", ""))
            if inbox.parent != self.home / "state" or inbox.suffix != ".inbox":
                raise ValueError("no exact worker launch inbox")
            task = slug(inbox.stem)
        sid, pid, started, cwd, shared, transcript = native(provider, self.home, payload, worker_hook)
        proof = {"pid": pid, "started": started, "shared": shared}
        if provider == "claude":
            proof["transcript_path"] = transcript
        if task:
            slug(task)
            inbox = Path(os.environ.get("FM_TASK_INBOX", ""))
            if inbox != self.home / "state" / (task + ".inbox"):
                raise ValueError("worker inbox does not belong to this home/task")
            meta_path = inbox.with_suffix(".meta")
            if meta_path.is_symlink():
                raise ValueError("symlinked launch record")
            meta = dict(line.split("=", 1) for line in meta_path.read_text().splitlines()
                        if "=" in line)
            role = meta.get("kind")
            generation = os.environ.get("FM_NOTIFY_SPAWN_GEN")
            if (meta.get("endpoint_task_id") != task or meta.get("harness") != provider
                    or role not in ("ship", "scout", "secondmate")
                    or (secondmate_hook and role != "secondmate")
                    or not generation or meta.get("spawn_gen") != generation
                    or cwd != Path(meta["worktree"]).resolve(strict=True)):
                raise ValueError("native session and launch ownership disagree")
            proof.update(meta=str(meta_path), generation=generation)
        else:
            role, task = "firstmate", "supervisor"
            if cwd != self.home or (self.home / ".fm-secondmate-home").exists():
                raise ValueError("not this primary supervisor")
            lock = self.home / "state" / ".lock"
            complete = self.home / "state" / ".session-start-complete"
            if (lock.is_symlink() or complete.is_symlink() or
                    lock.read_text().strip() != str(pid) or
                    complete.read_text().strip() != str(pid)):
                raise ValueError("native process does not own completed supervisor startup")
            if provider == "claude" and (self.home / "state" / ".lock-session").read_text().strip() != sid:
                raise ValueError("Claude supervisor lock session mismatch")
        binding = dict(version=1, home=str(self.home), provider=provider,
                       session_id=sid, role=role, task_id=task, proof=proof)
        path = self.binding_path(provider, sid)
        with self.locked():
            previous = read(path) if path.exists() else binding
            if previous != binding and live(previous):
                raise ValueError("native session already belongs to another owner; revoke first")
            if role == "firstmate":
                root = self.state / "root.json"
                if root.exists():
                    previous = read(root)
                    if previous != {"provider": provider, "session_id": sid}:
                        old = self.binding_path(previous["provider"], previous["session_id"])
                        if old.exists() and self.valid_binding(read(old)):
                            raise ValueError("another verified supervisor session is still bound")
                write(root, {"provider": provider, "session_id": sid})
            write(path, binding)
        return path

    def valid_binding(self, binding):
        try:
            if binding["version"] != 1 or binding["home"] != str(self.home):
                return False
            if not live(binding):
                return False
            proof = binding["proof"]
            if binding["role"] == "firstmate":
                state = self.home / "state"
                owned = ((state / ".lock").read_text().strip() == str(proof["pid"])
                         and (state / ".session-start-complete").read_text().strip() == str(proof["pid"]))
                if binding["provider"] == "claude":
                    owned = owned and (state / ".lock-session").read_text().strip() == binding["session_id"]
                return owned
            meta = dict(line.split("=", 1) for line in Path(proof["meta"]).read_text().splitlines() if "=" in line)
            return (Path(proof["meta"]) == self.home / "state" / (binding["task_id"] + ".meta")
                    and meta.get("spawn_gen") == proof["generation"]
                    and meta.get("endpoint_task_id") == binding["task_id"]
                    and meta.get("kind") == binding["role"]
                    and meta.get("harness") == binding["provider"])
        except (KeyError, OSError, ValueError, subprocess.SubprocessError):
            return False

    def root(self):
        root = read(self.state / "root.json")
        path = self.binding_path(root["provider"], root["session_id"])
        binding = read(path)
        if binding.get("role") != "firstmate" or not self.valid_binding(binding):
            raise ValueError("no verified root supervisor binding")
        return path, binding

    def current_root(self):
        try:
            path, root = self.root()
        except (ValueError, OSError, KeyError, subprocess.SubprocessError):
            if os.environ.get("FM_TASK_ID"):
                raise
            reasons = []
            for provider, key in (("codex", "CODEX_THREAD_ID"), ("claude", "CLAUDE_CODE_SESSION_ID")):
                if not os.environ.get(key):
                    continue
                try:
                    self.bind(provider, {})
                    path, root = self.root()
                    break
                except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
                    reasons.append(f"{provider}: {error}")
            else:
                if reasons:
                    raise ValueError("; ".join(reasons)) from None
                raise
        sid, pid, started, cwd, _, _ = native(root["provider"], self.home, root["proof"])
        if (os.environ.get("FM_TASK_ID") or sid != root["session_id"] or
                pid != root["proof"]["pid"] or started != root["proof"]["started"] or cwd != self.home):
            raise ValueError("operation requires the bound native root session")
        return path, root

    def consume(self, provider, payload, binding_path=None):
        env = dict(os.environ)
        env.pop("AGENT_NOTIFY_FIRSTMATE_BINDING", None)
        if binding_path:
            env["AGENT_NOTIFY_FIRSTMATE_BINDING"] = str(binding_path)
        else:
            # An unproved role must not fall through to the consumer's older,
            # weaker launch-env classifier (for example in a reused pane).
            for key in ("FM_TASK_ID", "FM_TASK_INBOX", "FM_NOTIFY_SPAWN_GEN"):
                env.pop(key, None)
        run([sys.executable, self.config["consumer"], "hook", provider],
            input=json.dumps(payload), env=env)

    def hook(self, provider, payload):
        path = None
        receipt = None
        try:
            sid = slug(payload.get("session_id", ""))
        except ValueError:
            payload.pop("firstmate_input", None)
            payload.pop("firstmate_event", None)
            self.consume(provider, payload)
            return
        candidate = self.binding_path(provider, sid)
        if (not candidate.exists() and os.environ.get("FM_TASK_INBOX")
                and os.environ.get("FM_NOTIFY_SPAWN_GEN")):
            try:
                self.bind(provider, payload, worker_hook=True)
            except (ValueError, OSError, KeyError, subprocess.SubprocessError):
                pass  # Unproved identity retains personal-session behavior.
        if candidate.exists():
            binding = read(candidate)
            # The authorized native hook supplies the session, independently of
            # a shared runtime's inherited tool environment. Bind established
            # ownership; the payload must select that same still-valid owner.
            if (binding.get("provider") == provider and binding.get("session_id") == sid
                    and self.valid_binding(binding)):
                if binding["role"] != "firstmate" or self.config["root_stop_accepted"]:
                    path = candidate
                event = payload.get("hook_event_name")
                if binding["role"] == "firstmate" and event in (
                        "UserPromptSubmit", "Stop", "PermissionRequest", "PostToolUse",
                        "PostToolUseFailure", "PermissionDenied", "Elicitation", "ElicitationResult"):
                    try:
                        selected = read(self.state / "root.json") == {"provider": provider, "session_id": sid}
                    except (OSError, ValueError):
                        selected = False
                    if selected:
                        receipt = {"version": 1, "provider": provider, "session_id": sid,
                                   "home": str(self.home), "role": "firstmate", "task_id": binding["task_id"],
                                   "hook_event_name": event, "binding_fingerprint": digest(binding),
                                   "proof_pid": binding["proof"]["pid"], "proof_started": binding["proof"]["started"],
                                   "root_stop_accepted": self.config["root_stop_accepted"],
                                   "binding_forwarded": path is not None}
        # Hook fields from callers are not producer assertions.
        payload.pop("firstmate_input", None)
        payload.pop("firstmate_event", None)
        if path and payload.get("hook_event_name") == "UserPromptSubmit":
            prompt = payload.get("prompt", "")
            for mode in ("kind", "home-doorbell"):
                try:
                    if mode == "kind":
                        run(["bash", str(CODE / "fm-operational-input.sh"), mode], input=prompt)
                    else:
                        run(["bash", "-c", '. "$1"; p=$(cat); fm_operational_doorbell_kind "$p" "$2" result',
                             "notify", str(CODE / "fm-operational-input.sh"), str(self.home / "state")], input=prompt)
                    payload["firstmate_input"] = "operational"
                    break
                except subprocess.CalledProcessError:
                    pass
        started = time.time()
        returncode = None
        try:
            self.consume(provider, payload, path)
            returncode = 0
        except subprocess.CalledProcessError as exc:
            returncode = exc.returncode
            raise
        finally:
            if receipt is not None:
                receipt.update(started_at=started, finished_at=time.time(), consumer_returncode=returncode)
                try:
                    directory = self.state / "hooks"
                    if directory.resolve() != directory:
                        raise ValueError("symlinked hook receipt directory")
                    write(directory / (provider + "-" + sid + "-" + receipt["hook_event_name"] + ".json"), receipt)
                except (OSError, ValueError):
                    print("warning: Agent Notify root hook receipt could not be written", file=sys.stderr)

    def event(self, event, occurred=None):
        slug(event["task_id"])
        slug(event["event_id"])
        event["version"] = 1
        path = self.state / "events" / (digest([event["kind"], event["task_id"], event["event_id"]]) + ".json")
        try:
            binding_path, root = self.current_root()
        except (ValueError, OSError, KeyError, subprocess.SubprocessError):
            if event["kind"] != "captain_call" or event.get("state") != "resolved":
                raise
            # Deck/services are not native root descendants. They may only
            # cancel a resolution already committed by the hold owner.
            env = {key: value for key, value in os.environ.items()
                   if key not in ("FM_ROOT_OVERRIDE", "FM_STATE_OVERRIDE", "FM_DATA_OVERRIDE")}
            env["FM_HOME"] = str(self.home)
            run(["bash", str(CODE / "fm-captain-hold.sh"), "resolved",
                 event["task_id"], event["event_id"].removeprefix("hold:")], env=env)
            binding_path, root = self.root()
        with self.locked():
            previous = read(path) if path.exists() else None
            resolved = event.get("state") == "resolved"
            if previous:
                if previous["event"].get("artifact_id") != event.get("artifact_id"):
                    raise ValueError("a durable outcome cannot be reassigned to a different artifact")
                if previous["event"].get("state") == "resolved" and not resolved:
                    return
                if previous["accepted"] and (not resolved or previous["event"].get("state") == "resolved"):
                    return
            # Freeze presentation alongside the first event. A later hold on the
            # same task cannot change the question that an older link addresses.
            if previous:
                event.pop("presentation", None)
                for key in ("summary", "context"):
                    if key in previous["event"]:
                        event[key] = previous["event"][key]
            else:
                self.present(event)
            historical = occurred is not None and occurred < self.config["since"]
            record = {"version": 1, "event": event, "accepted": historical}
            write(path, record)
            if historical:
                return
            self.consume(root["provider"], {"hook_event_name": "FirstmateEvent",
                         "session_id": root["session_id"], "firstmate_event": event}, binding_path)
            record["accepted"] = True
            write(path, record)

    def task_fields(self, task):
        try:
            shown = run(["bash", str(CODE / "fm-tasks-axi.sh"), "show", task, "--full"],
                        env={**{k: v for k, v in os.environ.items() if k not in
                               ("FM_ROOT_OVERRIDE", "FM_STATE_OVERRIDE", "FM_DATA_OVERRIDE")},
                             "FM_HOME": str(self.home)})
            fields = {}
            for key in ("title", "hold_reason"):
                match = re.search(r"^  " + key + r": (.*)$", shown, re.M)
                if match:
                    value = match[1]
                    fields[key] = json.loads(value) if value.startswith('"') else value
            return fields
        except (ValueError, OSError, subprocess.SubprocessError):
            return {}

    def present(self, event):
        presentation = event.pop("presentation", {})
        fields = self.task_fields(event["task_id"])
        title = display(fields.get("title"), PRESENTATION["task_label"])
        call = event["kind"] in ("captain_call", "response_required")
        if call:
            detail = display(fields.get("hold_reason"), PRESENTATION["detail"])
            if not detail or detail == "-":
                detail = "Revisa la pregunta y responde para continuar."
        else:
            detail = event.get("summary", "El encargo y sus entregas requeridas terminaron.")
        context = {"version": 1, "task_label": title or "Encargo de Firstmate",
                   "home_label": "Firstmate", "detail": detail, **presentation,
                   "target": {"view": "question" if call else "delivery",
                              "id": event["event_id"] if call else event["artifact_id"]}}
        event["context"] = context
        event["summary"] = display(context["detail"], 240)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("initialize")
    init.add_argument("--consumer", required=True)
    for name in ("bind", "hook", "revoke"):
        commands.add_parser(name).add_argument("provider", choices=("codex", "claude"))
    commands.choices["bind"].add_argument("--unless-valid", action="store_true",
        help="succeed unchanged while this session's recorded binding is still valid")
    commands.choices["hook"].add_argument("--consumer", required=True,
        help="absolute installed consumer path; also forwards unknown/unconfigured sessions")
    commands.add_parser("accept-root")
    call = commands.add_parser("call")
    call.add_argument("task")
    call.add_argument("occurrence", type=int)
    call.add_argument("state", choices=("open", "resolved"))
    call.add_argument("--at", required=True)
    response = commands.add_parser("response")
    response.add_argument("task")
    response.add_argument("request")
    response.add_argument("state", choices=("open", "resolved"))
    response.add_argument("--at", required=True)
    designation = commands.add_parser("designate")
    designation.add_argument("task")
    designation.add_argument("outcome")
    commands.add_parser("landed").add_argument("task")
    initiative = commands.add_parser("initiative")
    initiative.add_argument("task")
    initiative.add_argument("--requires", nargs="+", required=True)
    commands.add_parser("complete").add_argument("task")
    for command in (call, response, designation, initiative):
        for key in PRESENTATION:
            command.add_argument("--" + key.replace("_", "-"))
    args = parser.parse_args()
    bridge = Bridge(args.home)
    presentation = {key: plain(getattr(args, key), limit) for key, limit in PRESENTATION.items()
                    if getattr(args, key, None) is not None}
    if args.command == "initialize":
        consumer = Path(args.consumer)
        if not consumer.is_absolute() or not consumer.is_file():
            raise ValueError("consumer must be an existing absolute script path")
        if bridge.config:
            if bridge.config["consumer"] != str(consumer):
                raise ValueError("bridge is already initialized with a different consumer")
            return
        write(bridge.config_path, {"version": 1, "consumer": str(consumer),
                                  "since": time.time(), "root_stop_accepted": False})
        return
    if args.command == "hook":
        if not Path(args.consumer).is_absolute() or not Path(args.consumer).is_file():
            raise ValueError("hook consumer must be an existing absolute script path")
        if bridge.config and bridge.config["consumer"] != args.consumer:
            raise ValueError("hook consumer differs from the configured bridge")
        if not bridge.config:
            bridge.config = {"consumer": args.consumer}
            payload = json.load(sys.stdin)
            payload.pop("firstmate_input", None)
            payload.pop("firstmate_event", None)
            bridge.consume(args.provider, payload)
            return
    if not bridge.config:
        return
    if args.command == "bind":
        print(bridge.bind(args.provider, stdin_payload(), unless_valid=args.unless_valid))
    elif args.command == "hook":
        bridge.hook(args.provider, json.load(sys.stdin))
    elif args.command == "revoke":
        sid, _, _, _, _, _ = native(args.provider, bridge.home, stdin_payload())
        bridge.binding_path(args.provider, sid).unlink(missing_ok=True)
    elif args.command == "accept-root":
        bridge.current_root()
        bridge.config["root_stop_accepted"] = True
        write(bridge.config_path, bridge.config)
    elif args.command in ("call", "response"):
        if args.command == "call" and args.occurrence < 1:
            raise ValueError("captain hold occurrence must be positive")
        if args.command == "response":
            bridge.current_root()
        occurred = datetime.datetime.strptime(args.at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
        bridge.event({"kind": "captain_call" if args.command == "call" else "response_required", "task_id": args.task,
                      "event_id": "hold:" + str(args.occurrence) if args.command == "call" else slug(args.request), "state": args.state,
                      "action_required": args.state == "open", "presentation": presentation}, occurred)
    elif args.command in ("designate", "initiative"):
        # The root explicitly owns user-outcome semantics; workers cannot declare them.
        bridge.current_root()
        slug(args.task)
        value = {"version": 1, "task_id": args.task, **presentation}
        if args.command == "designate":
            value["outcome"] = slug(args.outcome)
        else:
            value["requires"] = sorted(set(slug(v) for v in args.requires))
        path = bridge.data / args.command / (args.task + ".json")
        with bridge.locked():
            if path.exists() and read(path) != value:
                raise ValueError("requested outcome declaration is immutable")
            if not path.exists() and args.command == "designate":
                shown = run(["bash", str(CODE / "fm-tasks-axi.sh"), "show", args.task, "--full"],
                            env={**os.environ, "FM_HOME": str(bridge.home)})
                if not re.search(r"^\s*state: (queued|in_flight)$", shown, re.M):
                    raise ValueError("only existing unlanded work can receive a requested-outcome designation")
                for existing in (bridge.data / "designate").glob("*.json"):
                    if read(existing).get("outcome") == args.outcome:
                        raise ValueError("outcome identity already belongs to another task")
            write(path, value)
    elif args.command == "landed":
        declaration = bridge.data / "designate" / (slug(args.task) + ".json")
        if not declaration.exists():
            return
        declaration = read(declaration)
        outcome = declaration["outcome"]
        row = json.load(sys.stdin)
        artifact = row["artifact"]
        if not isinstance(artifact, str) or not artifact.strip():
            raise ValueError("material landing requires an artifact")
        artifact_id = digest([args.task, artifact])
        presentation = {key: plain(declaration[key], limit) for key, limit in PRESENTATION.items() if key in declaration}
        presentation.setdefault("detail", {"reported": "Informe listo para consultar.",
            "merged": "Cambios integrados; entrega lista para consultar.",
            "done": "Cambios integrados en la copia local."}.get(row.get("verb"), "Entrega lista para consultar."))
        bridge.event({"kind": "deliverable_landed", "task_id": args.task,
                      "event_id": outcome, "artifact_id": artifact_id, "user_facing": True, "presentation": presentation})
        write(bridge.data / "landed" / (slug(outcome) + ".json"),
              {"version": 1, "task_id": args.task, "outcome": outcome, "artifact_id": artifact_id})
    elif args.command == "complete":
        declaration = read(bridge.data / "initiative" / (slug(args.task) + ".json"))
        outcomes = [read(bridge.data / "landed" / (v + ".json")) for v in declaration["requires"]]
        bridge.event({"kind": "initiative_completed", "task_id": args.task,
                      "initiative_id": args.task, "scope": "main", "user_facing": True,
                      "event_id": "complete", "artifact_id": digest(outcomes),
                      "presentation": {key: plain(declaration[key], limit) for key, limit in PRESENTATION.items() if key in declaration}})


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print("fm-agent-notify: " + str(exc), file=sys.stderr)
        sys.exit(1)
