#!/usr/bin/python3
"""Descriptor-safe preview I/O: keep a verified dir fd, pin PATH, bound subprocesses.

Writes stay under $HOME/.cache/omarchy/workspace-previews. Capture and stamp
keep that directory fd open for exclusive create, validate, rename, and cleanup.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time

MAX_JPEG_BYTES = 2 * 1024 * 1024
MAX_JPEG_DIM = 8192
MAX_TEXT_BYTES = 4096
MAX_MONITOR_BYTES = 65536
OVERFLOW_EXIT = 70
TIMEOUT_EXIT = 124
PINNED_PATH = "/usr/bin:/bin"
PINNED_PREFIXES = ("/usr/bin/", "/bin/")
PREVIEW_REL = (".cache", "omarchy", "workspace-previews")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
WS_SHOT = re.compile(r"^ws-([1-9]|1[0-9]|20)\.jpg$")
HIJACK_VARS = (
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "BASH_ENV",
    "ENV",
)


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _invalid_part(part: str) -> bool:
    return (not part) or part in (".", "..") or "/" in part or part == os.sep


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        if marker == 0x00:
            i += 1
            continue
        seglen = int.from_bytes(data[i + 2 : i + 4], "big")
        if seglen < 2:
            return None
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        i += 2 + seglen
    return None


def validate_jpeg(data: bytes) -> bytes:
    if len(data) > MAX_JPEG_BYTES:
        fail("jpeg exceeds byte ceiling", OVERFLOW_EXIT)
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        fail("not a bounded jpeg")
    dims = jpeg_dimensions(data)
    if dims is None:
        fail("jpeg dimensions missing")
    width, height = dims
    if width <= 0 or height <= 0 or width > MAX_JPEG_DIM or height > MAX_JPEG_DIM:
        fail("jpeg exceeds dimension ceiling")
    return data


def home_root() -> str:
    home = os.environ.get("HOME") or os.path.expanduser("~")
    home = os.path.abspath(home)
    if not home or home == os.sep:
        fail("invalid home")
    return home


def preview_dir() -> str:
    return os.path.join(home_root(), *PREVIEW_REL)


def require_preview_dir(path: str) -> str:
    path = os.path.abspath(path)
    if path != preview_dir():
        fail("path not in preview cache")
    return path


def require_preview_file(path: str) -> tuple[str, str]:
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    name = os.path.basename(path)
    require_preview_dir(directory)
    if _invalid_part(name) or name.startswith(".") or not SAFE_NAME.match(name):
        fail("invalid destination name")
    return directory, name


def _pinned_path(path: str) -> bool:
    path = os.path.abspath(path)
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in PINNED_PREFIXES)


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in HIJACK_VARS:
        env.pop(key, None)
    env["PATH"] = PINNED_PATH
    return env


def resolve_cmd(argv: list[str]) -> list[str]:
    if not argv:
        fail("invalid run bounds")
    name = argv[0]
    if "/" in name:
        if not os.path.isabs(name) or _invalid_part(os.path.basename(name)) or not _pinned_path(name):
            fail("executable not in pinned prefixes")
        candidates = [name]
        explicit = True
    else:
        if _invalid_part(name):
            fail("invalid executable")
        candidates = [f"/usr/bin/{name}", f"/bin/{name}"]
        explicit = False
    for cand in candidates:
        try:
            info = os.lstat(cand)
        except OSError:
            continue
        target = cand
        if stat.S_ISLNK(info.st_mode):
            try:
                target = os.path.realpath(cand)
                info = os.stat(target)
            except OSError:
                continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if not os.access(target, os.X_OK):
            continue
        if not _pinned_path(cand) or not _pinned_path(target):
            if explicit:
                fail("executable not in pinned prefixes")
            continue
        return [target, *argv[1:]]
    fail("executable not found" if not explicit else "executable not in pinned prefixes")


def open_regular_nofollow(name: str, flags: int, dir_fd: int) -> int:
    if _invalid_part(name):
        fail("invalid destination name")
    try:
        return os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
    except OSError:
        fail("refusing symlink or missing path")


def check_owned_regular(fd: int) -> os.stat_result:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        fail("not a regular file")
    if info.st_uid != os.getuid():
        fail("unexpected file owner")
    return info


def open_verified_dir(path: str) -> int:
    """Open $HOME/.cache/omarchy/workspace-previews via openat(NOFOLLOW) from HOME."""
    path = require_preview_dir(path)
    home = home_root()
    try:
        fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        try:
            fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError:
            fail("refusing symlink or missing parent directory")
    try:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            fail("not a directory")
        if info.st_uid != os.getuid():
            fail("unexpected directory owner")
        for part in PREVIEW_REL:
            if not part or part in (".", "..") or "/" in part:
                fail("invalid path component")
            try:
                nxt = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=fd,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                try:
                    nxt = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=fd,
                    )
                except OSError:
                    fail("refusing symlink or missing path")
            except OSError:
                fail("refusing symlink or missing path")
            os.close(fd)
            fd = nxt
            info = os.fstat(fd)
            if not stat.S_ISDIR(info.st_mode):
                fail("not a directory")
            if info.st_uid != os.getuid():
                fail("unexpected directory owner")
            os.fchmod(fd, 0o700)
        return fd
    except BaseException:
        os.close(fd)
        raise


def exclusive_temp(dir_fd: int) -> tuple[int, str]:
    for _ in range(32):
        name = ".pub-" + os.urandom(8).hex()
        try:
            fd = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=dir_fd,
            )
        except FileExistsError:
            continue
        except OSError:
            fail("refusing symlink or missing path")
        return fd, name
    fail("could not create exclusive temp")


def publish_bytes(path: str, data: bytes) -> None:
    dest_dir, dest_name = require_preview_file(path)
    dir_fd = open_verified_dir(dest_dir)
    tmp_name = ""
    fd = -1
    try:
        fd, tmp_name = exclusive_temp(dir_fd)
        check_owned_regular(fd)
        os.fchmod(fd, 0o600)
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(tmp_name, dest_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = ""
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=1)
    except Exception:
        pass


def stream_capped(argv: list[str], timeout_ms: int, max_bytes: int) -> bytes:
    if timeout_ms <= 0 or max_bytes <= 0 or not argv:
        fail("invalid run bounds")
    argv = resolve_cmd(argv)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=child_env(),
        start_new_session=True,
        close_fds=True,
    )
    assert proc.stdout is not None
    raw = proc.stdout.fileno()
    flags = fcntl.fcntl(raw, fcntl.F_GETFL)
    fcntl.fcntl(raw, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    buf = bytearray()
    deadline = time.monotonic() + timeout_ms / 1000
    try:
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                _kill_group(proc)
                fail("subprocess deadline exceeded", TIMEOUT_EXIT)
            ready, _, _ = select.select([raw], [], [], remain)
            if ready:
                try:
                    chunk = os.read(raw, 4096)
                except BlockingIOError:
                    chunk = b""
                if chunk:
                    if len(buf) + len(chunk) > max_bytes:
                        _kill_group(proc)
                        fail("subprocess output exceeds ceiling", OVERFLOW_EXIT)
                    buf.extend(chunk)
                    continue
                break
            if proc.poll() is not None:
                while True:
                    try:
                        chunk = os.read(raw, 4096)
                    except BlockingIOError:
                        break
                    if not chunk:
                        break
                    if len(buf) + len(chunk) > max_bytes:
                        _kill_group(proc)
                        fail("subprocess output exceeds ceiling", OVERFLOW_EXIT)
                    buf.extend(chunk)
                break
        rc = proc.wait(timeout=1)
    except BaseException:
        _kill_group(proc)
        raise
    finally:
        try:
            proc.stdout.close()
        except OSError:
            pass
    if rc != 0:
        raise SystemExit(rc or 1)
    return bytes(buf)


def focused_monitor() -> str:
    raw = stream_capped(["hyprctl", "-j", "monitors"], 1000, MAX_MONITOR_BYTES)
    try:
        monitors = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("invalid monitor list")
    if not isinstance(monitors, list):
        fail("invalid monitor list")
    for mon in monitors:
        if not isinstance(mon, dict) or mon.get("focused") is not True:
            continue
        name = mon.get("name")
        if isinstance(name, str) and name and "/" not in name and name not in (".", ".."):
            return name
    fail("no focused monitor")


def cmd_read(path: str) -> None:
    directory, name = require_preview_file(path)
    dir_fd = open_verified_dir(directory)
    try:
        fd = open_regular_nofollow(name, os.O_RDONLY, dir_fd)
        try:
            info = check_owned_regular(fd)
            if info.st_size > MAX_JPEG_BYTES:
                fail("jpeg exceeds byte ceiling", OVERFLOW_EXIT)
            data = os.read(fd, MAX_JPEG_BYTES + 1)
            if len(data) != info.st_size or len(data) > MAX_JPEG_BYTES:
                fail("jpeg size mismatch", OVERFLOW_EXIT)
            data = validate_jpeg(data)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    sys.stdout.buffer.write(__import__("base64").b64encode(data))
    sys.stdout.buffer.write(b"\n")


def cmd_read_text(path: str) -> None:
    directory, name = require_preview_file(path)
    dir_fd = open_verified_dir(directory)
    try:
        fd = open_regular_nofollow(name, os.O_RDONLY, dir_fd)
        try:
            info = check_owned_regular(fd)
            if info.st_size > MAX_TEXT_BYTES:
                fail("payload exceeds byte ceiling", OVERFLOW_EXIT)
            data = os.read(fd, MAX_TEXT_BYTES + 1)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)
    sys.stdout.buffer.write(data)


def cmd_write(path: str) -> None:
    data = sys.stdin.buffer.read(MAX_JPEG_BYTES + 1)
    data = validate_jpeg(data)
    publish_bytes(path, data)


def cmd_publish(path: str, jpeg: bool) -> None:
    ceiling = MAX_JPEG_BYTES if jpeg else MAX_TEXT_BYTES
    data = sys.stdin.buffer.read(ceiling + 1)
    if len(data) > ceiling:
        fail("payload exceeds byte ceiling", OVERFLOW_EXIT)
    if jpeg:
        data = validate_jpeg(data)
    publish_bytes(path, data)


def cmd_prepare_dir(path: str) -> None:
    fd = open_verified_dir(path)
    os.close(fd)


def cmd_stage(directory: str) -> None:
    dir_fd = open_verified_dir(directory)
    try:
        fd, name = exclusive_temp(dir_fd)
        try:
            check_owned_regular(fd)
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        sys.stdout.write(os.path.join(preview_dir(), name) + "\n")
    finally:
        os.close(dir_fd)


def cmd_commit(tmp: str, dest: str, jpeg: bool) -> None:
    dest_dir, dest_name = require_preview_file(dest)
    tmp = os.path.abspath(tmp)
    tmp_dir = os.path.dirname(tmp)
    tmp_name = os.path.basename(tmp)
    if tmp_dir != dest_dir:
        fail("temp not in destination directory")
    if not tmp_name.startswith(".pub-") or _invalid_part(tmp_name):
        fail("temp name not exclusive")
    dir_fd = open_verified_dir(dest_dir)
    try:
        fd = open_regular_nofollow(tmp_name, os.O_RDONLY, dir_fd)
        try:
            info = check_owned_regular(fd)
            if jpeg:
                if info.st_size > MAX_JPEG_BYTES:
                    fail("jpeg exceeds byte ceiling", OVERFLOW_EXIT)
                data = os.read(fd, MAX_JPEG_BYTES + 1)
                validate_jpeg(data)
            os.fsync(fd)
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
            raise
        os.close(fd)
        os.rename(tmp_name, dest_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def cmd_discard(tmp: str) -> None:
    tmp = os.path.abspath(tmp)
    directory = os.path.dirname(tmp)
    name = os.path.basename(tmp)
    require_preview_dir(directory)
    if not name.startswith(".pub-") or _invalid_part(name):
        fail("temp name not exclusive")
    dir_fd = open_verified_dir(directory)
    try:
        fd = open_regular_nofollow(name, os.O_RDONLY, dir_fd)
        try:
            check_owned_regular(fd)
        finally:
            os.close(fd)
        os.unlink(name, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def cmd_run(timeout_ms: int, max_bytes: int, argv: list[str]) -> None:
    sys.stdout.buffer.write(stream_capped(argv, timeout_ms, max_bytes))


def cmd_capture(workspace_id: str, dest: str) -> None:
    if not workspace_id.isdigit():
        fail("invalid workspace")
    ident = int(workspace_id)
    if ident < 1 or ident > 20:
        fail("invalid workspace")
    expected = os.path.join(preview_dir(), f"ws-{ident}.jpg")
    if os.path.abspath(dest) != expected:
        fail("invalid destination")
    dest_dir, dest_name = require_preview_file(expected)
    if not WS_SHOT.match(dest_name):
        fail("invalid destination name")
    dir_fd = open_verified_dir(dest_dir)
    tmp_name = ""
    fd = -1
    try:
        monitor = focused_monitor()
        fd, tmp_name = exclusive_temp(dir_fd)
        check_owned_regular(fd)
        os.fchmod(fd, 0o600)
        data = stream_capped(
            ["grim", "-t", "jpeg", "-q", "45", "-s", "0.2", "-o", monitor, "-"],
            2000,
            MAX_JPEG_BYTES,
        )
        validate_jpeg(data)
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(tmp_name, dest_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = ""
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def cmd_stamp_wallpaper() -> None:
    home = home_root()
    link = os.path.join(home, ".local", "state", "omarchy", "current", "background")
    stamp = os.path.join(preview_dir(), "wallpaper.path")
    try:
        target = os.path.realpath(link)
    except OSError:
        return
    if not target or not os.path.exists(target):
        return
    payload = (target + "\n").encode()
    if len(payload) > MAX_TEXT_BYTES:
        fail("payload exceeds byte ceiling", OVERFLOW_EXIT)
    dest_dir, dest_name = require_preview_file(stamp)
    dir_fd = open_verified_dir(dest_dir)
    tmp_name = ""
    fd = -1
    try:
        existing = b""
        try:
            existing_fd = os.open(
                dest_name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=dir_fd,
            )
        except OSError:
            existing_fd = -1
        if existing_fd >= 0:
            try:
                existing = os.read(existing_fd, MAX_TEXT_BYTES + 1)
            finally:
                os.close(existing_fd)
        if existing == payload:
            return
        fd, tmp_name = exclusive_temp(dir_fd)
        check_owned_regular(fd)
        os.fchmod(fd, 0o600)
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.rename(tmp_name, dest_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = ""
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        fail(
            "usage: preview-helper.py read|write|run|publish|prepare-dir|stage|"
            "commit|discard|capture|read-text|stamp-wallpaper ..."
        )
    action = argv[1]
    if action == "read":
        if len(argv) != 3:
            fail("usage: preview-helper.py read PATH")
        cmd_read(argv[2])
        return
    if action == "read-text":
        if len(argv) != 3:
            fail("usage: preview-helper.py read-text PATH")
        cmd_read_text(argv[2])
        return
    if action == "write":
        if len(argv) != 3:
            fail("usage: preview-helper.py write PATH")
        cmd_write(argv[2])
        return
    if action == "prepare-dir":
        if len(argv) != 3:
            fail("usage: preview-helper.py prepare-dir DIR")
        cmd_prepare_dir(argv[2])
        return
    if action == "stage":
        if len(argv) != 3:
            fail("usage: preview-helper.py stage DIR")
        cmd_stage(argv[2])
        return
    if action == "commit":
        jpeg = False
        args = argv[2:]
        if args and args[0] == "--jpeg":
            jpeg = True
            args = args[1:]
        if len(args) != 2:
            fail("usage: preview-helper.py commit [--jpeg] TMP DEST")
        cmd_commit(args[0], args[1], jpeg)
        return
    if action == "discard":
        if len(argv) != 3:
            fail("usage: preview-helper.py discard TMP")
        cmd_discard(argv[2])
        return
    if action == "publish":
        jpeg = False
        args = argv[2:]
        if args and args[0] == "--jpeg":
            jpeg = True
            args = args[1:]
        if len(args) != 1:
            fail("usage: preview-helper.py publish [--jpeg] PATH")
        cmd_publish(args[0], jpeg)
        return
    if action == "capture":
        if len(argv) != 4:
            fail("usage: preview-helper.py capture WORKSPACE_ID DEST")
        cmd_capture(argv[2], argv[3])
        return
    if action == "stamp-wallpaper":
        if len(argv) != 2:
            fail("usage: preview-helper.py stamp-wallpaper")
        cmd_stamp_wallpaper()
        return
    if action == "run":
        if len(argv) < 5:
            fail("usage: preview-helper.py run TIMEOUT_MS MAX_BYTES [--] CMD...")
        timeout_ms = int(argv[2])
        max_bytes = int(argv[3])
        cmd = argv[4:]
        if cmd and cmd[0] == "--":
            cmd = cmd[1:]
        cmd_run(timeout_ms, max_bytes, cmd)
        return
    fail("unknown action")


if __name__ == "__main__":
    main(sys.argv)
