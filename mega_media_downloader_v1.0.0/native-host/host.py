import json
import os
import ctypes
import re
import shutil
import struct
import subprocess
import sys
import threading
import uuid
import base64
import codecs
import secrets
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from Crypto.Cipher import AES
from queue import Queue, Empty

HOST_NAME = "com.megamediadownloader.host"
CONFIG_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "MegaMediaDownloader" / "config.json"
JOBS_PATH = Path(os.environ.get("APPDATA", str(Path.home()))) / "MegaMediaDownloader" / "jobs.json"
lock = threading.RLock()
write_lock = threading.Lock()
jobs = []
job_queue = Queue()
active_process = None
choose_process = None
choose_state = None
choose_lock = threading.RLock()
config = {
    "moviesWindows": "",
    "tvWindows": "",
    "moviesNas": "",
    "tvNas": "",
    "megadlPath": "megatools.exe"
}

def send(obj):
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    with write_lock:
        sys.stdout.buffer.write(struct.pack("<I", len(data)))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

def read_message():
    header = sys.stdin.buffer.read(4)
    if not header:
        return None
    if len(header) != 4:
        return None
    size = struct.unpack("<I", header)[0]
    if size > 1024 * 1024:
        return None
    data = sys.stdin.buffer.read(size)
    if len(data) != size:
        return None
    return json.loads(data.decode("utf-8"))

def load_state():
    global config, jobs
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        config.update({k: str(v) for k, v in data.items() if k in config})
    except Exception:
        pass
    # Persisted jobs are informational only; active process state is not resumed automatically.
    try:
        loaded = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
        jobs = [j for j in loaded if j.get("status") in ("completed", "failed", "cancelled")][-50:]
    except Exception:
        jobs = []

def save_state():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    JOBS_PATH.write_text(json.dumps(jobs[-100:], indent=2), encoding="utf-8")

def safe_link(url):
    if not isinstance(url, str) or len(url) > 4096:
        return False
    return re.match(r"^https://(www\.)?mega\.(nz|co\.nz)/(?:file|folder|#|#!|#F!|#f!|#N!|#n!|[A-Za-z0-9])", url, re.I) is not None

