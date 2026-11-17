#!/usr/bin/env python3
"""Kela: authenticated loopback-only Docker bridge. No public ingress."""
import argparse
import collections
import concurrent.futures
import hmac
import http.client
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import struct
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API = "/v1.45"
MAX_BODY = 256 * 1024
IDENTIFIER = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,255}$")
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
JOBS = collections.OrderedDict()
LOCK = threading.Lock()


class DockerError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, timeout=45):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


def docker(method, path, body=None, raw=False):
    connection = UnixConnection()
    try:
        data = None if body is None else json.dumps(body).encode()
        connection.request(method, API + path, body=data, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        content = response.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise DockerError(502, "Docker response exceeded 8 MiB")
        if response.status >= 400:
            try:
                message = json.loads(content).get("message", "Docker request failed")
            except (ValueError, AttributeError):
                message = "Docker request failed"
            raise DockerError(response.status, message)
        return content if raw else (json.loads(content) if content else {})
    finally:
        connection.close()


def identifier(value):
    if not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid identifier")
    return urllib.parse.quote(value, safe="")


def demultiplex(content):
    output, offset = [], 0
    while offset + 8 <= len(content) and content[offset] in (0, 1, 2) and content[offset + 1:offset + 4] == b"\0\0\0":
        length = struct.unpack(">I", content[offset + 4:offset + 8])[0]
        if offset + 8 + length > len(content):
            break
        output.append(content[offset + 8:offset + 8 + length])
        offset += 8 + length
    return (b"".join(output) if offset == len(content) else content).decode("utf-8", errors="replace")


def container_spec(data):
    name = data.get("name", "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", name):
        raise ValueError("Enter a valid container name")
    image = data.get("image", "").strip()
    if not image or len(image) > 255 or any(c.isspace() for c in image):
        raise ValueError("Enter a valid image reference")
    exposed, bindings = {}, {}
    for value in data.get("ports", []):
        match = re.fullmatch(r"(?:(127\.0\.0\.1|0\.0\.0\.0):)?([0-9]{1,5}):([0-9]{1,5})(?:/(tcp|udp))?", value.strip())
        if not match:
            raise ValueError("Port format: [127.0.0.1:]8081:80[/tcp|udp]")
        address, host, target, protocol = match.groups()
        if not (1 <= int(host) <= 65535 and 1 <= int(target) <= 65535):
            raise ValueError("Ports must be between 1 and 65535")
        key = target + "/" + (protocol or "tcp")
        exposed[key] = {}
        bindings.setdefault(key, []).append({"HostIp": address or "0.0.0.0", "HostPort": host})
    restart = data.get("restart", "unless-stopped")
    if restart not in ("no", "always", "unless-stopped", "on-failure"):
        raise ValueError("Invalid restart policy")
    network = data.get("network", "phone-edge")
    identifier(network)
    environment = data.get("environment", [])
    binds = data.get("binds", [])
    if not isinstance(environment, list) or not all(isinstance(e, str) and "=" in e for e in environment):
        raise ValueError("Environment format: KEY=value, one per line")
    if not isinstance(binds, list) or not all(isinstance(b, str) and ":" in b and len(b) < 4096 for b in binds):
        raise ValueError("Mount format: source:/container/path[:ro], one per line")
    body = {"Image": image, "Env": environment, "ExposedPorts": exposed,
            "Labels": {"com.krashkanter.kela.managed": "true"},
            "HostConfig": {"PortBindings": bindings, "Binds": binds,
                           "RestartPolicy": {"Name": restart}, "NetworkMode": network}}
    command = data.get("command", "").strip()
    if command:
        body["Cmd"] = shlex.split(command)
    return name, body


def pull_image(job_id, image):
    connection = UnixConnection(timeout=600)
    try:
        connection.request("POST", API + "/images/create?" + urllib.parse.urlencode({"fromImage": image}))
        response = connection.getresponse()
        if response.status >= 400:
            raise ValueError(json.loads(response.read()).get("message", "Pull failed"))
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            if "error" in event:
                raise ValueError(event["error"])
            message = " ".join(str(event.get(k, "")) for k in ("id", "status", "progress")).strip()
            with LOCK:
                JOBS[job_id]["message"] = message
        with LOCK:
            JOBS[job_id].update(state="done", message="Pulled " + image)
    except Exception as error:
        with LOCK:
            JOBS[job_id].update(state="error", message=str(error))
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "Kela"
    sys_version = ""

    def log_message(self, *args):
        pass  # Never log authorization headers, environment, or container payloads.

    def respond(self, status, value):
        content = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def handle_request(self):
        # Reject browser requests: no CORS, no ambient cookies, no token in URLs.
        if self.headers.get("Origin") or not hmac.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + self.server.token):
            self.respond(401, {"error": "Unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY:
                self.respond(413, {"error": "Request too large"})
                return
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer encoding is unsupported")
            if length and self.headers.get_content_type() != "application/json":
                raise ValueError("Expected application/json")
            data = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            path = urllib.parse.urlsplit(self.path).path
            parts = [urllib.parse.unquote(p) for p in path.strip("/").split("/")]
            method = self.command
            if parts == ["v1", "overview"] and method == "GET":
                info = docker("GET", "/info")
                disk = shutil.disk_usage("/var/lib/docker")
                self.respond(200, {"name": info.get("Name", "Redmi"), "version": info.get("ServerVersion", ""),
                    "containers": info.get("Containers", 0), "running": info.get("ContainersRunning", 0),
                    "images": info.get("Images", 0), "memory": info.get("MemTotal", 0),
                    "cpus": info.get("NCPU", 0), "storageDriver": info.get("Driver", ""),
                    "diskUsed": disk.used, "diskTotal": disk.total, "architecture": info.get("Architecture", "")})
            elif parts == ["v1", "containers"] and method == "GET":
                self.respond(200, docker("GET", "/containers/json?all=true"))
            elif parts == ["v1", "containers"] and method == "POST":
                name, spec = container_spec(data)
                result = docker("POST", "/containers/create?" + urllib.parse.urlencode({"name": name}), spec)
                # Keep created container on start failure so the user can inspect/remove it.
                if data.get("start", True):
                    try:
                        docker("POST", "/containers/" + identifier(result["Id"]) + "/start")
                    except DockerError as error:
                        result["warning"] = "Created, but start failed: " + error.message
                self.respond(201, result)
            elif len(parts) in (3, 4) and parts[:2] == ["v1", "containers"]:
                target = "/containers/" + identifier(parts[2])
                if len(parts) == 3 and method == "DELETE":
                    force = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("force") == ["true"]
                    self.respond(200, docker("DELETE", target + "?force=" + str(force).lower() + "&v=false"))
                elif len(parts) == 3 and method == "GET":
                    self.respond(200, docker("GET", target + "/json"))
                elif len(parts) == 4 and parts[3] == "logs" and method == "GET":
                    self.respond(200, {"text": demultiplex(docker("GET", target + "/logs?stdout=true&stderr=true&tail=300&timestamps=true", raw=True))})
                elif len(parts) == 4 and parts[3] in ("start", "stop", "restart") and method == "POST":
                    self.respond(200, docker("POST", target + "/" + parts[3] + "?t=10"))
                else:
                    self.respond(404, {"error": "Not found"})
            elif parts == ["v1", "images"] and method == "GET":
                self.respond(200, docker("GET", "/images/json"))
            elif parts == ["v1", "images", "pull"] and method == "POST":
                image = data.get("image", "").strip()
                if not image or len(image) > 255 or any(c.isspace() for c in image):
                    raise ValueError("Enter a valid image reference")
                with LOCK:
                    if any(j["state"] == "running" for j in JOBS.values()):
                        raise DockerError(409, "An image pull is already running")
                    while len(JOBS) >= 20:
                        JOBS.popitem(last=False)
                    job = secrets.token_hex(12)
                    JOBS[job] = {"state": "running", "message": "Pulling " + image}
                POOL.submit(pull_image, job, image)
                self.respond(202, {"id": job})
            elif len(parts) == 3 and parts[:2] == ["v1", "jobs"] and method == "GET":
                with LOCK:
                    result = dict(JOBS.get(parts[2], {"state": "error", "message": "Job no longer available"}))
                self.respond(200, result)
            elif len(parts) == 3 and parts[:2] == ["v1", "images"] and method == "DELETE":
                self.respond(200, docker("DELETE", "/images/" + identifier(parts[2])))
            elif parts == ["v1", "networks"] and method == "GET":
                self.respond(200, docker("GET", "/networks"))
            elif parts == ["v1", "volumes"] and method == "GET":
                self.respond(200, docker("GET", "/volumes"))
            elif parts == ["v1", "volumes"] and method == "POST":
                name = data.get("name", "")
                identifier(name)
                self.respond(201, docker("POST", "/volumes/create", {"Name": name}))
            elif len(parts) == 3 and parts[:2] == ["v1", "volumes"] and method == "DELETE":
                self.respond(200, docker("DELETE", "/volumes/" + identifier(parts[2])))
            else:
                self.respond(404, {"error": "Not found"})
        except DockerError as error:
            self.respond(error.status, {"error": error.message})
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            self.respond(400, {"error": str(error)})
        except (OSError, http.client.HTTPException) as error:
            self.respond(502, {"error": "Docker unavailable: " + str(error)})

    do_GET = do_POST = do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9473)
    parser.add_argument("--token-file", default="/etc/kela/token")
    args = parser.parse_args()
    token_path = Path(args.token_file)
    token_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not token_path.exists():
        descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as file:
            file.write(secrets.token_urlsafe(48))
    token = token_path.read_text().strip()
    if len(token) < 32:
        raise SystemExit("Token must contain at least 32 characters")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.token = token
    print("Kela listening on 127.0.0.1:" + str(args.port), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()