# ZhiShao RDK X5 Project

这是 ZhiShao / RDK X5 项目的 Codex 工作区。当前仓库用于开发、文档整理、验证和同步到 RDK 测试目录，不直接覆盖 RDK 或导入目录。

## 当前项目组成

```text
rdk_app/                             RDK 主程序开发区
windows_brain/                       VLM 服务开发备用区
cloud_auth/                          云服务器网页登录与用户管理网关
_import_rdk/ZhiShao_V2/              RDK 原始导入基线
_import_windows/vlm_service_cascade.py  Windows VLM 原始导入文件
```

## 主运行链路

比赛/演示主链路已经以云服务器 VLM 为主，Windows VLM 不再是必需运行组件：

```text
RDK 摄像头 / 姿态检测 / 飞书 / Web 看护页
  -> rdk_app/brain/brain_client.py
  -> RDK 本机 127.0.0.1:19000
  -> zhishao-brain-tunnel SSH 本地转发
  -> 云服务器 127.0.0.1:9000 zhishao-brain
  -> DashScope / Qwen-VL
  -> 分析结果返回 RDK
```

云服务器同时承担公网看护入口：

```text
公网用户
  -> http://124.222.118.121
  -> 云服务器 Nginx + cloud_auth 登录网关
  -> RDK 反向隧道 127.0.0.1:15000
  -> RDK Web 看护页
```

## RDK 主程序

开发位置：

```text
rdk_app/
```

作用：
- 在 RDK X5 上运行主程序。
- 负责摄像头采集、姿态检测、摔倒检测、云台跟随、Web 看护页、飞书交互、日报和突发情况通知。
- 通过 `brain/brain_client.py` 调用云端 VLM 大脑。

## 云端 VLM 大脑

当前主部署运行在云服务器：

```text
systemd 服务：zhishao-brain
监听地址：127.0.0.1:9000
RDK 访问地址：http://127.0.0.1:19000
```

作用：
- 提供 `/ask`、`/analyze`、`/summarize`、`/privacy_check`、`/health`。
- 调用 DashScope / Qwen-VL，为 RDK 提供视觉语言分析能力。
- 端口 `9000` 只在云服务器本机使用，不对公网开放。

`windows_brain/` 保留为本地开发备用区。只有调试 Windows 本地 VLM 时才需要启动它。

## 云服务器认证网关

开发位置：

```text
cloud_auth/
```

作用：
- 替代公网看护页的浏览器 Basic Auth 弹窗。
- 提供登录、退出登录、管理员用户管理和 Nginx `auth_request` 校验入口。
- 用户账号保存在云服务器 SQLite 数据库中，密码只保存哈希。
- RDK 不保存公网登录账号。

## 常驻服务

RDK 测试目录运行时应保持：

```text
zhishao-rdk-test       RDK 主程序
zhishao-tunnel         RDK Web 到云服务器的反向隧道
zhishao-brain-tunnel   RDK 到云端 VLM 的本地转发隧道
```

云服务器运行时应保持：

```text
zhishao-brain          云端 VLM 大脑
zhishao-auth           登录与用户管理网关
nginx                  公网入口反向代理
```

## 工作流

1. 功能开发优先修改 `rdk_app/`、`windows_brain/` 或 `cloud_auth/`。
2. 不移动、不覆盖 `_import_rdk/` 和 `_import_windows/`。
3. 修改完成后先查看 Git diff。
4. 默认同步到 RDK 测试目录 `/home/sunrise/ZhiShao_V2_codex_test`。
5. RDK 测试通过后，再决定是否替换正式目录 `/home/sunrise/ZhiShao_V2`。

更多说明：

```text
docs/ARCHITECTURE.md
docs/API_CONTRACT.md
docs/DEVELOPMENT_SETUP.md
docs/RDK_SYNC_TODO.md
```

## 注意

- 不提交 `.env`、日志、缓存、数据库、模型文件、图片和 GIF。
- 不把 DashScope Key、飞书密钥、SSH 私钥或网页登录密码写入代码。
- 修改端口、摄像头、串口、模型路径、服务启动方式前，需要单独说明影响。
