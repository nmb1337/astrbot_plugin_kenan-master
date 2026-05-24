# 群聊定时广播 / Group Scheduled Broadcast

AstrBot 群聊定时广播插件 —— 支持 @全体 + 自定义消息 + 自定义图片 + 群白名单 + 定时发送。

## ✨ 功能

- **@全体成员**：发送消息时自动附带 @全体
- **自定义消息**：可在 WebUI 中自由编辑广播文字内容
- **自定义图片**：支持附带一张网络图片（URL）
- **群聊白名单**：只有白名单内的群聊才会收到定时广播
- **定时发送**：支持配置多个发送时间点，每天自动推送
- **可视化配置**：所有配置项均可在 WebUI 中直接修改

## 📋 指令

| 指令 | 说明 | 权限 |
|------|------|------|
| `/broadcast whitelist add [群号]` | 添加群到白名单（不填则添加当前群） | 管理员 |
| `/broadcast whitelist remove [群号]` | 从白名单移除群（不填则移除当前群） | 管理员 |
| `/broadcast whitelist list` | 查看白名单群聊列表 | 所有人 |
| `/broadcast status` | 查看定时广播配置状态 | 所有人 |

## ⚙️ 配置

在 WebUI 插件配置页面中设置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `group_whitelist` | list | `[]` | 群聊白名单列表 |
| `enable_schedule` | bool | `false` | 是否启用定时发送 |
| `schedule_times` | list | `["08:00", "12:00", "18:00"]` | 定时发送时间（HH:MM 格式） |
| `schedule_message` | text | 定时提醒文案 | 广播文字内容 |
| `schedule_image_url` | string | `""` | 广播图片路径（可选，支持远程 URL 或本地绝对路径） |

## 🚀 使用流程

1. 在 WebUI 中开启插件
2. 在目标群聊中发送 `/broadcast whitelist add` 将群加入白名单
3. 在 WebUI 中配置广播消息、图片、发送时间
4. 打开 `enable_schedule` 开关
5. 每天到点自动在白名单群聊中发送 @全体 + 文字 + 图片

## � 状态查看示例

发送 `/broadcast status` 可实时查看：

```
📊 群聊定时广播 状态
━━━━━━━━━━━━━━━━
⏰ 定时发送: ✅ 已启用
🔄 调度器: ✅ 运行中
💓 最后心跳: 2026-05-24 22:11:06
🕐 发送时间: 08:00, 12:00, 18:00
📝 广播消息: ⏰ 定时提醒：请注意查看群公告！
🖼️ 广播图片: https://example.com/notice.png
👥 白名单群数: 2
📡 UMO 缓存状态:
  • 1083691732: ✅ 已缓存
  • 987654321: ❌ 未缓存(需有人发言)
```

## 🔧 技术说明

- 依赖 AstrBot 内置 API，无需额外安装 Python 包
- 通过 `initialize()` + `on_astrbot_loaded` 双重机制确保调度器可靠启动（插件热重载也生效）
- 每 5 分钟打印心跳日志，可实时确认调度器运行状态
- 使用 KV 存储防止同一分钟重复发送
- 添加白名单时立即捕获 `unified_msg_origin`，无需等待群内发言
- 监听群消息自动更新 UMO 缓存（低优先级，不干扰指令处理）
- 支持 aiocqhttp / qq_official / qq_official_webhook 平台

## 🩺 故障排查

| 现象 | 检查项 |
|------|--------|
| 到时间没发消息 | 发送 `/broadcast status`，确认调度器是否 ✅ 运行中、UMO 是否 ✅ 已缓存 |
| UMO 显示 ❌ 未缓存 | 在白名单群内发送 `/broadcast whitelist add` 重新捕获，或任意发一条消息 |
| 图片不显示 | 确认图片 URL 以 `http://` 或 `https://` 开头，且可公网访问 |
| 调度器未启动 | 在 WebUI 中确认 `enable_schedule` 已设为 `true`，然后重载插件 |

## 📦 安装

将本插件放入 AstrBot 的 `data/plugins/` 目录，在 WebUI 中启用即可。

---

> Powered by [AstrBot](https://github.com/AstrBotDevs/AstrBot)
