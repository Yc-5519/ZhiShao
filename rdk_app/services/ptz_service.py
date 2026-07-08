import time

import numpy as np

from settings import (
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    PTZ_COMMAND_INTERVAL,
    PTZ_DEADZONE_X,
    PTZ_DEADZONE_Y,
    PTZ_EDGE_FAST_RATIO,
    PTZ_EDGE_GAIN_BOOST,
    PTZ_KP_X,
    PTZ_KP_Y,
    PTZ_LOST_PREDICT_SECONDS,
    PTZ_MAX_STEP_X,
    PTZ_MAX_STEP_Y,
    PTZ_MIN_STEP_X,
    PTZ_MIN_STEP_Y,
    PTZ_NO_TARGET_SEARCH_DELAY_SECONDS,
    PTZ_NO_TARGET_SEARCH_DURATION_SECONDS,
)
from core.ptz_controller import ptz


class PTZService:
    """PTZ manual control, target following, and gentle search."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.follow_enabled = True
        self.last_seen = time.time()
        self.last_calc = time.time()
        self.last_cmd = 0.0
        self.search_start = None
        self.search_centered = False
        self.manual_hold_until = 0.0
        self.fall_hold_until = 0.0
        self.last_pan_direction = 0
        self.last_target_direction = 0
        self.kf_enabled = False
        self.x = np.zeros((4, 1), dtype=np.float32)
        self.p = np.eye(4, dtype=np.float32) * 10
        self.f = np.eye(4, dtype=np.float32)
        self.h = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        self.q = np.eye(4, dtype=np.float32) * 0.05
        self.r = np.eye(2, dtype=np.float32) * 2

    def _axis_delta(self, error, deadzone, kp, min_step, max_step, frame_size):
        if abs(error) <= deadzone:
            return 0.0
        boost = PTZ_EDGE_GAIN_BOOST if abs(error) >= frame_size * PTZ_EDGE_FAST_RATIO else 1.0
        delta = error * kp * boost
        delta = max(-max_step, min(max_step, delta))
        if abs(delta) < min_step:
            return 0.0
        return delta

    def _apply_follow_errors(self, error_x, error_y, x_gain=1.0, y_gain=1.0):
        moved = False
        delta_x = self._axis_delta(
            error_x,
            PTZ_DEADZONE_X,
            PTZ_KP_X * x_gain,
            PTZ_MIN_STEP_X,
            PTZ_MAX_STEP_X,
            CAMERA_WIDTH,
        )
        delta_y = self._axis_delta(
            error_y,
            PTZ_DEADZONE_Y,
            PTZ_KP_Y * y_gain,
            PTZ_MIN_STEP_Y,
            PTZ_MAX_STEP_Y,
            CAMERA_HEIGHT,
        )
        if delta_x:
            moved = ptz.set_pan(ptz.current_pan - delta_x) or moved
            self.last_pan_direction = -1 if delta_x > 0 else 1
        if delta_y:
            moved = ptz.set_tilt(ptz.current_tilt + delta_y) or moved
        return moved

    def _continue_last_direction_search(self, now):
        direction = self.last_target_direction or self.last_pan_direction
        if not direction:
            return False
        if now - self.last_cmd < PTZ_COMMAND_INTERVAL:
            self.runtime.update(ptz_mode="按最后方向寻找")
            return True
        moved = ptz.set_pan(self._current_pan() + direction * PTZ_MAX_STEP_X)
        if moved:
            self.last_cmd = now
        self.runtime.update(ptz_mode="按最后方向寻找")
        return True

    def _remember_target_side(self, cx):
        error_x = float(cx) - CAMERA_WIDTH / 2
        if abs(error_x) >= max(12.0, CAMERA_WIDTH * 0.03):
            self.last_target_direction = -1 if error_x > 0 else 1

    def set_follow_enabled(self, enabled):
        self.follow_enabled = bool(enabled)
        self.runtime.update(follow_enabled=self.follow_enabled, ptz_mode="跟随/待命" if enabled else "暂停")
        return True, "已恢复自动跟随与巡航。" if enabled else "已暂停自动跟随，云台保持当前位置。"

    def center(self):
        self.manual_hold_until = time.time() + 1.2
        if not ptz.center():
            return False, "云台回中失败：串口不可用或指令未发送成功。"
        self.kf_enabled = False
        self.runtime.update(ptz_mode="手动回中")
        return True, "云台已回到中位，自动跟随短暂停顿。"

    def _current_pan(self):
        return ptz.current_pan if ptz.current_pan >= 0 else 90

    def _current_tilt(self):
        return ptz.current_tilt if ptz.current_tilt >= 0 else 90

    def move(self, direction, step=15):
        self.manual_hold_until = time.time() + 1.2
        if not ptz.ensure_connected():
            return False, "云台串口不可用：请检查 /dev/ttyS1、供电和底板连接。"
        ok = False
        if direction == "left":
            ok = ptz.set_pan(self._current_pan() - step)
            label = "左转"
        elif direction == "right":
            ok = ptz.set_pan(self._current_pan() + step)
            label = "右转"
        elif direction == "up":
            ok = ptz.set_tilt(self._current_tilt() - 12)
            label = "上调"
        elif direction == "down":
            ok = ptz.set_tilt(self._current_tilt() + 12)
            label = "下调"
        else:
            return False, "未知云台方向。"
        if not ok:
            return False, f"云台{label}失败：指令未发送成功，请检查串口连接。"
        self.kf_enabled = False
        self.runtime.update(ptz_mode="手动微调")
        return True, f"云台已{label}。当前角度：水平 {self._current_pan()}°，俯仰 {self._current_tilt()}°。"

    def _init_kf(self, cx, cy):
        self.x = np.array([[cx], [cy], [0], [0]], dtype=np.float32)
        self.p = np.eye(4, dtype=np.float32) * 10
        self.kf_enabled = True

    def _predict(self, dt):
        if not self.kf_enabled:
            return
        self.f[0, 2] = dt
        self.f[1, 3] = dt
        self.x = self.f @ self.x
        self.p = self.f @ self.p @ self.f.T + self.q

    def _update(self, cx, cy):
        z = np.array([[cx], [cy]], dtype=np.float32)
        s = self.h @ self.p @ self.h.T + self.r
        k = self.p @ self.h.T @ np.linalg.inv(s)
        self.x = self.x + k @ (z - self.h @ self.x)
        self.p = self.p - k @ self.h @ self.p

    def follow(self, target):
        if not self.follow_enabled:
            return
        now = time.time()
        if now < self.fall_hold_until:
            self.runtime.update(ptz_mode="摔倒风险保持")
            return
        if now < self.manual_hold_until:
            self.runtime.update(ptz_mode="手动微调保持")
            return
        dt = max(now - self.last_calc, 0.001)
        self.last_calc = now
        self.last_seen = now
        self._remember_target_side(target["cx"])
        self.search_start = None
        self.search_centered = False
        if not self.kf_enabled:
            self._init_kf(target["cx"], target["cy"])
        else:
            self._predict(dt)
            self._update(target["cx"], target["cy"])
        error_x = float(self.x[0, 0]) - CAMERA_WIDTH / 2
        error_y = float(self.x[1, 0]) - CAMERA_HEIGHT / 2
        if now - self.last_cmd < PTZ_COMMAND_INTERVAL:
            return
        moved = self._apply_follow_errors(error_x, error_y)
        if moved:
            self.last_cmd = now
            self.runtime.update(ptz_mode="自动跟随")

    def focus_fall_target(self, target):
        if not self.follow_enabled:
            return
        now = time.time()
        if now < self.manual_hold_until:
            self.runtime.update(ptz_mode="摔倒风险确认")
            return
        self.last_seen = now
        self.fall_hold_until = now + 4.0
        self.search_start = None
        self.search_centered = False
        self.kf_enabled = False
        if now - self.last_cmd < PTZ_COMMAND_INTERVAL:
            self.runtime.update(ptz_mode="摔倒风险确认")
            return
        offset_y = float(target.get("cy", CAMERA_HEIGHT)) - CAMERA_HEIGHT * 0.52
        if offset_y <= CAMERA_HEIGHT * 0.08:
            self.runtime.update(ptz_mode="摔倒风险观察")
            return
        tilt_step = max(PTZ_MIN_STEP_Y, min(PTZ_MAX_STEP_Y, offset_y * PTZ_KP_Y * 1.2))
        target_tilt = min(125, self._current_tilt() + tilt_step)
        moved = ptz.set_tilt(target_tilt)
        if moved:
            self.last_cmd = now
        self.runtime.update(ptz_mode="摔倒风险确认")

    def on_no_target(self):
        if not self.follow_enabled:
            return
        now = time.time()
        if now < self.fall_hold_until:
            self.kf_enabled = False
            self.search_start = None
            self.runtime.update(ptz_mode="摔倒风险保持")
            return
        if now < self.manual_hold_until:
            self.runtime.update(ptz_mode="手动微调保持")
            return
        if self._continue_last_direction_search(now):
            self.kf_enabled = False
            return
        if self.kf_enabled and now - self.last_seen <= PTZ_LOST_PREDICT_SECONDS:
            dt = max(now - self.last_calc, 0.001)
            self.last_calc = now
            self._predict(dt)
            if now - self.last_cmd > PTZ_COMMAND_INTERVAL:
                error_x = float(self.x[0, 0]) - CAMERA_WIDTH / 2
                error_y = float(self.x[1, 0]) - CAMERA_HEIGHT / 2
                moved = self._apply_follow_errors(error_x, error_y, x_gain=0.85, y_gain=0.80)
                if moved:
                    self.last_cmd = now
            self.runtime.update(ptz_mode="短时外推")
            return
        no_target_elapsed = now - self.last_seen
        if no_target_elapsed < PTZ_NO_TARGET_SEARCH_DELAY_SECONDS:
            if (self.last_target_direction or self.last_pan_direction) and no_target_elapsed > PTZ_LOST_PREDICT_SECONDS:
                self.search_start = None
                self.kf_enabled = False
                self._continue_last_direction_search(now)
                return
            self.search_start = None
            self.kf_enabled = False
            self.runtime.update(ptz_mode="等待目标经过")
            return
        if self.search_start is None:
            self.search_start = now
        if now - self.search_start <= PTZ_NO_TARGET_SEARCH_DURATION_SECONDS:
            self.gentle_search(now=now)
            return
        self._center_after_search(now)

    def _center_after_search(self, now):
        self.kf_enabled = False
        if self.search_centered:
            self.runtime.update(ptz_mode="回中等待")
            return
        if now - self.last_cmd < 0.35:
            return
        if ptz.center():
            self.last_cmd = now
            self.search_centered = True
            self.runtime.update(ptz_mode="回中等待")

    def gentle_search(self, now=None):
        now = time.time() if now is None else now
        if now < self.manual_hold_until:
            self.runtime.update(ptz_mode="手动微调保持")
            return
        if self.search_start is None:
            self.search_start = now
            self.kf_enabled = False
        if now - self.last_cmd < 0.35:
            return
        elapsed = now - self.search_start
        pan = 90 + 32 * np.sin(0.45 * elapsed)
        tilt = 90 + 10 * np.sin(0.25 * elapsed)
        moved = ptz.set_pan(pan)
        moved = ptz.set_tilt(tilt) or moved
        if moved:
            self.last_cmd = now
            self.runtime.update(ptz_mode="无人搜索")

    def serial_ok(self):
        return bool(ptz.is_open())
