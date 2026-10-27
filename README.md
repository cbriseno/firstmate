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
- [Platform setup](docs/platforms.md), [configuration](docs/configuration.md), and the backend guides for [tmux](docs/tmux-backend.md), [Herdr](docs/herdr-backend.md), [Zellij](docs/zellij-backend.md), [Orca](docs/orca-backend.md), [cmux](docs/cmux-backend.md), [Paseo](docs/paseo-backend.md), and [Rex](docs/rex-backend.md) cover prerequisites and differences per platform, and a [reviewed public-export workflow](docs/public-export.md) shares generic changes without importing private operator history; [wedge alarms](docs/wedge-alarm.md), [remote secondmates](docs/remote-secondmates.md), and the [documentation guide](docs/documentation-audiences.md) cover the remaining areas.

The original [MIT license and copyright notice](LICENSE) and inherited commit history are preserved.
