# ollama_llama_proxy.py
#
# PURPOSE: VS Code Copilot (as of May 2026) only supports Ollama as a local model
# provider. This proxy pretends to BE Ollama on port 11434 so VS Code Copilot can
# connect to it, while secretly forwarding every request to your real llama.cpp
# server running on localhost:8080.
#
# Flow:
#   VS Code Copilot  -->  this proxy (port 11434, speaks Ollama API)
#                              |
#                              v
#                     llama.cpp server (port 8080, speaks OpenAI-compatible API)
#
# VS Code Copilot calls TWO different paths depending on its version / mode:
#   - Older / chat mode:  POST /v1/chat/completions  (OpenAI Chat Completions style)
#   - Newer / agent mode: POST /v1/responses         (OpenAI Responses API style)
# Both arrive at THIS proxy on port 11434 and are forwarded to llama.cpp.
# llama.cpp only speaks Chat Completions, so /v1/responses is translated on the fly.
#
# Configure VS Code: Settings -> "GitHub Copilot: Local Provider" -> Ollama
# Make sure llama.cpp is already running with --port 8080 before starting this proxy.

import json
import http.server
import urllib.request
import urllib.error
from datetime import datetime

# --- Configuration ---
LLAMA_HOST = "localhost"          # llama.cpp server host
LLAMA_PORT = 8080                 # llama.cpp server port
PROXY_PORT = 11434                # must match Ollama's default so VS Code finds it
MODEL_NAME = "huihui-qwen3:latest"  # Ollama REQUIRES the 'name:tag' format


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

    We normalise everything into the Chat Completions format that llama.cpp understands.
    """
    messages = []

    # "instructions" becomes a system message
    instructions = parsed.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": instructions})

    # "input" can be a plain string or a list of message objects
    input_field = parsed.get("input", [])
    if isinstance(input_field, str):
        messages.append({"role": "user", "content": input_field})
    elif isinstance(input_field, list):
        for item in input_field:
            role = item.get("role", "user")
            content = item.get("content", "")
            # content can itself be a list of content parts
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

    # Pass through optional sampling params if present
    for key in ("temperature", "top_p", "max_tokens", "stop"):
        if key in parsed:
            chat_body[key] = parsed[key]

    return chat_body


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
            print(f"[proxy]   -> version probe, returning 0.6.4")
            self.send_json(200, {"version": "0.6.4"})

        elif self.path == "/api/tags":
            print(f"[proxy]   -> /api/tags probe, advertising model '{MODEL_NAME}'")
            self.send_json(200, {
                "models": [
                    {
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
                    }
                ]
            })

        elif self.path == "/v1/models":
            print(f"[proxy]   -> /v1/models probe, advertising model '{MODEL_NAME}'")
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

            # --- /api/show --- VS Code calls this after /api/tags to get model details
            if self.path == "/api/show":
                model = parsed.get("model", MODEL_NAME)
                print(f"[proxy]   -> /api/show for '{model}', returning model details")
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

            # --- /api/chat -> /v1/chat/completions (Ollama native chat path) ---
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

            # --- /api/generate -> /v1/completions ---
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

            # --- /v1/chat/completions ---
            # VS Code Copilot calls this DIRECTLY on port 11434 (bypassing /api/chat).
            # We just forward it straight through to llama.cpp on port 8080.
            elif self.path == "/v1/chat/completions":
                parsed["model"] = parsed.get("model", MODEL_NAME)
                print(f"[proxy]   -> /v1/chat/completions passthrough to llama.cpp")
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

            # --- /v1/responses ---
            # Newer VS Code Copilot agent mode uses the OpenAI Responses API.
            # llama.cpp doesn't speak this; we translate it to Chat Completions first.
            elif self.path == "/v1/responses":
                print(f"[proxy]   -> /v1/responses (Responses API) -> translating to Chat Completions")
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
                print(f"[proxy]   -> UNHANDLED POST '{self.path}' body={json.dumps(parsed)[:300]}")
                self.send_json(404, {"error": f"Unhandled POST: {self.path}"})

        except Exception as e:
            print(f"[proxy] ERROR on {self.path}: {e}")
            self.send_json(500, {"error": str(e)})


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PROXY_PORT), OllamaProxyHandler)
    print("=" * 60)
    print("Ollama <-> llama.cpp proxy")
    print("=" * 60)
    print(f"  Listening (as Ollama):  http://0.0.0.0:{PROXY_PORT}")
    print(f"  Forwarding to llama.cpp: http://{LLAMA_HOST}:{LLAMA_PORT}")
    print(f"  Advertised model name:   {MODEL_NAME}")
    print()
    print("Handled routes:")
    print("  GET  /api/version, /api/tags, /v1/models")
    print("  POST /api/show, /api/chat, /api/generate")
    print("  POST /v1/chat/completions  <- VS Code Copilot (chat mode)")
    print("  POST /v1/responses         <- VS Code Copilot (agent mode)")
    print()
    print("In VS Code: Settings -> 'GitHub Copilot: Local Provider' -> Ollama")
    print(f"            Model: {MODEL_NAME}")
    print("=" * 60)
    server.serve_forever()