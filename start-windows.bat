@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kaggle 免费 GPU 一键开通

set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo 没找到 Python，正在用 winget 自动安装 Python 3.12 ...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo 安装完成后，请关掉这个窗口，再双击一次 start-windows.bat。
  echo 如果 winget 不可用，请到 https://www.python.org/downloads/ 下载安装，安装时勾选 "Add python.exe to PATH"。
  pause
  exit /b 1
)

%PY% kgpu.py setup
echo.
pause
