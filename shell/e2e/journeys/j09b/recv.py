# Récepteur jetable de l'audit j09b : webhook HTTP (8080) + SMTP clair (2525) + SMTP STARTTLS
# à certificat auto-signé (2526). Journalise dans /tmp/recv/*.jsonl. Lancé par helpers.ts
# dans un conteneur jetable, supprimé en fin de run.
import base64
import json
import os
import socket
import socketserver
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.makedirs("/tmp/recv", exist_ok=True)
LOCK = threading.Lock()


def log(name, obj):
    with LOCK, open(f"/tmp/recv/{name}.jsonl", "a") as f:
        f.write(json.dumps(obj) + "\n")


class Hook(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n).decode("utf8", "replace")
        log("http", {"path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.startswith("/fail"):
            self.send_response(500)
            self.end_headers()
            return
        if self.path.startswith("/redir"):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        if self.path.startswith("/slow"):
            time.sleep(14)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


class Smtp(socketserver.StreamRequestHandler):
    tls_cert = None

    def send(self, line):
        self.wfile.write((line + "\r\n").encode())
        self.wfile.flush()

    def handle(self):
        self.send("220 audit-recv ESMTP")
        state = {"user": None, "pass": None, "from": None, "rcpt": [], "tls": False}
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf8", "replace").rstrip("\r\n")
            cmd = line.upper()
            if cmd.startswith("EHLO") or cmd.startswith("HELO"):
                self.wfile.write(b"250-audit-recv\r\n")
                if self.tls_cert and not state["tls"]:
                    self.wfile.write(b"250-STARTTLS\r\n")
                self.wfile.write(b"250 AUTH PLAIN LOGIN\r\n")
                self.wfile.flush()
            elif cmd.startswith("STARTTLS") and self.tls_cert:
                self.send("220 go ahead")
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                ctx.load_cert_chain(*self.tls_cert)
                self.connection = ctx.wrap_socket(self.connection, server_side=True)
                self.rfile = self.connection.makefile("rb")
                self.wfile = self.connection.makefile("wb")
                state["tls"] = True
            elif cmd.startswith("AUTH PLAIN"):
                parts = line.split(" ", 2)
                cred = base64.b64decode(parts[2]).split(b"\0")
                state["user"], state["pass"] = cred[1].decode(), cred[2].decode()
                if state["pass"] == "wrong":
                    log("smtp_auth_fail", {"user": state["user"], "tls": state["tls"]})
                    self.send("535 5.7.8 Authentication credentials invalid")
                else:
                    self.send("235 2.7.0 ok")
            elif cmd.startswith("AUTH"):
                self.send("535 5.7.8 mechanism not supported")
            elif cmd.startswith("MAIL FROM"):
                state["from"] = line[10:].strip()
                self.send("250 ok")
            elif cmd.startswith("RCPT TO"):
                state["rcpt"].append(line[8:].strip())
                self.send("250 ok")
            elif cmd == "DATA":
                self.send("354 end with .")
                data = []
                while True:
                    l = self.rfile.readline().decode("utf8", "replace")
                    if l.rstrip("\r\n") == ".":
                        break
                    data.append(l)
                log("smtp", {**state, "data": "".join(data)})
                self.send("250 queued")
            elif cmd == "QUIT":
                self.send("221 bye")
                return
            else:
                self.send("250 ok")


class Plain(Smtp):
    pass


class Tls(Smtp):
    tls_cert = ("/tmp/recv/cert.pem", "/tmp/recv/key.pem")


socketserver.ThreadingTCPServer.allow_reuse_address = True
subprocess.run(
    "openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/recv/key.pem -out /tmp/recv/cert.pem "
    "-days 1 -subj /CN=not-the-real-host",
    shell=True,
    check=True,
    capture_output=True,
)
for port, h in ((2525, Plain), (2526, Tls)):
    threading.Thread(
        target=socketserver.ThreadingTCPServer(("0.0.0.0", port), h).serve_forever, daemon=True
    ).start()
ThreadingHTTPServer(("0.0.0.0", 8080), Hook).serve_forever()
