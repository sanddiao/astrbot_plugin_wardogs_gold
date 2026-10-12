# astrbot_plugin_wardogs_gold

查询 **WARDOGS** 游戏内金条（Gold Bar）当日价格与历史走势的 AstrBot 插件。

数据源：[wardogsfieldkit.com](https://wardogsfieldkit.com/en/gold/)（社区维护，非官方）。

## 指令

| 指令 | 说明 |
| --- | --- |
| `金条` / `金价` | 当前 1 根金条的价格，附前一日对比 |
| `金条 7` | 最近 7 天走势（带迷你走势条），最多 30 天 |
| `金条历史` | 全量样本数、区间、最高/最低/均值 |

## 实现说明

金价页面里内嵌了一段 `[{"date": "2026-10-11", "rate": 272761}, ...]` 的 JSON，
插件直接按 `type="application/json"` 的脚本块提取，不做 DOM 解析，改版时只依赖这一个结构。

- 结果缓存 10 分钟，避免刷站
- 站点不可达或页面结构变化时只回一句提示，不抛异常
- 不依赖第三方库，用 AstrBot 自带的 `aiohttp`
