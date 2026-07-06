# 智哨 ZhiShao RDK X5 智能看护系统

智哨是一个运行在 RDK X5 上的智能看护项目。它用本地摄像头和姿态检测完成边缘侧看护，用云端 VLM 大脑完成复杂画面理解，并通过 Web 页面和飞书让家属查看状态、控制云台和接收提醒。

当前主运行目录已经切到 RDK 正式目录：

```text
/home/sunrise/ZhiShao_V2
```

当前正式服务：

```text
zhishao-rdk
```

测试目录仍保留，但不再作为主运行入口：

```text
/home/sunrise/ZhiShao_V2_test
```

## 已实现功能

- RDK 本地摄像头采集。
- RDK 本地 YOLO 姿态检测和人体骨架显示。
- 摔倒风险检测、状态机判断和云端复核。
- 云台自动跟随、人物锁定、短时丢失接回。
- 画面里 1 分钟没有人时，云台自动搜索；找不到就回中等待，不再因为“没人”直接发飞书报警。
- Web 看护页：状态、骨架画面、锁定状态、云台控制、最近事件、日报入口。
- 飞书管家：系统自检、监控链接、说明书、日报、最近事件、锁定人物、云台控制和问答。
- 云端 VLM：视觉问答、摔倒复核、隐私复核、日报总结。
- 公网入口：云服务器 Nginx + 登录网关 + RDK 隧道。
- 云端账号管理：管理员创建用户，密码哈希保存在云服务器，不保存在 RDK。

## 项目结构

```text
rdk_app/                         RDK 主程序开发区
windows_brain/                   Windows VLM 开发备用区
cloud_auth/                      云服务器登录与用户管理网关
docs/                            架构、接口、同步和测试文档
_import_rdk/ZhiShao_V2/          RDK 原始导入基线，只保留参考
_import_windows/                 Windows VLM 原始导入基线，只保留参考
outputs/                         输出占位目录
work/                            临时工作占位目录
```

不要移动、删除或覆盖 `_import_rdk/` 和 `_import_windows/`。它们是原始导入基线。

## 主运行链路

### 看护主链路

```text
RDK 摄像头
  -> RDK 姿态检测 / 摔倒检测 / 云台跟随
  -> RDK Web 看护页 + 飞书管家
  -> 用户查看状态、控制云台、接收提醒
```

### 云端 VLM 链路

```text
RDK brain_client.py
  -> http://127.0.0.1:19000
  -> zhishao-brain-tunnel
  -> 云服务器 127.0.0.1:9000 zhishao-brain
  -> DashScope / Qwen-VL
  -> 返回分析结果给 RDK
```

Windows VLM 现在只是开发备用，不是主运行依赖。Windows 电脑关闭后，普通看护、公网页面、飞书指令和云端 VLM 问答仍应可用。

### 公网访问链路

```text
公网用户
  -> http://124.222.118.121
  -> 云服务器 Nginx
  -> cloud_auth 登录校验
  -> RDK 反向隧道 127.0.0.1:15000
  -> RDK Web 看护页
```

## 常驻服务

RDK 上应保持：

```text
zhishao-rdk            正式 RDK 主程序
zhishao-tunnel         公网 Web 反向隧道
zhishao-brain-tunnel   RDK 到云端 VLM 的本地转发隧道
```

云服务器上应保持：

```text
zhishao-brain          云端 VLM 大脑
zhishao-auth           登录与用户管理服务
nginx                  公网入口反向代理
```

RDK 测试服务现在应保持停用：

```text
zhishao-rdk-test       inactive / disabled
```

## 快速检查

在 RDK 上检查正式服务：

```bash
systemctl is-active zhishao-rdk
systemctl is-active zhishao-tunnel zhishao-brain-tunnel
readlink /proc/$(systemctl show zhishao-rdk -p MainPID --value)/cwd
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:19000/health
```

期望：

```text
zhishao-rdk 为 active
工作目录为 /home/sunrise/ZhiShao_V2
RDK health 返回 200
VLM health 返回 200
```

公网检查：

```text
http://124.222.118.121/
```

未登录应跳转登录页；登录后应打开看护页。

飞书检查：

```text
@智哨管家 系统自检
@智哨管家 监控链接
@智哨管家 说明书
```

## 开发流程

当前允许直接在 RDK 正式目录修改：

```text
/home/sunrise/ZhiShao_V2
```

推荐流程：

1. 修改前先备份正式目录。
2. 只改源码、测试和文档。
3. 不读取、不打印、不提交 `.env`。
4. 不改摄像头、串口、端口、模型路径、飞书密钥、DashScope 密钥，除非明确需要。
5. 修改后在 RDK 正式目录运行检查。
6. 验证通过后，把正式目录源码反向同步回本地 `rdk_app/`。
7. 本地运行测试、提交 Git、推送 GitHub。

RDK 正式目录验证：

```bash
cd /home/sunrise/ZhiShao_V2
python3 -m py_compile main.py settings.py services/*.py brain/*.py
python3 -m unittest discover -s tests
sudo systemctl restart zhishao-rdk
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:19000/health
```

本地验证：

```powershell
python -m unittest discover -s rdk_app\tests
python -m py_compile rdk_app\main.py rdk_app\settings.py rdk_app\brain\brain_client.py
git diff --check
```

## 不要提交的内容

以下内容不能提交到 Git：

```text
.env
logs/
__pycache__/
*.db
*.bin
*.png
*.gif
SSH 私钥
DashScope Key
飞书密钥
网页登录密码
```

模型文件 `yolov8n-pose.bin` 应保留在 RDK 正式目录，不进入 Git。

## 重要文档

```text
docs/ARCHITECTURE.md          架构说明
docs/API_CONTRACT.md          云端 VLM 接口契约
docs/CLOUD_AUTH_GATEWAY.md    云端登录网关说明
docs/DEVELOPMENT_SETUP.md     开发与验证说明
docs/FOLLOW_STABILITY_TEST.md 人物跟随实机测试说明
docs/RDK_SYNC_TODO.md         RDK 同步与验收说明
```

## 当前维护重点

- 人物跟随稳定性：减少滞后、抖动、丢失和多人切错。
- Web 看护页流畅度：降低 RDK 编码压力和公网传输压力。
- 云端链路稳定性：确保 RDK 重启、云服务器重启后服务自动恢复。
- HTTPS + 域名：让公网入口更正式、更安全。
- 演示验收脚本：固定系统自检、监控链接、锁定人物、跟随、日报、问答等流程。
