#!/usr/bin/env python3
import importlib.util
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HELPER = Path(__file__).with_name("preview-helper.py")
TEST_HOME_ROOT = os.path.join(
    os.path.expanduser("~"), ".cache", "omarchy", "workspace-thumbs-tests"
)


def jpeg(width=16, height=16):
    sof = (
        b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


def load_helper():
    spec = importlib.util.spec_from_file_location("preview_helper", HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PreviewHelperTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_HOME_ROOT, mode=0o700, exist_ok=True)
        os.chmod(TEST_HOME_ROOT, 0o700)
        self._tmp = tempfile.TemporaryDirectory(dir=TEST_HOME_ROOT, prefix="home-")
        self.home = self._tmp.name
        os.chmod(self.home, 0o700)
        self.cache = os.path.join(self.home, ".cache", "omarchy", "workspace-previews")
        self.env = os.environ.copy()
        self.env["HOME"] = self.home
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home
        self.mod = load_helper()

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        self._tmp.cleanup()

    def run_helper(self, *args, stdin=None, timeout=5, env=None):
        return subprocess.run(
            ["/usr/bin/python3", "-I", str(HELPER), *args],
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=self.env if env is None else env,
        )

    def test_write_then_read_roundtrip(self):
        data = jpeg()
        path = os.path.join(self.cache, "ws-1.jpg")
        write = self.run_helper("write", path, stdin=data)
        self.assertEqual(write.returncode, 0, write.stderr)
        read = self.run_helper("read", path)
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(__import__("base64").b64decode(read.stdout.strip()), data)

    def test_write_refuses_path_outside_home_cache(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ws-1.jpg")
            write = self.run_helper("write", path, stdin=data)
            self.assertNotEqual(write.returncode, 0)
            self.assertFalse(os.path.exists(path))

    def test_write_refuses_tmp_even_if_named_like_cache(self):
        data = jpeg()
        with tempfile.TemporaryDirectory(prefix="tmp-cache-") as folder:
            fake = os.path.join(folder, ".cache", "omarchy", "workspace-previews", "ws-1.jpg")
            os.makedirs(os.path.dirname(fake), mode=0o700)
            write = self.run_helper("write", fake, stdin=data)
            self.assertNotEqual(write.returncode, 0)
            self.assertFalse(os.path.isfile(fake) and Path(fake).read_bytes() == data)

    def test_write_refuses_symlink_directory(self):
        data = jpeg()
        real = os.path.join(self.home, "real")
        os.makedirs(real, mode=0o700)
        cache_parent = os.path.join(self.home, ".cache", "omarchy")
        os.makedirs(cache_parent, mode=0o700)
        os.symlink(real, os.path.join(cache_parent, "workspace-previews"))
        path = os.path.join(self.cache, "ws-1.jpg")
        write = self.run_helper("write", path, stdin=data)
        self.assertNotEqual(write.returncode, 0)

    def test_write_replaces_symlink_dest_atomically(self):
        data = jpeg()
        os.makedirs(self.cache, mode=0o700)
        real = os.path.join(self.cache, "other.jpg")
        Path(real).write_bytes(b"keep")
        dest = os.path.join(self.cache, "ws-1.jpg")
        os.symlink(real, dest)
        write = self.run_helper("write", dest, stdin=data)
        self.assertEqual(write.returncode, 0, write.stderr)
        self.assertFalse(os.path.islink(dest))
        self.assertEqual(Path(dest).read_bytes(), data)
        self.assertEqual(Path(real).read_bytes(), b"keep")

    def test_write_rejects_invalid_jpeg(self):
        path = os.path.join(self.cache, "ws-1.jpg")
        write = self.run_helper("write", path, stdin=b"not-a-jpeg")
        self.assertNotEqual(write.returncode, 0)
        self.assertFalse(os.path.exists(path))

    def test_prepare_dir_creates_private_dir(self):
        dir_fd = self.mod.open_verified_dir(self.cache)
        os.close(dir_fd)
        st = os.lstat(self.cache)
        self.assertTrue(stat.S_ISDIR(st.st_mode))
        self.assertFalse(stat.S_ISLNK(st.st_mode))
        self.assertEqual(st.st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o700)
        cache_home = os.path.join(self.home, ".cache")
        self.assertEqual(stat.S_IMODE(os.lstat(cache_home).st_mode), 0o700)

    def test_prepare_dir_refuses_symlink_parent(self):
        real = os.path.join(self.home, "real")
        os.makedirs(real, mode=0o700)
        os.makedirs(os.path.join(self.home, ".cache"), mode=0o700)
        os.symlink(real, os.path.join(self.home, ".cache", "omarchy"))
        with self.assertRaises(SystemExit):
            self.mod.open_verified_dir(self.cache)

    def test_prepare_dir_refuses_symlink(self):
        real = os.path.join(self.home, "real")
        os.makedirs(real, mode=0o700)
        os.makedirs(os.path.join(self.home, ".cache", "omarchy"), mode=0o700)
        os.symlink(real, self.cache)
        with self.assertRaises(SystemExit):
            self.mod.open_verified_dir(self.cache)

    def test_exclusive_temp_keeps_dir_fd(self):
        dir_fd = self.mod.open_verified_dir(self.cache)
        fd = -1
        try:
            fd, name = self.mod.exclusive_temp(dir_fd)
            info = os.fstat(fd)
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertEqual(info.st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertTrue(name.startswith(".pub-"))
            listed = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            self.assertEqual(listed.st_ino, info.st_ino)
            os.close(fd)
            fd = -1
            again_fd, again_name = self.mod.exclusive_temp(dir_fd)
            os.close(again_fd)
            self.assertNotEqual(again_name, name)
            os.unlink(name, dir_fd=dir_fd)
            os.unlink(again_name, dir_fd=dir_fd)
        finally:
            if fd >= 0:
                os.close(fd)
            os.close(dir_fd)

    def test_read_text_rejects_symlink(self):
        os.makedirs(self.cache, mode=0o700)
        real = os.path.join(self.cache, "real")
        Path(real).write_text("secret\n")
        link = os.path.join(self.cache, "stamp.txt")
        os.symlink(real, link)
        result = self.run_helper("read-text", link)
        self.assertNotEqual(result.returncode, 0)

    def test_read_rejects_symlink(self):
        data = jpeg()
        os.makedirs(self.cache, mode=0o700)
        real = os.path.join(self.cache, "real.jpg")
        link = os.path.join(self.cache, "ws-1.jpg")
        Path(real).write_bytes(data)
        os.symlink(real, link)
        read = self.run_helper("read", link)
        self.assertNotEqual(read.returncode, 0)

    def test_stream_fail_closed_on_overflow(self):
        with self.assertRaises(SystemExit) as cm:
            self.mod.stream_capped(
                ["python3", "-c", "import sys; sys.stdout.buffer.write(b'0123456789')"],
                1000,
                8,
            )
        self.assertEqual(cm.exception.code, 70)

    def test_stream_live_overflow_kills_before_deadline(self):
        started = time.monotonic()
        with self.assertRaises(SystemExit) as cm:
            self.mod.stream_capped(
                [
                    "python3",
                    "-c",
                    "import sys\nwhile True:\n    sys.stdout.buffer.write(b'B'*4096)\n    sys.stdout.buffer.flush()\n",
                ],
                5000,
                64,
            )
        elapsed = time.monotonic() - started
        self.assertEqual(cm.exception.code, 70)
        self.assertLess(elapsed, 2.0)

    def test_stream_fail_closed_on_timeout(self):
        with self.assertRaises(SystemExit) as cm:
            self.mod.stream_capped(["python3", "-c", "import time; time.sleep(2)"], 200, 1024)
        self.assertEqual(cm.exception.code, 124)

    def test_stream_kills_process_group(self):
        started = time.monotonic()
        with self.assertRaises(SystemExit) as cm:
            self.mod.stream_capped(
                [
                    "python3",
                    "-c",
                    "import os, time\n"
                    "pid = os.fork()\n"
                    "if pid == 0:\n"
                    "    while True:\n"
                    "        os.write(1, b'G'*512)\n"
                    "else:\n"
                    "    time.sleep(8)\n",
                ],
                4000,
                64,
            )
        elapsed = time.monotonic() - started
        self.assertEqual(cm.exception.code, 70)
        self.assertLess(elapsed, 2.0)

    def test_stream_replaces_child_path(self):
        data = self.mod.stream_capped(
            ["python3", "-c", "import os,sys; sys.stdout.write(os.environ['PATH'])"],
            1000,
            4096,
        )
        self.assertEqual(data, b"/usr/bin:/bin")

    def test_stream_drops_ld_preload(self):
        os.environ["LD_PRELOAD"] = "/not/a/real.so"
        try:
            data = self.mod.stream_capped(
                ["python3", "-c", "import os,sys; sys.stdout.write(os.environ.get('LD_PRELOAD',''))"],
                1000,
                4096,
            )
            self.assertEqual(data, b"")
        finally:
            os.environ.pop("LD_PRELOAD", None)

    def test_stream_ignores_ambient_path(self):
        evil = os.path.join(self.home, "evil")
        os.makedirs(evil, mode=0o700)
        decoy = os.path.join(evil, "python3")
        Path(decoy).write_text("#!/usr/bin/python3\nimport sys\nsys.stdout.write('EVIL')\n")
        os.chmod(decoy, 0o700)
        old_path = os.environ.get("PATH")
        os.environ["PATH"] = evil + ":/usr/bin:/bin"
        try:
            data = self.mod.stream_capped(
                ["python3", "-c", "import sys; sys.stdout.write('ok')"],
                1000,
                4096,
            )
            self.assertEqual(data, b"ok")
        finally:
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path

    def test_resolve_cmd_pins_and_rejects_tmp(self):
        pinned = self.mod.resolve_cmd(["python3"])
        self.assertTrue(pinned[0].startswith("/usr/bin/") or pinned[0].startswith("/bin/"))
        with self.assertRaises(SystemExit):
            self.mod.resolve_cmd(["/tmp/evil"])
        with self.assertRaises(SystemExit):
            self.mod.resolve_cmd(["./python3"])
        evil = os.path.join(self.home, "evil-bin")
        Path(evil).write_text("#!/usr/bin/python3\nprint('nope')\n")
        os.chmod(evil, 0o700)
        with self.assertRaises(SystemExit):
            self.mod.resolve_cmd([evil])

    def test_focused_monitor_rejects_flag_injection(self):
        self.mod.stream_capped = lambda *a, **k: b'[{"focused": true, "name": "--help"}]'
        with self.assertRaises(SystemExit):
            self.mod.focused_monitor()
        self.mod.stream_capped = lambda *a, **k: b'[{"focused": true, "name": "-o"}]'
        with self.assertRaises(SystemExit):
            self.mod.focused_monitor()
        self.mod.stream_capped = lambda *a, **k: b'[{"focused": true, "name": "eDP-1"}]'
        self.assertEqual(self.mod.focused_monitor(), "eDP-1")

    def test_capture_rejects_dest_outside_cache(self):
        result = self.run_helper("capture", "1", "/tmp/ws-1.jpg")
        self.assertNotEqual(result.returncode, 0)

    def test_capture_rejects_dest_mismatch(self):
        dest = os.path.join(self.cache, "ws-2.jpg")
        result = self.run_helper("capture", "1", dest)
        self.assertNotEqual(result.returncode, 0)

    def test_removed_footgun_cli(self):
        self.assertNotEqual(self.run_helper("stage", self.cache).returncode, 0)
        self.assertNotEqual(self.run_helper("commit", "a", "b").returncode, 0)
        self.assertNotEqual(self.run_helper("run", "1000", "8", "--", "python3", "-c", "print(1)").returncode, 0)
        self.assertNotEqual(self.run_helper("prepare-dir", self.cache).returncode, 0)
        with self.assertRaises(SystemExit):
            self.mod.stream_tool("python3", ["-c", "print(1)"], 1000, 4096)
        with self.assertRaises(SystemExit):
            self.mod.stream_tool("grim", ["-o", "eDP-1", "/tmp/out.jpg"], 1000, 4096)

    def test_stamp_refuses_wallpaper_in_tmp(self):
        outside = tempfile.NamedTemporaryFile(prefix="wall-", suffix=".png", delete=False)
        try:
            outside.write(b"png")
            outside.close()
            link_dir = os.path.join(self.home, ".local", "state", "omarchy", "current")
            os.makedirs(link_dir, mode=0o700)
            os.symlink(outside.name, os.path.join(link_dir, "background"))
            result = self.run_helper("stamp-wallpaper")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(self.cache, "wallpaper.path")))
        finally:
            os.unlink(outside.name)

    def test_stamp_wallpaper_writes_cache_not_tmp(self):
        wallpaper = os.path.join(self.home, "wall.png")
        Path(wallpaper).write_bytes(b"png")
        link_dir = os.path.join(self.home, ".local", "state", "omarchy", "current")
        os.makedirs(link_dir, mode=0o700)
        os.symlink(wallpaper, os.path.join(link_dir, "background"))
        result = self.run_helper("stamp-wallpaper")
        self.assertEqual(result.returncode, 0, result.stderr)
        stamp = os.path.join(self.cache, "wallpaper.path")
        self.assertEqual(Path(stamp).read_text(), wallpaper + "\n")
        again = self.run_helper("stamp-wallpaper")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(Path(stamp).read_text(), wallpaper + "\n")


class ProductionPathTests(unittest.TestCase):
    def test_helper_keeps_dir_fd_api(self):
        source = HELPER.read_text()
        self.assertIn("dir_fd=dir_fd", source)
        self.assertIn("src_dir_fd=dir_fd", source)
        self.assertIn("dst_dir_fd=dir_fd", source)
        self.assertIn("start_new_session=True", source)
        self.assertIn('{"PATH": PINNED_PATH}', source)
        self.assertIn("select.select", source)
        self.assertIn("os.killpg", source)
        self.assertIn('os.open("/",', source)
        self.assertIn("ALLOWED_TOOLS", source)
        self.assertIn('"-o", monitor, "-"', source)
        self.assertIn("os.readlink", source)
        self.assertIn("def scrub_runtime_env", source)
        self.assertNotIn("subprocess.run(", source)
        self.assertNotIn("def cmd_stage", source)
        self.assertNotIn("def cmd_commit", source)
        self.assertNotIn("def cmd_run", source)
        self.assertNotIn("def cmd_prepare_dir", source)
        self.assertNotIn("os.path.realpath(link)", source)
        self.assertNotIn("/tmp", source)

    def test_scripts_pin_path_and_stay_out_of_tmp(self):
        capture = Path(__file__).with_name("capture-workspace-preview.sh").read_text()
        stamp = Path(__file__).with_name("update-wallpaper-stamp.sh").read_text()
        for script in (capture, stamp):
            self.assertIn('PATH="/usr/bin:/bin"', script)
            self.assertIn("/usr/bin/env -i", script)
            self.assertIn("/usr/bin/python3 -I", script)
            self.assertIn("#!/usr/bin/bash", script)
            self.assertNotIn("/tmp", script)
            self.assertNotIn("jq", script)
            self.assertNotIn("timeout", script)
            self.assertNotIn("readlink", script)
            self.assertNotIn("stage", script)
            self.assertNotIn("commit", script)
            self.assertNotIn("prepare-dir", script)
        self.assertIn('capture "$workspace_id" "$destination"', capture)
        self.assertNotIn("grim", capture)
        self.assertIn("stamp-wallpaper", stamp)


if __name__ == "__main__":
    unittest.main()
