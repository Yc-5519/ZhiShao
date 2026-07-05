# Windows Brain

这是 VLM 服务的本地开发备用区，来源于：

```text
_import_windows/vlm_service_cascade.py
```

当前主运行链路已经改为云服务器 `zhishao-brain`。Windows 电脑不再是 RDK 演示链路的必需组件。

## 提供接口

```text
/ask
/analyze
/summarize
/privacy_check
/health
```

接口契约见：

```text
docs/API_CONTRACT.md
```

## 启动前配置

需要通过环境变量配置 DashScope / Qwen-VL：

```text
DASHSCOPE_API_KEY
DASHSCOPE_URL
QWEN_VL_MODEL
```

不要把真实 API Key 写入代码或提交到 Git。

## 本地开发启动

```powershell
python windows_brain\vlm_service_cascade.py
```

默认监听：

```text
0.0.0.0:9000
```

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:9000/health
```

如需让 RDK 临时调用 Windows 本地服务，需要在 RDK `.env` 中显式覆盖 VLM URL。比赛/演示默认不使用这条链路。
