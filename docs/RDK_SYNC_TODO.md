# RDK X5 同步待办

当前默认策略：先同步到 RDK 测试目录，不覆盖正式目录。

```text
RDK 正式目录：/home/sunrise/ZhiShao_V2
RDK 测试目录：/home/sunrise/ZhiShao_V2_codex_test
Windows 工作区：F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5
```

## 基本原则

- 不直接覆盖 `/home/sunrise/ZhiShao_V2`。
- 先把 Codex 修改同步到 `/home/sunrise/ZhiShao_V2_codex_test`。
- 在测试目录完成启动和硬件验证后，再决定是否替换正式目录。
- `.env`、日志、缓存、数据库、模型文件和生成图片不作为普通代码同步目标。

## 等 RDK 在身边后执行

1. 在 RDK 上确认 IP：

```bash
hostname -I
```

2. 在 Windows 测试 SSH：

```powershell
ssh sunrise@<RDK_IP>
```

3. 如需重新拉取 RDK 正式目录到 Codex 导入区，先确认不会覆盖本地分析成果，再执行导入命令。

推荐拉取到 `_import_rdk/ZhiShao_V2` 之外的新临时目录做对比，确认后再合并：

```powershell
scp -r sunrise@<RDK_IP>:/home/sunrise/ZhiShao_V2 "F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5\work\ZhiShao_V2_from_rdk"
```

4. 在 Codex 工作区完成修改后，先查看 Git diff：

```powershell
git status --short
git diff -- README.md docs
```

5. 在 RDK 上创建测试目录：

```bash
mkdir -p /home/sunrise/ZhiShao_V2_codex_test
```

6. 从 Windows 同步到 RDK 测试目录。

如果后续整理出正式工作目录，例如 `rdk_app/`，优先同步该目录内容；在当前导入基线阶段，可按确认后的范围同步 `_import_rdk/ZhiShao_V2/`：

```powershell
scp -r "F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5\_import_rdk\ZhiShao_V2\*" sunrise@<RDK_IP>:/home/sunrise/ZhiShao_V2_codex_test/
```

7. 如需同步 Windows VLM 服务文件到 Windows 运行目录，先在 Windows 本机另行备份，再复制：

```powershell
Copy-Item -LiteralPath "F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5\_import_windows\vlm_service_cascade.py" -Destination "<Windows_VLM_运行目录>\vlm_service_cascade.py" -Force
```

## RDK 测试目录验证建议

在 RDK 测试目录执行前，先确认 `.env`、模型文件、摄像头、串口和飞书配置均来自测试环境或已明确授权。

```bash
cd /home/sunrise/ZhiShao_V2_codex_test
python3 -m py_compile main.py settings.py brain/brain_client.py
python3 -m unittest discover -s tests
```

硬件相关验证建议：

```bash
python3 main.py
```

观察项目是否能启动 Web、飞书、摄像头、云台和视觉线程。若测试目录验证失败，不要替换正式目录。

## 替换正式目录前检查

只有在测试目录验证通过后，才考虑替换正式目录。替换前至少确认：

- Git diff 已审查。
- RDK 测试目录运行正常。
- Windows VLM 服务 `/health` 正常。
- 飞书消息收发正常。
- 摄像头和云台验证正常。
- 已备份 `/home/sunrise/ZhiShao_V2`。

正式目录替换属于高风险操作，需要单独确认后再执行。
