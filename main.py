import asyncio
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
import astrbot.api.message_components as Comp


@register(
    "astrbot_plugin_group_broadcast",
    "Kenan",
    "群聊定时广播插件：支持@全体+自定义消息+自定义图片+群白名单+定时发送",
    "1.0.0",
)
class GroupBroadcast(Star):
    """
    群聊定时广播插件。

    功能：
    1. /broadcast whitelist add/remove/list —— 管理群白名单（管理员）
    2. /broadcast status —— 查看定时广播状态
    3. 定时自动广播 —— 根据配置的时间，自动向白名单群聊发送 @全体+消息+图片
    """

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._scheduler_task: asyncio.Task | None = None

    # ==================== 生命周期 ====================

    @filter.on_astrbot_loaded()
    async def _on_bot_loaded(self):
        """Bot 加载完成后启动调度器"""
        if self.config.get("enable_schedule", False):
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
            logger.info("[群聊定时广播] 调度器已启动")

    async def terminate(self):
        """插件卸载时停止调度器"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            logger.info("[群聊定时广播] 调度器已停止")

    # ==================== 后台调度 ====================

    async def _scheduler_loop(self):
        """
        定时调度循环，每 30 秒检查一次当前时间是否匹配配置的发送时间。
        使用 KV 存储（按日期+时间组合键）防止同一分钟重复发送。
        """
        while True:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                schedule_times = self.config.get("schedule_times", [])

                if current_time in schedule_times:
                    today_key = f"sent_{now.strftime('%Y%m%d')}_{current_time}"
                    already_sent = await self.get_kv_data(today_key, False)
                    if not already_sent:
                        logger.info(f"[群聊定时广播] 触发定时发送: {current_time}")
                        await self._do_scheduled_broadcast()
                        await self.put_kv_data(today_key, True)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("[群聊定时广播] 调度循环被取消")
                break
            except Exception as e:
                logger.error(f"[群聊定时广播] 调度器异常: {e}")
                await asyncio.sleep(30)

    async def _do_scheduled_broadcast(self):
        """遍历白名单群聊，发送定时广播消息。"""
        group_whitelist = self.config.get("group_whitelist", [])
        message = self.config.get("schedule_message", "")
        image_url = self.config.get("schedule_image_url", "")

        if not group_whitelist:
            logger.warning("[群聊定时广播] 白名单为空，跳过定时发送")
            return

        for group_id in group_whitelist:
            try:
                umo = await self.get_kv_data(f"umo_{group_id}", None)
                if not umo:
                    logger.warning(
                        f"[群聊定时广播] 群 {group_id} 尚未记录 unified_msg_origin，跳过"
                    )
                    continue

                chain = self._build_message_chain(message, image_url)
                await self.context.send_message(umo, chain)
                logger.info(f"[群聊定时广播] 定时广播已发送至群 {group_id}")
                await asyncio.sleep(1)  # 避免多群发送过快被限流
            except Exception as e:
                logger.error(f"[群聊定时广播] 发送至群 {group_id} 失败: {e}")

    # ==================== 消息监听：记录白名单群的 UMO ====================

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def _on_group_message(self, event: AstrMessageEvent):
        """
        监听所有群消息，当消息来自白名单群聊时，
        自动记录其 unified_msg_origin，供定时发送使用。
        """
        try:
            group_id = event.get_group_id()
            whitelist = self.config.get("group_whitelist", [])
            if group_id and group_id in whitelist:
                await self.put_kv_data(f"umo_{group_id}", event.unified_msg_origin)
        except Exception:
            pass  # 静默处理，不影响正常消息流

    # ==================== 指令组 ====================

    @filter.command_group("broadcast")
    def broadcast(self):
        """定时广播指令组"""
        pass

    # ==================== 白名单管理 ====================

    @broadcast.group("whitelist")
    def whitelist(self):
        """白名单管理子指令组"""
        pass

    @whitelist.command("add")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def whitelist_add(self, event: AstrMessageEvent, group_id: str = ""):
        """
        添加群到白名单 —— /broadcast whitelist add [group_id]
        不填 group_id 则添加当前群。仅管理员可用。
        """
        if not group_id:
            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result("❌ 请在群聊中使用，或手动指定群号。")
                return

        whitelist: list = list(self.config.get("group_whitelist", []))
        if group_id in whitelist:
            yield event.plain_result(f"⚠️ 群 {group_id} 已在白名单中。")
            return

        whitelist.append(group_id)
        self.config["group_whitelist"] = whitelist
        self.config.save_config()
        yield event.plain_result(f"✅ 已添加群 {group_id} 到白名单。")

    @whitelist.command("remove")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def whitelist_remove(self, event: AstrMessageEvent, group_id: str = ""):
        """
        从白名单移除群 —— /broadcast whitelist remove [group_id]
        不填 group_id 则移除当前群。仅管理员可用。
        """
        if not group_id:
            group_id = event.get_group_id()
            if not group_id:
                yield event.plain_result("❌ 请在群聊中使用，或手动指定群号。")
                return

        whitelist: list = list(self.config.get("group_whitelist", []))
        if group_id not in whitelist:
            yield event.plain_result(f"⚠️ 群 {group_id} 不在白名单中。")
            return

        whitelist.remove(group_id)
        self.config["group_whitelist"] = whitelist
        self.config.save_config()
        # 同时清理该群的 UMO 缓存
        await self.delete_kv_data(f"umo_{group_id}")
        yield event.plain_result(f"✅ 已从白名单移除群 {group_id}。")

    @whitelist.command("list")
    async def whitelist_list(self, event: AstrMessageEvent):
        """
        查看白名单列表 —— /broadcast whitelist list
        """
        whitelist = self.config.get("group_whitelist", [])
        if not whitelist:
            yield event.plain_result("📋 白名单为空。")
            return

        msg = "📋 白名单群聊：\n" + "\n".join(f"• {gid}" for gid in whitelist)
        yield event.plain_result(msg)

    # ==================== 状态查看 ====================

    @broadcast.command("status")
    async def cmd_status(self, event: AstrMessageEvent):
        """
        查看插件状态 —— /broadcast status
        """
        enable = self.config.get("enable_schedule", False)
        times = self.config.get("schedule_times", [])
        msg_text = self.config.get("schedule_message", "")
        img_url = self.config.get("schedule_image_url", "")
        whitelist = self.config.get("group_whitelist", [])

        lines = [
            "📊 群聊定时广播 状态",
            "━━━━━━━━━━━━━━━━",
            f"⏰ 定时发送: {'✅ 已启用' if enable else '❌ 已禁用'}",
            f"🕐 发送时间: {', '.join(times) if times else '未设置'}",
            f"📝 广播消息: {msg_text if msg_text else '未设置'}",
            f"🖼️ 广播图片: {img_url if img_url else '未设置'}",
            f"👥 白名单群数: {len(whitelist)}",
        ]
        if whitelist:
            lines.append(f"📋 白名单: {', '.join(whitelist)}")
        yield event.plain_result("\n".join(lines))

    # ==================== 工具方法 ====================

    @staticmethod
    def _build_message_chain(message: str, image_url: str) -> list:
        """
        构建消息链：@全体 + 文本消息 + 图片（可选）。

        Args:
            message: 文本消息内容
            image_url: 图片 URL（http/https 开头），为空则不附加图片

        Returns:
            消息链列表
        """
        chain = [Comp.At(qq="all"), Comp.Plain(f"\n{message}")]
        if image_url and image_url.startswith(("http://", "https://")):
            chain.append(Comp.Image.fromURL(image_url))
        return chain
