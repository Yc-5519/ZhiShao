# 云端 VLM 服务接口契约

本文记录 `zhishao-brain` 提供给 RDK 主程序调用的 HTTP 接口。当前主部署运行在云服务器 `127.0.0.1:9000`，RDK 通过 `zhishao-brain-tunnel` 在本机访问 `http://127.0.0.1:19000`。

`windows_brain/vlm_service_cascade.py` 保留为开发备用实现，接口应与云端服务保持一致。

## 通用约定

- RDK 侧基础地址：`http://127.0.0.1:19000`
- 云服务器本机地址：`http://127.0.0.1:9000`
- 上游模型：DashScope / Qwen-VL
- 图片字段使用 JPEG base64 或 multipart JPEG 文件。
- 失败时优先返回结构化 JSON，RDK 端再按保护策略兜底。
- 云服务器 `9000` 不对公网开放，只通过 SSH 隧道访问。

## POST /ask

用途：处理用户自然语言问答，可按需要携带当前画面。

请求 Content-Type：

```text
application/json
```

请求字段：

```json
{
  "question": "用户原始问题",
  "prompt": "RDK 端组装后的完整提示词",
  "image": "可选，JPEG base64 字符串"
}
```

成功返回字段：

```json
{
  "answer": "给用户的回答文本",
  "need_image": false
}
```

失败兜底：
- `prompt` 为空时返回 HTTP 400，并返回 `answer` 与 `need_image=false`。
- 模型返回无法解析为 JSON 时，服务清理原始文本后作为 `answer` 返回。
- 服务内部异常时返回 HTTP 500，并返回 `answer` 与 `need_image=false`。
- RDK 请求失败时，天气类问题会尝试本地天气兜底；其他问题由上层返回本地状态兜底。

## POST /analyze

用途：对 RDK 侧疑似高风险事件图片进行 VLM 复核，例如摔倒、滑倒或异常姿态。

请求 Content-Type：

```text
multipart/form-data
```

请求字段：

```text
image  JPEG 图片文件
```

成功返回字段：

```json
{
  "location": "场景或区域描述",
  "risk_level": "normal 或 critical",
  "description": "现场研判描述"
}
```

失败兜底：
- 缺少 `image` 文件时返回 HTTP 400，并返回默认 `location`、`risk_level=normal`、`description`。
- 模型返回无法解析为 JSON 时，服务返回 `risk_level=critical` 和模型原始描述，倾向保护性处理。
- 服务内部异常时返回 HTTP 500，并返回 `risk_level=critical`。
- RDK 请求失败时返回 `None`，由摔倒检测或告警流程决定后续动作。

## POST /summarize

用途：根据 RDK 活动日志生成简短日报或关怀总结。

请求 Content-Type：

```text
application/json
```

请求字段：

```json
{
  "log_content": "当天活动日志文本"
}
```

成功返回字段：

```json
{
  "summary": "日报总结文本"
}
```

失败兜底：
- `log_content` 缺失时，服务使用默认空活动记录文本。
- DashScope / Qwen-VL 暂无返回时，服务返回默认提示文本。
- RDK 请求失败时返回空字符串。

## POST /privacy_check

用途：判断当前真实摄像头画面是否适合短时间开放给家属查看。

请求 Content-Type：

```text
application/json
```

请求字段：

```json
{
  "image": "JPEG base64 字符串"
}
```

成功返回字段：

```json
{
  "safe_to_show": false,
  "risk_level": "safe/privacy_risk/uncertain/unknown/blocked",
  "reason": "通过或拒绝的具体原因",
  "confidence": 0.0,
  "evidence": ["最多若干条画面依据"],
  "block_type": "none/privacy_risk/uncertain/no_image/service_unavailable/parse_error"
}
```

失败兜底：
- 缺少 `image` 时返回 HTTP 400，并返回 `safe_to_show=false`、`block_type=no_image`。
- 模型不可用时返回 `safe_to_show=false`、`block_type=service_unavailable`。
- 模型 JSON 解析失败时返回 `safe_to_show=false`、`block_type=parse_error`。
- RDK 端连接失败、返回字段缺失或处理异常时，按保护策略拒绝开放真实画面。

## GET /health

用途：检查云端 VLM 大脑是否启动，以及 DashScope API Key 是否已配置。

请求字段：无。

成功返回字段：

```json
{
  "ok": true,
  "service": "ZhiShao Brain",
  "model": "当前模型名",
  "dashscope_configured": true,
  "endpoints": ["/ask", "/analyze", "/summarize", "/privacy_check"]
}
```

失败兜底：
- 云端服务未启动时，RDK 健康检查会连接失败。
- `dashscope_configured=false` 表示服务进程可用，但模型调用配置不完整。