def normalize_path(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError("A destination folder is required.")
    value = os.path.expandvars(os.path.expanduser(value.strip()))
    path = Path(value)
    # Only allow normal local paths or UNC paths; reject device namespaces.
    if value.startswith("\\\\?\\") or value.startswith("\\\\.\\"):
        raise ValueError("Device paths are not allowed.")
    if not (path.is_absolute() or value.startswith("\\\\")):
        raise ValueError("Use an absolute Windows path or a UNC share path.")
    return value

def b64url_decode(value):
    value = value.replace("-", "+").replace("_", "/")
    return base64.b64decode(value + "=" * ((4 - len(value) % 4) % 4))

def b64url_encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

def parse_public_folder_link(url):
    """Return (public folder handle, folder key bytes) for modern or legacy folder links."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in ("mega.nz", "www.mega.nz", "mega.co.nz", "www.mega.co.nz"):
        raise ValueError("Enter a public MEGA folder link.")
    match = re.match(r"^/folder/([A-Za-z0-9_-]+)$", parsed.path)
    if match:
        handle = match.group(1)
        key_text = parsed.fragment
    else:
        fragment = urllib.parse.unquote(parsed.fragment or "")
        # Legacy format: #F!HANDLE!KEY
        parts = fragment.split("!")
        if len(parts) >= 3 and parts[0].upper() == "F":
            handle, key_text = parts[1], parts[2]
        else:
            raise ValueError("This link is not a supported public folder link. Use a MEGA folder link, not a file link.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", handle or ""):
        raise ValueError("Could not read the folder ID from this MEGA link.")
    key = b64url_decode(key_text)
    if len(key) != 16:
        raise ValueError("The folder link key is missing or invalid. Copy the complete MEGA link including the part after #.")
    return handle, key

def decrypt_public_node_key(node, folder_handle, folder_key):
    """Decrypt a node key from a public-folder response.

    MEGA responses can include key entries with different share/owner prefixes.
    Prefer the public-folder handle when present, but validate candidate keys by
    decrypting the node attributes instead of assuming the prefix is always the
    folder handle. This prevents valid nodes being rejected solely due to the
    prefix format returned by the API.
    """
    if node.get("h") == folder_handle:
        return folder_key

    encoded = node.get("k", "")
    candidates = []
    for candidate in encoded.split("/"):
        if ":" not in candidate:
            continue
        prefix, encrypted = candidate.split(":", 1)
        try:
            cipher_text = b64url_decode(encrypted)
        except Exception:
            continue
        if len(cipher_text) not in (16, 32):
            continue
        # Try the expected public-folder prefix first, then other API prefixes.
        candidates.append((prefix != folder_handle, cipher_text))

    for _, cipher_text in sorted(candidates, key=lambda item: item[0]):
        try:
            key = AES.new(folder_key, AES.MODE_ECB).decrypt(cipher_text)
            # A wrong AES key can still produce bytes of a plausible length.
            # Validate against the encrypted MEGA attributes before accepting it.
            decrypt_public_node_name(node, key)
            return key
        except Exception:
            continue

    raise ValueError(
        "MEGA returned node keys that could not be decrypted with this folder link key. "
        "Make sure the complete public folder URL, including the key after #, was pasted."
    )

def decrypt_public_node_name(node, node_key):
    encrypted = b64url_decode(node.get("a", ""))
    if not encrypted or len(encrypted) % 16:
        raise ValueError("MEGA returned invalid encrypted file metadata.")
    if node.get("t") == 0 and len(node_key) >= 32:
        attr_key = bytes(a ^ b for a, b in zip(node_key[:16], node_key[16:32]))
    else:
        attr_key = node_key[:16]
    clear = AES.new(attr_key, AES.MODE_CBC, iv=b"\0" * 16).decrypt(encrypted).rstrip(b"\0")
    if not clear.startswith(b"MEGA"):
        raise ValueError("Could not decrypt a filename. Check that the full folder link key was copied.")
    attrs = json.loads(clear[4:].decode("utf-8"))
    name = attrs.get("n")
    if not isinstance(name, str) or not name:
        raise ValueError("MEGA returned a node without a filename.")
    return name

def list_public_folder(url):
    folder_handle, folder_key = parse_public_folder_link(url)
    query_id = str(secrets.randbelow(900000000) + 100000000)
    endpoint = "https://g.api.mega.co.nz/cs?" + urllib.parse.urlencode({"id": query_id, "n": folder_handle})
    body = json.dumps([{"a": "f", "c": 1, "r": 1, "ca": 1}]).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json", "User-Agent": "MEGA-Media-Downloader/1.4"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError("Could not retrieve the MEGA folder listing: " + str(exc)[:180])
    if not isinstance(payload, list) or not payload:
        raise ValueError("MEGA returned an unexpected folder listing response.")
    result = payload[0]
    if isinstance(result, int):
        raise ValueError(f"MEGA API returned error {result} while listing the folder.")
    nodes = result.get("f")
    if not isinstance(nodes, list):
        raise ValueError("MEGA did not return a file list. The link may be private, expired, or incomplete.")

    decoded = {}
    errors = []
    for node in nodes:
        if node.get("t") not in (0, 1) or not node.get("h"):
            continue
        try:
            node_key = decrypt_public_node_key(node, folder_handle, folder_key)
            name = decrypt_public_node_name(node, node_key)
            decoded[node["h"]] = {"handle": node["h"], "parent": node.get("p", ""), "name": name,
                                  "type": "folder" if node.get("t") == 1 else "file",
                                  "size": int(node.get("s", 0) or 0), "key": node_key}
        except Exception as exc:
            errors.append(str(exc))
    if folder_handle not in decoded:
        # Some MEGA responses omit a decryptable root node; create a virtual root.
        decoded[folder_handle] = {"handle": folder_handle, "parent": "", "name": "", "type": "folder", "size": 0, "key": folder_key}

    # Resolve relative paths from parent handles, guarding against malformed cycles.
    def relative_parts(handle, seen=None):
        seen = set() if seen is None else seen
        if handle == folder_handle or handle in seen:
            return []
        seen.add(handle)
        node = decoded.get(handle)
        if not node:
            return []
        parent = node.get("parent")
        return relative_parts(parent, seen) + [node["name"]]

    items = []
    for handle, node in decoded.items():
        if handle == folder_handle:
            continue
        parts = relative_parts(handle)
        if not parts:
            continue
        relative_path = "/".join(parts)
        item = {"id": handle, "name": node["name"], "type": node["type"], "size": node["size"], "relativePath": relative_path}
        if node["type"] == "file":
            if len(node["key"]) != 32:
                continue
            item["url"] = f"https://mega.nz/#!{handle}!{b64url_encode(node['key'])}"
        items.append(item)
    items.sort(key=lambda item: (item["relativePath"].casefold(), item["type"] != "folder"))
    if not items and errors:
        raise ValueError(errors[0][:220])
    return items

def enqueue_job(url, path, category, target, label, relative_path=None):
    job = {
        "id": uuid.uuid4().hex[:12], "url": url, "path": path,
        "category": category, "target": target, "status": "queued",
        "progress": 0, "detail": "Waiting in queue", "label": label
    }
    if relative_path:
        job["relativePath"] = relative_path
    jobs.append(job)
    job_queue.put(job)
    return job

def send_job(job):
    send({"type": "job", "job": dict(job)})

def suspend_process(pid):
    """Suspend a Windows process using the native NT process API."""
    if os.name != "nt":
        raise OSError("Pause/resume is supported only on Windows.")
    PROCESS_SUSPEND_RESUME = 0x0800
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtSuspendProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtSuspendProcess.restype = ctypes.c_long
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        status = ntdll.NtSuspendProcess(handle)
        if status != 0:
            raise OSError(f"Windows could not pause the download (NTSTATUS 0x{status & 0xffffffff:08X}).")
    finally:
        kernel32.CloseHandle(handle)

def resume_process(pid):
    """Resume a Windows process suspended by suspend_process."""
    if os.name != "nt":
        raise OSError("Pause/resume is supported only on Windows.")
    PROCESS_SUSPEND_RESUME = 0x0800
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        status = ntdll.NtResumeProcess(handle)
        if status != 0:
            raise OSError(f"Windows could not resume the download (NTSTATUS 0x{status & 0xffffffff:08X}).")
    finally:
        kernel32.CloseHandle(handle)

def worker():
    global active_process
    while True:
        item = job_queue.get()
        if item is None:
            break
        with lock:
            job = next((j for j in jobs if j["id"] == item["id"]), None)
            if not job or job.get("status") == "cancelled":
                job_queue.task_done()
                continue
            job["status"] = "downloading"
            job["detail"] = "Starting megatools…"
            send_job(job)
        try:
            destination = normalize_path(job["path"])
            os.makedirs(destination, exist_ok=True)
            exe = config.get("megadlPath") or "megatools.exe"
            exe = os.path.expandvars(os.path.expanduser(exe))
            if not os.path.isabs(exe):
                found = shutil.which(exe)
                if not found:
                    raise FileNotFoundError("megatools executable not found. Install megatools or set its full path in Settings.")
                exe = found
            # megatools 1.11.x uses: megatools dl --path DESTINATION URL.
            # Retain compatibility with standalone megadl builds as well.
            if Path(exe).name.lower() in ("megatools.exe", "megatools"):
                command = [exe, "dl", "--path", destination, job["url"]]
            else:
                command = [exe, "--path", destination, job["url"]]
            # No shell: the URL and path are passed as individual arguments.
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            with lock:
                active_process = proc
                job["pid"] = proc.pid
            output_tail = []
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                output_tail.append(line[-300:])
                if len(output_tail) > 8:
                    output_tail.pop(0)
                percent = re.search(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%", line)
                with lock:
                    if job.get("status") == "cancelled":
                        try: proc.terminate()
                        except Exception: pass
                    elif percent:
                        job["progress"] = min(99, max(0, int(float(percent.group(1)))))
                    job["detail"] = line[-240:]
                    send_job(job)
            code = proc.wait()
            with lock:
                if job.get("status") == "cancelled":
                    job["detail"] = "Cancelled. Partial files may remain."
                elif code == 0:
                    job["status"] = "completed"; job["progress"] = 100; job["detail"] = "Download complete"
                else:
                    job["status"] = "failed"
                    diagnostic = " | ".join(output_tail[-3:])
                    job["detail"] = (f"Download command exited with code {code}: {diagnostic}" if diagnostic else f"Download command exited with code {code}")[:240]
                job.pop("pid", None)
                active_process = None
                save_state()
                send_job(job)
        except Exception as e:
            with lock:
                job["status"] = "failed"
                job["detail"] = str(e)[:240]
                active_process = None
                save_state()
                send_job(job)
        finally:
            job_queue.task_done()

ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CHOOSE_PROMPT = "Enter numbers of files or folders to download"


def parse_megatools_choose_tree(output):
    """Parse the numbered tree printed by megatools --choose-files."""
    output = ANSI_ESCAPE_RE.sub("", output)
    items = []
    stack = []
    size_re = re.compile(r"\s+\((\d+(?:\.\d+)?\s*(?:B|KiB|MiB|GiB|TiB|KB|MB|GB|TB))\)\s*$", re.I)
    line_re = re.compile(r"^\s*(?P<prefix>(?:(?:\|--|\|  ))*)\s*(?P<number>\d+)\.\s+(?P<label>.*?)\s*$")
    for line in output.splitlines():
        match = line_re.match(line)
        if not match:
            continue
        number = int(match.group("number"))
        prefix = match.group("prefix") or ""
        depth = prefix.count("|")
        label = match.group("label").strip()
        size_label = ""
        size_match = size_re.search(label)
        if size_match:
            size_label = size_match.group(1).strip()
            label = label[:size_match.start()].rstrip()
        is_folder = label.endswith("/")
        name = label[:-1] if is_folder else label
        while stack and stack[-1]["depth"] >= depth:
            stack.pop()
        parent_path = stack[-1]["path"] if stack else ""
        relative_path = f"{parent_path}/{name}" if parent_path else name
        item = {
            "number": number,
            "id": str(number),
            "name": name,
            "type": "folder" if is_folder else "file",
            "sizeLabel": size_label,
            "relativePath": relative_path,
            "depth": depth,
        }
        items.append(item)
        if is_folder:
            stack.append({"depth": depth, "path": relative_path})
    return items


def resolve_megatools_executable():
    exe = config.get("megadlPath") or "megatools.exe"
    exe = os.path.expandvars(os.path.expanduser(exe))
    if not os.path.isabs(exe):
        found = shutil.which(exe)
        if not found:
            raise FileNotFoundError("megatools executable not found. Set its full path in Settings.")
        exe = found
    if Path(exe).name.lower() not in ("megatools.exe", "megatools"):
        raise ValueError("The interactive folder picker requires megatools.exe, not a standalone megadl executable. Set megatools.exe in Settings.")
    return exe


def update_choose_job(detail=None, status=None, progress=None):
    global choose_state
    with choose_lock:
        state = choose_state
        if not state:
            return
        job = state.get("job")
        if not job:
            return
        if detail is not None:
            job["detail"] = str(detail)[-240:]
        if status is not None:
            job["status"] = status
        if progress is not None:
            job["progress"] = progress
        with lock:
            save_state()
            send_job(job)


def read_choose_process(proc, state):
    """Read megatools output continuously so its interactive prompt stays live."""
    output = ""
    line_buffer = ""
    prompt_sent = False
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        while True:
            chunk = proc.stdout.read(1)
            if not chunk:
                break
            char = decoder.decode(chunk, final=False)
            if not char:
                continue
            output += char
            line_buffer += char

            if not prompt_sent:
                cleaned = ANSI_ESCAPE_RE.sub("", output)
                prompt_at = cleaned.lower().find(CHOOSE_PROMPT.lower())
                if prompt_at >= 0:
                    tree_text = cleaned[:prompt_at]
                    items = parse_megatools_choose_tree(tree_text)
                    state["items"] = items
                    state["awaiting_selection"] = True
                    prompt_sent = True
                    send({"type": "chooseFilesTree", "items": items, "prompt": CHOOSE_PROMPT})
                    update_choose_job("Waiting for your file selection", "selecting")

            if char in ("\n", "\r"):
                line = ANSI_ESCAPE_RE.sub("", line_buffer).strip()
                line_buffer = ""
                if line:
                    # Avoid replacing the useful selection prompt with the tree itself.
                    if prompt_sent and CHOOSE_PROMPT.lower() not in line.lower():
                        update_choose_job(line, "downloading" if state.get("selection_sent") else "selecting")
                        send({"type": "chooseFilesOutput", "line": line})

        tail_char = decoder.decode(b"", final=True)
        if tail_char:
            output += tail_char
            line_buffer += tail_char
        code = proc.wait()
        with choose_lock:
            job = state.get("job")
            if job:
                if state.get("cancelled"):
                    job["status"] = "cancelled"
                    job["detail"] = "Folder download cancelled"
                elif code == 0:
                    job["status"] = "completed"
                    job["progress"] = 100
                    job["detail"] = "Download complete"
                else:
                    job["status"] = "failed"
                    tail = ANSI_ESCAPE_RE.sub("", output).splitlines()[-3:]
                    diagnostic = " | ".join(line.strip() for line in tail if line.strip())
                    job["detail"] = (diagnostic or f"megatools exited with code {code}")[-240:]
                with lock:
                    save_state()
                    send_job(job)
        send({"type": "chooseFilesDone", "exitCode": code, "cancelled": bool(state.get("cancelled"))})
    except Exception as exc:
        send({"type": "error", "message": "Could not read megatools file picker: " + str(exc)[:220]})
    finally:
        global choose_process, choose_state
        with choose_lock:
            if choose_process is proc:
                choose_process = None
            if choose_state is state:
                choose_state = None
        try:
            if proc.poll() is None:
                proc.terminate()
        except Exception:
            pass


def start_choose_files(msg):
    global choose_process, choose_state
    url = msg.get("url")
    if not safe_link(url):
        raise ValueError("Only supported public MEGA HTTPS folder links are accepted.")
    parse_public_folder_link(url)  # Validate that this is a supported folder link.
    path = normalize_path(msg.get("path"))
    category = msg.get("category", "custom")
    target = msg.get("target", "windows")
    if category not in ("movies", "tv", "custom") or target not in ("windows", "nas"):
        raise ValueError("Invalid category or destination type.")
    os.makedirs(path, exist_ok=True)
    with choose_lock:
        if choose_process is not None and choose_process.poll() is None:
            raise ValueError("A megatools folder picker is already running. Finish or cancel it first.")
        exe = resolve_megatools_executable()
        command = [exe, "dl", "--choose-files", "--path", path, url]
        proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        job = {
            "id": uuid.uuid4().hex[:12], "url": url, "path": path,
            "category": category, "target": target, "status": "selecting", "kind": "chooseFiles",
            "progress": 0, "detail": "Opening megatools file picker…",
            "label": "MEGA folder selection"
        }
        with lock:
            jobs.append(job)
            save_state()
            send_job(job)
            send({"type": "jobs", "jobs": [dict(j) for j in jobs]})
        state = {"job": job, "items": [], "awaiting_selection": False, "selection_sent": False, "cancelled": False}
        choose_process = proc
        choose_state = state
        send({"type": "chooseFilesLoading", "message": "Waiting for megatools to list the folder…"})
        threading.Thread(target=read_choose_process, args=(proc, state), daemon=True).start()


def submit_choose_selection(msg):
    with choose_lock:
        proc = choose_process
        state = choose_state
        if not proc or proc.poll() is not None or not state:
            raise ValueError("The megatools picker is no longer running. Browse the folder again.")
        if not state.get("awaiting_selection"):
            raise ValueError("The megatools file list is not ready yet.")
        if state.get("selection_sent"):
            raise ValueError("A selection has already been submitted for this picker.")
        numbers = msg.get("numbers")
        if not isinstance(numbers, list) or not numbers:
            raise ValueError("Select at least one file or folder.")
        allowed = {int(item["number"]) for item in state.get("items", [])}
        try:
            numbers = sorted(set(int(number) for number in numbers))
        except (TypeError, ValueError):
            raise ValueError("The selection contains an invalid item number.")
        if not numbers or any(number not in allowed for number in numbers):
            raise ValueError("The selection contains an item number that megatools did not list.")
        selection = " ".join(str(number) for number in numbers)
        proc.stdin.write((selection + "\n").encode("utf-8"))
        proc.stdin.flush()
        state["selection_sent"] = True
        update_choose_job("Selection sent to megatools; download starting…", "downloading")
        send({"type": "chooseFilesSelectionSent", "numbers": numbers})


def cancel_choose_files():
    global choose_process, choose_state
    with choose_lock:
        proc = choose_process
        state = choose_state
        if not proc or proc.poll() is not None:
            raise ValueError("There is no active megatools folder picker.")
        if state:
            state["cancelled"] = True
        try:
            proc.terminate()
        except Exception as exc:
            raise ValueError("Could not stop megatools: " + str(exc)[:180])



def handle(msg):
    global config, active_process
    action = msg.get("action")
    if action in ("hello", "ping"):
        send({"type": "hello" if action == "hello" else "pong", "version": "1.4.0"})
    elif action == "list":
        with lock:
            send({"type": "jobs", "jobs": [dict(j) for j in jobs]})
    elif action == "clearHistory":
        with lock:
            # Keep queued, downloading, paused, and selecting jobs.
            active_statuses = ("queued", "downloading", "paused", "selecting")
            jobs[:] = [
                job for job in jobs
                if job.get("status") in active_statuses
            ]
            save_state()
            send({"type": "jobs", "jobs": [dict(j) for j in jobs]})
    elif action == "getConfig":
        with lock:
            send({"type": "config", "config": dict(config)})

    elif action == "setConfig":
        incoming = msg.get("config", {})
        if not isinstance(incoming, dict):
            raise ValueError("Invalid config.")
        with lock:
            for key in config:
                if key in incoming and isinstance(incoming[key], str):
                    config[key] = incoming[key][:1024]
            save_state()
            send({"type": "config", "config": dict(config)})
    elif action == "chooseFiles":
        start_choose_files(msg)
    elif action == "chooseFilesSelect":
        submit_choose_selection(msg)
    elif action == "cancelChooseFiles":
        cancel_choose_files()
    elif action == "listFolder":
        url = msg.get("url")
        if not safe_link(url):
            raise ValueError("Only supported public MEGA HTTPS links are accepted.")
        send({"type": "folderLoading"})
        items = list_public_folder(url)
        send({"type": "folderFiles", "items": items, "fileCount": sum(1 for item in items if item["type"] == "file")})
    elif action == "enqueueSelected":
        path = normalize_path(msg.get("path"))
        category = msg.get("category", "custom")
        target = msg.get("target", "windows")
        selected = msg.get("items")
        if category not in ("movies", "tv", "custom") or target not in ("windows", "nas"):
            raise ValueError("Invalid category or destination type.")
        if not isinstance(selected, list) or not selected or len(selected) > 500:
            raise ValueError("Select at least one file (up to 500 files per batch).")
        added = []
        root = Path(path)
        # Validate the full batch before queueing anything, so one bad item can't
        # leave the user with a partially queued selection.
        validated = []
        for item in selected:
            if not isinstance(item, dict) or not safe_link(item.get("url")):
                raise ValueError("One of the selected files has an invalid MEGA link.")
            rel = item.get("relativePath")
            if not isinstance(rel, str) or not rel or len(rel) > 1024 or "\\" in rel:
                raise ValueError("A selected file has an invalid relative path.")
            rel_path = PurePosixPath(rel)
            if rel_path.is_absolute() or any(part in ("", ".", "..") for part in rel_path.parts):
                raise ValueError("A selected file path is unsafe.")
            destination = str(root.joinpath(*rel_path.parts[:-1])) if len(rel_path.parts) > 1 else path
            destination = normalize_path(destination)
            validated.append((item["url"], destination, rel_path.name, rel))
        with lock:
            for file_url, destination, label, rel in validated:
                job = enqueue_job(file_url, destination, category, target, label, rel)
                added.append(job)
            save_state()
            for job in added: send_job(job)
            send({"type": "jobs", "jobs": [dict(j) for j in jobs]})
    elif action == "enqueue":
        url = msg.get("url")
        if not safe_link(url):
            raise ValueError("Only supported public MEGA HTTPS links are accepted.")
        path = normalize_path(msg.get("path"))
        category = msg.get("category", "custom")
        target = msg.get("target", "windows")
        if category not in ("movies", "tv", "custom") or target not in ("windows", "nas"):
            raise ValueError("Invalid category or destination type.")
        with lock:
            job = enqueue_job(url, path, category, target, "MEGA download")
            save_state(); send_job(job)
            send({"type": "jobs", "jobs": [dict(j) for j in jobs]})
    elif action in ("pause", "resume"):
        jid = msg.get("id")
        with lock:
            job = next((j for j in jobs if j["id"] == jid), None)
            if not job:
                raise ValueError("Job not found.")
            if action == "pause":
                if job.get("status") != "downloading":
                    raise ValueError("Only an active download can be paused.")
                if not active_process or job.get("pid") != active_process.pid:
                    raise ValueError("The download process is not available to pause.")
                suspend_process(active_process.pid)
                job["status"] = "paused"
                job["detail"] = "Download paused"
            else:
                if job.get("status") != "paused":
                    raise ValueError("This download is not paused.")
                if not active_process or job.get("pid") != active_process.pid:
                    raise ValueError("The paused download process is no longer available.")
                resume_process(active_process.pid)
                job["status"] = "downloading"
                job["detail"] = "Download resumed"
            save_state()
            send_job(job)
    elif action == "cancel":
        jid = msg.get("id")
        with lock:
            job = next((j for j in jobs if j["id"] == jid), None)
            if not job: raise ValueError("Job not found.")
            if job["status"] == "queued":
                job["status"] = "cancelled"; job["detail"] = "Cancelled before starting"
            elif job["status"] == "downloading" and active_process:
                job["status"] = "cancelled"; job["detail"] = "Stopping download…"
                try: active_process.terminate()
                except Exception: pass
            save_state(); send_job(job)
    else:
        raise ValueError("Unknown action.")

def main():
    load_state()
    threading.Thread(target=worker, daemon=True).start()
    send({"type": "hello", "version": "1.4.0"})
    while True:
        try:
            msg = read_message()
            if msg is None: break
            try: handle(msg)
            except Exception as e: send({"type": "error", "message": str(e)[:300]})
        except Exception as e:
            send({"type": "error", "message": "Invalid native message: " + str(e)[:200]})

if __name__ == "__main__":
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    main()
