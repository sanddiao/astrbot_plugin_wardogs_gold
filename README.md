# astrbot_plugin_wardogs_gold

AstrBot 插件：查询 WARDOGS 游戏内金条价格，并生成 JPG 走势图。

## 指令

| 指令 | 作用 |
| --- | --- |
| `/gold [天数\|all]` | 文本查询当前价格与区间走势（别名 `/金条` `/金价` `/wardogsgold`） |
| `/goldchart [天数\|all]` | 生成 JPG 走势图（别名 `/金价图` `/金条走势`） |

示例：`/gold 30`、`/gold all`、`/goldchart 90`、`/goldchart all`

## 安装

1. 把插件文件夹放到 AstrBot 的 `data/plugins/` 下，确保路径是
   `data/plugins/astrbot_plugin_wardogs_gold/main.py`（不要在中间多套一层文件夹）
2. 安装依赖：`pip install -r requirements.txt`
3. 在 WebUI「插件管理」中启用并重载插件（部分版本需重启 AstrBot）

## 依赖

仅 `Pillow>=9.0.0`（绘图引擎，惰性导入；未安装时 `/gold` 文本查询仍可用）。

## 数据源

wardogsfieldkit.com 的 Gold Price & History 页面（社区追踪，非官方）。
页面把完整每日序列内嵌为 `<script id="gold-series" type="application/json">`，
插件用标准库 `urllib` + `re` 解析，无需任何第三方 API。
价格每日 UTC 0 点刷新，新一天汇率未公布时显示最近已知日期。

## 常见问题：发了 `/金价` 没反应，反而是大模型在回复？

这说明消息没有被插件接住，落到了 AstrBot 的 **LLM 兜底回复**（此时模型的回答看起来很像"插件作者在解释"，但那是它根据上下文编的，不能当诊断依据）。按顺序排查：

1. **看启动日志**：加载成功时控制台一定有
   `[wardogs_gold] 插件已加载，可用指令：...`。没有这行就是插件根本没加载成功，
   往上翻日志找该插件的 `Traceback`。
2. **看目录层级**：必须是 `data/plugins/astrbot_plugin_wardogs_gold/main.py`，
   从 GitHub 下载 zip 解压时很容易多套一层。
3. **看 WebUI 插件管理**：插件是否已启用；改完代码必须重载（旧版甚至要重启）才生效。
4. **看唤醒前缀**：AstrBot 默认前缀是 `/`；若你改过前缀（或关闭了忽略前缀），
   要按你的设置发送。群聊里通常还需要 @ 机器人才能触发指令。
5. **看版本**：本插件要求 AstrBot `>=3.4.28`（用到了指令别名）。
   代码已做兼容：新版（无 `register`）和旧版（`filter.command` 不支持 `alias`）都能正常加载。

## 兼容性说明

- 插件通过 `metadata.yaml` 注册；`@register` 装饰器在新版 AstrBot 已移除，
  代码用 try/except 降级为空装饰器，一份代码同时兼容新旧版本。
- 指令别名优先用 `filter.command(name, alias={...})`；若当前版本不支持 `alias` 参数，
  自动降级为堆叠多个 `filter.command` 逐个注册，效果等价。
