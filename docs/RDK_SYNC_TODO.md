# RDK X5 同步待办

当前 RDK X5 不在身边，暂不执行远程同步。

## 等 RDK 在身边后执行

1. 确认 RDK IP：

```bash
hostname -I
```

2. 在 Windows 测试 SSH：

```powershell
ssh sunrise@<RDK_IP>
```

3. 拉取 RDK 项目到当前工作区：

```powershell
scp -r sunrise@<RDK_IP>:/home/sunrise/ZhiShao_V2/* "F:\CodexWorkspace\Project_01_ZhiShao_RDK_X5\_import_rdk\"
```

4. 回到 Codex 项目，让 Codex 分析差异：

```text
请分析 _import_windows 和 _import_rdk 的差异，判断如何合并成统一项目结构。先给方案，不要直接覆盖文件。
```

## 注意

不要直接覆盖 RDK 的 `/home/sunrise/ZhiShao_V2`。先同步到测试目录，验证通过后再替换正式目录。
