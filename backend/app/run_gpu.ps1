# run_gpu.ps1 — Launch run_r0.py with GPU (CUDA) support
# Adds nvidia DLL directories from venv to PATH so onnxruntime finds cublasLt64_12.dll

$venvSP = "$PSScriptRoot\venv\lib\site-packages"
$nvidiaRoot = "$venvSP\nvidia"

if (Test-Path $nvidiaRoot) {
    Get-ChildItem $nvidiaRoot -Directory | ForEach-Object {
        $binDir = Join-Path $_.FullName "bin"
        if (Test-Path $binDir) {
            $env:PATH = "$binDir;$env:PATH"
            Write-Host "[GPU] Added DLL path: $binDir"
        }
    }
} else {
    Write-Warning "nvidia packages not found in venv -- GPU may not work"
}

Write-Host "[GPU] Launching run_r0.py on GPU..."
& "$PSScriptRoot\venv\Scripts\python.exe" "$PSScriptRoot\scripts\run_r0.py" @args
