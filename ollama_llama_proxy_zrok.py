# ollama_llama_proxy.py
#
# PURPOSE: VS Code Copilot (as of May 2026) only supports Ollama as a local model
# provider. This proxy pretends to BE Ollama on port 11434 so VS Code Copilot can
# connect to it, while secretly forwarding every request to your real llama.cpp
# server running on localhost:8080.
#
# A zrok v2 public share is started automatically, exposing this proxy at a
# public HTTPS URL that you can use from any remote machine in VS Code.
#
# Flow:
#   VS Code (remote) --> zrok public URL --> this proxy (port 11434, speaks Ollama API)
#                                                      |
#                                                      v
#                                             llama.cpp server (port 8080, OpenAI API)
#
# Pre-requisites:
#   1. zrok2 installed and environment enabled:  zrok2 enable <token>
#   2. llama.cpp running:  llama-server --port 8080 -m your-model.gguf
#
# Usage:
#   python ollama_llama_proxy_zrok.py
#
# In VS Code (on any machine):
#   Settings -> "GitHub Copilot: Local Provider" -> Ollama
#   Set the Ollama URL to the zrok HTTPS URL printed at startup.
#   Model: huihui-qwen3:latest

import atexit
import json
import re
import signal
import subprocess
import sys
import threading
import http.server
import urllib.request
import urllib.error
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LLAMA_HOST  = "localhost"             # llama.cpp server host
LLAMA_PORT  = 8080                    # llama.cpp server port
PROXY_PORT  = 11434                   # must match Ollama's default
MODEL_NAME  = "huihui-qwen3:latest"   # Ollama requires 'name:tag' format
ZROK_CMD    = "zrok2"                 # zrok v2 binary name

# ---------------------------------------------------------------------------
# zrok lifecycle
# ---------------------------------------------------------------------------
_zrok_proc: "subprocess.Popen | None" = None


def start_zrok_share() -> "str | None":
    """
    Launch `zrok2 share public <PROXY_PORT>` and return the public URL.

    zrok2 TUI output looks like (with box-drawing chars, no https:// prefix):
        │die26fizlp03.shares.zrok.io││[PUBLIC] [PROXY]│

    We match the bare hostname and prepend https:// ourselves.
    We read both stdout and stderr so we catch it regardless of which pipe
    zrok2 writes to.  On Windows, CREATE_NO_WINDOW prevents console-handle errors.
    """
    global _zrok_proc

    cmd = [ZROK_CMD, "share", "public", str(PROXY_PORT)]
    print(f"[zrok]  Starting: {' '.join(cmd)}")

    kwargs: dict = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        _zrok_proc = subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError:
        print(f"[zrok]  ERROR: '{ZROK_CMD}' not found.")
        print( "[zrok]         Is zrok2 installed and on your PATH?")
        return None

    public_url: "str | None" = None
    url_event = threading.Event()

    # zrok2 TUI prints just the hostname (no protocol), surrounded by box chars:
    #   │die26fizlp03.shares.zrok.io│
    # Match the token + domain; we'll add https:// ourselves.
    hostname_pattern = re.compile(
        r'([a-z0-9]+\.shares?\.(?:zrok\.io|myzrok\.io))', re.IGNORECASE
    )

    def _pipe_reader(pipe, label):
        nonlocal public_url
        for line in pipe:
            stripped = line.rstrip()
            if stripped:
                print(f"[zrok/{label}]  {stripped}")
            if not url_event.is_set():
                m = hostname_pattern.search(stripped)
                if m:
                    public_url = "https://" + m.group(1)
                    url_event.set()
        url_event.set()  # unblock wait() if pipe closes before URL appears

    t_out = threading.Thread(target=_pipe_reader, args=(_zrok_proc.stdout, "out"), daemon=True)
    t_err = threading.Thread(target=_pipe_reader, args=(_zrok_proc.stderr, "err"), daemon=True)
    t_out.start()
    t_err.start()

    # Wait up to 30 s for the URL
    url_event.wait(timeout=30)

    if public_url:
        print(f"[zrok]  Share is live: {public_url}")
    else:
        print("[zrok]  WARNING: timed out waiting for public URL.")
        print("[zrok]           The proxy is still running locally.")
        print("[zrok]           Check the [zrok] output above for errors.")

    return public_url


