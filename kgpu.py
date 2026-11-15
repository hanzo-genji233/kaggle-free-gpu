#!/usr/bin/env python3
"""kgpu.py — 用 Kaggle 免费双卡 T4 GPU 跑批处理任务（Windows / macOS / Linux 通用）。

只依赖 Python 3.9+ 标准库；kaggle 官方工具会自动装进本目录的 .venv，不污染系统。

一键开通（推荐，第一次用）：
  python kgpu.py setup                自动安装 → 浏览器登录 → 提醒手机验证 → 跑一次 GPU 测试
  （Windows 双击 start-windows.bat，Mac 双击 start-mac.command，效果一样）

日常使用：
  python kgpu.py doctor               检查：工具、登录、额度
  python kgpu.py quota                查看剩余 GPU / TPU 额度
  python kgpu.py new <目录> <名字>     新建任务文件夹（名字只用小写字母、数字、-）
  python kgpu.py run <目录>            提交到 T4 x2，等跑完，下载结果到 <目录>/output
  python kgpu.py run <目录> --no-wait  只提交，不等待
  python kgpu.py fetch <目录>          下载结果（任务跑完后用）
  python kgpu.py gputest              再跑一次 GPU + 联网测试
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, ".venv")
IS_WIN = os.name == "nt"
ACCEL_GPU = "NvidiaTeslaT4"
DONE = re.compile(r'status "KernelWorkerStatus\.(COMPLETE|ERROR|CANCEL\w*)"')
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
YES = "--yes" in sys.argv  # 非交互（测试用）：跳过所有「按回车」

MAIN_PY = '''"""Kaggle GPU 任务。把真正的计算写在下面，产物写到 /kaggle/working/ 才能下载。"""
import json, os, shutil, subprocess, urllib.request

print("== GPU ==")
if shutil.which("nvidia-smi"):
    print(subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout)
else:
    print("NO GPU: 找不到 nvidia-smi")

print("== 联网 ==")
try:
    urllib.request.urlopen("https://pypi.org", timeout=10)
    print("internet OK")
except Exception as e:
    print("NO INTERNET:", e)

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


def say(msg=""):
    print(msg, flush=True)


def die(msg):
    say("✗ " + msg)
    sys.exit(1)


def pause(msg="按回车继续..."):
    if YES:
        return ""
    try:
        return input(msg)
    except EOFError:
        return ""


# ---------- 找工具 ----------

def venv_bin(name):
    sub = "Scripts" if IS_WIN else "bin"
    p = os.path.join(VENV, sub, name + (".exe" if IS_WIN else ""))
    return p if os.path.exists(p) else None


def kaggle_bin(required=True):
    exe = venv_bin("kaggle") or shutil.which("kaggle")
    if not exe and required:
        die("还没装 kaggle 工具。先运行：python kgpu.py setup")
    return exe


def kaggle(*args, retries=5, quiet=False):
    """调用 kaggle CLI；api.kaggle.com 偶发 SSL 断开，自动重试。"""
    out = ""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for i in range(retries):
        p = subprocess.run([kaggle_bin(), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        out = (p.stdout or "") + (p.stderr or "")
        transient = any(k in out for k in ("SSLError", "Max retries exceeded", "ConnectionError",
                                             "Connection aborted", "timed out"))
        if p.returncode == 0 and not transient:
            return out
        if not transient:
            break
        time.sleep(5 * (i + 1))
    if not quiet:
        say(out.strip())
    return None


def username(required=True):
    out = kaggle("config", "view", quiet=True) or ""
    m = re.search(r"username:\s*(\S+)", out)
    if not m or m.group(1) == "None":
        if required:
            die("还没登录 Kaggle。先运行：python kgpu.py setup")
        return None
    return m.group(1)


# ---------- 任务 ----------

def meta_id(folder):
    path = os.path.join(folder, "kernel-metadata.json")
    if not os.path.exists(path):
        die(f"{path} 不存在。先用 new 建任务。")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["id"]


def write_task(folder, slug, code=MAIN_PY, gpu=True):
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
    say(f"✓ 已建任务 {meta['id']} → {folder}")


def push(folder, gpu=True):
    args = ["kernels", "push", "-p", folder] + (["--accelerator", ACCEL_GPU] if gpu else [])
    out = kaggle(*args)
    if not out or "successfully" not in out:
        die("提交失败。")
    say("✓ 已提交到 Kaggle 云端")


def wait(kid):
    say(f"… 等待 {kid}（GPU 常要排队 10 分钟以上，窗口别关，可以先去做别的）")
    last = ""
    while True:
        out = kaggle("kernels", "status", kid, quiet=True) or ""
        m = DONE.search(out)
        st = re.search(r"KernelWorkerStatus\.(\w+)", out)
        if st and st.group(1) != last:
            last = st.group(1)
            say(f"  [{time.strftime('%H:%M:%S')}] {last}")
        if m:
            return m.group(1)
        time.sleep(30)


def fetch(folder, show=True):
    kid = meta_id(folder)
    dest = os.path.join(folder, "output")
    shutil.rmtree(dest, ignore_errors=True)
    if kaggle("kernels", "output", kid, "-p", dest) is None:
        die("下载失败，稍后重试：python kgpu.py fetch " + folder)
    log = []
    for name in sorted(os.listdir(dest)):
        if name.endswith(".log"):
            try:
                with open(os.path.join(dest, name), encoding="utf-8") as f:
                    for e in json.load(f):
                        line = e.get("data", "").rstrip()
                        if line and not any(k in line for k in ("SyntaxWarning", "NbConvertApp",
                                                                 "re.sub(", "Escape underscores")):
                            log.append(line)
            except Exception:
                log.append("(日志不是 JSON，直接打开看：" + name + ")")
    if show:
        say("== 云端日志 ==")
        say("\n".join(log))
        say("✓ 结果在 " + dest)
    return "\n".join(log)


# ---------- 一键开通 ----------

def step(n, total, title):
    say(f"\n[{n}/{total}] {title}")


def pip_install():
    py = venv_bin("python")
    base = [py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "kaggle", "six"]
    say("  正在安装 kaggle 官方工具（约 1 分钟）...")
    if subprocess.run(base + ["--timeout", "30", "--retries", "2"]).returncode == 0:
        return True
    say("  官方源太慢或失败，改用清华镜像重试...")
    return subprocess.run(base + ["-i", MIRROR]).returncode == 0


def gputest():
    slug = "kgpu-test-" + time.strftime("%m%d-%H%M%S")  # 每次新名字，避开「验证前建的任务不能联网」
    folder = os.path.join(ROOT, "tasks", slug)
    write_task(folder, slug)
    push(folder)
    state = wait(meta_id(folder))
    log = fetch(folder, show=False)
    m = re.search(r"devices:\s*(\d+)", log)
    gpus = int(m.group(1)) if m else 0
    say("\n========== 测试结果 ==========")
    ok_gpu = "NO GPU" not in log and ("Tesla" in log or gpus > 0)
    ok_net = "internet OK" in log
    say(("✓" if ok_gpu else "✗") + " GPU：" + (f"拿到 {gpus or '?'} 张 Tesla T4" if ok_gpu else "没有 GPU"))
    say(("✓" if ok_net else "✗") + " 联网：" + ("正常" if ok_net else "不通"))
    if ok_gpu and ok_net:
        say("\n🎉 开通成功！以后这样用：")
        say("   python kgpu.py new my-job my-job   → 改 my-job/main.py → python kgpu.py run my-job")
        return True
    say("\n还差一步：多半是还没做手机验证。")
    say("  1. 打开 https://www.kaggle.com/settings → Phone verification，用真实手机号验证")
    say("  2. 验证后运行：python kgpu.py gputest（会自动用新名字重测）")
    if state != "COMPLETE":
        say("  （任务状态：" + state + "，日志在 " + os.path.join(folder, "output") + "）")
    return False


def setup():
    total = 5
    say("Kaggle 免费 GPU 一键开通（每周 30 小时双卡 T4）")
    step(1, total, "检查 Python")
    if sys.version_info < (3, 9):
        die("Python 版本太低（需要 3.9+），请到 https://www.python.org/downloads/ 安装新版。")
    say(f"  ✓ Python {sys.version.split()[0]}")

    step(2, total, "安装 kaggle 官方工具（装在本目录 .venv，不影响系统）")
    if not venv_bin("python"):
        if subprocess.run([sys.executable, "-m", "venv", VENV]).returncode != 0:
            die("创建虚拟环境失败。Linux 上先装 python3-venv。")
    if not venv_bin("kaggle") and not pip_install():
        die("安装失败，请检查网络后重新运行。")
    say("  ✓ " + (kaggle("--version") or "").strip())

    step(3, total, "登录 Kaggle 账号")
    user = username(required=False)
    if not user:
        say("  还没有账号的话，先去 https://www.kaggle.com 注册（免费）。")
        say("  接下来会自动打开浏览器，点同意授权即可。")
        pause("  准备好了按回车...")
        subprocess.run([kaggle_bin(), "auth", "login"])
        user = username(required=False)
        if not user:
            die("登录没有完成。重新运行本脚本再试一次。")
    say(f"  ✓ 已登录：{user}")

    step(4, total, "手机验证（必须在网页上自己做，脚本做不了）")
    say("  不验证：任务不会报错，但没有 GPU、不能联网。")
    say("  位置：kaggle.com → 右上角头像 → Settings → Phone verification（用真实手机号）")
    ans = pause("  已经验证过直接回车；还没验证输入 o 回车，帮你打开网页：")
    if ans.strip().lower() == "o":
        webbrowser.open("https://www.kaggle.com/settings")
        pause("  验证完成后回车继续...")

    step(5, total, "提交一个 GPU 测试任务，确认真的能用")
    say((kaggle("quota", quiet=True) or "").strip())
    gputest()


def main(argv):
    args = [a for a in argv[1:] if a != "--yes"]
    if not args or args[0] in ("-h", "--help", "help"):
        say(__doc__)
        return
    cmd = args[0]
    if cmd == "setup":
        setup()
    elif cmd == "gputest":
        gputest()
    elif cmd == "doctor":
        say("✓ kaggle 工具：" + kaggle_bin())
        say((kaggle("--version") or "").strip())
        say("✓ 已登录：" + username())
        say(kaggle("quota") or "")
        say("提示：能看到额度不代表能用 GPU；跑 python kgpu.py gputest 确认。")
    elif cmd == "quota":
        say(kaggle("quota") or "")
    elif cmd == "new" and len(args) >= 3:
        write_task(args[1], args[2])
        say("下一步：改 main.py，再运行 python kgpu.py run " + args[1])
    elif cmd == "run" and len(args) >= 2:
        folder = args[1]
        push(folder)
        if "--no-wait" in args:
            say("稍后运行：python kgpu.py fetch " + folder)
            return
        state = wait(meta_id(folder))
        say(("✓ " if state == "COMPLETE" else "✗ ") + "任务结束：" + state)
        fetch(folder)
    elif cmd == "fetch" and len(args) >= 2:
        fetch(args[1])
    else:
        say(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        say("\n已取消。")
