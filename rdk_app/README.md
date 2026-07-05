# RDK App

这是 RDK X5 主程序开发区，来源于：

```text
_import_rdk/ZhiShao_V2/
```

后续 RDK 侧功能开发优先在本目录完成。原始导入目录 `_import_rdk/` 保留为基线，不直接覆盖。

## 主要入口

```text
main.py
```

主要模块：

```text
settings.py             配置加载
brain/brain_client.py   云端 VLM 大脑客户端
services/               Web、飞书、视觉、摔倒检测、跟随、日报、突发通知和存储服务
core/                   YOLO pose 解码、云台底层控制和工具
notify/                 飞书机器人封装
tests/                  单元测试
```

## 云端 VLM

当前主链路通过 RDK 本机地址访问云端 VLM：

```text
http://127.0.0.1:19000
```

该地址由 `zhishao-brain-tunnel` 转发到云服务器 `127.0.0.1:9000`。Windows VLM 只作为开发备用。

## 未纳入开发区的运行文件

以下文件需要在 RDK 测试环境中按需补齐，不提交到 Git：

```text
.env
logs/
__pycache__/
yolov8n-pose.bin
*.db
*.png
*.gif
```

## 验证建议

Windows Codex 工作区适合做静态检查和非硬件单测：

```powershell
python -m unittest discover -s rdk_app\tests
python -m py_compile rdk_app\preflight_check.py rdk_app\settings.py
```

RDK 测试目录适合做完整验证：

```bash
cd /home/sunrise/ZhiShao_V2_codex_test
python3 preflight_check.py
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:19000/health
```

摄像头、串口云台、BPU 模型和飞书长连接必须在 RDK X5 上验证。
