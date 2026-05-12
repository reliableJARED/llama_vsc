# VS Code Copilot + Local Llama.cpp Integration

A complete solution for running local AI models with VS Code Copilot on Windows with NVIDIA GPU support. This repository bridges VS Code Copilot's Ollama interface with a powerful llama.cpp server, enabling you to use high-performance local models like Qwen3.5-27B directly in your development workflow.

## 🎯 What This Does

This project enables **VS Code Copilot** to communicate with a local **llama.cpp** server through an Ollama-compatible proxy:

```
VS Code Copilot → Ollama Proxy (port 11434) → llama.cpp Server (port 8080) → Your Local GPU
```

### Key Features

- **Local Model Execution**: Run powerful models like Qwen3.5-27B on your local NVIDIA GPU
- **VS Code Integration**: Seamlessly integrate with GitHub Copilot's "Bring Your Own Model" (BYOM) feature
- **Ollama Compatibility**: Proxy translates Ollama API calls to llama.cpp's OpenAI-compatible interface
- **Multi-GPU Support**: Configure single or multi-GPU setups (optimized for RTX 5090/5060 Ti)
- **Vision Support**: Includes multimodal projector for image understanding capabilities

## 📋 Prerequisites

### For Running the Proxy Only

If you already have a llama.cpp server running (or will use an existing installation), the proxy requires **only Python** - it uses standard library modules with no external dependencies:

1. **Python 3.10+**
   ```powershell
   python --version
   ```

**That's it!** The proxy uses only built-in Python modules:
- `http.server` - HTTP server and request handling
- `urllib.request` - Forwarding requests to llama.cpp
- `json` - Request/response serialization
- `datetime` - Timestamp generation

### For Building llama.cpp from Source (Using the .bat File)

If you're using `run_qwen35_Q6_k_llama.bat` to build and set up llama.cpp from scratch, you'll also need:

2. **Git**
   ```powershell
   git --version
   ```

3. **CMake** (for building llama.cpp)
   ```powershell
   cmake --version
   ```

4. **CUDA Toolkit** (with NVIDIA GPU drivers)
   ```powershell
   nvcc --version
   ```

5. **Visual Studio Build Tools**
   - Install "Desktop development with C++" workload
   - Includes MSVC build tools and Windows 10/11 SDK

### Hardware Requirements

- **NVIDIA GPU** with minimum 24GB VRAM (RTX 3090/4090/5090 recommended)
- **For Qwen3.5-27B**:
  - Q6_K quantization: ~22GB VRAM (recommended, allows larger context)
  - Q8_0 quantization: ~28.5GB VRAM (higher precision, smaller context window)

## 🚀 Quick Start

### Option 1: Using an Existing llama.cpp Server

If you already have a llama.cpp server installed and running:

1. **Start your llama.cpp server** on port 8080 (or your preferred port)
2. **Proceed to the Proxy Setup section** below to launch the proxy

This is the simplest setup - no build tools required, just Python!

### Option 2: Automated Setup with Batch Script

The included `run_qwen35_Q6_k_llama.bat` automates the complete setup process from scratch:

```powershell
# Double-click or run from PowerShell:
.\run_qwen35_Q6_k_llama.bat
```

**What the script does:**

1. ✅ Validates all prerequisites (Git, CMake, CUDA, Python, Visual Studio)
2. ✅ Initializes MSVC build environment for compilation
3. ✅ Installs `huggingface_hub` Python package for model downloads
4. ✅ Clones llama.cpp repository and builds with CUDA support (targeting Blackwell sm_120 architecture)
5. ✅ Downloads Qwen3.5-27B-Q6_K model and vision projector from Hugging Face
6. ✅ Starts the llama.cpp server on port 8080

**Server Web UI**: Once started, access the server interface at http://localhost:8080

**Note**: The batch script is ideal for first-time setup. On subsequent runs, it will skip steps that have already been completed (e.g., if llama.cpp is already built).

## 🔧 Proxy Setup

The `ollama_llama_proxy.py` bridges VS Code Copilot and llama.cpp. 

**No external dependencies required** - the proxy uses only Python's standard library:
- `http.server` - HTTP server and request handling  
- `urllib.request` - Forwarding requests to llama.cpp
- `json` - Request/response serialization
- `datetime` - Timestamp generation

### Starting the Proxy

```powershell
# Make sure llama.cpp server is running on port 8080 first
python ollama_llama_proxy.py
```

