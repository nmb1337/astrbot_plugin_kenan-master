import asyncio
import os
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
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
        self._scheduler_started: bool = False
        self._last_heartbeat: str = ""

    # ==================== 生命周期 ====================

    async def initialize(self):
        """
        插件初始化时启动调度器。
        initialize 在每次插件加载/热重载时都会调用，比 on_astrbot_loaded 更可靠。
        """
        await self._ensure_scheduler_running()

    @filter.on_astrbot_loaded()
    async def _on_bot_loaded(self):
        """Bot 首次加载完成后的兜底启动（热重载时可能不会触发此钩子）。"""
        await self._ensure_scheduler_running()

    async def _ensure_scheduler_running(self):
        """确保调度器已启动（幂等操作）。"""
        if self._scheduler_started:
            return
        if not self.config.get("enable_schedule", False):
            logger.info("[群聊定时广播] 定时发送未启用，调度器不启动")
            return
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        self._scheduler_started = True
        logger.info("[群聊定时广播] ✅ 调度器已启动")

    async def terminate(self):
        """插件卸载时停止调度器"""
        self._scheduler_started = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            logger.info("[群聊定时广播] 调度器已停止")

    # ==================== 后台调度 ====================

    async def _scheduler_loop(self):
        """
        定时调度循环，每 30 秒检查一次当前时间是否匹配配置的发送时间。
        使用 KV 存储（按日期+时间组合键）防止同一分钟重复发送。
        每 5 分钟打印一次心跳日志，方便确认调度器存活。
        """
        heartbeat_interval = 5 * 60  # 每 5 分钟打一次心跳
        last_heartbeat_ts = 0.0

        logger.info("[群聊定时广播] 🔄 调度循环开始运行")
        while self._scheduler_started:
            try:
                now = datetime.now()
                current_time = now.strftime("%H:%M")
                schedule_times = self.config.get("schedule_times", [])

                # 心跳日志
                if now.timestamp() - last_heartbeat_ts >= heartbeat_interval:
                    last_heartbeat_ts = now.timestamp()
                    self._last_heartbeat = now.strftime("%Y-%m-%d %H:%M:%S")
                    logger.info(
                        f"[群聊定时广播] 💓 调度器心跳 [{self._last_heartbeat}] "
                        f"白名单: {len(self.config.get('group_whitelist', []))} 个群, "
                        f"发送时间: {schedule_times}"
                    )

                # 时间匹配
                if current_time in schedule_times:
                    today_key = f"sent_{now.strftime('%Y%m%d')}_{current_time}"
                    already_sent = await self.get_kv_data(today_key, False)
                    if not already_sent:
                        logger.info(f"[群聊定时广播] 🚀 触发定时发送: {current_time}")
                        await self._do_scheduled_broadcast()
                        await self.put_kv_data(today_key, True)

                await asyncio.sleep(30)
            except asyncio.CancelledError:
                logger.info("[群聊定时广播] 调度循环被取消")
                break
            except Exception as e:
                logger.error(f"[群聊定时广播] 调度器异常: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _do_scheduled_broadcast(self):
        """遍历白名单群聊，发送定时广播消息。"""
        group_whitelist = self.config.get("group_whitelist", [])
        message = self.config.get("schedule_message", "")
        image_url = self.config.get("schedule_image_url", "")

        if not group_whitelist:
            logger.warning("[群聊定时广播] ⚠️ 白名单为空，跳过定时发送")
            return

        logger.info(f"[群聊定时广播] 开始向 {len(group_whitelist)} 个群发送广播")
        success_count = 0
        skip_count = 0
        fail_count = 0

        for group_id in group_whitelist:
            try:
                umo = await self.get_kv_data(f"umo_{group_id}", None)
                if not umo:
                    logger.warning(
                        f"[群聊定时广播] ⚠️ 群 {group_id} 尚无 UMO 记录，"
                        f"请确保白名单群内有人发言后 UMO 才会被自动捕获"
                    )
                    skip_count += 1
                    continue

                chain = self._build_message_chain(message, image_url)
                await self.context.send_message(umo, chain)
                logger.info(f"[群聊定时广播] ✅ 已发送至群 {group_id}")
                success_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[群聊定时广播] ❌ 发送至群 {group_id} 失败: {e}", exc_info=True)
                fail_count += 1

        logger.info(
            f"[群聊定时广播] 本轮发送完成: 成功 {success_count}, "
            f"跳过(无UMO) {skip_count}, 失败 {fail_count}"
        )

    # ==================== 消息监听：记录白名单群的 UMO ====================

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-1)
    async def _on_group_message(self, event: AstrMessageEvent):
        """
        监听所有群消息（低优先级，不干扰指令处理），
        当消息来自白名单群聊时，自动记录 unified_msg_origin 供定时发送使用。
        """
        try:
            group_id = event.get_group_id()
            if not group_id:
                return
            whitelist = self.config.get("group_whitelist", [])
            if str(group_id) in whitelist:
                umo = event.unified_msg_origin
                if umo:
                    await self.put_kv_data(f"umo_{group_id}", umo)
                    logger.debug(f"[群聊定时广播] 📝 已记录群 {group_id} 的 UMO")
        except Exception as e:
            logger.debug(f"[群聊定时广播] UMO 记录异常（可忽略）: {e}")

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
        不填 group_id 则添加当前群并立即捕获 UMO。仅管理员可用。
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
        # 立即捕获当前群的 UMO，避免定时发送时因无 UMO 而跳过
        umo = event.unified_msg_origin
        if umo:
            await self.put_kv_data(f"umo_{group_id}", umo)
            logger.info(f"[群聊定时广播] 📝 添加白名单时已记录群 {group_id} 的 UMO")
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

        # 检查各群的 UMO 缓存状态
        umo_status_parts = []
        for gid in whitelist:
            umo = await self.get_kv_data(f"umo_{gid}", None)
            status = "✅ 已缓存" if umo else "❌ 未缓存(需有人发言)"
            umo_status_parts.append(f"  • {gid}: {status}")

        lines = [
            "📊 群聊定时广播 状态",
            "━━━━━━━━━━━━━━━━",
            f"⏰ 定时发送: {'✅ 已启用' if enable else '❌ 已禁用'}",
            f"🔄 调度器: {'✅ 运行中' if self._scheduler_started else '❌ 未启动'}",
        ]
        if self._last_heartbeat:
            lines.append(f"💓 最后心跳: {self._last_heartbeat}")
        lines += [
            f"🕐 发送时间: {', '.join(times) if times else '未设置'}",
            f"📝 广播消息: {msg_text if msg_text else '未设置'}",
            f"🖼️ 广播图片: {img_url if img_url else '未设置'}",
            f"👥 白名单群数: {len(whitelist)}",
        ]
        if umo_status_parts:
            lines.append("📡 UMO 缓存状态:")
            lines.extend(umo_status_parts)
        yield event.plain_result("\n".join(lines))

    # ==================== 工具方法 ====================

    @staticmethod
    def _build_message_chain(message: str, image_url: str) -> MessageChain:
        """
        构建消息链（MessageChain）：@全体 + 文本消息 + 图片（可选）。

        Args:
            message: 文本消息内容
            image_url: 图片路径，支持以下形式：
                - http/https URL（远程图片）
                - 本地绝对路径，如 C:/images/photo.jpg
                为空则不附加图片

        Returns:
            MessageChain 对象
        """
        mc = MessageChain()
        mc.chain.append(Comp.At(qq="all"))
        mc.chain.append(Comp.Plain(f"\n{message}"))

        if image_url:
            if image_url.startswith(("http://", "https://")):
                mc.chain.append(Comp.Image.fromURL(image_url))
            elif os.path.isfile(image_url):
                mc.chain.append(Comp.Image.fromFileSystem(image_url))
            else:
                logger.warning(f"[群聊定时广播] 图片路径无效或文件不存在: {image_url}")
        return mc
