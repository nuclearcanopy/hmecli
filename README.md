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
    hmecli generate -n 5 --label shopping [--json] [--delay 2]
    hmecli list [--all] [--json]
    hmecli status
    hmecli logout

`login` opens icloud.com; sign in (2FA, "Trust this browser"), press Enter, and
the session is read from your browser's cookie store. Your Apple ID password is
never entered into the CLI.

Exit codes: 0 ok, 1 error, 2 not logged in / session expired.

## Session

Stored at `$XDG_CONFIG_HOME/hmecli/session.json` (mode 600; override with
`HMECLI_SESSION`). It holds your iCloud cookies: treat it like a password.
Apple rate-limits generation (~5/hour is common); `--delay` spaces requests.

## Development

    nix develop
    python -m unittest
    nix flake check

Research on similar projects: `hme-research.md`. License: MIT.
