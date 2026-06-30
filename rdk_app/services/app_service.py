import os

import cv2
import requests

from settings import PUBLIC_MONITOR_URL
from settings import BASE_DIR
from core.ptz_controller import ptz
from services.text_overlay import draw_chinese_text


class AppService:
    """Unified command/status facade used by Feishu and Web."""

    RAW_VIEW_SECONDS = 180

    def __init__(self, store, runtime, frame_hub, vision_worker, ptz_service, report_service, brain, bot):
        self.store = store
        self.runtime = runtime
        self.frame_hub = frame_hub
        self.vision_worker = vision_worker
        self.ptz_service = ptz_service
        self.report_service = report_service
        self.brain = brain
        self.bot = bot

    def status_payload(self):
        metrics = self.store.get_metrics()
        events = self.store.list_events(limit=8, date=self.store.today())
        return {
            "ok": True,
            "status": self.runtime.snapshot(),
            "metrics": metrics,
            "events": events,
            "status_text": self.status_text(),
            "system_brief_text": self.system_brief_text(metrics),
            "comfort_text": self.comfort_text(metrics),
            "family_summary": self.family_summary(metrics),
            "privacy_text": self.privacy_status_text(),
            "video_age": {
                "raw": self.frame_hub.raw_age(),
                "skeleton": self.frame_hub.skeleton_age(),
            },
        }

    def comfort_text(self, metrics=None):
        metrics = metrics or self.store.get_metrics()
        confirmed = int(metrics.get("confirmed_fall_count", 0) or 0)
        suspects = int(metrics.get("suspect_fall_count", 0) or 0)
        seen_minutes = float(metrics.get("seen_seconds", 0) or 0) / 60
        active_minutes = float(metrics.get("active_seconds", 0) or 0) / 60
        if confirmed:
            return "需要尽快确认"
        if suspects:
            return "有过疑似风险"
        if seen_minutes < 5:
            return "今日数据较少"
        if active_minutes < 10:
            return "整体平稳，活动偏少"
        return "整体平稳"

    def family_summary(self, metrics=None):
        metrics = metrics or self.store.get_metrics()
        state = self.runtime.snapshot()
        last_seen = metrics.get("last_seen_time") or state.get("last_seen_time") or "今天暂未看到目标"
        target_count = int(state.get("target_count", 0) or 0)
        if state.get("fall_state") in ("SUSPECT", "VALIDATING"):
            risk = "系统正在复核一个可能需要关心的姿态。"
        elif int(metrics.get("confirmed_fall_count", 0) or 0):
            risk = "今天出现过高风险提醒，请优先确认父母是否安好。"
        elif int(metrics.get("suspect_fall_count", 0) or 0):
            risk = "今天出现过疑似风险，系统已记录并保持关注。"
        elif target_count:
            risk = "当前能看到可信人体目标，安全状态平稳。"
        else:
            risk = "当前暂未看到目标，设备仍在线守护。"
        return f"{risk}\n最近看到目标：{last_seen}"

    def status_text(self):
        metrics = self.store.get_metrics()
        state = self.runtime.snapshot()
        raw_line = (
            f"真实画面：临时开启中，剩余 {state['raw_video_seconds_left']} 秒"
            if state["raw_video_allowed"]
            else "真实画面：默认关闭，开启前需大模型隐私复核"
        )
        return (
            f"安心状态：{self.comfort_text(metrics)}\n"
            f"{self.family_summary(metrics)}\n"
            f"看护模式：{state['care_mode']}（状态可见，画面克制）\n"
            f"{raw_line}\n"
            f"摄像头：{'正常' if state['camera_ok'] else '无画面'} ({state['camera_message']})\n"
            f"自动跟随：{'开启' if state['follow_enabled'] else '暂停'}\n"
            f"云台状态：{state['ptz_mode']}\n"
            f"摔倒检测模式：{state['fall_mode']}\n"
            f"摔倒状态机：{state['fall_state']}\n"
            f"视觉候选/可信目标：{state.get('raw_pose_count', 0)} / {state.get('target_count', 0)}\n"
            f"今日看到人时长：{float(metrics.get('seen_seconds', 0) or 0) / 60:.1f} 分钟\n"
            f"今日活动时长：{float(metrics.get('active_seconds', 0) or 0) / 60:.1f} 分钟\n"
            f"摔倒疑似次数：{int(metrics.get('suspect_fall_count', 0) or 0)}\n"
            f"确诊告警次数：{int(metrics.get('confirmed_fall_count', 0) or 0)}\n"
            f"{self.vision_worker.lock_status_text()}"
        )

    def system_brief_text(self, metrics=None):
        metrics = metrics or self.store.get_metrics()
        state = self.runtime.snapshot()
        raw_text = (
            f"临时开启 {state['raw_video_seconds_left']} 秒"
            if state.get("raw_video_allowed")
            else "默认关闭"
        )
        fall_state = {
            "NORMAL": "平稳",
            "CANDIDATE": "观察中",
            "SUSPECT": "疑似风险",
            "VALIDATING": "复核中",
            "CONFIRMED": "已告警",
            "REJECTED": "已拦截",
            "VALIDATION_FAILED": "复核失败",
        }.get(state.get("fall_state"), state.get("fall_state", "未知"))
        return "\n".join(
            [
                f"安心状态：{self.comfort_text(metrics)}",
                f"摄像头：{'正常' if state.get('camera_ok') else '无画面'}",
                f"自动跟随：{'开启' if state.get('follow_enabled') else '暂停'}",
                f"摔倒检测：{state.get('fall_mode', '保守')} / {fall_state}",
                f"可信目标：{state.get('target_count', 0)}",
                f"真实画面：{raw_text}",
            ]
        )

    def get_video_frame(self, source):
        if source == "raw":
            if not self.runtime.raw_video_allowed():
                skeleton = self.frame_hub.get_skeleton()
                if skeleton is not None:
                    return skeleton
                return self.frame_hub.privacy_frame("真实画面默认关闭，请先通过隐私复核")
            raw = self.frame_hub.get_raw()
            if raw is not None:
                return self._with_raw_view_overlay(raw)
        if source == "skeleton":
            skeleton = self.frame_hub.get_skeleton()
            if skeleton is not None:
                return skeleton
        return self.frame_hub.blank_frame()

    def _with_raw_view_overlay(self, frame):
        view = frame.copy()
        h, w = view.shape[:2]
        seconds_left = self.runtime.raw_seconds_left()
        overlay = view.copy()
        cv2.rectangle(overlay, (0, 0), (w, 52), (8, 18, 28), -1)
        cv2.rectangle(overlay, (0, h - 34), (w, h), (8, 18, 28), -1)
        view = cv2.addWeighted(overlay, 0.68, view, 0.32, 0)
        view = draw_chinese_text(view, "临时安全确认：隐私复核通过", (14, 7), size=18, color=(255, 255, 0))
        view = draw_chinese_text(view, f"{seconds_left} 秒后自动关闭｜请勿录屏、截图、转发", (14, 29), size=15, color=(245, 245, 245))
        view = draw_chinese_text(view, "真实画面仅用于确认安全，默认使用脱敏看护", (14, h - 27), size=13, color=(245, 245, 245))
        return view

    def handle_command(self, command, source="feishu"):
        command = (command or "").strip()
        mapping = {
            "lock": lambda: self.vision_worker.lock_current(),
            "lock_elder": lambda: self.vision_worker.lock_current("老人"),
            "unlock": self.vision_worker.unlock,
            "pause_follow": lambda: self.ptz_service.set_follow_enabled(False),
            "resume_follow": lambda: self.ptz_service.set_follow_enabled(True),
            "center": self.ptz_service.center,
            "left": lambda: self.ptz_service.move("left"),
            "right": lambda: self.ptz_service.move("right"),
            "up": lambda: self.ptz_service.move("up"),
            "down": lambda: self.ptz_service.move("down"),
            "mode_conservative": lambda: self.vision_worker.set_fall_mode("conservative"),
            "mode_sensitive": lambda: self.vision_worker.set_fall_mode("sensitive"),
            "report": self._send_report,
            "family_safe": lambda: self._family_action("已确认安全"),
            "family_false_alarm": lambda: self._family_action("误报"),
            "open_raw_view": self.open_raw_view,
            "close_raw_view": self.close_raw_view,
        }
        if command not in mapping:
            return False, "未知指令。"
        ok, reply = mapping[command]()
        return ok, reply

    def open_raw_view(self):
        frame = self.frame_hub.get_raw()
        if frame is None:
            self.store.record_event("raw_view_blocked", "真实画面开启失败：当前没有可复核画面。", "warning")
            return False, "当前没有可复核画面，暂时不能开启真实画面。请稍后再试。"

        result = self.brain.privacy_check(frame)
        safe = bool(result and result.get("safe_to_show"))
        reason = (result or {}).get("reason", "云端大脑未返回明确结论。")
        risk_level = (result or {}).get("risk_level", "unknown")
        block_type = (result or {}).get("block_type", "unknown")
        confidence = float((result or {}).get("confidence", 0.0) or 0.0)
        evidence = (result or {}).get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            evidence = []
        if not safe:
            if block_type == "service_unavailable":
                title = "真实画面未开启：隐私复核服务不可用，已按保护策略拒绝。"
            elif risk_level == "privacy_risk" or block_type == "privacy_risk":
                title = "真实画面未开启：画面存在隐私风险。"
            elif risk_level == "uncertain" or block_type == "uncertain":
                title = "真实画面未开启：模型不确定，已按保护策略拒绝。"
            else:
                title = "真实画面未开启：隐私复核未通过。"
            evidence_text = "；".join(str(item) for item in evidence[:3] if str(item).strip())
            detail = f"{title}原因：{reason}"
            if evidence_text:
                detail += f"依据：{evidence_text}"
            detail += f" 风险等级：{risk_level}，置信度：{confidence:.2f}"
            self.store.record_event(
                "raw_view_privacy_blocked",
                detail,
                "warning",
                {
                    "risk_level": risk_level,
                    "reason": reason,
                    "confidence": confidence,
                    "evidence": evidence[:3],
                    "block_type": block_type,
                },
            )
            return False, (
                "真实画面未开启。\n"
                f"{title}\n"
                f"具体原因：{reason}\n"
                f"风险等级：{risk_level}，置信度：{confidence:.2f}\n"
                "为保护父母隐私，请先使用脱敏画面、电话或语音确认。"
            )

        self.runtime.allow_raw_video(self.RAW_VIEW_SECONDS)
        self.store.record_event(
            "raw_view_opened",
            f"大模型确认无明显隐私泄露后，家属临时开启真实画面 {self.RAW_VIEW_SECONDS // 60} 分钟。",
            "info",
            {"seconds": self.RAW_VIEW_SECONDS, "privacy_check": result},
        )
        return True, (
            f"大模型已确认当前画面无明显隐私泄露，真实画面临时开启 {self.RAW_VIEW_SECONDS // 60} 分钟。\n"
            "请只用于确认安全，到时会自动关闭；默认看护仍以状态和脱敏画面为主。\n"
            "隐私提示：请避免录屏、截图、转发或让无关人员观看。"
        )

    def close_raw_view(self):
        self.runtime.close_raw_video()
        self.store.record_event("raw_view_closed", "真实画面已关闭，恢复边界看护。", "info")
        return True, "真实画面已关闭。当前仅展示安心状态和脱敏画面。"

    def _send_report(self):
        self.report_service.send_report()
        return True, "图文健康日报已生成。"

    def _family_action(self, action):
        self.store.record_family_action(action)
        return True, f"已记录家属处置：{action}。"

    def privacy_status_text(self):
        state = self.runtime.snapshot()
        if state["raw_video_allowed"]:
            raw = f"真实画面临时开启中，剩余 {state['raw_video_seconds_left']} 秒。"
        else:
            raw = "真实画面默认关闭，开启前必须通过大模型隐私复核。"
        return (
            "隐私与安心边界\n"
            f"- 看护模式：{state['care_mode']}\n"
            "- 家属默认看到安心状态、活动概览和脱敏骨架。\n"
            f"- {raw}\n"
            "- 摔倒告警优先发送文字结论和脱敏证据，减少不必要打扰。"
        )

    def reassurance_text(self):
        state = self.runtime.snapshot()
        metrics = self.store.get_metrics()
        url = state.get("monitor_url") or "http://RDK_IP:5000"
        if self.comfort_text(metrics) == "整体平稳":
            advice = "当前暂无必要查看真实画面；如仍不放心，可先打开脱敏看护页。"
        else:
            advice = "建议先电话问候；如果联系不上，可申请临时查看真实画面，系统会先做大模型隐私复核。"
        return (
            f"{self.family_summary(metrics)}\n\n"
            f"{advice}\n"
            f"看护页：{url}\n"
            "可用指令：临时查看真实画面、关闭真实画面、查看隐私状态。"
        )

    def current_activity_text(self):
        state = self.runtime.snapshot()
        metrics = self.store.get_metrics()
        target_count = int(state.get("target_count", 0) or 0)
        last_seen = metrics.get("last_seen_time") or state.get("last_seen_time") or "今天暂未看到目标"
        fall_state = state.get("fall_state", "NORMAL")
        active_track = state.get("active_track_id") or "无"
        lock_line = (
            f"当前跟随轨迹：{active_track}，{state.get('follow_reason') or '暂无跟随原因'}。"
            if active_track != "无"
            else f"当前跟随轨迹：无，{state.get('follow_reason') or '暂无可信目标'}。"
        )

        if fall_state in {"SUSPECT", "VALIDATING"}:
            activity = "系统正在复核一个可能需要关心的姿态，建议先通过电话或语音确认。"
        elif fall_state == "CONFIRMED":
            activity = "系统已经确认高风险提醒，请优先确认父母是否安全。"
        elif target_count <= 0:
            activity = "根据脱敏骨架判断：当前暂未看到可信人体目标，设备仍在线守护。"
        elif getattr(self.vision_worker, "is_moving", False):
            activity = "根据脱敏骨架判断：当前能看到可信人体目标，骨架位置有变化，像是在走动、调整姿势或进行轻微活动。"
        else:
            activity = "根据脱敏骨架判断：当前能看到可信人体目标，姿态比较稳定，像是在停留、静坐或缓慢活动。"

        return (
            f"{activity}\n"
            f"最近看到目标：{last_seen}\n"
            f"{lock_line}\n"
            "说明：这里基于脱敏骨架、人体框和活动统计判断，不主动查看或发送真实画面。"
        )

    def visual_question_answer(self, question):
        """Use the cloud brain to understand the current scene, but only expose sanitized evidence."""
        raw = self.frame_hub.get_raw()
        if raw is None:
            return {
                "answer": "当前摄像头暂时没有可分析画面。我会继续在线守护；你也可以稍后再问一次。",
                "used_vision": False,
                "need_image": False,
            }

        state = self.runtime.snapshot()
        metrics = self.store.get_metrics()
        context = (
            f"本次家属的问题是：{question}\n"
            "你必须只回答这个问题，不要扩展到天气、地点、产品说明、隐私策略、健康建议或监控入口。"
            "你可以分析这张实时摄像头帧来判断人物正在做什么，"
            "但最终回复必须保护隐私：不要描述可识别面部细节、屏幕文字、身体隐私部位、裸露/换衣/如厕等敏感细节；"
            "如果画面存在隐私风险，只能用克制说法，例如“当前不适合展开描述，建议用电话确认”。"
            "如果问题是“他/他们在做什么”，请围绕当前问题做更完整的看护分析："
            "可以描述人数、站坐姿态、是否移动、是否像在交流/协作、所在环境类型、是否有明显危险姿态。"
            "不要主动描述天气、气温、城市或无关环境。"
            "如果看不清或无法判断动作，直接说当前无法准确判断，不要换话题回答。"
            "回复保持 3 到 5 句话，尽量自然具体。"
            "不要说你在查看或发送真实画面；飞书附件只会展示脱敏骨架 GIF。"
            f"当前本地状态：可信人体 {state.get('target_count', 0)} 个，"
            f"当前跟随轨迹 {state.get('active_track_id') or '无'}，"
            f"锁定对象 {state.get('locked_name') or '未锁定'}，"
            f"最近看到目标 {metrics.get('last_seen_time') or state.get('last_seen_time') or '今天暂未看到目标'}。"
            "必须返回 need_image=true，因为回复会附带脱敏骨架证据。"
        )
        result = self.brain.ask(question, raw, system_note=context)
        if not result or not result.get("answer"):
            return {
                "answer": self.current_activity_text(),
                "used_vision": False,
                "need_image": True,
            }
        return {
            "answer": result.get("answer", "").strip(),
            "used_vision": True,
            "need_image": True,
        }

    def self_check(self):
        state = self.runtime.snapshot()
        serial_ok = self.ptz_service.serial_ok()
        public_url = state.get("public_monitor_url") or (state.get("monitor_url") if PUBLIC_MONITOR_URL else "")
        lan_url = state.get("lan_monitor_url") or state.get("monitor_url") or "未生成"
        lines = ["智哨系统自检"]
        lines.append(f"{'通过' if state['running'] else '注意'} - 主程序：{'运行中' if state['running'] else '未启动'}")
        lines.append(f"{'通过' if state['camera_ok'] else '注意'} - 摄像头：{state['camera_message']}")
        lines.append(f"{'通过' if serial_ok else '注意'} - 云台串口：{ptz.port} {'已连接' if serial_ok else '未连接'}")
        lines.append(f"通过 - 本地看板：{lan_url}")
        lines.append(self._public_connectivity_line(public_url))
        lines.append(self._brain_connectivity_line())
        if hasattr(self.store, "access_summary"):
            lines.append(f"访问摘要：{self.store.access_summary()}")
        lines.append("")
        lines.append(self.status_text())
        return "\n".join(lines)

    def _public_connectivity_line(self, public_url):
        if not public_url:
            return "注意 - 公网入口：未配置，外网手机暂时不能直接打开看护页。"
        health_url = f"{public_url.rstrip('/')}/health"
        try:
            response = requests.get(health_url, timeout=3)
            if response.status_code == 200:
                return f"通过 - 公网入口：{public_url}"
            if response.status_code in (401, 403):
                return f"通过 - 公网入口：{public_url}（需要登录）"
            return f"注意 - 公网入口：{public_url} HTTP {response.status_code}"
        except Exception as exc:
            return f"注意 - 公网入口：{public_url} 暂时不可达（{exc}）"

    def _brain_connectivity_line(self):
        if not hasattr(self.brain, "health_check"):
            return "注意 - VLM 大脑：当前客户端没有健康检查接口。"
        try:
            result = self.brain.health_check() or {}
        except Exception as exc:
            return f"注意 - VLM 大脑：健康检查异常（{exc}）"
        label = result.get("label", "VLM 大脑")
        detail = result.get("detail", "")
        return f"{'通过' if result.get('ok') else '注意'} - {label}：{detail}"

    def manual(self):
        state = self.runtime.snapshot()
        url = state.get("monitor_url") or "http://RDK_IP:5000"
        public_url = state.get("public_monitor_url") or url
        lan_url = state.get("lan_monitor_url") or url
        return (
            "智哨使用说明\n\n"
            "在群里发指令：先 @智哨管家，再写指令。\n"
            "例子：@智哨管家 系统自检\n"
            "私聊可以直接发指令。\n\n"
            "你只要记住：\n"
            "1. 想看页面，发：@智哨管家 监控链接\n"
            "2. 想查设备，发：@智哨管家 系统自检\n"
            "3. 想跟住一个人，发：@智哨管家 锁定当前人物\n"
            "4. 想看今天情况，发：@智哨管家 日报\n\n"
            "网页入口：\n"
            f"公网入口：{public_url}\n"
            f"备用入口：{lan_url}\n\n"
            "常用指令：\n"
            "菜单：发一张按钮卡片，不会输字就点按钮。\n"
            "监控链接：发看护网页地址。\n"
            "系统自检：检查程序、摄像头、云台、网页、大脑是否正常。\n"
            "查看状态：看老人现在是否正常、今天看到多久、有没有告警。\n"
            "日报：生成今天的看护日报。\n\n"
            "看画面：\n"
            "默认不显示真实画面，只显示状态和骨架。\n"
            "想看真实画面，发：临时查看真实画面。\n"
            "系统会先检查隐私风险，通过后只开一小会儿。\n"
            "看完马上关，发：关闭真实画面。\n\n"
            "跟随人物：\n"
            "先让人站到画面里。\n"
            "然后发：锁定当前人物。\n"
            "想看锁住谁了，发：查看锁定状态。\n"
            "不想跟了，发：取消锁定。\n"
            "云台不动了，发：恢复跟随。\n"
            "云台乱动，发：暂停跟随。\n"
            "想回到中间，发：云台回中。\n\n"
            "摔倒相关：\n"
            "保守模式：少误报，日常用这个。\n"
            "灵敏模式：反应快，需要更快提醒时用这个。\n"
            "已确认安全：你确认人没事。\n"
            "误报：这次不是摔倒。\n\n"
            "可以直接问：\n"
            "现在安全吗\n"
            "他在干什么\n"
            "今天活动怎么样"
        )

    def quick_help(self):
        return (
            "智哨指令菜单\n\n"
            "群里使用：先 @智哨管家，再写指令。\n"
            "例子：@智哨管家 监控链接\n"
            "私聊使用：直接发指令。\n\n"
            "不会用就发：@智哨管家 菜单\n"
            "想看网页发：@智哨管家 监控链接\n"
            "想查设备发：@智哨管家 系统自检\n"
            "想跟人发：@智哨管家 锁定当前人物\n"
            "想停跟随发：@智哨管家 暂停跟随\n"
            "想继续跟发：@智哨管家 恢复跟随\n"
            "想看状态发：@智哨管家 查看状态\n"
            "想看日报发：@智哨管家 日报\n"
            "想看完整说明发：@智哨管家 说明书\n\n"
            "可以直接问：现在安全吗 / 他在干什么 / 今天怎么样"
        )
    def recent_events_text(self, limit=6):
        events = self.store.list_events(limit=limit, date=self.store.today())
        if not events:
            return "今天还没有记录到看护事件。"
        lines = ["最近看护事件："]
        for event in events:
            lines.append(f"{event.get('ts', '')} {event.get('type', '')}: {event.get('message', '')}")
        return "\n".join(lines)

    def ask_brain(self, question):
        frame = self.frame_hub.get_skeleton()
        state = self.runtime.snapshot()
        privacy_context = (
            f"本次家属的问题是：{question}\n"
            "只回答这个问题，不要主动扩展天气、地点、产品说明、隐私策略、健康建议或监控入口。"
            "注意：你收到的图片是脱敏骨架画面，不是真实摄像头画面。"
            f"当前真实画面{'临时开启' if state.get('raw_video_allowed') else '默认关闭'}。"
            "回答时必须基于脱敏骨架和本地状态判断，不要声称自己看到了真实画面。"
            "如果无法从脱敏骨架判断用户所问内容，直接说当前无法准确判断，不要改答其他话题。"
            "回复保持 3 到 5 句话，可以分析人数、姿态、动作变化、互动关系和安全状态，但不要加入用户没问的天气或产品说明。"
        )
        result = self.brain.ask(question, frame, system_note=privacy_context)
        if not result:
            return {
                "answer": (
                    "云端大脑暂时连接不上，本地看护仍在运行。\n\n"
                    f"{self.system_brief_text()}\n\n"
                    "我现在不能做复杂视觉问答，但摄像头状态、摔倒检测、云台跟随和看护页仍可继续使用。"
                ),
                "need_image": False,
            }
        return result

    def make_reply_gif(self):
        import imageio

        frames = self.frame_hub.get_reply_frames()
        if not frames:
            return None
        gif_path = os.path.join(BASE_DIR, "logs", "temp_reply.gif")
        rgb_frames = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames]
        imageio.mimsave(gif_path, rgb_frames, format="GIF", fps=10, loop=0)
        return gif_path
