#!/usr/bin/env python3
"""hmecli: generate iCloud Hide My Email aliases from the command line.

login   reads your icloud.com session from your browser's cookie store
        (you sign in, including 2FA, in the browser; no password is ever typed here)
generate / list / status / logout
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import webbrowser

APP = "hmecli"
BROWSERS = ["firefox", "chrome", "chromium", "brave", "edge", "vivaldi", "opera"]
REGIONS = {
    "global": {
        "origin": "https://www.icloud.com",
        "domain": "icloud.com",
        "host": "p68-maildomainws.icloud.com",
        "setup": "https://setup.icloud.com/setup/ws/1",
        "lang": "en-us",
    },
    "china": {
        "origin": "https://www.icloud.com.cn",
        "domain": "icloud.com.cn",
        "host": "p217-maildomainws.icloud.com.cn",
        "setup": "https://setup.icloud.com.cn/setup/ws/1",
        "lang": "zh-cn",
    },
}
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0.0.0 Safari/537.36")
AUTH_COOKIES = ("X-APPLE-WEBAUTH-USER", "X-APPLE-WEBAUTH-TOKEN")

EXIT_OK, EXIT_ERROR, EXIT_AUTH = 0, 1, 2


class HmeError(Exception):
    code = EXIT_ERROR


class SessionError(HmeError):
    code = EXIT_AUTH


# ---------------------------------------------------------------- session store

def session_path(env=None):
    env = os.environ if env is None else env
    if env.get("HMECLI_SESSION"):
        return env["HMECLI_SESSION"]
    base = env.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP, "session.json")


def save_session(data, path):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def load_session(path):
    try:
        with open(path) as f:
            data = json.load(f)
        if not (data["cookies"] and data["host"]):
            raise KeyError("empty")
    except (OSError, ValueError, KeyError, TypeError):
        raise SessionError(f"not logged in. Run: {APP} login")
    if os.stat(path).st_mode & 0o077:
        print(f"warning: {path} is readable by others; run chmod 600", file=sys.stderr)
    return data


# ---------------------------------------------------------------- API client

class Client:
    def __init__(self, cookies, region="global", host=None, dsid="", opener=None):
        self.r = REGIONS[region]
        self.cookies, self.dsid = cookies, dsid
        self.host = host or self.r["host"]
        self.opener = opener or urllib.request.urlopen

    def headers(self):
        return {
            "User-Agent": UA,
            "Content-Type": "text/plain",
            "Accept": "*/*",
            "Origin": self.r["origin"],
            "Referer": self.r["origin"] + "/",
            "Cookie": self.cookies,
        }

    def url(self, version, path):
        q = ("clientBuildNumber=2626Build17&clientMasteringNumber=2626Build17"
             f"&clientId=&dsid={self.dsid}")
        return f"https://{self.host}/{version}/hme/{path}?{q}"

    def call(self, method, url, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.headers())
        try:
            with self.opener(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 421):
                raise SessionError(f"session expired or rejected (HTTP {e.code}). "
                                   f"Run: {APP} login")
            raise HmeError(f"HTTP {e.code} from {method} {url.split('?')[0]}")
        except urllib.error.URLError as e:
            raise HmeError(f"network error: {e.reason}")
        except ValueError:
            raise HmeError("unexpected non-JSON response from iCloud")

    @staticmethod
    def check(resp, what):
        if not resp.get("success"):
            msg = (resp.get("error") or {}).get("errorMessage") or "unknown error"
            raise HmeError(f"{what} failed: {msg}")
        return resp["result"]

    def validate(self):
        """Returns (host, dsid, name). Raises SessionError if not signed in."""
        resp = self.call("POST", self.r["setup"] + "/validate")
        try:
            url = resp["webservices"]["premiummailsettings"]["url"]
        except (KeyError, TypeError):
            raise SessionError(f"not signed in to iCloud (or no iCloud+). Run: {APP} login")
        host = url.split("//", 1)[-1].split("/")[0].split(":")[0]
        info = resp.get("dsInfo") or {}
        name = info.get("fullName") or info.get("appleId") or ""
        return host, str(info.get("dsid", "")), name

    def generate(self):
        res = self.check(self.call("POST", self.url("v1", "generate"),
                                   {"langCode": self.r["lang"]}), "generate")
        return res["hme"]

    def reserve(self, hme, label, note):
        res = self.check(self.call("POST", self.url("v1", "reserve"),
                                   {"hme": hme, "label": label, "note": note}), "reserve")
        return res["hme"]["hme"]

    def list(self):
        return self.check(self.call("GET", self.url("v2", "list")), "list")


# ---------------------------------------------------------------- browser cookies

def read_browser_cookies(browser, domain):
    """Cookie header string for `domain` from a browser store, or '' if none."""
    import browser_cookie3  # imported lazily; only needed for login
    jar = getattr(browser_cookie3, browser)(domain_name=domain)
    pairs = {c.name: c.value for c in jar
             if c.domain.lstrip(".").endswith(domain)}
    if not any(n in pairs for n in AUTH_COOKIES):
        return ""
    return "; ".join(f"{k}={v}" for k, v in pairs.items())


def capture_session(region, browsers, reader=read_browser_cookies, client_factory=Client,
                    log=lambda m: None):
    r = REGIONS[region]
    failures = []
    for b in browsers:
        try:
            cookies = reader(b, r["domain"])
        except ImportError:
            raise HmeError("browser_cookie3 is missing (use the nix package)")
        except Exception as e:  # missing browser, locked DB, keyring problems...
            failures.append(f"{b}: {type(e).__name__}")
            continue
        if not cookies:
            failures.append(f"{b}: no iCloud sign-in found")
            continue
        client = client_factory(cookies, region)
        try:
            host, dsid, name = client.validate()
        except SessionError:
            failures.append(f"{b}: session not valid")
            continue
        log(f"using {b} session")
        return {"cookies": cookies, "region": region, "host": host, "dsid": dsid,
                "name": name, "browser": b, "saved_at": int(time.time())}
    raise HmeError("no valid iCloud session found in browser(s) ["
                   + "; ".join(failures) + "]. Sign in at icloud.com first, "
                   "or pick one with --browser")


# ---------------------------------------------------------------- commands

def client_from_session(s, opener=None):
    return Client(s["cookies"], s.get("region", "global"), s["host"], s.get("dsid", ""),
                  opener=opener)


def cmd_login(a, env=None, reader=read_browser_cookies, client_factory=Client, wait=input):
    r = REGIONS[a.region]
    if not a.no_open:
        print(f"Opening {r['origin']} - sign in (including 2FA) and choose "
              "'Trust this browser'.", file=sys.stderr)
        webbrowser.open(r["origin"])
    if not a.no_wait and sys.stdin.isatty():
        wait("Press Enter once you see your iCloud home page... ")
    browsers = [a.browser] if a.browser else BROWSERS
    s = capture_session(a.region, browsers, reader, client_factory,
                        log=lambda m: print(m, file=sys.stderr))
    path = session_path(env)
    save_session(s, path)
    print(f"Logged in{' as ' + s['name'] if s['name'] else ''}. Session saved to {path}",
          file=sys.stderr)
    return EXIT_OK


def cmd_status(a, env=None, opener=None):
    s = load_session(session_path(env))
    name = client_from_session(s, opener).validate()[2]
    print(f"logged in{' as ' + name if name else ''} (browser: {s.get('browser', '?')})")
    return EXIT_OK


def cmd_generate(a, env=None, opener=None, sleep=time.sleep):
    if a.count < 1:
        raise HmeError("--count must be >= 1")
    c = client_from_session(load_session(session_path(env)), opener)
    out, err = [], None
    show = sys.stderr.isatty() and not a.json
    for i in range(a.count):
        if i:
            sleep(a.delay)
        try:
            if show:
                print(f"\r[{i + 1}/{a.count}]", end="", file=sys.stderr, flush=True)
            addr = c.reserve(c.generate(), a.label, a.note)
        except HmeError as e:
            err = e
            break
        out.append(addr)
        if not a.json:
            if show:
                print("\r\033[K", end="", file=sys.stderr)
            print(addr, flush=True)
    if show:
        print("\r\033[K", end="", file=sys.stderr)
    if a.json:
        print(json.dumps(out))
    if err:
        print(f"error: {err} ({len(out)}/{a.count} generated)", file=sys.stderr)
        return err.code
    return EXIT_OK


def cmd_list(a, env=None, opener=None):
    c = client_from_session(load_session(session_path(env)), opener)
    emails = c.list().get("hmeEmails", [])
    if not a.all:
        emails = [e for e in emails if e.get("isActive")]
    if a.json:
        print(json.dumps(emails, indent=2))
    else:
        for e in emails:
            print(f"{e['hme']}\t{'active' if e.get('isActive') else 'inactive'}"
                  f"\t{e.get('label', '')}")
    return EXIT_OK


def cmd_logout(a, env=None):
    path = session_path(env)
    try:
        os.remove(path)
        print(f"removed {path}", file=sys.stderr)
    except FileNotFoundError:
        print("no session stored", file=sys.stderr)
    return EXIT_OK


def build_parser():
    p = argparse.ArgumentParser(
        prog=APP, description="Generate iCloud Hide My Email aliases.",
        epilog="exit codes: 0 ok, 1 error, 2 not logged in / session expired")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("login", help="capture your iCloud session from your browser")
    s.add_argument("--browser", choices=BROWSERS, help="default: try all")
    s.add_argument("--region", choices=REGIONS, default="global")
    s.add_argument("--no-open", action="store_true", help="don't launch the browser")
    s.add_argument("--no-wait", action="store_true", help="don't wait for Enter")
    s.set_defaults(fn=cmd_login)

    s = sub.add_parser("generate", help="generate and reserve aliases")
    s.add_argument("-n", "--count", type=int, default=1)
    s.add_argument("-l", "--label", default="hmecli")
    s.add_argument("--note", default="Generated with hmecli")
    s.add_argument("--json", action="store_true", help="print a JSON array")
    s.add_argument("--delay", type=float, default=2.0, help="seconds between aliases")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("list", help="list aliases (active by default)")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("status", help="check that the stored session still works")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("logout", help="delete the stored session")
    s.set_defaults(fn=cmd_logout)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except HmeError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