**Expected output:**
```
============================================================
Ollama <-> llama.cpp proxy
============================================================
  Listening (as Ollama):  http://0.0.0.0:11434
  Forwarding to llama.cpp: http://localhost:8080
  Advertised model name:   huihui-qwen3:latest
```

### Proxy Configuration

Edit `ollama_llama_proxy.py` to customize settings:

```python
# --- Configuration ---
LLAMA_HOST = "localhost"          # llama.cpp server host
LLAMA_PORT = 8080                 # llama.cpp server port
PROXY_PORT = 11434                # Ollama's default port (required)
MODEL_NAME = "huihui-qwen3:latest"  # Model identifier in 'name:tag' format
```

### API Routes Handled

**GET Endpoints:**
- `/api/version` - Returns proxy version (0.6.4)
- `/api/tags` - Lists available models with metadata
- `/v1/models` - OpenAI-compatible model listing

**POST Endpoints:**
- `/api/show` - Model details and capabilities
- `/api/chat` - Ollama-native chat interface
- `/api/generate` - Text generation endpoint
- `/v1/chat/completions` - VS Code Copilot (chat mode)
- `/v1/responses` - VS Code Copilot (agent mode with Responses API translation)

## 🛠️ VS Code Configuration (BYOM Setup)

Follow these steps to configure VS Code Copilot to use your local model:

### Step 1: Access Model Picker

1. Open **VS Code**
2. Open **Copilot Chat** panel (Ctrl+Shift+P → "Copilot: Show Chat")
3. Click the **Model picker dropdown** in the chat header

### Step 2: Configure Local Provider

1. Navigate to **Settings** (File → Preferences → Settings or Ctrl+,)
2. Search for **"GitHub Copilot: Local Provider"**
3. Select **Ollama** as the local provider

### Step 3: Add Your Model

1. In the Model picker, select **"Add Model"** or **"Bring Your Own Model"**
2. Choose **Ollama** as the provider
3. Enter the model name: `huihui-qwen3:latest`
4. Confirm the custom model appears in the model picker

### Step 4: Verify Connection

1. Ensure both services are running:
   - llama.cpp server on port 8080
   - Proxy on port 11434
2. Select `huihui-qwen3:latest` from the model picker
3. Start prompting in the chat - Copilot will use your local model

### Alternative: Using Settings UI

You can also configure through the Settings interface:

1. **Settings** → **"GitHub Copilot"** → **"Local Provider"**
2. Set provider to **Ollama**
3. Configure base URL: `http://localhost:11434`
4. Select model: `huihui-qwen3:latest`

## 📊 Model Information

### Qwen3.5-27B Specifications

- **Architecture**: Qwen3 transformer-based language model
- **Parameters**: 27 billion
- **Format**: GGUF (GPU-optimized)
- **Quantization Options**:
  - **Q6_K** (~22GB): Recommended for balanced performance and context size
  - **Q8_0** (~28.5GB): Higher precision, ideal for maximum quality
- **Context Length**: Up to 65,000 tokens (Q6_K) or 24,576 tokens (Q8_0)
- **Attention Heads**: 32
- **Capabilities**: Text completion, tool use, multimodal vision support

### VRAM Usage Guide

| Quantization | Model Size | Context Size | Free VRAM (32GB GPU) | Use Case |
|-------------|-----------|--------------|---------------------|----------|
| Q6_K | ~22 GB | 65,000 tokens | ~10 GB | Large context, complex tasks |
| Q8_0 | ~28.5 GB | 24,576 tokens | ~3.5 GB | Maximum precision, standard context |

## ⚙️ Advanced Configuration

### GPU Selection

In `run_qwen35_Q6_k_llama.bat`, configure GPU usage:

```batch
:: Use ONLY RTX 5090 (Device 0)
set CUDA_VISIBLE_DEVICES=0

:: Use ONLY RTX 5060 Ti (Device 1)
set CUDA_VISIBLE_DEVICES=1

:: Use BOTH GPUs (comment out or delete the line)
:: set CUDA_VISIBLE_DEVICES=0,1
```

### Context Size Tuning

Adjust based on your quantization choice:

**For Q6_K (~22GB):**
```batch
--ctx-size 65000
```

**For Q8_0 (~28.5GB):**
```batch
--ctx-size 24576
:: or for smaller context
--ctx-size 16384
```

### Inference Parameters

The server uses these optimized defaults (configurable in the batch script):

