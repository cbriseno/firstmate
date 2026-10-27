# Firstmate - personal experimental fork

**Unofficial fork of [Firstmate](https://github.com/kunchenguid/firstmate), originally created by Kun Chen and upstream contributors.**
This repository is an experiment for personal use and evaluation of these tools.
It is not an official upstream release or an endorsed project.

## Changes in this experiment

- Richer task snapshots for a web kanban: current state, historical declarations, waiting reasons, next actions, and dependencies.
- Durable decision answers that can be recorded and reconciled through the existing inbox and hold mechanisms.
- Retained delivery history and follow-up questions about completed work, with guarded request handling.
- Task and delivery timestamps that preserve known precision and leave unknown times unknown.
- Optional notification event routing through an Agent Notify bridge, configured separately for each private operational home.
- [Platform setup](docs/platforms.md) for Linux, macOS and the Windows WSL2 route, including the read-only prerequisite doctor and how to launch the primary with Claude Code or Codex, and a [reviewed public-export workflow](docs/public-export.md) that shares generic changes without importing private operator history.

The original [MIT license and copyright notice](LICENSE) and inherited commit history are preserved.
