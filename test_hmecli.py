import argparse, contextlib, io, json, os, stat, tempfile, unittest
import hmecli as h


class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


class Fake:
    def __init__(self, responses):
        self.responses, self.reqs = list(responses), []
    def __call__(self, req, timeout=0):
        self.reqs.append(req)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return FakeResp(json.dumps(r).encode())


def ok(result): return {"success": True, "result": result}
VALID = {"webservices": {"premiummailsettings": {"url": "https://p99-maildomainws.icloud.com:443"}},
         "dsInfo": {"dsid": 123, "fullName": "Test"}}


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = {"XDG_CONFIG_HOME": self.d}
        h.save_session({"cookies": "X-APPLE-WEBAUTH-USER=1", "region": "global",
                        "host": "p99-maildomainws.icloud.com", "dsid": "123"},
                       h.session_path(self.env))

    def run_cmd(self, fn, args, **kw):
        out, err = io.StringIO(), io.StringIO()
        ns = h.build_parser().parse_args(args)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = fn(ns, env=self.env, **kw)
            except h.HmeError as e:
                print(f"error: {e}", file=err); rc = e.code
        return rc, out.getvalue(), err.getvalue()

    def test_session_file_mode_and_path(self):
        p = h.session_path(self.env)
        self.assertEqual(p, os.path.join(self.d, "hmecli", "session.json"))
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_generate_text_and_request_shape(self):
        f = Fake([ok({"hme": "a@icloud.com"}), ok({"hme": {"hme": "a@icloud.com"}}),
                  ok({"hme": "b@icloud.com"}), ok({"hme": {"hme": "b@icloud.com"}})])
        rc, out, _ = self.run_cmd(h.cmd_generate, ["generate", "-n", "2", "--delay", "0",
                                  "-l", "L"], opener=f, sleep=lambda s: None)
        self.assertEqual((rc, out), (0, "a@icloud.com\nb@icloud.com\n"))
        g, r = f.reqs[0], f.reqs[1]
        self.assertTrue(g.full_url.startswith(
            "https://p99-maildomainws.icloud.com/v1/hme/generate?"))
        self.assertIn("dsid=123", g.full_url)
        self.assertEqual(json.loads(r.data)["label"], "L")
        self.assertEqual(g.get_header("Cookie"), "X-APPLE-WEBAUTH-USER=1")
        self.assertEqual(g.get_header("Origin"), "https://www.icloud.com")

    def test_generate_json(self):
        f = Fake([ok({"hme": "a@icloud.com"}), ok({"hme": {"hme": "a@icloud.com"}})])
        rc, out, _ = self.run_cmd(h.cmd_generate, ["generate", "--json"], opener=f)
        self.assertEqual(json.loads(out), ["a@icloud.com"])

    def test_expired_session_exit2(self):
        import urllib.error
        f = Fake([urllib.error.HTTPError("u", 401, "x", {}, None)])
        rc, _, err = self.run_cmd(h.cmd_generate, ["generate"], opener=f)
        self.assertEqual(rc, 2)
        self.assertIn("login", err)

    def test_partial_failure(self):
        f = Fake([ok({"hme": "a@icloud.com"}), ok({"hme": {"hme": "a@icloud.com"}}),
                  {"success": False, "error": {"errorMessage": "limit reached"}}])
        rc, out, err = self.run_cmd(h.cmd_generate, ["generate", "-n", "2", "--delay", "0"],
                                    opener=f, sleep=lambda s: None)
        self.assertEqual(rc, 1)
        self.assertEqual(out, "a@icloud.com\n")
        self.assertIn("limit reached", err)
        self.assertIn("1/2", err)

    def test_missing_session(self):
        self.env = {"XDG_CONFIG_HOME": tempfile.mkdtemp()}
        rc, _, err = self.run_cmd(h.cmd_generate, ["generate"])
        self.assertEqual(rc, 2)
        self.assertIn("login", err)

    def test_list_filters_inactive(self):
        f = Fake([ok({"hmeEmails": [{"hme": "a@x", "isActive": True, "label": "l"},
                                    {"hme": "b@x", "isActive": False}]})])
        rc, out, _ = self.run_cmd(h.cmd_list, ["list"], opener=f)
        self.assertEqual(out, "a@x\tactive\tl\n")

    def test_status(self):
        rc, out, _ = self.run_cmd(h.cmd_status, ["status"], opener=Fake([VALID]))
        self.assertEqual(rc, 0)
        self.assertIn("Test", out)

    def test_login_picks_valid_browser_and_stores(self):
        self.env = {"XDG_CONFIG_HOME": tempfile.mkdtemp()}
        calls = []
        def reader(b, domain):
            calls.append(b)
            if b == "firefox": raise FileNotFoundError
            return "X-APPLE-WEBAUTH-USER=zz; other=1"
        def factory(cookies, region):
            return h.Client(cookies, region, opener=Fake([VALID]))
        rc, _, err = self.run_cmd(h.cmd_login, ["login", "--no-open", "--no-wait"],
                                  reader=reader, client_factory=factory)
        self.assertEqual((rc, calls), (0, ["firefox", "chrome"]))
        s = h.load_session(h.session_path(self.env))
        self.assertEqual(s["host"], "p99-maildomainws.icloud.com")
        self.assertEqual(s["dsid"], "123")
        self.assertNotIn("zz", err)  # secrets never printed

    def test_login_no_session_found(self):
        rc, _, err = self.run_cmd(h.cmd_login, ["login", "--no-open", "--no-wait",
                                  "--browser", "firefox"], reader=lambda b, d: "")
        self.assertEqual(rc, 1)
        self.assertIn("Sign in", err)

    def test_logout(self):
        rc, _, _ = self.run_cmd(h.cmd_logout, ["logout"])
        self.assertFalse(os.path.exists(h.session_path(self.env)))


if __name__ == "__main__":
    unittest.main()
