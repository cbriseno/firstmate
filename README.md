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
- [Platform setup and prerequisite checks](docs/platforms.md), plus a [reviewed public-export workflow](docs/public-export.md) for sharing generic changes without importing private operator history.

Documentation: [configuration](docs/configuration.md), [platforms](docs/platforms.md), [wedge alarms](docs/wedge-alarm.md), [remote secondmates](docs/remote-secondmates.md), [public export](docs/public-export.md), and backend guides for [tmux](docs/tmux-backend.md), [Herdr](docs/herdr-backend.md), [Zellij](docs/zellij-backend.md), [Orca](docs/orca-backend.md), [cmux](docs/cmux-backend.md), [Paseo](docs/paseo-backend.md), and [Rex](docs/rex-backend.md). The [documentation guide](docs/documentation-audiences.md) explains how the docs are organized.

The original [MIT license and copyright notice](LICENSE) and inherited commit history are preserved.
