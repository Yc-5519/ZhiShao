# 开发区与验证说明

本文说明当前 Codex 工作区的开发目录、云端 VLM 主链路和验证方式。

## 开发目录

```text
rdk_app/          RDK X5 主程序开发区
windows_brain/    VLM 服务开发备用区
cloud_auth/       云服务器网页登录与用户管理网关
```

`_import_rdk/` 和 `_import_windows/` 继续作为原始导入基线保留。后续新增功能、修复问题和整理代码时，优先修改开发区，不直接覆盖导入目录。

## RDK 主程序开发区

`rdk_app/` 来自 `_import_rdk/ZhiShao_V2/`，但不包含以下运行产物或敏感文件：

```text
.env
logs/
__pycache__/
*.bin
*.db
*.png
*.gif
```

RDK 测试目录需要自行补齐：
- `.env`：来自测试环境，不提交到 Git。
- `yolov8n-pose.bin`：模型文件，不作为普通 Git 文件提交。
- RDK 专用运行库，例如 `hobot_dnn`。
- 摄像头、串口云台和飞书配置。

## 云端 VLM 主链路

当前主链路不依赖 Windows VLM：

```text
RDK brain_client.py
-> http://127.0.0.1:19000
-> zhishao-brain-tunnel
-> 云服务器 http://127.0.0.1:9000
-> zhishao-brain
-> DashScope / Qwen-VL
```

RDK 侧 `.env` 应使用：

```text
ZHISHAO_VLM_BASE_URL=http://127.0.0.1:19000
```

不要把云服务器 `9000` 端口开放到公网。它只应在云服务器本机监听，由 RDK 通过 SSH 隧道访问。

## Windows VLM 开发备用

`windows_brain/` 来自 `_import_windows/vlm_service_cascade.py`。它用于本地开发或接口验证，不是当前主运行链路的必需组件。

运行前需要配置：

```text
DASHSCOPE_API_KEY
DASHSCOPE_URL
QWEN_VL_MODEL
```

`DASHSCOPE_API_KEY` 是敏感配置，不要写入代码或提交到 Git。

## 本地只读语法检查

在 Windows Codex 工作区可运行：

```powershell
python -m unittest discover -s rdk_app\tests
python -m py_compile rdk_app\preflight_check.py rdk_app\settings.py
git diff --check
```

Windows Codex 工作区只适合做静态检查和非硬件单测。摄像头、串口云台、BPU 模型和飞书长连接需要在 RDK X5 上验证。

## RDK 验证

默认目标仍是测试目录：

```text
/home/sunrise/ZhiShao_V2_codex_test
```

不要直接覆盖正式目录：

```text
/home/sunrise/ZhiShao_V2
```

RDK 测试目录中建议执行：

```bash
cd /home/sunrise/ZhiShao_V2_codex_test
python3 preflight_check.py
python3 -m py_compile main.py settings.py brain/brain_client.py services/incident_monitor.py
python3 -m unittest discover -s tests
```

服务状态验收：

```bash
systemctl is-active zhishao-rdk-test zhishao-tunnel zhishao-brain-tunnel
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:19000/health
```

云服务器验收：

```bash
systemctl is-active zhishao-brain zhishao-auth nginx
curl http://127.0.0.1:9000/health
```

同步和替换正式目录的详细流程见：

```text
docs/RDK_SYNC_TODO.md
```
