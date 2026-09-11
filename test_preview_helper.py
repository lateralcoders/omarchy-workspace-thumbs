#!/usr/bin/env python3
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).with_name("preview-helper.py")


def jpeg(width=16, height=16):
    # Minimal 8-bit baseline SOF0 JPEG large enough for dimension parsing.
    sof = (
        b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8" + sof + b"\xff\xd9"


def run_helper(*args, stdin=None, timeout=5):
    return subprocess.run(
        ["python3", str(HELPER), *args],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


class PreviewHelperTests(unittest.TestCase):
    def test_write_then_read_roundtrip(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ws-1.jpg")
            write = run_helper("write", path, stdin=data)
            self.assertEqual(write.returncode, 0, write.stderr)
            read = run_helper("read", path)
            self.assertEqual(read.returncode, 0, read.stderr)
            self.assertEqual(__import__("base64").b64decode(read.stdout.strip()), data)

    def test_write_refuses_symlink_directory(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            real = os.path.join(folder, "real")
            os.mkdir(real, 0o700)
            link = os.path.join(folder, "linked")
            os.symlink(real, link)
            path = os.path.join(link, "ws-1.jpg")
            write = run_helper("write", path, stdin=data)
            self.assertNotEqual(write.returncode, 0)

    def test_write_replaces_symlink_dest_atomically(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            real = os.path.join(folder, "other.jpg")
            Path(real).write_bytes(b"keep")
            dest = os.path.join(folder, "ws-1.jpg")
            os.symlink(real, dest)
            write = run_helper("write", dest, stdin=data)
            self.assertEqual(write.returncode, 0, write.stderr)
            self.assertFalse(os.path.islink(dest))
            self.assertEqual(Path(dest).read_bytes(), data)
            self.assertEqual(Path(real).read_bytes(), b"keep")

    def test_stage_commit_jpeg(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            staged = run_helper("stage", folder)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            tmp = staged.stdout.decode().strip()
            self.assertTrue(os.path.basename(tmp).startswith(".pub-"))
            Path(tmp).write_bytes(data)
            dest = os.path.join(folder, "ws-1.jpg")
            commit = run_helper("commit", "--jpeg", tmp, dest)
            self.assertEqual(commit.returncode, 0, commit.stderr)
            self.assertFalse(os.path.exists(tmp))
            self.assertEqual(Path(dest).read_bytes(), data)

    def test_prepare_dir_creates_private_dir(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "workspace-previews")
            result = run_helper("prepare-dir", cache)
            self.assertEqual(result.returncode, 0, result.stderr)
            st = os.lstat(cache)
            self.assertTrue(stat.S_ISDIR(st.st_mode))
            self.assertFalse(stat.S_ISLNK(st.st_mode))
            self.assertEqual(st.st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o700)

    def test_prepare_dir_refuses_symlink_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            real = os.path.join(folder, "real")
            os.mkdir(real, 0o700)
            parent = os.path.join(folder, "omarchy")
            os.symlink(real, parent)
            leaf = os.path.join(parent, "workspace-previews")
            result = run_helper("prepare-dir", leaf)
            self.assertNotEqual(result.returncode, 0)

    def test_stage_is_exclusive_nofollow_owned(self):
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            staged = run_helper("stage", folder)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            tmp = staged.stdout.decode().strip()
            st = os.lstat(tmp)
            self.assertTrue(stat.S_ISREG(st.st_mode))
            self.assertFalse(stat.S_ISLNK(st.st_mode))
            self.assertEqual(st.st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
            again = run_helper("stage", folder)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertNotEqual(again.stdout.decode().strip(), tmp)

    def test_commit_rejects_symlink_tmp(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            real = os.path.join(folder, ".pub-notreally")
            Path(real).write_bytes(data)
            tmp = os.path.join(folder, ".pub-link")
            os.symlink(real, tmp)
            dest = os.path.join(folder, "ws-1.jpg")
            commit = run_helper("commit", "--jpeg", tmp, dest)
            self.assertNotEqual(commit.returncode, 0)
            self.assertFalse(os.path.exists(dest))

    def test_commit_rejects_tmp_outside_dest_dir(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            other = os.path.join(folder, "other")
            os.mkdir(other, 0o700)
            staged = run_helper("stage", other)
            tmp = staged.stdout.decode().strip()
            Path(tmp).write_bytes(data)
            dest = os.path.join(folder, "ws-1.jpg")
            commit = run_helper("commit", "--jpeg", tmp, dest)
            self.assertNotEqual(commit.returncode, 0)

    def test_commit_rejects_invalid_jpeg_and_removes_tmp(self):
        with tempfile.TemporaryDirectory() as folder:
            os.chmod(folder, 0o700)
            staged = run_helper("stage", folder)
            tmp = staged.stdout.decode().strip()
            Path(tmp).write_bytes(b"not-a-jpeg")
            dest = os.path.join(folder, "ws-1.jpg")
            commit = run_helper("commit", "--jpeg", tmp, dest)
            self.assertNotEqual(commit.returncode, 0)
            self.assertFalse(os.path.exists(tmp))
            self.assertFalse(os.path.exists(dest))

    def test_read_text_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            real = os.path.join(folder, "real")
            Path(real).write_text("secret\n")
            link = os.path.join(folder, "stamp")
            os.symlink(real, link)
            result = run_helper("read-text", link)
            self.assertNotEqual(result.returncode, 0)

    def test_prepare_dir_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            real = os.path.join(folder, "real")
            os.mkdir(real, 0o700)
            link = os.path.join(folder, "cache")
            os.symlink(real, link)
            result = run_helper("prepare-dir", link)
            self.assertNotEqual(result.returncode, 0)

    def test_read_rejects_symlink(self):
        data = jpeg()
        with tempfile.TemporaryDirectory() as folder:
            real = os.path.join(folder, "real.jpg")
            link = os.path.join(folder, "ws-1.jpg")
            Path(real).write_bytes(data)
            os.symlink(real, link)
            read = run_helper("read", link)
            self.assertNotEqual(read.returncode, 0)

    def test_run_fail_closed_on_overflow(self):
        result = run_helper("run", "1000", "8", "--", "python3", "-c", "import sys; sys.stdout.buffer.write(b'0123456789')")
        self.assertEqual(result.returncode, 70)
        self.assertEqual(result.stdout, b"")

    def test_run_fail_closed_on_timeout(self):
        result = run_helper(
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


if __name__ == "__main__":
    unittest.main()
