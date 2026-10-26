#!/usr/bin/env python3
"""Private transport for fm-codex-stop-autoarm.sh, pinned to Codex 0.164.

Uses the attested executable's ephemeral `app-server proxy --sock` client;
never starts a server. That command is a byte relay; the existing control
socket requires RFC6455 upgrade and masked JSON text frames, not JSON lines.
Only initialize, our queue/add, and bounded turns/list
are allowed. stdout is a metadata projection, stderr never contains vendor
responses. Summary is used only to join our clientId to its turn ID; item
content is discarded in memory. Outcomes use notLoaded. No notification or
arbitrary error text is retained. Requires Python 3's standard library.
"""

import argparse
import base64
import hashlib
import json
import os
import selectors
import subprocess
import struct
import time


CAPACITY = "Selected model is at capacity. Please try a different model."
MAX_LINE = 1024 * 1024
PAGES = 4
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def identifier(value):
    if not isinstance(value, str) or not 0 < len(value) < 200:
        raise ValueError()
    if any(ord(c) < 32 for c in value):
        raise ValueError()
    return value


class Client:
    def __init__(self, args, diagnostic):
        self.diagnostic = diagnostic
        if args.remote != "unix://" and not args.remote.startswith("unix:///"):
            raise ValueError()
        self.deadline = time.monotonic() + 4
        self.pending = b""
        self.sequence = 0
        command = [args.executable, "app-server", "proxy"]
        if args.remote != "unix://":
            command += ["--sock", args.remote[7:]]
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)

    def close(self):
        self.selector.close()
        self.proc.stdin.close()
        if self.proc.poll() is None:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc.stdout.close()

    def send(self, obj):
        self.diagnostic["phase"] = "write"
        self.send_frame(1, json.dumps(obj, separators=(",", ":")).encode())

    def send_frame(self, opcode, data):
        # The public control socket is WebSocket over Unix, even when reached
        # through the official byte-relay proxy. RFC6455 requires client masks.
        if len(data) > MAX_LINE:
            raise ValueError()
        mask = os.urandom(4)
        size = len(data)
        header = bytes([0x80 | opcode])
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += b"\xfe" + struct.pack("!H", size)
        else:
            header += b"\xff" + struct.pack("!Q", size)
        self.proc.stdin.write(header + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))
        self.proc.stdin.flush()

    def receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or not self.selector.select(remaining):
            raise TimeoutError()
        block = os.read(self.proc.stdout.fileno(), 65536)
        if not block:
            raise EOFError()
        self.pending += block
        if len(self.pending) > MAX_LINE + 16384:
            raise ValueError()

    def take(self, size):
        while len(self.pending) < size:
            self.receive()
        data, self.pending = self.pending[:size], self.pending[size:]
        return data

    def upgrade(self):
        self.diagnostic["phase"] = "upgrade"
        key = base64.b64encode(os.urandom(16)).decode()
        request = ("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                   "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                   "Sec-WebSocket-Key: " + key + "\r\n\r\n")
        self.proc.stdin.write(request.encode())
        self.proc.stdin.flush()
        while b"\r\n\r\n" not in self.pending:
            if len(self.pending) >= 16384:
                raise ValueError()
            self.receive()
        raw, self.pending = self.pending.split(b"\r\n\r\n", 1)
        if len(raw) > 16384:
            raise ValueError()
        lines = raw.decode("ascii").split("\r\n")
        status = lines[0].split(" ", 2)
        code = int(status[1])
        self.diagnostic["httpCode"] = code
        if status[0] != "HTTP/1.1" or code != 101:
            raise ValueError()
        headers = {}
        for line in lines[1:]:
            name, value = line.split(":", 1)
            name = name.strip().lower()
            if name in headers:
                raise ValueError()
            headers[name] = value.strip()
        expected = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()).decode()
        if (headers.get("sec-websocket-accept") != expected
                or headers.get("upgrade", "").lower() != "websocket"
                or "upgrade" not in {v.strip() for v in headers.get("connection", "").lower().split(",")}
                or "sec-websocket-extensions" in headers
                or "sec-websocket-protocol" in headers):
            raise ValueError()

    def line(self):
        # Only the pinned uncompressed JSON text profile, not a general
        # WebSocket stack. Control/continuation frames remain bounded too.
        self.diagnostic["phase"] = "frame"
        parts = bytearray()
        started = False
        for _ in range(128):
            first, second = self.take(2)
            final, opcode = bool(first & 0x80), first & 15
            if first & 0x70 or second & 0x80:
                raise ValueError()
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self.take(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.take(8))[0]
            if size > MAX_LINE or (opcode >= 8 and (not final or size > 125)):
                raise ValueError()
            data = self.take(size)
            if opcode == 8:
                raise EOFError()
            if opcode == 9:
                self.send_frame(10, data)
                continue
            if opcode == 10:
                continue
            if (opcode == 1 and started) or (opcode == 0 and not started) or opcode not in (0, 1):
                raise ValueError()
            started = True
            parts.extend(data)
            if len(parts) > MAX_LINE:
                raise ValueError()
            if final:
                break
        else:
            raise ValueError()
        self.diagnostic["phase"] = "decode"
        return json.loads(parts)

    def request(self, method, params):
        self.diagnostic["operation"] = method
        self.sequence += 1
        self.send({"id": self.sequence, "method": method, "params": params})
        for _ in range(64):
            obj = self.line()
            if obj.get("id") == self.sequence and "method" not in obj:
                if "error" in obj:
                    self.diagnostic["phase"] = "rpc"
                    code = obj["error"].get("code")
                    if type(code) is int:
                        self.diagnostic["rpcCode"] = code
                    raise ValueError()
                self.diagnostic["phase"] = "project"
                result = obj["result"]
                if method == "thread/turns/list":
                    # Drop inseparable content at the decoding boundary,
                    # before returning anything to correlation/outcome logic.
                    data = result["data"]
                    if not isinstance(data, list) or len(data) > 1:
                        raise ValueError()
                    projected = []
                    for turn in data:
                        row = {"id": identifier(turn["id"])}
                        if params["itemsView"] == "summary":
                            row["clients"] = [item.get("clientId") for item in turn.get("items", [])
                                              if item.get("type") == "userMessage"]
                        else:
                            row["status"] = turn.get("status")
                            error = turn.get("error") or {}
                            row["error_class"] = "capacity" if row["status"] == "failed" and error.get("message") == CAPACITY else "other"
                        projected.append(row)
                    return {"data": projected, "nextCursor": result.get("nextCursor")}
                return result
            # Ignore unsolicited traffic, including other threads, without
            # inspecting, projecting, logging or responding to its payload.
        raise ValueError()

    def turns(self, thread, view):
        cursor = None
        for _ in range(PAGES):
            params = {"threadId": thread, "limit": 1,
                      "sortDirection": "desc", "itemsView": view}
            if cursor is not None:
                params["cursor"] = cursor
            result = self.request("thread/turns/list", params)
            data = result["data"]
            if not isinstance(data, list) or len(data) > 1:
                raise ValueError()
            yield from data
            cursor = result.get("nextCursor")
            if cursor is None:
                return
            identifier(cursor)


