"""Local MinerU launcher: browser-owned lifetime, no conversion parameter changes."""
import argparse
import asyncio
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
from datetime import datetime
import functools
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import uuid
import webbrowser

PORT = 7860
URL = f"http://127.0.0.1:{PORT}/"
GRACE = 30
START_TIMEOUT = 180


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def request_status(state, method="GET", endpoint="status"):
    request = urllib.request.Request(
        URL + "__lifecycle/" + endpoint, method=method,
        headers={"X-Mineru-Lifecycle": state.get("token", "")})
    with urllib.request.urlopen(request, timeout=2) as response:
        value = json.load(response)
    if value.get("instance") != state.get("instance"):
        raise RuntimeError("The port belongs to a different service.")
    return value


class BrowserLifetime:
    """Native WebSocket connectivity, independent of background JS timer throttling."""
    def __init__(self, now=time.monotonic):
        self.now = now
        self.lock = threading.RLock()
        self.clients = set()
        self.ever_connected = False
        self.empty_since = now()
        self.closing = False

    def connect(self, client):
        with self.lock:
            if self.closing:
                return False
            self.clients.add(client)
            self.ever_connected = True
            return True

    def disconnect(self, client):
        with self.lock:
            self.clients.discard(client)
            if not self.clients:
                self.empty_since = self.now()

    def should_close(self):
        with self.lock:
            timeout = GRACE if self.ever_connected else START_TIMEOUT
            expired = not self.clients and self.now() - self.empty_since >= timeout
            if expired:
                self.closing = True
            return expired


def script(token):
    return """<script>
(() => {
  if (window.__mineruLifetime) return;
  window.__mineruLifetime = true;
  let socket, leaving = false;
  function connect() {
    if (leaving || (socket && socket.readyState < 2)) return;
    socket = new WebSocket('ws://' + location.host + '/__lifecycle/ws?token=' + TOKEN);
    socket.onclose = () => { if (!leaving) setTimeout(connect, 1000); };
  }
  window.addEventListener('pagehide', () => { leaving = true; if(socket) socket.close(); });
  window.addEventListener('pageshow', () => { leaving = false; connect(); });
  connect();
})();
</script>""".replace("TOKEN", json.dumps(token))


def interrupt_runs(runtime, instance, reason):
    for path in (runtime / "runs").glob("*.json"):
        value = read(path)
        if value.get("instance") == instance and value.get("status") == "running":
            value.update(status="interrupted", reason=reason,
                         ended_at=datetime.now().astimezone().isoformat())
            save(path, value)


