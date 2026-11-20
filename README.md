# hmecli

Generate iCloud Hide My Email aliases from the command line. Python stdlib plus
`browser-cookie3` (only used by `login`). Needs iCloud+. Uses unofficial Apple
endpoints, so it may break without notice.

## Install

Nix:

    nix run github:nuclearcanopy/hmecli -- --help

As a flake input, use `inputs.hmecli.overlays.default` (gives `pkgs.hmecli`) or
`inputs.hmecli.packages.${system}.hmecli`.

pipx (from a clone; not on PyPI yet):

    pipx install .

Arch: `cd packaging/arch && makepkg -si` (builds from a local checkout).

## Usage

    hmecli login [--browser firefox] [--region global|china]
    hmecli generate -n 5 [--label shopping] [--json] [--delay 2]
    hmecli list [--all] [--json]
    hmecli deactivate alias@icloud.com
    hmecli delete alias@icloud.com [--yes]
    hmecli status
    hmecli logout

`generate` asks once per run on a terminal:

    Label (Enter for none): shopping

Press Enter to skip it and the aliases get no label. `--label TEXT` skips the
prompt (`--label ""` means no label), and nothing is asked with `--json` or when
stdin is not a terminal; those runs use no label unless `--label` is given.
With no label, the reserve request omits the label field.

`login` opens icloud.com; sign in (2FA, "Trust this browser"), press Enter, and
the session is read from your browser's cookie store. Your Apple ID password is
never entered into the CLI.

`deactivate` stops an alias forwarding; it can be reactivated in iCloud. `delete`
is **permanent and cannot be undone**: it asks for confirmation (a still-active
alias is deactivated first), refuses to run non-interactively unless you pass
`--yes`. Both take the alias address, which is looked up in `hmecli list --all`.

Exit codes: 0 ok, 1 error, 2 not logged in / session expired.

## Session

Stored at `$XDG_CONFIG_HOME/hmecli/session.json` (mode 600; override with
`HMECLI_SESSION`). It holds your iCloud cookies: treat it like a password.
Apple rate-limits generation (~5/hour is common); `--delay` spaces requests.

## Development

    nix develop
    python -m unittest
    nix flake check

Research on similar projects: `hme-research.md`.

Licensed under AGPL-3.0-or-later; see `LICENSE`.
