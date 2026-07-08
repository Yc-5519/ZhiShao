# ZhiShao - RDK X5 Privacy-Aware Smart Care System

ZhiShao is a smart care system for home elder care. It uses the RDK X5 as the edge computing core, combines local human pose detection with a servo pan-tilt camera, and provides web and Feishu interactions for family members.

The project focuses on two real needs at the same time:

- Detect safety risks such as falls, abnormal posture, camera failure, and long periods without a visible person.
- Reduce unnecessary exposure of raw camera footage by using skeleton views, status summaries, and privacy review.

## Highlights

- Runs human pose detection locally on RDK X5 with YOLOv8 Pose.
- Shows a privacy-friendly skeleton view by default instead of continuous raw video.
- Detects fall risks from body keypoints and records care events.
- Sends Feishu reminders for confirmed high-risk situations and device exceptions.
- Uses a servo pan-tilt platform to follow the target person and reduce fixed-view blind spots.
- Supports target locking, short-term reacquisition, and duplicate target suppression.
- Provides a mobile-friendly web dashboard with login protection through a cloud gateway.
- Uses DashScope Qwen-VL Max for privacy review, scene understanding, Q&A, and daily summaries.
- Keeps user accounts on the cloud server; passwords are stored as hashes and not on the RDK device.

## System Overview

```text
Camera and servo pan-tilt
  -> RDK X5 edge application
       -> YOLOv8 Pose human pose detection
       -> skeleton view generation
       -> fall and abnormal-state detection
       -> target tracking and pan-tilt control
       -> event recording
       -> local web dashboard and Feishu commands

RDK X5
  -> SSH tunnel
  -> cloud gateway and cloud visual service
       -> user login
       -> public web access
       -> DashScope / Qwen-VL Max

Family members
  -> mobile browser or PC browser
  -> Feishu assistant
```

## Repository Layout

```text
rdk_app/          RDK X5 edge application
cloud_auth/       Cloud login and user management gateway
windows_brain/    Local visual service fallback for development
docs/             Architecture, API, deployment, and operation documents
_import_rdk/      Imported RDK baseline kept for reference
_import_windows/  Imported Windows baseline kept for reference
```

## Runtime Components

### RDK X5 Edge Application

The RDK application is responsible for camera capture, YOLOv8 Pose inference, skeleton rendering, fall-risk detection, target tracking, servo pan-tilt control, event storage, web dashboard, and Feishu command handling.

Formal runtime path on the RDK device:

```text
/home/sunrise/ZhiShao_V2
```

Formal systemd service:

```text
zhishao-rdk
```

### Cloud Gateway

The cloud gateway provides public access and login protection before traffic reaches the RDK dashboard. User accounts are created and managed by an administrator on the cloud server.

Main components:

```text
cloud_auth/
nginx
zhishao-auth
```

### Cloud Visual Service

The cloud visual service provides higher-level visual reasoning through DashScope Qwen-VL Max. The RDK accesses it through a local forwarded address, so the model service port does not need to be exposed directly to the public network.

Main chain:

```text
RDK brain_client.py
  -> http://127.0.0.1:19000
  -> SSH tunnel
  -> cloud server 127.0.0.1:9000
  -> DashScope / Qwen-VL Max
```

## User Interfaces

### Web Dashboard

The dashboard provides:

- skeleton care view
- current safety state
- target ID and lock status
- pan-tilt control buttons
- fall and abnormal-state records
- recent events
- daily summary entry
- temporary raw-view request with privacy review

### Feishu Assistant

Typical commands:

```text
说明书
系统自检
监控链接
当前是否安全
当前动作
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

When the user asks whether the current situation is safe, the assistant first reports the current state, then mentions whether high-risk reminders occurred today. When skeleton evidence is available, it can attach a desensitized skeleton GIF instead of exposing raw camera footage.

## Privacy Design

ZhiShao is designed around privacy-aware care:

- Raw camera footage is not shown by default.
- The default view uses skeletons, target states, and event summaries.
- Temporary raw view requires explicit user confirmation.
- Cloud visual review can check privacy risk before raw view is opened.
- Feishu replies prefer text conclusions and desensitized skeleton evidence.
- Target locking does not rely on face recognition.

## Safety and Device Exception Handling

The system records and reports key care situations:

- suspected fall or high-risk posture
- camera disconnected or unable to read frames
- long periods without a visible reliable person
- recovery after the target is visible again
- public gateway or service connectivity abnormalities

For fall-related events, the system prioritizes safety confirmation and provides family members with concise status information and available desensitized evidence.

## Main Documents

```text
docs/ARCHITECTURE.md          System architecture
docs/API_CONTRACT.md          Cloud visual service API contract
docs/CLOUD_AUTH_GATEWAY.md    Cloud login gateway
docs/DEVELOPMENT_SETUP.md     Development and operation notes
docs/FOLLOW_STABILITY_TEST.md Follow and stability test notes
docs/RDK_SYNC_TODO.md         RDK synchronization notes
```

## Project Goal

ZhiShao turns passive monitoring into active care. It helps family members know whether an older adult is safe, while preserving dignity by avoiding unnecessary raw-video exposure.
