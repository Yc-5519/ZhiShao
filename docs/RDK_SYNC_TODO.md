# RDK X5 同步与验收说明

默认策略：先同步到 RDK 测试目录，不覆盖正式目录。

```text
RDK 正式目录：/home/sunrise/ZhiShao_V2
RDK 测试目录：/home/sunrise/ZhiShao_V2_codex_test
Windows 工作区：F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5
```

## 基本原则

- 不直接覆盖 `/home/sunrise/ZhiShao_V2`。
- 先把 Codex 修改同步到 `/home/sunrise/ZhiShao_V2_codex_test`。
- `.env`、日志、缓存、数据库、模型文件和生成图片不作为普通代码同步目标。
- RDK 测试目录验证通过后，再单独决定是否替换正式目录。

## 同步流程

1. 在 RDK 上确认 IP：

```bash
hostname -I
```

2. 在 Windows 测试 SSH：

```powershell
ssh sunrise@<RDK_IP>
```

3. 在 Codex 工作区检查改动：

```powershell
git status --short
git diff
```

4. 确保 RDK 测试目录存在：

```bash
mkdir -p /home/sunrise/ZhiShao_V2_codex_test
```

5. 同步 RDK 开发区到测试目录：

```powershell
scp -r "F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5\rdk_app\*" sunrise@<RDK_IP>:/home/sunrise/ZhiShao_V2_codex_test/
```

不要同步 `.env` 的真实内容，不要同步模型、日志、数据库、缓存、图片或 GIF。

## RDK 测试目录验证

进入测试目录：

```bash
cd /home/sunrise/ZhiShao_V2_codex_test
```

只读检查：

```bash
python3 -m py_compile main.py settings.py brain/brain_client.py services/incident_monitor.py
python3 -m unittest discover -s tests
```

部署前自检：

```bash
python3 preflight_check.py
```

常驻服务检查：

```bash
systemctl is-active zhishao-rdk-test zhishao-tunnel zhishao-brain-tunnel
```

本地健康检查：

```bash
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:19000/health
```

飞书验证：

```text
@智哨管家 系统自检
@智哨管家 监控链接
@智哨管家 他在干什么
```

## 云服务器验证

云服务器应保持以下服务运行：

```text
zhishao-brain
zhishao-auth
nginx
```

在云服务器上检查：

```bash
systemctl is-active zhishao-brain zhishao-auth nginx
curl http://127.0.0.1:9000/health
```

公网入口检查：

```text
http://124.222.118.121/
```

未登录应进入登录页；登录后应打开看护页。

## 云端 VLM 验收标准

- RDK `curl http://127.0.0.1:19000/health` 返回 `200`。
- 返回 JSON 中 `ok=true`。
- 返回 JSON 中 `dashscope_configured=true`。
- Windows 电脑关闭后，飞书“系统自检”和 VLM 问答仍可用。
- 云服务器公网不开放 `9000` 端口，VLM 只通过 SSH 隧道访问。

## 替换正式目录前检查

只有测试目录验证通过后，才考虑替换正式目录。替换前至少确认：

- Git diff 已审查。
- RDK 测试目录运行正常。
- `zhishao-rdk-test`、`zhishao-tunnel`、`zhishao-brain-tunnel` 均为 `active`。
- 云端 `zhishao-brain` `/health` 正常。
- 飞书消息收发正常。
- 摄像头和云台验证正常。
- 已备份 `/home/sunrise/ZhiShao_V2`。

正式目录替换属于高风险操作，需要单独确认后再执行。
