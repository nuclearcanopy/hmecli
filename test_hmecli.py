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

    def gen(self, args, tty, answer="", **kw):
        f = Fake([ok({"hme": "a@icloud.com"}), ok({"hme": {"hme": "a@icloud.com"}})] * 3)
        asked = []
        rc, out, err = self.run_cmd(h.cmd_generate, ["generate", "--delay", "0"] + args,
                                    opener=f, sleep=lambda s: None, isatty=lambda: tty,
                                    ask=lambda p: asked.append(p) or answer)
        bodies = [json.loads(r.data) for r in f.reqs if r.full_url.split("?")[0].endswith("reserve")]
        return rc, asked, err, bodies

    def test_label_prompt_answer_used(self):
        rc, asked, err, b = self.gen([], True, "shop")
        self.assertEqual((rc, len(asked)), (0, 1))
        self.assertIn("Label (Enter for none): ", err)
        self.assertEqual(b[0]["label"], "shop")

    def test_label_prompt_empty_means_none(self):
        _, asked, _, b = self.gen([], True, "")
        self.assertEqual(len(asked), 1)
        self.assertNotIn("label", b[0])

    def test_no_prompt_without_tty(self):
        _, asked, err, b = self.gen([], False, "x")
        self.assertEqual(asked, [])
        self.assertNotIn("Label", err)
        self.assertNotIn("label", b[0])

    def test_no_prompt_with_json(self):
        _, asked, _, b = self.gen(["--json"], True, "x")
        self.assertEqual(asked, [])
        self.assertNotIn("label", b[0])

    def test_label_flag_no_prompt(self):
        _, asked, _, b = self.gen(["--label", "L"], True, "x")
        self.assertEqual(asked, [])
        self.assertEqual(b[0]["label"], "L")

    def test_empty_label_flag_means_none(self):
        _, asked, _, b = self.gen(["--label", ""], True, "x")
        self.assertEqual(asked, [])
        self.assertNotIn("label", b[0])

    def test_prompt_once_for_three(self):
        _, asked, _, b = self.gen(["-n", "3"], True, "shop")
        self.assertEqual(len(asked), 1)
        self.assertEqual([x["label"] for x in b], ["shop"] * 3)

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

    A = {"hme": "a@icloud.com", "anonymousId": "ANON-A", "isActive": True}
    B = {"hme": "b@icloud.com", "anonymousId": "ANON-B", "isActive": False}

    def lst(self): return ok({"hmeEmails": [self.A, self.B]})

    def test_deactivate(self):
        f = Fake([self.lst(), ok({})])
        rc, out, _ = self.run_cmd(h.cmd_deactivate, ["deactivate", "A@iCloud.com"], opener=f)
        self.assertEqual((rc, out), (0, "deactivated a@icloud.com\n"))
        r = f.reqs[1]
        self.assertEqual((r.get_method(), json.loads(r.data)), ("POST", {"anonymousId": "ANON-A"}))
        self.assertTrue(r.full_url.startswith(
            "https://p99-maildomainws.icloud.com/v1/hme/deactivate?"))

    def test_delete_inactive_confirmed(self):
        f = Fake([self.lst(), ok({})])
        rc, out, _ = self.run_cmd(h.cmd_delete, ["delete", "b@icloud.com"], opener=f,
                                  confirm=lambda p: "y", isatty=lambda: True)
        self.assertEqual((rc, out), (0, "deleted b@icloud.com\n"))
        self.assertEqual(len(f.reqs), 2)
        r = f.reqs[1]
        self.assertTrue(r.full_url.startswith(
            "https://p99-maildomainws.icloud.com/v1/hme/delete?"))
        self.assertEqual(json.loads(r.data), {"anonymousId": "ANON-B"})

    def test_delete_active_deactivates_first(self):
        f = Fake([self.lst(), ok({}), ok({})])
        prompts = []
        rc, out, _ = self.run_cmd(h.cmd_delete, ["delete", "a@icloud.com"], opener=f,
                                  confirm=lambda p: prompts.append(p) or "yes",
                                  isatty=lambda: True)
        self.assertEqual(rc, 0)
        self.assertEqual([r.full_url.split("?")[0].rsplit("/", 1)[1] for r in f.reqs[1:]],
                         ["deactivate", "delete"])
        self.assertIn("permanent", prompts[0].lower())
        self.assertIn("deactivate", prompts[0].lower())

    def test_delete_declined_makes_no_call(self):
        f = Fake([self.lst()])
        rc, out, _ = self.run_cmd(h.cmd_delete, ["delete", "a@icloud.com"], opener=f,
                                  confirm=lambda p: "n", isatty=lambda: True)
        self.assertEqual((rc, out), (1, ""))
        self.assertEqual(len(f.reqs), 1)  # only the list lookup

    def test_delete_non_tty_without_yes_refuses(self):
        f = Fake([self.lst()])
        rc, _, err = self.run_cmd(h.cmd_delete, ["delete", "a@icloud.com"], opener=f,
                                  isatty=lambda: False)
        self.assertEqual(rc, 1)
        self.assertIn("--yes", err)
        self.assertEqual(len(f.reqs), 1)

    def test_delete_yes_skips_prompt(self):
        f = Fake([self.lst(), ok({})])
        rc, _, _ = self.run_cmd(h.cmd_delete, ["delete", "--yes", "b@icloud.com"], opener=f,
                                isatty=lambda: False)
        self.assertEqual((rc, len(f.reqs)), (0, 2))

    def test_alias_not_found_and_bare_id(self):
        for cmd, fn in (("delete", h.cmd_delete), ("deactivate", h.cmd_deactivate)):
            f = Fake([self.lst()])
            rc, _, err = self.run_cmd(fn, [cmd, "--yes", "zz@icloud.com"] if cmd == "delete"
                                      else [cmd, "zz@icloud.com"], opener=f)
            self.assertEqual(rc, 1)
            self.assertIn("not found", err)
            self.assertEqual(len(f.reqs), 1)
        f = Fake([])
        rc, _, err = self.run_cmd(h.cmd_deactivate, ["deactivate", "ANON-A"], opener=f)
        self.assertEqual((rc, len(f.reqs)), (1, 0))

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
