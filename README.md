# astrbot_plugin_wardogs_gold

AstrBot 插件：查询 WARDOGS 游戏内金条价格，并生成 JPG 走势图。

## 指令
- `/gold [天数|all]` —— 文本查询价格与区间走势（别名 `/金条` `/金价`）
- `/goldchart [天数|all]` —— 生成 JPG 走势图（别名 `/金价图` `/金条走势`）

示例：`/gold 30`、`/gold all`、`/goldchart 90`、`/goldchart all`

## 安装
1. 将本插件文件夹复制到 AstrBot 的 `data/plugins/`
2. 安装依赖：`pip install -r requirements.txt`
3. 在 WebUI「插件管理」重载插件

## 数据源
wardogsfieldkit.com 的 Gold Price & History 页面（社区追踪，非官方）。
价格每日 UTC 0 点刷新，新一天汇率未公布时显示最近已知日期。

## 依赖
Pillow>=9.0.0（绘图引擎）
