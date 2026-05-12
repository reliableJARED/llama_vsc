@echo off
setlocal enabledelayedexpansion

:: FORCE the script to run in the folder where the .bat file is located
cd /d "%~dp0"

echo ====================================================================
echo Huihui-Qwen3.5-27B-abliterated- Q6_K Setup ^& Run (Blackwell sm_120)
echo ====================================================================
echo.

:: 1. Check Prerequisites & Detect Python Safely
echo [1/6] Checking prerequisites...
where git >nul 2>&1 || (echo ERROR: Git is not installed or not in your PATH. & pause & exit /b)
where cmake >nul 2>&1 || (echo ERROR: CMake is not installed or not in your PATH. & pause & exit /b)
where nvcc >nul 2>&1 || (echo ERROR: CUDA Toolkit is not installed or not in your PATH. & pause & exit /b)

set PY_CMD=python
where py >nul 2>&1
if %ERRORLEVEL% equ 0 set PY_CMD=py

%PY_CMD% --version >nul 2>&1 || (echo ERROR: Python is not functioning properly. & pause & exit /b)
echo All required tools found! (Using %PY_CMD% for Python)
echo.

:: 2. Setup MSVC Environment
echo [2/6] Initializing Visual Studio C++ Environment...
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo ERROR: vswhere.exe not found. Please install Visual Studio.
    pause
    exit /b
)

for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
    set "VS_PATH=%%i"
)

if not defined VS_PATH (
    echo ERROR: Could not find Visual Studio.
    pause
    exit /b
)
call "!VS_PATH!\VC\Auxiliary\Build\vcvars64.bat" >nul
echo.

:: 3. Install Hugging Face Hub
echo [3/6] Installing huggingface_hub...
%PY_CMD% -m pip install "huggingface_hub[cli]" >nul 2>&1
echo.

:: 4. Clone and Build llama.cpp
echo [4/6] Setting up and building llama.cpp...
if not exist "llama.cpp" (
    echo Cloning llama.cpp repository...
    git clone https://github.com/ggml-org/llama.cpp
)
cd llama.cpp

if not exist "build\bin\llama-server.exe" (
    echo Configuring CMake for CUDA ^(Targeting Blackwell architecture 120^)...
    set "ASM=cl.exe"
    cmake -B build -G Ninja -DCMAKE_POLICY_DEFAULT_CMP0194=OLD -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=cl.exe -DCMAKE_CXX_COMPILER=cl.exe -DCMAKE_ASM_COMPILER=cl.exe -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="120"
    if !errorlevel! neq 0 ( echo ERROR: CMake configuration failed. & pause & exit /b )

    echo Building llama-server...
    cmake --build build --config Release -j %NUMBER_OF_PROCESSORS% --target llama-server
    if !errorlevel! neq 0 ( echo ERROR: Build failed. & pause & exit /b )
) else (
    echo Build already successfully completed. Skipping compilation!
)
echo.

:: 5. Download Model Files using Native Python
echo [5/6] Downloading models to default Hugging Face cache...

:: Create temporary python script to safely fetch the Q6_K model
echo from huggingface_hub import snapshot_download > dl_model.py
echo path = snapshot_download(repo_id="mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF", allow_patterns="*Q6_K*") >> dl_model.py
echo with open("model_path.txt", "w") as f: f.write(path) >> dl_model.py

:: Create temporary python script to safely fetch the Vision Projector
echo from huggingface_hub import hf_hub_download > dl_vision.py
echo path = hf_hub_download(repo_id="unsloth/Qwen3.5-27B-GGUF", filename="mmproj-BF16.gguf") >> dl_vision.py
echo with open("vision_path.txt", "w") as f: f.write(path) >> dl_vision.py

echo.
echo Downloading Huihui-Qwen3.5-27B-abliterated-GGUF (Q6_K)...
%PY_CMD% dl_model.py
set /p MODEL_SNAP_DIR=<model_path.txt

echo.
echo Downloading mmproj-BF16.gguf vision projector...
%PY_CMD% dl_vision.py
set /p MMPROJ_FILE=<vision_path.txt

:: Clean up temp scripts
del dl_model.py dl_vision.py model_path.txt vision_path.txt

:: Automatically find the exact Q6_K file inside the snapshot directory
for %%f in ("!MODEL_SNAP_DIR!\*Q6_K*.gguf") do set "MODEL_FILE=%%f"
if not defined MODEL_FILE (
    echo ERROR: Q6_K model file not found in cache.
    pause
    exit /b
)

:: 6. Run Server
echo.
echo [6/6] Starting OpenAI-Compatible Server...
echo Model File:  !MODEL_FILE!
echo Vision File: !MMPROJ_FILE!
echo.
echo ====================================================================
echo The server Web UI will be available at: http://localhost:8080
echo Press Ctrl+C in this window to stop the server when you are done.
echo ====================================================================
echo.
echo model downloaded from https://huggingface.co/mradermacher/Huihui-Qwen3.5-27B-abliterated-GGUF

:: Note: Windows cmd requires escaping inner quotes in JSON string arguments
:: set "CHAT_TEMPLATE={\"enable_thinking\":false}"
set "CHAT_TEMPLATE={\"enable_thinking\":true}"

:: =======================================================
:: GPU SELECTION:
:: Set to 0 to use ONLY the RTX 5090 (Device 0)
:: Set to 1 to use ONLY the RTX 5060 Ti (Device 1)
:: Delete or comment out the line below to use BOTH GPUs
:: =======================================================
set CUDA_VISIBLE_DEVICES=0

build\bin\llama-server.exe ^
  -m "!MODEL_FILE!" ^
  --mmproj "!MMPROJ_FILE!" ^
  -ngl 99 ^
  --ctx-size 65000 ^
  --flash-attn on ^
  --jinja ^
  --temp 1.0 ^
  --top-p 0.95 ^
  --top-k 20 ^
  --presence-penalty 1.5 ^
  --min-p 0.05 ^
  --host 0.0.0.0 ^
  --port 8080 ^
  --chat-template-kwargs "!CHAT_TEMPLATE!"

pause