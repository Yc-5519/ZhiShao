import threading
import time

import requests

from settings import (
    INCIDENT_ALERT_COOLDOWN_SECONDS,
    INCIDENT_BRAIN_BAD_SECONDS,
    INCIDENT_CAMERA_BAD_SECONDS,
    INCIDENT_CHECK_INTERVAL_SECONDS,
    INCIDENT_FRAME_STALE_SECONDS,
    INCIDENT_MONITOR_ENABLED,
    INCIDENT_NO_PERSON_SECONDS,
    INCIDENT_PUBLIC_BAD_SECONDS,
)


class IncidentMonitorService:
    """Watch important runtime signals and notify family when action is needed."""

    def __init__(
        self,
        store,
        runtime,
        frame_hub,
        brain,
        bot,
        now=None,
        sleep=None,
        check_interval_seconds=None,
        alert_cooldown_seconds=None,
        camera_bad_seconds=None,
        frame_stale_seconds=None,
        brain_bad_seconds=None,
        public_bad_seconds=None,
        no_person_seconds=None,
        public_check=None,
        enabled=None,
    ):
        self.store = store
        self.runtime = runtime
        self.frame_hub = frame_hub
        self.brain = brain
        self.bot = bot
        self.now = now or time.time
        self.sleep = sleep or time.sleep
        self.check_interval_seconds = (
            INCIDENT_CHECK_INTERVAL_SECONDS if check_interval_seconds is None else float(check_interval_seconds)
        )
        self.alert_cooldown_seconds = (
            INCIDENT_ALERT_COOLDOWN_SECONDS if alert_cooldown_seconds is None else float(alert_cooldown_seconds)
        )
        self.camera_bad_seconds = INCIDENT_CAMERA_BAD_SECONDS if camera_bad_seconds is None else float(camera_bad_seconds)
        self.frame_stale_seconds = INCIDENT_FRAME_STALE_SECONDS if frame_stale_seconds is None else float(frame_stale_seconds)
        self.brain_bad_seconds = INCIDENT_BRAIN_BAD_SECONDS if brain_bad_seconds is None else float(brain_bad_seconds)
        self.public_bad_seconds = INCIDENT_PUBLIC_BAD_SECONDS if public_bad_seconds is None else float(public_bad_seconds)
        self.no_person_seconds = INCIDENT_NO_PERSON_SECONDS if no_person_seconds is None else float(no_person_seconds)
        self.public_check = public_check or self._default_public_check
        self.enabled = INCIDENT_MONITOR_ENABLED if enabled is None else bool(enabled)
        self._bad_since = {}
        self._active = set()
        self._last_alert_at = {}
        self._running = False
        self._thread = None

    def start(self):
        if not self.enabled or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="incident-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self):
        while self._running:
            try:
                self.check_once()
            except Exception as exc:
                self._record_event(
                    "incident_monitor_error",
                    f"突发情况巡检异常：{exc}",
                    "warning",
                    {"error": str(exc)},
                )
            self.sleep(self.check_interval_seconds)

    def check_once(self):
        if not self.enabled:
            return
        state = self.runtime.snapshot()
        self._check_camera(state)
        self._check_brain()
        self._check_public_gateway(state)
        self._check_no_person(state)

    def _check_camera(self, state):
        raw_age = self._safe_age(self.frame_hub.raw_age)
        skeleton_age = self._safe_age(self.frame_hub.skeleton_age)
        camera_ok = bool(state.get("camera_ok"))
        stale = raw_age > self.frame_stale_seconds and skeleton_age > self.frame_stale_seconds
        unhealthy = (not camera_ok) or stale
        reason = state.get("camera_message") or "摄像头状态异常"
        if stale:
            reason = f"{reason}；画面已经 {raw_age:.0f}s 未更新"
        self._handle_condition(
            key="camera",
            unhealthy=unhealthy,
            threshold=self.camera_bad_seconds,
            alert_title="智哨突发情况：摄像头异常",
            alert_message=(
                f"检测到摄像头可能断开、被遮挡或位置异常。\n"
                f"状态：{reason}\n"
                "请先检查摄像头电源、USB/排线、镜头是否被遮挡，确认设备没有被碰倒。"
            ),
            recover_title="智哨突发情况已恢复：摄像头正常",
            recover_message="摄像头画面已经恢复更新，系统继续看护。",
            event_type="incident_camera",
        )

    def _check_brain(self):
        try:
            result = self.brain.health_check() or {}
            ok = bool(result.get("ok"))
            detail = result.get("detail") or result.get("label") or "未返回详情"
        except Exception as exc:
            ok = False
            detail = str(exc)
        self._handle_condition(
            key="brain",
            unhealthy=not ok,
            threshold=self.brain_bad_seconds,
            alert_title="智哨突发情况：VLM 大脑连接异常",
            alert_message=(
                f"RDK 暂时连不上 VLM 大脑。\n"
                f"详情：{detail}\n"
                "本地看护、骨架检测和基础告警仍会继续；复杂画面问答可能暂时不可用。"
            ),
            recover_title="智哨突发情况已恢复：VLM 大脑已连接",
            recover_message=f"VLM 大脑健康检查恢复正常：{detail}",
            event_type="incident_brain",
        )

    def _check_public_gateway(self, state):
        public_url = (state.get("public_monitor_url") or "").strip()
        if not public_url:
            return
        try:
            ok = bool(self.public_check(public_url))
            detail = public_url
        except Exception as exc:
            ok = False
            detail = f"{public_url} {exc}"
        self._handle_condition(
            key="public_gateway",
            unhealthy=not ok,
            threshold=self.public_bad_seconds,
            alert_title="智哨突发情况：公网看护入口异常",
            alert_message=(
                f"公网入口暂时访问异常：{detail}\n"
                "局域网入口和 RDK 本地服务可能仍在运行。请检查云服务器、隧道服务或网络。"
            ),
            recover_title="智哨突发情况已恢复：公网入口可访问",
            recover_message=f"公网看护入口已恢复：{public_url}",
            event_type="incident_public_gateway",
        )

    def _check_no_person(self, state):
        target_count = int(state.get("target_count", 0) or 0)
        seen_before = bool(str(state.get("last_seen_time") or "").strip())
        self._handle_condition(
            key="no_person",
            unhealthy=seen_before and target_count <= 0,
            threshold=self.no_person_seconds,
            alert_title="智哨突发情况：长时间没有看到人",
            alert_message=(
                "系统长时间没有看到人，也没有看到可信人体目标。\n"
                "可能原因：老人离开画面、摄像头被移动、摄像头倾倒、光线太暗或被遮挡。\n"
                "请先通过电话确认安全，再检查摄像头角度和现场环境。"
            ),
            recover_title="智哨突发情况已恢复：重新看到人体目标",
            recover_message="系统已经重新看到可信人体目标，继续正常看护。",
            event_type="incident_no_person",
        )

    def _handle_condition(
        self,
        key,
        unhealthy,
        threshold,
        alert_title,
        alert_message,
        recover_title,
        recover_message,
        event_type,
    ):
        now = self.now()
        if unhealthy:
            self._bad_since.setdefault(key, now)
            if now - self._bad_since[key] < threshold:
                return
            last_alert = self._last_alert_at.get(key, -10**12)
            if key in self._active and now - last_alert < self.alert_cooldown_seconds:
                return
            self._send_alert(key, alert_title, alert_message, event_type, "warning")
            return

        self._bad_since.pop(key, None)
        if key in self._active:
            self._send_alert(key, recover_title, recover_message, f"{event_type}_recovered", "info", recovered=True)

    def _send_alert(self, key, title, message, event_type, level, recovered=False):
        content = (
            f"{message}\n\n"
            f"时间：{self.store.now_text()}\n"
            "提示：如果现场可能有危险，请优先电话或语音确认，再决定是否查看监控页面。"
        )
        try:
            self.bot.send_webhook(title, content)
        finally:
            self._record_event(event_type, message, level, {"condition": key})
            if not recovered:
                self.store.add_metrics(alerts_sent_count=1)
                self._active.add(key)
                self._last_alert_at[key] = self.now()
            else:
                self._active.discard(key)
                self._last_alert_at.pop(key, None)

    def _record_event(self, event_type, message, level, data):
        self.store.record_event(event_type, message, level, data)

    def _safe_age(self, getter):
        try:
            return float(getter())
        except Exception:
            return 999.0

    def _default_public_check(self, public_url):
        health_url = f"{public_url.rstrip('/')}/health"
        response = requests.get(health_url, timeout=3)
        return response.status_code in (200, 401, 403)
