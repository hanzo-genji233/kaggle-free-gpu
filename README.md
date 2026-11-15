# kaggle-free-gpu

用 Kaggle 官方免费额度（**每周 30 小时双卡 T4 GPU**）跑批处理任务的一键脚本。
Windows、macOS 双击就能开通，Linux 也能用；只需要 Python 3.9+（没有的话启动器会帮你装）。

提交任务后可以关电脑，云端自己跑；跑完一条命令把结果下载回来。

## 免费额度

| 项目 | 额度 |
|---|---|
| GPU | 每周 30 小时，T4 × 2，各 15GB 显存 |
| TPU | 每周 20 小时 |
| 单次任务 | 最长 12 小时 |
| 重置 | 每周六 00:00 UTC（北京时间 08:00） |

## 一键开通（第一次用，约 15 分钟，大部分时间在排队）

1. 注册 [kaggle.com](https://www.kaggle.com) 账号（免费）。
2. 下载本仓库：点绿色 **Code** → **Download ZIP**，解压。
3. 双击启动器：
   - **Windows**：双击 `start-windows.bat`。没装 Python 会用 winget 自动装，装完再双击一次。
   - **Mac**：右键 `start-mac.command` → 打开（第一次要右键，绕过「无法验证开发者」提示）。
   - 命令行也行：`python kgpu.py setup`
4. 跟着窗口提示走，脚本会自动做完这 5 步：

   ```
   [1/5] 检查 Python
   [2/5] 安装 kaggle 官方工具（装在本目录 .venv，不影响系统；国内慢会自动换清华镜像）
   [3/5] 登录 Kaggle（自动打开浏览器，点同意）
   [4/5] 提醒你做手机验证（只能在网页上自己做）
   [5/5] 提交一个 GPU 测试任务，打印结果：
         ✓ GPU：拿到 2 张 Tesla T4
         ✓ 联网：正常
         🎉 开通成功！
   ```

**手机验证必须做**：Kaggle → 右上角头像 → Settings → Phone verification。
不验证也不会报错，但任务里没有 GPU、不能联网。验证后运行 `python kgpu.py gputest` 重测。

> Windows 上下面命令里的 `python` 不可用时，换成 `py`。

## 跑一个 GPU 任务

```bash
python kgpu.py new my-job my-job     # 新建任务文件夹 my-job（名字只用小写字母、数字、-）
# 打开 my-job/main.py，把你的代码写进「在这里写你的任务」
python kgpu.py run my-job            # 提交到双卡 T4 → 等待 → 结果下载到 my-job/output
```

其他命令：

| 命令 | 作用 |
|---|---|
| `python kgpu.py quota` | 查看剩余额度 |
| `python kgpu.py run <目录> --no-wait` | 只提交，不等待 |
| `python kgpu.py fetch <目录>` | 任务跑完后下载结果和日志 |
| `python kgpu.py doctor` | 检查工具、登录、额度 |
| `python kgpu.py gputest` | 再跑一次 GPU + 联网测试 |

- 产物要写到 `/kaggle/working/`，才能被下载。
- 模板 `main.py` 会先打印显卡和联网状态，方便确认环境。
- 跑完想收通知：在任务里读 `NOTIFY_WEBHOOK` 环境变量发 webhook。不要把 token 写进公开代码。

## 实测踩过的坑

1. **装完就崩，提示缺少 six 模块**：新版 kaggle 2.2.5 漏了这个依赖，一键脚本已自动补装。
2. **没做手机验证，任务也能「跑完」**：日志里会出现 `NO GPU: 找不到 nvidia-smi`，额度一分钟都不扣。
3. **验证前建的任务，验证后还是不能联网**：换一个新名字重新 `new` 一个任务（`gputest` 每次自动用新名字）。
4. **GPU 任务排队 10 分钟以上**：状态是 `QUEUED`，属于正常。
5. **偶发 `SSLError`**：脚本已自动重试。

## 适合 / 不适合

- 适合：音视频大批量转写（Whisper）、开源模型推理、量化、小模型微调、批量生图。
- 不适合：常驻服务（单次最长 12 小时）、公司或客户的敏感数据（会上传到云端）、几分钟的小任务。
- 保号：只用一个账号，不开小号；不挖矿，不做扫描。

## License

MIT