def stop_zrok_share():
    """Terminate the zrok subprocess cleanly."""
    global _zrok_proc
    if _zrok_proc and _zrok_proc.poll() is None:
        print("\n[zrok]  Stopping share...")
        _zrok_proc.terminate()
        try:
            _zrok_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _zrok_proc.kill()
        print("[zrok]  Share stopped.")
    _zrok_proc = None


# Register cleanup on normal exit and signals
atexit.register(stop_zrok_share)
for _sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(_sig, lambda s, f: sys.exit(0))


# ---------------------------------------------------------------------------
# llama.cpp forwarding helpers
# ---------------------------------------------------------------------------

def forward_to_llama(path, body):
    """Send a non-streaming POST to llama.cpp and return (status_code, response_text)."""
    data = json.dumps(body).encode()
    print(f"[proxy] -> llama.cpp POST {path}  (non-stream)")
    print(f"[proxy]    body: {json.dumps(body)[:300]}")
    req = urllib.request.Request(
        f"http://{LLAMA_HOST}:{LLAMA_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        response_text = resp.read().decode()
        print(f"[proxy] <- llama.cpp {resp.status}  response: {response_text[:300]}")
        return resp.status, response_text


def forward_stream_to_llama(path, body, wfile):
    """Pipe SSE chunks from llama.cpp directly to the client."""
    data = json.dumps(body).encode()
    print(f"[proxy] -> llama.cpp POST {path}  (streaming)")
    print(f"[proxy]    body: {json.dumps(body)[:300]}")
    req = urllib.request.Request(
        f"http://{LLAMA_HOST}:{LLAMA_PORT}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        chunk_count = 0
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            wfile.write(chunk)
            wfile.flush()
            chunk_count += 1
        print(f"[proxy] <- llama.cpp stream finished ({chunk_count} chunks)")


def responses_to_chat_completions(parsed):
    """
    Translate an OpenAI Responses API request body into a Chat Completions body.

    The Responses API (used by newer VS Code Copilot) differs from Chat Completions:
      - "input" (string or list) instead of "messages"
      - "instructions" instead of a system message
      - no "stream" at the top level (streaming is implied differently)
    """
    messages = []

    instructions = parsed.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    input_field = parsed.get("input", [])
    if isinstance(input_field, str):
        messages.append({"role": "user", "content": input_field})
    elif isinstance(input_field, list):
        for item in input_field:
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "") for p in content if p.get("type") == "text"
                ]
                content = "\n".join(text_parts)
            messages.append({"role": role, "content": content})

    chat_body = {
        "model": parsed.get("model", MODEL_NAME),
        "messages": messages,
        "stream": parsed.get("stream", False),
    }

    for key in ("temperature", "top_p", "max_tokens", "stop"):
        if key in parsed:
            chat_body[key] = parsed[key]

    return chat_body


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class OllamaProxyHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[proxy] {self.command} {self.path} -> {args[0] if args else ''}")

    def send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ------------------------------------------------------------------
    # GET handlers
    # ------------------------------------------------------------------
    def do_GET(self):
        print(f"[proxy] GET {self.path}")

        if self.path in ("/", "/api/version"):
            self.send_json(200, {"version": "0.6.4"})

        elif self.path == "/api/tags":
            self.send_json(200, {
                "models": [{
                    "name": MODEL_NAME,
                    "model": MODEL_NAME,
                    "modified_at": datetime.utcnow().isoformat() + "Z",
                    "size": 22000000000,
                    "digest": "aaaaaaaaaaaaaaaa",
                    "details": {
                        "parent_model": "",
                        "format": "gguf",
                        "family": "qwen3",
                        "families": ["qwen3"],
                        "parameter_size": "27B",
                        "quantization_level": "Q6_K"
                    }
                }]
            })

        elif self.path == "/v1/models":
            self.send_json(200, {
                "object": "list",
                "data": [{
                    "id": MODEL_NAME,
                    "object": "model",
                    "created": int(datetime.utcnow().timestamp()),
                    "owned_by": "local"
                }]
            })

        else:
            print(f"[proxy]   -> UNHANDLED GET '{self.path}'")
            self.send_json(404, {"error": f"Unhandled GET: {self.path}"})

    # ------------------------------------------------------------------
    # POST handlers
    # ------------------------------------------------------------------
    def do_POST(self):
        try:
            parsed = self.read_body()
            is_stream = parsed.get("stream", False)
            print(f"[proxy] POST {self.path}  stream={is_stream}")

            if self.path == "/api/show":
                self.send_json(200, {
                    "model": MODEL_NAME,
                    "modelfile": f"FROM {MODEL_NAME}",
                    "parameters": "temperature 1.0\ntop_p 0.95",
                    "template": "{{ .Prompt }}",
                    "details": {
                        "parent_model": "",
                        "format": "gguf",
                        "family": "qwen3",
                        "families": ["qwen3"],
                        "parameter_size": "27B",
                        "quantization_level": "Q6_K"
                    },
                    "model_info": {
                        "general.architecture": "qwen3",
                        "general.parameter_count": 27000000000,
                        "general.quantization_version": 2,
                        "qwen3.context_length": 65000,
                        "qwen3.attention.head_count": 32,
                    },
                    "capabilities": ["completion", "tools"]
                })

            elif self.path == "/api/chat":
                llama_body = {
                    "model": MODEL_NAME,
                    "messages": parsed.get("messages", []),
                    "stream": is_stream,
                    "temperature": parsed.get("options", {}).get("temperature"),
                    "top_p": parsed.get("options", {}).get("top_p"),
                }
                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    forward_stream_to_llama("/v1/chat/completions", llama_body, self.wfile)
                else:
                    status, body = forward_to_llama("/v1/chat/completions", llama_body)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())

            elif self.path == "/api/generate":
                llama_body = {
                    "model": MODEL_NAME,
                    "prompt": parsed.get("prompt", ""),
                    "stream": is_stream,
                }
                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    forward_stream_to_llama("/v1/completions", llama_body, self.wfile)
                else:
                    status, body = forward_to_llama("/v1/completions", llama_body)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())

            elif self.path == "/v1/chat/completions":
                parsed["model"] = parsed.get("model", MODEL_NAME)
                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    forward_stream_to_llama("/v1/chat/completions", parsed, self.wfile)
                else:
                    status, body = forward_to_llama("/v1/chat/completions", parsed)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())

            elif self.path == "/v1/responses":
                print(f"[proxy]   -> /v1/responses -> translating to Chat Completions")
                chat_body = responses_to_chat_completions(parsed)
                is_stream = chat_body.get("stream", False)
                if is_stream:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    forward_stream_to_llama("/v1/chat/completions", chat_body, self.wfile)
                else:
                    status, body = forward_to_llama("/v1/chat/completions", chat_body)
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())

            else:
                print(f"[proxy]   -> UNHANDLED POST '{self.path}'")
                self.send_json(404, {"error": f"Unhandled POST: {self.path}"})

        except Exception as e:
            print(f"[proxy] ERROR on {self.path}: {e}")
            self.send_json(500, {"error": str(e)})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PROXY_PORT), OllamaProxyHandler)

    print("=" * 60)
    print("Ollama <-> llama.cpp proxy  +  zrok public share")
    print("=" * 60)
    print(f"  Proxy listening:          http://0.0.0.0:{PROXY_PORT}")
    print(f"  Forwarding to llama.cpp:  http://{LLAMA_HOST}:{LLAMA_PORT}")
    print(f"  Advertised model:         {MODEL_NAME}")
    print()

    public_url = start_zrok_share()

    print()
    print("=" * 60)
    if public_url:
        print("  VS Code setup (on any remote machine):")
        print("    Settings -> 'GitHub Copilot: Local Provider' -> Ollama")
        print(f"    Ollama URL:  {public_url}")
        print(f"    Model:       {MODEL_NAME}")
    else:
        print("  zrok URL not detected — check [zrok] output above.")
        print(f"  Fallback (local only):  http://localhost:{PROXY_PORT}")
    print("=" * 60)
    print()
    print("Press Ctrl-C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[proxy] Shutting down...")
        server.server_close()