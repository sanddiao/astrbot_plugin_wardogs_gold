"""WARDOGS 金条价格查询插件。

数据源：https://wardogsfieldkit.com/en/gold/ （社区维护，非官方）
页面里内嵌了一段 [{"date": "...", "rate": 123}, ...] 的 JSON，直接取它。
"""

from __future__ import annotations

import json
import re
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

GOLD_PAGE = "https://wardogsfieldkit.com/en/gold/"
USER_AGENT = "Mozilla/5.0 (compatible; AstrBot-WardogsGold/1.0)"
CACHE_TTL = 600
MAX_TREND_DAYS = 30

_JSON_BLOCK_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
    re.S,
)
_SPARK_LEVELS = "▁▂▃▄▅▆▇█"


def parse_history(html: str) -> list[dict[str, object]]:
    """从金价页面里取出 {date, rate} 序列，按日期升序返回。"""
    for block in _JSON_BLOCK_RE.findall(html or ""):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, list) or not data:
            continue
        rows: list[tuple[str, float]] = []
        for item in data:
            if not isinstance(item, dict):
                rows = []
                break
            date = str(item.get("date") or "").strip()
            rate = item.get("rate")
            if not date or not isinstance(rate, (int, float)) or isinstance(rate, bool):
                rows = []
                break
            rows.append((date, float(rate)))
        if rows:
            rows.sort(key=lambda row: row[0])
            return [{"date": date, "rate": rate} for date, rate in rows]
    return []


def sparkline(values: list[float]) -> str:
    if not values:
        return ""
    low, high = min(values), max(values)
    span = high - low
    if span <= 0:
        return _SPARK_LEVELS[0] * len(values)
    chars = []
    for value in values:
        index = int(round((value - low) / span * (len(_SPARK_LEVELS) - 1)))
        chars.append(_SPARK_LEVELS[index])
    return "".join(chars)


def money(value: float) -> str:
    return f"${value:,.0f}"


def percent(new: float, old: float) -> str:
    if not old:
        return "—"
    return f"{(new - old) / old * 100:+.1f}%"


@register(
    "astrbot_plugin_wardogs_gold",
    "sanddiao",
    "查询 WARDOGS 游戏内金条价格，支持查看区间走势与最近行情。",
    "1.0.0",
)
class WardogsGold(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self._cache: list[dict[str, object]] = []
        self._cache_at = 0.0

    # ── 数据 ──

    async def _history(self, force: bool = False) -> list[dict[str, object]]:
        now = time.time()
        if not force and self._cache and now - self._cache_at < CACHE_TTL:
            return self._cache
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as session:
            async with session.get(GOLD_PAGE) as resp:
                resp.raise_for_status()
                html = await resp.text()
        rows = parse_history(html)
        if rows:
            self._cache = rows
            self._cache_at = now
        return rows

    @staticmethod
    def _arg(event: AstrMessageEvent) -> str:
        text = str(getattr(event, "message_str", "") or "")
        return text.strip()

    @staticmethod
    def _days(event: AstrMessageEvent) -> int:
        match = re.search(r"(\d{1,3})", WardogsGold._arg(event))
        if not match:
            return 0
        return min(int(match.group(1)), MAX_TREND_DAYS)

    # ── 输出 ──

    @staticmethod
    def _quote_text(rows: list[dict[str, object]]) -> str:
        latest = rows[-1]
        lines = [
            f"WARDOGS 金条 · {latest['date']}",
            f"1 根 = {money(float(latest['rate']))}",
        ]
        if len(rows) >= 2:
            prev = rows[-2]
            lines.append(
                f"较前一日 {percent(float(latest['rate']), float(prev['rate']))}"
                f"（{money(float(prev['rate']))}）",
            )
        lines.append("数据源 wardogsfieldkit.com")
        return "\n".join(lines)

    @staticmethod
    def _trend_text(rows: list[dict[str, object]], days: int) -> str:
        window = rows[-days:]
        values = [float(row["rate"]) for row in window]
        lines = [
            f"WARDOGS 金条 · 最近 {len(window)} 天",
            sparkline(values),
            f"区间 {window[0]['date']} ~ {window[-1]['date']}",
            f"最高 {money(max(values))} · 最低 {money(min(values))}",
            "—" * 8,
        ]
        for row in reversed(window):
            lines.append(f"{row['date']}  {money(float(row['rate']))}")
        return "\n".join(lines)

    @staticmethod
    def _history_text(rows: list[dict[str, object]]) -> str:
        values = [float(row["rate"]) for row in rows]
        high_row = max(rows, key=lambda row: float(row["rate"]))
        low_row = min(rows, key=lambda row: float(row["rate"]))
        avg = sum(values) / len(values)
        return "\n".join(
            [
                f"WARDOGS 金条历史 · 共 {len(rows)} 天",
                f"区间 {rows[0]['date']} ~ {rows[-1]['date']}",
                f"最高 {money(float(high_row['rate']))}（{high_row['date']}）",
                f"最低 {money(float(low_row['rate']))}（{low_row['date']}）",
                f"均值 {money(avg)}",
                f"当前 {money(values[-1])} · {percent(values[-1], avg)} vs 均值",
            ],
        )

    async def _render(self, event: AstrMessageEvent):
        try:
            rows = await self._history()
        except Exception as exc:  # noqa: BLE001 - 网络异常统一兜底
            logger.warning(f"wardogs gold 拉取失败: {exc}")
            yield event.plain_result("金价没拉到 站点可能抽风了 过会儿再试")
            return
        if not rows:
            yield event.plain_result("页面里没解析到金价数据 大概改版了")
            return
        arg = self._arg(event)
        if "历史" in arg:
            yield event.plain_result(self._history_text(rows))
            return
        days = self._days(event)
        if days > 1:
            yield event.plain_result(self._trend_text(rows, days))
            return
        yield event.plain_result(self._quote_text(rows))

    # ── 命令 ──

    @filter.command("金条")
    async def gold(self, event: AstrMessageEvent):
        """金条 / 金条 7 / 金条历史。"""
        async for item in self._render(event):
            yield item

    @filter.command("金价")
    async def gold_price(self, event: AstrMessageEvent):
        """金价：等同「金条」。"""
        async for item in self._render(event):
            yield item
