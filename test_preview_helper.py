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
        self._tmp = tempfile.TemporaryDirectory()
        self.home = self._tmp.name
        os.chmod(self.home, 0o700)
        self.cache = os.path.join(self.home, ".cache", "omarchy", "workspace-previews")
        self.env = os.environ.copy()
        self.env["HOME"] = self.home

    def tearDown(self):
        self._tmp.cleanup()

    def run_helper(self, *args, stdin=None, timeout=5, env=None):
        return subprocess.run(
            ["/usr/bin/python3", str(HELPER), *args],
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
            self.assertFalse(os.path.isfile(fake) and os.path.getsize(fake) > 0 and Path(fake).read_bytes() == data)

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

    def test_stage_commit_jpeg(self):
        data = jpeg()
        staged = self.run_helper("stage", self.cache)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        tmp = staged.stdout.decode().strip()
        self.assertTrue(os.path.basename(tmp).startswith(".pub-"))
        self.assertEqual(os.path.dirname(tmp), self.cache)
        Path(tmp).write_bytes(data)
        dest = os.path.join(self.cache, "ws-1.jpg")
        commit = self.run_helper("commit", "--jpeg", tmp, dest)
        self.assertEqual(commit.returncode, 0, commit.stderr)
        self.assertFalse(os.path.exists(tmp))
        self.assertEqual(Path(dest).read_bytes(), data)

    def test_prepare_dir_creates_private_dir(self):
        result = self.run_helper("prepare-dir", self.cache)
        self.assertEqual(result.returncode, 0, result.stderr)
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
        result = self.run_helper("prepare-dir", self.cache)
        self.assertNotEqual(result.returncode, 0)

    def test_stage_is_exclusive_nofollow_owned(self):
        staged = self.run_helper("stage", self.cache)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        tmp = staged.stdout.decode().strip()
        st = os.lstat(tmp)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertFalse(stat.S_ISLNK(st.st_mode))
        self.assertEqual(st.st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        again = self.run_helper("stage", self.cache)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertNotEqual(again.stdout.decode().strip(), tmp)

    def test_commit_rejects_symlink_tmp(self):
        data = jpeg()
        os.makedirs(self.cache, mode=0o700)
        real = os.path.join(self.cache, ".pub-notreally")
        Path(real).write_bytes(data)
        tmp = os.path.join(self.cache, ".pub-link")
        os.symlink(real, tmp)
        dest = os.path.join(self.cache, "ws-1.jpg")
        commit = self.run_helper("commit", "--jpeg", tmp, dest)
        self.assertNotEqual(commit.returncode, 0)
        self.assertFalse(os.path.exists(dest))

    def test_commit_rejects_tmp_outside_dest_dir(self):
        data = jpeg()
        other = os.path.join(self.home, "other")
        os.makedirs(other, mode=0o700)
        tmp = os.path.join(other, ".pub-" + os.urandom(4).hex())
        Path(tmp).write_bytes(data)
        dest = os.path.join(self.cache, "ws-1.jpg")
        commit = self.run_helper("commit", "--jpeg", tmp, dest)
        self.assertNotEqual(commit.returncode, 0)
        self.assertFalse(os.path.exists(dest))

    def test_commit_rejects_invalid_jpeg_and_removes_tmp(self):
        staged = self.run_helper("stage", self.cache)
        tmp = staged.stdout.decode().strip()
        Path(tmp).write_bytes(b"not-a-jpeg")
        dest = os.path.join(self.cache, "ws-1.jpg")
        commit = self.run_helper("commit", "--jpeg", tmp, dest)
        self.assertNotEqual(commit.returncode, 0)
        self.assertFalse(os.path.exists(tmp))
        self.assertFalse(os.path.exists(dest))

    def test_read_text_rejects_symlink(self):
        os.makedirs(self.cache, mode=0o700)
        real = os.path.join(self.cache, "real")
        Path(real).write_text("secret\n")
        link = os.path.join(self.cache, "stamp.txt")
        os.symlink(real, link)
        result = self.run_helper("read-text", link)
        self.assertNotEqual(result.returncode, 0)

    def test_prepare_dir_refuses_symlink(self):
        real = os.path.join(self.home, "real")
        os.makedirs(real, mode=0o700)
        os.makedirs(os.path.join(self.home, ".cache", "omarchy"), mode=0o700)
        os.symlink(real, self.cache)
        result = self.run_helper("prepare-dir", self.cache)
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

    def test_run_fail_closed_on_overflow(self):
        result = self.run_helper(
            "run", "1000", "8", "--", "python3", "-c", "import sys; sys.stdout.buffer.write(b'0123456789')"
        )
        self.assertEqual(result.returncode, 70)
        self.assertEqual(result.stdout, b"")

    def test_run_live_overflow_kills_before_deadline(self):
        started = time.monotonic()
        result = self.run_helper(
            "run",
            "5000",
            "64",
            "--",
            "python3",
            "-c",
            "import sys\nwhile True:\n    sys.stdout.buffer.write(b'B'*4096)\n    sys.stdout.buffer.flush()\n",
            timeout=8,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 70)
        self.assertEqual(result.stdout, b"")
        self.assertLess(elapsed, 2.0)

    def test_run_fail_closed_on_timeout(self):
        result = self.run_helper(
            "run",
            "200",
            "1024",
            "--",
            "python3",
            "-c",
            "import time; time.sleep(2)",
            timeout=5,
        )
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.stdout, b"")

    def test_run_replaces_child_path(self):
        result = self.run_helper(
            "run",
            "1000",
            "4096",
            "--",
            "python3",
            "-c",
            "import os,sys; sys.stdout.write(os.environ['PATH'])",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"/usr/bin:/bin")

    def test_run_ignores_ambient_path(self):
        evil = os.path.join(self.home, "evil")
        os.makedirs(evil, mode=0o700)
        decoy = os.path.join(evil, "python3")
        Path(decoy).write_text("#!/usr/bin/python3\nimport sys\nsys.stdout.write('EVIL')\n")
        os.chmod(decoy, 0o700)
        env = self.env.copy()
        env["PATH"] = evil + ":/usr/bin:/bin"
        result = self.run_helper(
            "run",
            "1000",
            "4096",
            "--",
            "python3",
            "-c",
            "import sys; sys.stdout.write('ok')",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"ok")

    def test_run_rejects_unpinned_executable(self):
        evil = os.path.join(self.home, "evil-bin")
        Path(evil).write_text("#!/usr/bin/python3\nprint('nope')\n")
        os.chmod(evil, 0o700)
        result = self.run_helper("run", "1000", "4096", "--", evil)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_capture_rejects_dest_outside_cache(self):
        result = self.run_helper("capture", "1", "/tmp/ws-1.jpg")
        self.assertNotEqual(result.returncode, 0)

    def test_capture_rejects_dest_mismatch(self):
        dest = os.path.join(self.cache, "ws-2.jpg")
        result = self.run_helper("capture", "1", dest)
        self.assertNotEqual(result.returncode, 0)

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

    def test_resolve_cmd_pins_and_rejects_tmp(self):
        mod = load_helper()
        pinned = mod.resolve_cmd(["python3"])
        self.assertTrue(pinned[0].startswith("/usr/bin/") or pinned[0].startswith("/bin/"))
        with self.assertRaises(SystemExit):
            mod.resolve_cmd(["/tmp/evil"])
        with self.assertRaises(SystemExit):
            mod.resolve_cmd(["./python3"])


class ProductionPathTests(unittest.TestCase):
    def test_helper_keeps_dir_fd_api(self):
        source = HELPER.read_text()
        self.assertIn("dir_fd=dir_fd", source)
        self.assertIn("src_dir_fd=dir_fd", source)
        self.assertIn("dst_dir_fd=dir_fd", source)
        self.assertIn("start_new_session=True", source)
        self.assertIn('env["PATH"] = PINNED_PATH', source)
        self.assertIn("select.select", source)
        self.assertIn("os.killpg", source)
        self.assertNotIn("subprocess.run(", source)
        self.assertNotIn("/tmp", source)

    def test_scripts_pin_path_and_stay_out_of_tmp(self):
        capture = Path(__file__).with_name("capture-workspace-preview.sh").read_text()
        stamp = Path(__file__).with_name("update-wallpaper-stamp.sh").read_text()
        for script in (capture, stamp):
            self.assertIn('PATH="/usr/bin:/bin"', script)
            self.assertIn("/usr/bin/python3", script)
            self.assertIn("#!/usr/bin/bash", script)
            self.assertNotIn("/tmp", script)
            self.assertNotIn("jq", script)
            self.assertNotIn("timeout", script)
            self.assertNotIn("readlink", script)
        self.assertIn('capture "$workspace_id" "$destination"', capture)
        self.assertNotIn("grim", capture)
        self.assertIn("stamp-wallpaper", stamp)
        self.assertNotIn("prepare-dir", capture)
        self.assertNotIn("prepare-dir", stamp)


if __name__ == "__main__":
    unittest.main()
