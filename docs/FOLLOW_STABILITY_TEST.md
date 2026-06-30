# 智哨人物跟随稳定性测试说明

本文用于比赛前验证 RDK 测试目录中的人物跟随能力。默认测试目录为：

```text
/home/sunrise/ZhiShao_V2_codex_test
```

不要覆盖正式目录：

```text
/home/sunrise/ZhiShao_V2
```

## 测试前检查

1. 确认测试服务运行：

```bash
systemctl is-active zhishao-rdk-test
curl http://127.0.0.1:5000/health
```

2. 打开公网看护页并登录：

```text
http://124.222.118.121/
```

3. 飞书发送：

```text
系统自检
监控链接
锁定当前人物
```

## 五个固定测试场景

每个场景建议测试 1 分钟，测试后记录：是否抖动、是否滞后、是否切错人、是否能接回、是否过冲。

| 场景 | 操作 | 通过标准 |
| --- | --- | --- |
| 慢走 | 被看护人从画面左侧慢慢走到右侧，再走回中间 | 云台平滑跟随，不频繁来回小幅抖动 |
| 快走 | 被看护人较快横向通过画面 | 云台能跟上主体方向，不长期丢失目标 |
| 横向穿越 | 被看护人从画面边缘进入并穿过中心 | 画面中心附近能重新稳定住目标 |
| 多人同框 | 另一个人短暂进入画面，锁定目标继续移动 | 系统优先保持锁定人物，不明显切到新人 |
| 短暂遮挡 | 锁定人物离开或被遮挡 3 到 6 秒后返回 | 系统能重新接回锁定目标，飞书锁定状态仍合理 |

## 只允许调的参数

如果实机效果不理想，优先只调整以下环境变量，不改摄像头、串口、端口、模型路径或飞书配置：

```text
ZHISHAO_PTZ_DEADZONE_X
ZHISHAO_PTZ_DEADZONE_Y
ZHISHAO_PTZ_KP_X
ZHISHAO_PTZ_KP_Y
ZHISHAO_PTZ_MAX_STEP_X
ZHISHAO_PTZ_MAX_STEP_Y
ZHISHAO_TARGET_LOCK_REACQUIRE_SECONDS
ZHISHAO_PTZ_LOST_PREDICT_SECONDS
```

调参方向：

- 抖动明显：增大 deadzone，或降低 kp。
- 跟随滞后：适当提高 kp，或提高 max step。
- 走快丢失：适当提高 max step，保留短时预测时间。
- 多人切错：先使用“锁定当前人物”，必要时开启锁定后再演示。
- 短暂消失接不回：适当提高锁定重识别时间。

每次只改一类参数，重启服务后重新测试同一个场景：

```bash
sudo systemctl restart zhishao-rdk-test
systemctl is-active zhishao-rdk-test
curl http://127.0.0.1:5000/health
```

## 回滚点

本阶段提交后，Git commit 就是回滚点。若跟随效果变差，先回到上一提交或恢复测试目录文件，不要直接替换正式目录。

回滚后仍需确认：

```bash
systemctl is-active zhishao-rdk-test
curl http://127.0.0.1:5000/health
```
