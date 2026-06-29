#!/usr/bin/env python3
"""mock_metadata.py — simulate AWS IMDSv2 (Instance Metadata Service v2).

A stdlib http.server that implements the two-step IMDSv2 flow:
  1. PUT /latest/api/token  (with X-aws-ec2-metadata-token-ttl-seconds header)
     → returns a session token
  2. GET /latest/meta-data/iam/security-credentials/<role>
     (with X-aws-ec2-metadata-token header = the session token)
     → returns JSON with AccessKeyId, SecretAccessKey, Token, Expiration

This simulates what the EC2 hypervisor provides at 169.254.169.254 — a credential
that exists only because the machine IS the machine, backed by the cloud control plane.
No stored secret: the identity is the instance itself.

NOTE: This mock simulates the hypervisor-backed metadata service. In production, the
real IMDS is provided by the hypervisor and is unreachable from outside the instance.
"""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# The fake IAM role and credentials — obvious dev values
IAM_ROLE = "demo-instance-role"
FAKE_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
FAKE_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# Session tokens: {token_str: expiry_time}
_sessions: dict[str, float] = {}
_lock = threading.Lock()
_rotation_count = 0


def _generate_credentials() -> dict:
    """Generate a fake STS credential set (rotates on each call for demo purposes)."""
    global _rotation_count
    _rotation_count += 1
    expiry = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    return {
        "Code": "Success",
        "LastUpdated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Type": "AWS-HMAC",
        "AccessKeyId": FAKE_ACCESS_KEY,
        "SecretAccessKey": FAKE_SECRET_KEY,
        "Token": f"FwoGZXIvYXdzE-session-token-{_rotation_count:04d}",
        "Expiration": expiry,
    }


class IMDSv2Handler(BaseHTTPRequestHandler):
    """Handler implementing IMDSv2 PUT-then-GET flow."""

    def log_message(self, fmt, *args):
        """Suppress request logging (noisy in demo)."""
        pass

    def do_PUT(self):
        """PUT /latest/api/token — issue a session token."""
        if self.path != "/latest/api/token":
            self.send_error(404)
            return
        ttl_header = self.headers.get("X-aws-ec2-metadata-token-ttl-seconds")
        if not ttl_header:
            self.send_error(400, "Missing X-aws-ec2-metadata-token-ttl-seconds")
            return
        try:
            ttl = int(ttl_header)
        except ValueError:
            self.send_error(400, "Invalid TTL")
            return
        token = secrets.token_hex(32)
        with _lock:
            _sessions[token] = time.time() + ttl
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(token.encode())

    def do_GET(self):
        """GET /latest/meta-data/... — return metadata if session token is valid."""
        token = self.headers.get("X-aws-ec2-metadata-token")
        if not token:
            self.send_error(401, "Missing X-aws-ec2-metadata-token header")
            return
        with _lock:
            expiry = _sessions.get(token)
            if expiry is None or time.time() > expiry:
                self.send_error(401, "Invalid or expired session token")
                return

        # Role listing
        if self.path == "/latest/meta-data/iam/security-credentials/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(IAM_ROLE.encode())
            return

        # Credentials for the role
        if self.path == f"/latest/meta-data/iam/security-credentials/{IAM_ROLE}":
            creds = _generate_credentials()
            body = json.dumps(creds, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)


def run_server(host="127.0.0.1", port=51169, blocking=True):
    """Start the mock metadata server.

    Args:
        host: Bind address (default: loopback only).
        port: Port number (non-standard to avoid collisions).
        blocking: If True, serve_forever. If False, return (server, thread).
    """
    server = HTTPServer((host, port), IMDSv2Handler)
    if blocking:
        print(f"mock-imds: listening on {host}:{port} (Ctrl+C to stop)")
        server.serve_forever()
    else:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server, t


if __name__ == "__main__":
    run_server()
