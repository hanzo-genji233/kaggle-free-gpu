#!/usr/bin/env python3
"""kgpu.py — 用 Kaggle 免费双卡 T4 GPU 跑批处理任务（Windows / macOS / Linux 通用）。

只依赖 Python 3.8+ 标准库和官方 kaggle 命令行工具。

用法：
  python kgpu.py doctor               检查：kaggle 是否安装、是否登录、额度
  python kgpu.py quota                查看剩余 GPU / TPU 额度
  python kgpu.py new <目录> <名字>     新建任务文件夹（名字只用小写字母、数字、-）
  python kgpu.py run <目录>            提交到 T4 x2，等跑完，下载结果到 <目录>/output
  python kgpu.py run <目录> --no-wait  只提交，不等待
  python kgpu.py fetch <目录>          下载结果（任务跑完后用）
  python kgpu.py netcheck <名字>       提交一个联网诊断任务（不占 GPU）

第一次使用：
  pip install kaggle six              （six 必须带上，新版 CLI 漏了这个依赖）
  kaggle auth login                   （浏览器授权）
  到 kaggle.com → Settings → Phone verification 完成手机验证（否则没有 GPU、不能联网）
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

ACCEL_GPU = "NvidiaTeslaT4"
DONE = re.compile(r'status "KernelWorkerStatus\.(COMPLETE|ERROR|CANCEL\w*)"')

MAIN_PY = '''"""Kaggle GPU 任务。把真正的计算写在下面，产物写到 /kaggle/working/ 才能下载。"""
import json, os, shutil, subprocess, urllib.request

print("== GPU ==")
if shutil.which("nvidia-smi"):
    print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout)
else:
    print("NO GPU: 找不到 nvidia-smi（账号做过手机验证吗？）")

print("== 联网 ==")
try:
    urllib.request.urlopen("https://pypi.org", timeout=10)
    print("internet OK")
except Exception as e:
    print("NO INTERNET:", e, "（验证前建的任务不能联网，换个新名字重建）")

try:
    import torch
    print("torch cuda:", torch.cuda.is_available(), "devices:", torch.cuda.device_count())
except Exception as e:
    print("torch 检查失败:", e)

# ===== 在这里写你的任务 =====


# ============================

with open("/kaggle/working/result.txt", "w") as f:
    f.write("done\\n")

# 可选：跑完发通知（飞书 / 钉钉 / 企业微信机器人等 webhook）。不要把 token 写进公开代码。
hook = os.environ.get("NOTIFY_WEBHOOK", "")
if hook:
    body = json.dumps({"msg_type": "text", "content": {"text": "Kaggle GPU 任务完成"}}).encode()
    urllib.request.urlopen(urllib.request.Request(hook, body, {"Content-Type": "application/json"}), timeout=10)
'''

NET_PY = '''import socket, urllib.request
for h in ["pypi.org", "huggingface.co"]:
    try:
        print(h, socket.getaddrinfo(h, 443)[0][4])
    except Exception as e:
        print(h, "DNS FAIL", e)
try:
    print("https:", urllib.request.urlopen("https://pypi.org", timeout=10).status)
except Exception as e:
    print("https FAIL", e)
'''


def die(msg):
    print("✗ " + msg)
    sys.exit(1)


def kaggle_bin():
    exe = shutil.which("kaggle")
    if not exe:
        die("没找到 kaggle 命令。先运行：pip install kaggle six")
    return exe


def kaggle(*args, retries=5, quiet=False):
    """调用 kaggle CLI；api.kaggle.com 偶发 SSL 断开，自动重试。"""
    out = ""
    for i in range(retries):
        p = subprocess.run([kaggle_bin(), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        transient = "SSLError" in out or "Max retries exceeded" in out or "Connection" in out
        if p.returncode == 0 and not transient:
            return out
        if not transient:
            break
        time.sleep(5 * (i + 1))
    if not quiet:
        print(out.strip())
    return None


def username():
    out = kaggle("config", "view", quiet=True) or ""
    m = re.search(r"username:\s*(\S+)", out)
    if not m or m.group(1) == "None":
        die("还没登录。先运行：kaggle auth login")
    return m.group(1)


def meta_id(folder):
    path = os.path.join(folder, "kernel-metadata.json")
    if not os.path.exists(path):
        die(f"{path} 不存在。先用 new 建任务。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["id"]


def write_task(folder, slug, code, gpu=True):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,49}", slug):
        die("名字只能用小写字母、数字和 -，3 到 50 个字符。")
    os.makedirs(folder, exist_ok=True)
    meta = {
        "id": f"{username()}/{slug}", "title": slug, "code_file": "main.py",
        "language": "python", "kernel_type": "script", "is_private": True,
        "enable_gpu": gpu, "enable_tpu": False, "enable_internet": True,
        "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": [],
    }
    with open(os.path.join(folder, "kernel-metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    main = os.path.join(folder, "main.py")
    if not os.path.exists(main):
        with open(main, "w", encoding="utf-8") as f:
            f.write(code)
    print(f"✓ 已建任务 {meta['id']} → {folder}")


def push(folder, gpu=True):
    args = ["kernels", "push", "-p", folder] + (["--accelerator", ACCEL_GPU] if gpu else [])
    out = kaggle(*args)
    if not out or "successfully" not in out:
        die("提交失败。")
    print("✓ " + out.strip().splitlines()[-1])


def wait(kid):
    print(f"… 等待 {kid}（GPU 任务常排队 10 分钟以上，可以先去做别的）")
    last = ""
    while True:
        out = kaggle("kernels", "status", kid, quiet=True) or ""
        m = DONE.search(out)
        st = re.search(r"KernelWorkerStatus\.(\w+)", out)
        if st and st.group(1) != last:
            last = st.group(1)
            print(f"  [{time.strftime('%H:%M:%S')}] {last}")
        if m:
            return m.group(1)
        time.sleep(30)


def fetch(folder):
    kid = meta_id(folder)
    dest = os.path.join(folder, "output")
    shutil.rmtree(dest, ignore_errors=True)
    if kaggle("kernels", "output", kid, "-p", dest) is None:
        die("下载失败，稍后重试：python kgpu.py fetch " + folder)
    for name in sorted(os.listdir(dest)):
        if name.endswith(".log"):
            print(f"== 日志 {name} ==")
            try:
                with open(os.path.join(dest, name), encoding="utf-8") as f:
                    for e in json.load(f):
                        line = e.get("data", "").rstrip()
                        if line and not any(k in line for k in ("SyntaxWarning", "NbConvertApp", "re.sub(", "Escape underscores")):
                            print(line)
            except Exception:
                print("(日志不是 JSON，直接打开看)")
    print("✓ 结果在 " + dest + "：", ", ".join(sorted(os.listdir(dest))))


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = argv[1]
    if cmd == "doctor":
        print("✓ kaggle 命令：" + kaggle_bin())
        print((kaggle("--version") or "").strip())
        print("✓ 已登录：" + username())
        print(kaggle("quota") or "")
        print("提示：额度能显示不代表能用 GPU，还要在网页上完成手机验证。")
    elif cmd == "quota":
        print(kaggle("quota") or "")
    elif cmd == "new" and len(argv) >= 4:
        write_task(argv[2], argv[3], MAIN_PY)
        print("下一步：改 main.py，再运行 python kgpu.py run " + argv[2])
    elif cmd == "run" and len(argv) >= 3:
        folder = argv[2]
        push(folder)
        if "--no-wait" in argv:
            print("稍后运行：python kgpu.py fetch " + folder)
            return
        state = wait(meta_id(folder))
        print(("✓ " if state == "COMPLETE" else "✗ ") + "任务结束：" + state)
        fetch(folder)
    elif cmd == "fetch" and len(argv) >= 3:
        fetch(argv[2])
    elif cmd == "netcheck" and len(argv) >= 3:
        folder = os.path.join(os.getcwd(), argv[2])
        write_task(folder, argv[2], NET_PY, gpu=False)
        push(folder, gpu=False)
        print("任务结束：" + wait(meta_id(folder)))
        fetch(folder)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    if os.name == "nt":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main(sys.argv)