- **Temperature**: 1.0 (balanced creativity)
- **Top-P**: 0.95 (nucleus sampling)
- **Top-K**: 20 (token candidate pool)
- **Presence Penalty**: 1.5 (encourages topic diversity)
- **Min-P**: 0.05 (minimum probability threshold)
- **Flash Attention**: Enabled for performance

### Enabling Thinking Mode

The chat template supports a "thinking" mode for complex reasoning:

```batch
:: Enable thinking (default)
set "CHAT_TEMPLATE={\"enable_thinking\":true}"

:: Disable thinking for faster responses
set "CHAT_TEMPLATE={\"enable_thinking\":false}"
```

## 📁 Repository Structure

```
llama_vsc/
├── run_qwen35_Q6_k_llama.bat    # Automated setup and server launch script
├── ollama_llama_proxy.py         # Ollama ↔ llama.cpp bridge proxy
├── readme.md                     # This documentation
└── llama.cpp/                    # Cloned during setup (if not already present)
    ├── build/
    │   └── bin/
    │       └── llama-server.exe  # Compiled server binary
    └── ...
```

## 🔍 Troubleshooting

### Common Issues

**1. Prerequisites Not Found**
```
ERROR: Git is not installed or not in your PATH.
```
- Ensure Git, CMake, CUDA, and Python are installed
- Add their `bin` directories to system PATH
- Restart terminal after installation

**2. Build Tools Missing (When Using .bat File)**
```
ERROR: vswhere.exe not found. Please install Visual Studio.
```
- Install "Desktop development with C++" from Visual Studio Installer
- Include MSVC tools and Windows SDK
- Note: This only applies if building llama.cpp from source using the batch script

**3. Model Download Fails**
```
ERROR: Model file path could not be determined.
```
- Check internet connection
- Verify Hugging Face access (may require authentication for large downloads)
- Ensure sufficient disk space (~25GB for Q6_K model + vision projector)

**4. Proxy Connection Issues**
```
[proxy] ERROR on /v1/chat/completions: Connection refused
```
- Confirm llama.cpp server is running on port 8080
- Check that proxy is listening on port 11434
- Verify no other application is using these ports

**5. VRAM Out of Memory**
- Switch from Q8_0 to Q6_K quantization
- Reduce `--ctx-size` parameter
- Use single GPU if multi-GPU causes fragmentation

### Debug Mode

Enable verbose logging in the proxy by adding:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🌐 API Compatibility

This solution supports multiple API standards:

- **Ollama API**: Native compatibility for VS Code integration
- **OpenAI Chat Completions**: Standard `/v1/chat/completions` endpoint
- **OpenAI Responses API**: Translated to Chat Completions for agent mode
- **Streaming Support**: Server-Sent Events (SSE) for real-time responses

## 📚 Additional Resources

- [llama.cpp GitHub Repository](https://github.com/ggml-org/llama.cpp)
- [Qwen3.5-27B on Hugging Face](https://huggingface.co/unsloth/Qwen3.5-27B-GGUF)
- [VS Code Copilot BYOM Documentation](https://learn.microsoft.com/en-us/visualstudio/ide/copilot-select-add-models?view=visualstudio#bring-your-own-model-byom)
- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)

## 🔄 Workflow Summary

1. **Setup**: Run `run_qwen35_Q6_k_llama.bat` to build and download model
2. **Start Server**: The script launches llama.cpp server (or start manually)
3. **Launch Proxy**: Run `python ollama_llama_proxy.py`
4. **Configure VS Code**: Set up Ollama provider with BYOM steps
5. **Start Coding**: Use Copilot Chat with your local model

## 📝 Notes

- The proxy automatically handles both streaming and non-streaming requests
- Model files are cached in the default Hugging Face directory (`~/.cache/huggingface`)
- Subsequent runs of the batch script will skip already-completed steps
- The server Web UI at http://localhost:8080 provides additional monitoring and testing capabilities

## 🤝 Contributing

This repository is designed for Windows with NVIDIA GPU. For adaptations to other platforms:

- **Linux/macOS**: Convert `.bat` scripts to shell scripts (`.sh`)
- **AMD/Intel GPUs**: Adjust CMake flags for `GGML_AMD` or `GGML_METAL`
- **Different Models**: Update `MODEL_QUANT` and model filenames in the batch script

## 📄 License

This project is provided as-is for local development use. Ensure compliance with the licenses of included components:
- llama.cpp: MIT License
- Qwen3.5-27B: Model license from unsloth/Hugging Face
