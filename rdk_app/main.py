import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from brain.brain_client import brain
from notify.feishu_bot import bot
from services.app_service import AppService
from services.feishu_service import FeishuService
from services.incident_monitor import IncidentMonitorService
from services.ptz_service import PTZService
from services.report_service import ReportService
from services.runtime_state import FrameHub, RuntimeState
from services.store import Store
from services.vision_worker import VisionWorker
from services.web_dashboard import WebDashboard, get_lan_monitor_url, get_monitor_url, get_public_monitor_url

_MAIN_LOCK_HANDLE = None


def acquire_single_instance_lock():
    """Prevent two main.py processes from replying to the same Feishu event."""
    global _MAIN_LOCK_HANDLE
    try:
        import fcntl

        lock_path = "/tmp/zhishao_v3_main.lock"
        _MAIN_LOCK_HANDLE = open(lock_path, "w", encoding="utf-8")
        fcntl.flock(_MAIN_LOCK_HANDLE, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _MAIN_LOCK_HANDLE.write(str(os.getpid()))
        _MAIN_LOCK_HANDLE.flush()
        return True
    except BlockingIOError:
        print("[WARN] [系统] 检测到智哨主程序已在运行，本次启动已退出，避免飞书重复回复。")
        return False
    except Exception as e:
        print(f"[WARN] [系统] 单实例锁检查失败：{e}。为避免重复回复，本次启动已退出。")
        return False


def send_fall_alert(bot_client, store):
    def _send(description, location, evidence_path=None):
        image_key = ""
        if evidence_path:
            try:
                image_key = bot_client.upload_image(evidence_path) or ""
            except Exception as exc:
                print(f"[WARN] [飞书告警] 骨架证据图上传失败: {exc}")
        text = (
            "【智哨安心提醒】\n\n"
            f"发生时间：{store.now_text()}\n"
            f"疑似位置：{location}\n"
            f"系统研判：{description}\n\n"
            "看护建议：建议先电话或语音确认父母是否安好；如果联系不上，再通过安心看护页临时查看真实画面。\n"
            "隐私说明：默认不主动推送真实画面，优先使用状态结论和脱敏证据。"
        )
        bot_client.send_webhook("智哨安心提醒", text, image_key=image_key)
        store.add_metrics(alerts_sent_count=1)
        print("[INFO] [飞书告警] 安心提醒已推送。")

    return _send


def build_app():
    store = Store()
    runtime = RuntimeState()
    frame_hub = FrameHub()
    ptz_service = PTZService(runtime)
    report_service = ReportService(store, bot, brain)
    vision = VisionWorker(frame_hub, runtime, store, ptz_service, brain, send_fall_alert(bot, store))
    app_service = AppService(store, runtime, frame_hub, vision, ptz_service, report_service, brain, bot)
    monitor_url = get_monitor_url()
    runtime.update(
        monitor_url=monitor_url,
        public_monitor_url=get_public_monitor_url(),
        lan_monitor_url=get_lan_monitor_url(),
        fall_mode="保守",
        care_mode="边界看护",
    )
    web = WebDashboard(app_service)
    feishu = FeishuService(app_service, bot)
    incident_monitor = IncidentMonitorService(store, runtime, frame_hub, brain, bot)
    return store, runtime, frame_hub, ptz_service, report_service, vision, app_service, web, feishu, incident_monitor


if __name__ == "__main__":
    print("==============================================================")
    print("[START] [智哨 ZhiShao V3 · 有边界安心看护版] 主程序启动")
    print("==============================================================")

    if not acquire_single_instance_lock():
        sys.exit(0)

    store, runtime, frame_hub, ptz_service, report_service, vision, app_service, web, feishu, incident_monitor = build_app()
    try:
        report_service.start_timer()
        web.start()
        feishu.start()
        vision.start()
        incident_monitor.start()
        print("[OK] [系统] 飞书、Web、视觉、日报服务已全部启动。")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] 收到终止指令，智哨安全下线。")
        incident_monitor.stop()
        vision.stop()
        ptz_service.center()
