# Platform setup

Firstmate uses Bash, Unix process groups, filesystem permissions and a terminal runtime.
Use Linux or macOS directly, or a Linux distribution inside WSL2 on Windows.
Native PowerShell, Git Bash/MSYS, Cygwin and WSL1 are not validated Firstmate runtimes; startup, bootstrap and dispatch refuse them before changing operational state.
A native Windows harness or a tmux-compatible executable does not establish compatible Firstmate process ownership, locking or supervision.
Other Unix kernels are not currently accepted.

## Prepare the runtime

Install Git, Bash, Python 3.9 or newer, Perl and jq with your platform's package manager.
The [toolchain configuration](configuration.md#toolchain) owns the additional agent, Node, forge and fleet tools and their version requirements.
Choose a supported primary harness and runtime; [tmux](tmux-backend.md) is the reference route.
The [upstream tmux installation guide](https://github.com/tmux/tmux/wiki/Installing) covers Linux distributions and macOS package managers.
On macOS, stock Bash 3.2 is supported by the existing compatibility lane; install Python and the selected backend separately.
Use the backend's own guide for platform constraints, especially macOS-only cmux.

On Windows, install WSL2 and a Linux distribution using [Microsoft's WSL installation instructions](https://learn.microsoft.com/en-us/windows/wsl/install).
Confirm the distribution uses version 2 with `wsl --list --verbose` in PowerShell, then run setup, Git, the primary harness, tools and backend inside that distribution.
Keep the checkout and operational home in the Linux filesystem, following [Microsoft's filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems).
Do not mix Windows `.exe` tools, Windows credential paths or drive-mounted operational state into the Linux runtime.
The WSL2 route is based on its Linux environment; it is not a claim of a completed Firstmate Windows acceptance run.

Clone the intended public repository, then run this from its root:

```sh
bash bin/fm-doctor.sh --backend tmux
```

The doctor is read-only and performs no network, installs, logins, service lifecycle actions or agent prompts.
It reports prerequisites, not a successful live dispatch or authentication result.
Startup's existing bootstrap remains responsible for installed tool versions and authentication checks.
Resolve reported missing dependencies before launching a primary harness using the [README setup](../README.md#install-and-launch).

## Private operational home and integrations

The existing [operational-home layout](configuration.md#operational-home-layout-and-state) keeps machine choices in `FM_HOME`, separate from tracked code.
When a caller invokes helpers from a separate code tree, pass that tree using the existing `FM_ROOT_OVERRIDE` and the private home explicitly using `FM_HOME`.
Select the helper executable from the code tree itself; an environment variable cannot relocate the executable already invoked.
Retain legacy home-local `bin/` discovery for integrations that previously used colocated code and state.
Do not put absolute machine paths, login material, project inventories, notification destinations or service addresses in tracked files.

The Deck web kanban can consume the existing snapshot and guarded action interfaces without changing their schemas.
Localhost is sufficient for public web operation; private remote access and network exposure belong to the operator's separate configuration.
Firstmate does not provision a web server or network exposure through the doctor or exporter.

Native Codex supervision is an optional Linux-only capability with exact process and executable identity checks.
The doctor does not enable it, attest a binding, install hooks or relax those checks on another platform.
Follow the [native Codex configuration contract](configuration.md#codex-native-supervision) and its current verification evidence before opting in.

## Verification limits

A successful Linux test is not macOS or Windows evidence.
The platform regressions simulate kernel classification and early refusal only; they do not certify a host or a backend.
Use the existing [runtime verification entry points](verification/runtime-backends.md) and an isolated dispatch on each actual target machine before relying on its supervision.
Exporting a public copy and carrying later improvements across the private/public boundary are covered by [public export](public-export.md).
