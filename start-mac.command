#!/bin/bash
# Mac 双击运行：Kaggle 免费 GPU 一键开通
cd "$(dirname "$0")" || exit 1

if ! /usr/bin/python3 -c "import sys" >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "没找到 Python 3。系统会弹窗安装「命令行开发者工具」，点「安装」，装完再双击本文件。"
  xcode-select --install
  read -n 1 -s -r -p "按任意键关闭..."
  exit 1
fi

PY=$(command -v python3 || echo /usr/bin/python3)
"$PY" kgpu.py setup
echo
read -n 1 -s -r -p "按任意键关闭..."
