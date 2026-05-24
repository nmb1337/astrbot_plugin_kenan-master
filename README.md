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
| `schedule_image_url` | string | `""` | 广播图片 URL（可选，需 http/https 开头） |

## 🚀 使用流程

1. 在 WebUI 中开启插件
2. 在目标群聊中发送 `/broadcast whitelist add` 将群加入白名单
3. 在 WebUI 中配置广播消息、图片、发送时间
4. 打开 `enable_schedule` 开关
5. 每天到点自动在白名单群聊中发送 @全体 + 文字 + 图片

## 🔧 技术说明

- 依赖 AstrBot 内置 API，无需额外安装 Python 包
- 通过 `on_astrbot_loaded` 钩子启动后台调度器，通过 `terminate()` 优雅停止
- 使用 KV 存储防止同一分钟重复发送
- 监听群消息自动记录 `unified_msg_origin`，实现主动消息推送
- 支持 aiocqhttp / qq_official / qq_official_webhook 平台

## 📦 安装

将本插件放入 AstrBot 的 `data/plugins/` 目录，在 WebUI 中启用即可。

---

> Powered by [AstrBot](https://github.com/AstrBotDevs/AstrBot)
