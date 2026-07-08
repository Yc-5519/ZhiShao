# ZhiShao - RDK X5 Privacy-Aware Smart Care System

ZhiShao is a smart care system built around the RDK X5 edge computing board. It combines local human pose detection, servo pan-tilt tracking, cloud visual reasoning, a mobile-friendly web dashboard, and Feishu notifications to support safer home care while reducing unnecessary exposure of real camera footage.

The project is designed for scenarios where older adults may live alone or spend long periods without direct family supervision. Instead of continuously exposing raw video, ZhiShao uses skeletal pose, status summaries, and privacy-aware visual review as the default interaction mode.

## Core Capabilities

- Local human pose detection on RDK X5 using YOLOv8 Pose.
- Skeleton-based privacy view instead of always showing raw camera footage.
- Fall risk detection with event records and Feishu notifications.
- Servo-controlled pan-tilt tracking to reduce blind spots from fixed camera angles.
- Target locking and short-term reacquisition after temporary disappearance.
- Cloud visual reasoning through DashScope Qwen-VL for privacy review, scene understanding, Q&A, and daily summaries.
- Public web access through a cloud gateway with user login.
- Feishu assistant for status checks, monitor links, daily summaries, recent events, and care commands.
- Admin-managed cloud accounts with password hashes stored on the cloud server, not on the RDK device.

## System Architecture

```text
Home environment
  -> Camera
  -> RDK X5 edge application
       - YOLOv8 Pose human pose detection
       - skeleton view generation
       - fall risk state machine
       - servo pan-tilt control
       - event recording
  -> Cloud gateway
       - public entry
       - user login
       - reverse tunnel to RDK web dashboard
  -> Cloud visual brain
       - DashScope / Qwen-VL
       - privacy review
       - scene understanding
       - Q&A and summaries
  -> User interfaces
       - Web dashboard
       - Feishu assistant
       - mobile browser access
```

## Repository Layout

```text
rdk_app/          Main RDK X5 edge application
cloud_auth/       Cloud login and user management gateway
windows_brain/    Local Windows VLM service for development fallback
docs/             Architecture, API, deployment, and operation documents
_import_rdk/      Original imported RDK baseline kept for reference
_import_windows/  Original imported Windows VLM baseline kept for reference
```

## Runtime Components

### RDK X5 Edge Application

The RDK application runs the camera pipeline, YOLOv8 Pose inference, target tracking, fall risk detection, servo pan-tilt control, event recording, web dashboard, and Feishu command handling.

The formal runtime path on the RDK device is:

```text
/home/sunrise/ZhiShao_V2
```

The formal systemd service is:

```text
zhishao-rdk
```

### Cloud Gateway

The cloud gateway provides public access and user authentication before traffic reaches the RDK dashboard. User accounts are managed on the cloud server, and passwords are stored as hashes.

Main components:

```text
cloud_auth/
nginx
zhishao-auth
```

### Cloud Visual Brain

The cloud visual brain provides VLM capabilities through DashScope Qwen-VL. The RDK accesses it through a local forwarded endpoint so that the cloud VLM service does not need to expose its model port directly to the public network.

Main chain:

```text
RDK brain_client.py
  -> http://127.0.0.1:19000
  -> SSH tunnel
  -> cloud server 127.0.0.1:9000
  -> DashScope / Qwen-VL
```

## User Interaction

### Web Dashboard

The web dashboard shows:

- skeleton care view
- current care status
- target lock and tracking status
- pan-tilt controls
- recent events
- daily summary entry
- privacy-aware raw view request flow

### Feishu Assistant

Typical commands:

```text
系统自检
监控链接
说明书
现在是否安全
最近事件
日报
锁定当前人物
取消锁定
暂停跟随
恢复跟随
云台回中
临时查看真实画面
关闭真实画面
```

Safety confirmation replies first state the current safety status, then mention whether high-risk events occurred today, and include a desensitized skeleton GIF when available.

## Privacy Design

ZhiShao is designed around privacy-first care:

- Raw camera footage is not shown by default.
- The default view uses skeletons, target states, and event summaries.
- Temporary raw view requires explicit user confirmation.
- Privacy review is performed before opening raw view when configured.
- Feishu replies prefer text conclusions and desensitized skeleton evidence.
- The system does not rely on face recognition for target locking.

## Deployment Notes

Secrets and local runtime files must stay outside Git:

```text
.env
logs/
*.db
*.bin
*.png
*.gif
private keys
DashScope keys
Feishu tokens or webhooks
login passwords
```

The YOLOv8 Pose BPU model file should remain on the RDK device and should not be committed to the repository.

## Main Documents

```text
docs/ARCHITECTURE.md          System architecture
docs/API_CONTRACT.md          Cloud VLM API contract
docs/CLOUD_AUTH_GATEWAY.md    Cloud login gateway
docs/DEVELOPMENT_SETUP.md     Development and operation notes
docs/RDK_SYNC_TODO.md         RDK synchronization notes
```

## Project Goal

ZhiShao turns passive monitoring into active care. It aims to detect risk earlier, reduce blind spots with servo pan-tilt tracking, keep family members informed through web and Feishu, and preserve dignity by avoiding unnecessary raw video exposure.