def project(args, client):
    thread = identifier(args.thread)
    client.upgrade()
    client.request("initialize", {
        "clientInfo": {"name": "firstmate_native_owner", "version": "1"},
        "capabilities": {"experimentalApi": True, "requestAttestation": False},
    })
    client.send({"method": "initialized"})
    if args.mode == "queue":
        client_id = identifier(args.client_id)
        # Only the owner's freshly generated operational instruction arrives
        # here. Never read a transcript, old queue input or response input.
        message = os.read(0, 16385).decode()
        if not message or len(message.encode()) > 16384:
            raise ValueError()
        result = client.request("thread/queue/add", {
            "threadId": thread, "clientUserMessageId": client_id,
            "input": [{"type": "text", "text": message, "textElements": []}],
        })
        submission = result["queuedSubmission"]
        if submission["clientUserMessageId"] != client_id:
            raise ValueError()
        return {"client_id": client_id, "submission": identifier(submission["id"])}
    turn_id = args.turn_id
    if not turn_id:
        client_id = identifier(args.client_id)
        matches = set()
        for turn in client.turns(thread, "summary"):
            if client_id in turn["clients"]:
                matches.add(identifier(turn["id"]))
            # No item is returned or retained. Content/text/preview is never
            # accessed, compared, formatted, reconstructed or retransmitted.
        if len(matches) != 1:
            return {"status": "unknown", "error_class": "correlation-missing"}
        turn_id = matches.pop()
    identifier(turn_id)
    for turn in client.turns(thread, "notLoaded"):
        if turn.get("id") != turn_id:
            continue
        status = turn.get("status")
        if status not in ("inProgress", "completed", "interrupted", "failed"):
            raise ValueError()
        return {"turn_id": turn_id, "status": status, "error_class": turn["error_class"]}
    return {"turn_id": turn_id, "status": "unknown", "error_class": "outcome-missing"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("queue", "outcome"))
    parser.add_argument("--executable", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--thread", required=True)
    parser.add_argument("--client-id", default="")
    parser.add_argument("--turn-id", default="")
    args = parser.parse_args()
    client = None
    diagnostic = {"phase": "spawn", "operation": "initialize", "rpcCode": None,
                  "exitCode": None, "deadline": False}
    try:
        client = Client(args, diagnostic)
        result = project(args, client)
        print(json.dumps(result, separators=(",", ":")))
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError, EOFError, TimeoutError) as error:
        # Includes rejected, interrupted and ambiguous dispatch. Never echo a
        # raw exception, vendor error or partially decoded private response.
        diagnostic["deadline"] = isinstance(error, TimeoutError)
        if client is not None:
            diagnostic["exitCode"] = client.proc.poll()
        print(json.dumps({"status": "unknown", "error_class": "protocol-unproved",
                          "diagnostic": diagnostic}, separators=(",", ":")))
        return 1
    finally:
        if client is not None:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