@contextmanager
def windows_job():
    """Own only the worker and descendants; closing the handle kills this job only."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    class Basic(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                    ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]
    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", Counters), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                    ("peak_job", ctypes.c_size_t)]
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        def assign(process):
            if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
        yield assign
    finally:
        kernel.CloseHandle(job)


@contextmanager
def instance_mutex(root):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = "Local\\MineruWeb_" + hashlib.sha256(str(root).lower().encode()).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(error)
    try:
        yield error != 183  # ERROR_ALREADY_EXISTS
    finally:
        kernel.CloseHandle(handle)


def run_worker(root, runtime, instance, token):
    # Parent assigns the Windows job before allowing any imports or children.
    if sys.stdin.readline().strip() != "go":
        return
    os.chdir(root)
    sys.path.insert(0, str(root))
    from fastapi import Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    import gradio as gr
    from mineru.cli import gradio_app as app_module

    lifetime = BrowserLifetime()
    stop = threading.Event()
    sessions_lock = threading.RLock()
    original_conversion = app_module.to_markdown

    @functools.wraps(original_conversion)
    async def tracked_conversion(*args, **kwargs):
        path = runtime / "runs" / f"{instance}_{uuid.uuid4().hex}.json"
        value = {"instance": instance, "status": "running",
                 "source_name": Path(str(args[0] if args else kwargs.get("file_path", ""))).name,
                 "started_at": datetime.now().astimezone().isoformat()}
        with sessions_lock:
            save(path, value)
        try:
            result = await original_conversion(*args, **kwargs)
            with sessions_lock:
                if not stop.is_set():
                    value.update(status="completed_needs_review", outputs=[str(x) for x in result[2:]],
                                 ended_at=datetime.now().astimezone().isoformat())
                    save(path, value)
            return result
        except BaseException as error:
            with sessions_lock:
                if not stop.is_set():
                    value.update(status="interrupted" if isinstance(error, asyncio.CancelledError) else "failed",
                                 error=f"{type(error).__name__}: {error}",
                                 ended_at=datetime.now().astimezone().isoformat())
                    save(path, value)
            raise
    app_module.to_markdown = tracked_conversion
    original_launch = gr.Blocks.launch

    def managed_launch(demo, *args, **kwargs):
        demo.head = (demo.head or "") + script(token)
        kwargs.update(prevent_thread_lock=True, inbrowser=False, share=False)
        result = original_launch(demo, *args, **kwargs)
        app = result[0]

        async def status(request: Request):
            if request.headers.get("X-Mineru-Lifecycle") != token:
                return JSONResponse({"error": "forbidden"}, status_code=403)
            with lifetime.lock:
                return {"instance": instance, "pid": os.getpid(),
                        "clients": len(lifetime.clients), "closing": lifetime.closing}

        async def shutdown(request: Request):
            if request.headers.get("X-Mineru-Lifecycle") != token:
                return JSONResponse({"error": "forbidden"}, status_code=403)
            stop.set()
            return {"instance": instance, "stopping": True}

        async def connection(websocket: WebSocket):
            if (websocket.query_params.get("token") != token or
                    websocket.headers.get("origin") != URL.rstrip("/")):
                await websocket.close(code=1008)
                return
            client = uuid.uuid4().hex
            if not lifetime.connect(client):
                await websocket.close(code=1012)
                return
            try:
                await websocket.accept()
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                lifetime.disconnect(client)

        app.add_api_route("/__lifecycle/status", status, methods=["GET"])
        app.add_api_route("/__lifecycle/stop", shutdown, methods=["POST"])
        app.add_api_websocket_route("/__lifecycle/ws", connection)
        while not stop.wait(0.25):
            if lifetime.should_close():
                break
        stop.set()
        with sessions_lock:
            interrupt_runs(runtime, instance, "Browser disconnected for 30 seconds, startup timed out, or explicit stop")
        # Native conversion threads may not support cancellation: allow close briefly,
        # then exit; the supervisor job also cleans up only our descendants.
        closer = threading.Thread(target=demo.close, daemon=True)
        closer.start()
        closer.join(timeout=3)
        os._exit(0)

    gr.Blocks.launch = managed_launch
    app_module.main(args=["--server-name", "127.0.0.1", "--server-port", str(PORT)],
                    standalone_mode=False)


def supervise(root, no_browser=False, stop_only=False):
    runtime = root / ".web_runtime"
    runtime.mkdir(exist_ok=True)
    state_path = runtime / "state.json"
    if stop_only:
        state = read(state_path)
        request_status(state, "POST", "stop")
        return
    with instance_mutex(root) as owner:
        if not owner:
            deadline = time.monotonic() + START_TIMEOUT
            while time.monotonic() < deadline:
                state = read(state_path)
                try:
                    status = request_status(state)
                    if not status["closing"]:
                        if not no_browser:
                            webbrowser.open(URL)
                        return
                except Exception:
                    time.sleep(0.5)
            raise RuntimeError("Existing launcher is still starting or stopping; inspect .web_runtime/logs.")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", PORT))  # Never kill an unrelated port owner.
        abandoned_instances = {value.get("instance") for path in (runtime / "runs").glob("*.json")
                               if (value := read(path)).get("status") == "running"}
        for abandoned in abandoned_instances:
            interrupt_runs(runtime, abandoned, "Recovered unfinished conversion after previous service exited")
        instance = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        state = {"instance": instance, "token": token, "status": "starting", "url": URL,
                 "supervisor_pid": os.getpid()}
        save(state_path, state)
        logs = runtime / "logs"
        logs.mkdir(exist_ok=True)
        log_path = logs / (datetime.now().strftime("%Y%m%d_%H%M%S_") + instance[:8] + ".log")
        worker = None
        try:
            with log_path.open("a", encoding="utf-8") as log, windows_job() as assign:
                python = root / ".venv" / "Scripts" / "python.exe"
                env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1", MINERU_WEB_TOKEN=token)
                worker = subprocess.Popen(
                    [str(python), "-B", str(Path(__file__).resolve()), "--worker", "--root", str(root),
                     "--instance", instance], cwd=root, env=env, stdin=subprocess.PIPE,
                    stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    assign(worker)
                except BaseException:
                    worker.terminate()  # Still gated: cannot have spawned children.
                    worker.wait(timeout=5)
                    raise
                worker.stdin.write(b"go\n")
                worker.stdin.flush()
                worker.stdin.close()
                state.update(worker_pid=worker.pid, log=str(log_path))
                save(state_path, state)
                deadline = time.monotonic() + START_TIMEOUT
                while time.monotonic() < deadline:
                    if worker.poll() is not None:
                        raise RuntimeError(f"MinerU exited before startup; see {log_path}")
                    try:
                        request_status(state)
                        break
                    except Exception:
                        time.sleep(0.5)
                else:
                    raise TimeoutError(f"MinerU did not become ready; see {log_path}")
                state["status"] = "ready"
                save(state_path, state)
                if not no_browser and not webbrowser.open(URL):
                    raise RuntimeError("Browser could not be opened. Start again or open " + URL)
                worker.wait()
        finally:
            # Job handle has closed: descendants are stopped before finalizing records.
            if worker is not None:
                worker.wait(timeout=10)
            interrupt_runs(runtime, instance, "MinerU service stopped before this conversion completed")
            state.update(status="stopped", ended_at=datetime.now().astimezone().isoformat())
            save(state_path, state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--instance")
    parser.add_argument("--no-browser", action="store_true", help="Readiness/lifecycle testing only")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.worker:
            run_worker(root, root / ".web_runtime", args.instance, os.environ["MINERU_WEB_TOKEN"])
        else:
            supervise(root, args.no_browser, args.stop)
    except Exception:
        details = traceback.format_exc()
        runtime = root / ".web_runtime"
        runtime.mkdir(exist_ok=True)
        (runtime / "last_error.txt").write_text(details, encoding="utf-8")
        if not args.worker:
            ctypes.windll.user32.MessageBoxW(None, "MinerU could not start or stop.\n" +
                                            str(runtime / "last_error.txt"), "MinerU", 0x10)
        raise


if __name__ == "__main__":
    main()
