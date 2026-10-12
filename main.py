# -*- coding: utf-8 -*-
"""
AstrBot 插件：WARDOGS 游戏内金条价格查询

数据源：wardogsfieldkit.com 的 Gold Price & History 页面。
该页面把完整的每日金条价格序列以 JSON 内嵌在
  <script id="gold-series" type="application/json"> ... </script>
中，因此无需调用任何外部 API，仅用 Python 标准库即可解析。

指令：
  /gold           查询当前金条价格 + 近 7 天走势概览
  /gold 30        查询近 30 天走势
  /gold all       查询全部历史走势概览
  /goldchart      生成近 30 天金条价格走势图（.jpg）
  /goldchart 90   生成近 90 天走势图
  /goldchart all  生成全部历史走势图
别名：/金条  /金价  /wardogsgold  /金价图  /金条走势  /goldchart
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.request
from typing import List, Dict, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain

PLUGIN_NAME = "wardogs_gold"
GOLD_PAGE_URL = "https://wardogsfieldkit.com/en/gold"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AstrBot-WARDOGS-Gold/1.0"

# 用于文本走势图的 Unicode 方块字符（由低到高）
SPARK = "▁▂▃▄▅▆▇█"


def _http_get(url: str, timeout: int = 15) -> str:
    """简单的 GET 请求，带 2 次重试。"""
    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning(f"[wardogs_gold] 第 {attempt + 1} 次请求失败: {e}")
    raise last_err if last_err else RuntimeError("未知网络错误")


def fetch_gold_series() -> List[Dict[str, object]]:
    """获取完整历史序列，返回按日期升序的列表：
    [{'date': 'YYYY-MM-DD', 'rate': int}, ...]
    """
    html = _http_get(GOLD_PAGE_URL)
    m = re.search(
        r'<script id="gold-series" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        raise ValueError("未能在页面中找到金条价格数据（gold-series）")
    series = json.loads(m.group(1))
    if not isinstance(series, list) or not series:
        raise ValueError("金条价格数据为空")
    return series


def fetch_ticker() -> Dict[str, Optional[str]]:
    """解析页面顶部金条行情条：当前价格、涨跌幅、日期。"""
    html = _http_get(GOLD_PAGE_URL)
    price_m = re.search(r'gold-ticker-price">\$([\d,]+)<', html)
    change_m = re.search(r'gold-change[^>]*>→\s*([-\d.]+)%', html)
    date_m = re.search(r'gold-ticker-date[^>]*>([^<]+)<', html)

    price = int(price_m.group(1).replace(",", "")) if price_m else None
    change = change_m.group(1) if change_m else None
    raw_date = date_m.group(1).strip() if date_m else ""
    d = re.search(r"(\d{4}-\d{2}-\d{2})", raw_date)
    date = d.group(1) if d else raw_date
    return {"price": price, "change": change, "date": date}


def sparkline(values: List[int], width: int = 24) -> str:
    """把数值序列渲染成文本走势图。"""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARK[-1] * width
    # 等距抽样到 width 个点
    step = max(1, len(values) // width)
    samples = values[::step][:width]
    out = []
    for v in samples:
        idx = int((v - lo) / (hi - lo) * (len(SPARK) - 1))
        out.append(SPARK[idx])
    return "".join(out)


def fmt_cash(n: int) -> str:
    return f"${n:,}"


def build_report(days: Optional[int]) -> str:
    series = fetch_gold_series()
    ticker = fetch_ticker()
    if not series:
        return "暂无金条价格数据。"

    latest = series[-1]
    if days is None:
        window = series
        label = "全部历史"
    else:
        window = series[-days:] if days < len(series) else series
        label = f"近 {len(window)} 天"

    rates = [int(r["rate"]) for r in window]
    low, high = min(rates), max(rates)
    first, last = rates[0], rates[-1]
    if first:
        chg = last - first
        pct = chg / first * 100
        sign = "+" if chg >= 0 else ""
        trend = f"{sign}{chg:,} ({sign}{pct:.1f}%)"
    else:
        trend = "N/A"

    lines: List[str] = []
    lines.append("WARDOGS 金条价格")
    if ticker.get("price"):
        lines.append(f"当前 1 金条 = {fmt_cash(ticker['price'])}")
        if ticker.get("change") is not None:
            lines.append(f"较前一日：{ticker['change']}%")
        if ticker.get("date"):
            lines.append(f"报价日期：{ticker['date']}（UTC，每日 0 点刷新）")
    lines.append("")
    lines.append(f"【{label}】")
    lines.append(f"区间最低：{fmt_cash(low)}")
    lines.append(f"区间最高：{fmt_cash(high)}")
    lines.append(f"首日 -> 末日：{fmt_cash(first)} -> {fmt_cash(last)}  波动 {trend}")
    lines.append(f"走势：{sparkline(rates)}")
    lines.append("")
    lines.append("最近几日：")
    for r in window[-7:]:
        lines.append(f"  {r['date']}  {fmt_cash(int(r['rate']))}")
    lines.append("")
    lines.append("数据来源：wardogsfieldkit.com（社区追踪，非官方）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 天数参数解析（/gold 与 /goldchart 共用）
# ---------------------------------------------------------------------------
def _parse_days(arg: str) -> Optional[int]:
    """把指令参数解析为天数。

    - ""          -> 7（默认近 7 天）
    - "all"/"全部" -> None（全部历史）
    - "30"        -> 30
    非法输入抛出 ValueError。
    """
    arg = (arg or "").strip().lower()
    if arg in ("", "all", "全部"):
        return None if arg in ("all", "全部") else 7
    return int(arg)


def _slice_series(series: List[Dict[str, object]], days: Optional[int]) -> List[Dict[str, object]]:
    if days is None:
        return series
    return series[-days:] if days < len(series) else series


# ---------------------------------------------------------------------------
# 走势图（.jpg）生成（基于 Pillow，依赖更轻，AstrBot 插件生态常用）
# ---------------------------------------------------------------------------
def build_chart(days: Optional[int], save_path: str) -> str:
    """根据历史序列生成折线走势图，保存为 JPG，返回文件路径。依赖 Pillow。

    Pillow 在 build_chart 内部惰性导入：即使环境未安装 Pillow，
    /gold 文本查询仍可用，只有 /goldchart 会捕获 ImportError 并提示安装。
    """
    from PIL import Image as PILImage, ImageDraw, ImageFont

    def load_font(size: int):
        """加载支持中文的字体；找不到则回退到默认字体。"""
        candidates = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        for f in candidates:
            if os.path.exists(f):
                try:
                    return ImageFont.truetype(f, size)
                except Exception:  # noqa: BLE001
                    pass
        return ImageFont.load_default()

    def text_right(d, xy, text, font, fill):
        b = d.textbbox((0, 0), text, font=font)
        d.text((xy[0] - (b[2] - b[0]), xy[1]), text, font=font, fill=fill)

    def text_center(d, xy, text, font, fill):
        b = d.textbbox((0, 0), text, font=font)
        d.text((xy[0] - (b[2] - b[0]) / 2, xy[1]), text, font=font, fill=fill)

    series = fetch_gold_series()
    if not series:
        raise ValueError("暂无金条价格数据")

    window = _slice_series(series, days)
    dates = [r["date"] for r in window]
    rates = [int(r["rate"]) for r in window]
    n = len(rates)

    low, high = min(rates), max(rates)
    first, last = rates[0], rates[-1]
    chg = last - first
    pct = (chg / first * 100) if first else 0.0
    sign = "+" if chg >= 0 else ""

    W, H = 1000, 480
    pad_l, pad_r, pad_t, pad_b = 72, 30, 84, 64
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    font_title = load_font(20)
    font_axis = load_font(13)
    font_label = load_font(12)

    span = max(1, high - low)
    y_min = max(0, low - span * 0.08)  # 价格非负，下界不小于 0
    y_max = high + span * 0.08

    def sx(i):
        return pad_l + (plot_w * i / (n - 1)) if n > 1 else pad_l + plot_w / 2

    def sy(v):
        return pad_t + plot_h * (1 - (v - y_min) / (y_max - y_min))

    # 网格 + y 轴刻度（5 等分）
    for k in range(6):
        yy = pad_t + plot_h * k / 5
        draw.line([(pad_l, yy), (pad_l + plot_w, yy)], fill=(228, 228, 228), width=1)
        val = y_max - (y_max - y_min) * k / 5
        text_right(draw, (pad_l - 8, yy - 8), f"${val:,.0f}", font_axis, (90, 90, 90))

    # 填充区域（浅金）
    fill_pts = [(sx(i), sy(rates[i])) for i in range(n)] + [
        (sx(n - 1), pad_t + plot_h),
        (sx(0), pad_t + plot_h),
    ]
    draw.polygon(fill_pts, fill=(236, 222, 170))

    # 折线
    draw.line([(sx(i), sy(rates[i])) for i in range(n)], fill=(200, 161, 58), width=2)

    # x 轴日期标签（约 10 个）
    step = max(1, n // 10)
    for i in range(0, n, step):
        xx = sx(i)
        draw.line([(xx, pad_t + plot_h), (xx, pad_t + plot_h + 5)], fill=(150, 150, 150))
        text_center(draw, (xx, pad_t + plot_h + 9), dates[i], font_label, (90, 90, 90))

    # 最新点标记
    draw.ellipse([sx(n - 1) - 4, sy(last) - 4, sx(n - 1) + 4, sy(last) + 4], fill=(214, 69, 69))
    text_right(draw, (sx(n - 1) - 6, sy(last) - 22), f"${last:,}", font_axis, (214, 69, 69))

    # 标题 / 副标题
    label = "ALL" if days is None else f"last {n} days"
    draw.text((pad_l, 22), f"WARDOGS Gold Bar Price  ({label})", font=font_title, fill=(40, 40, 40))
    draw.text(
        (pad_l, 54),
        f"latest ${last:,}   {sign}{chg:,} ({sign}{pct:.1f}%)   low ${low:,} / high ${high:,}",
        font=font_axis,
        fill=(120, 120, 120),
    )

    img.save(save_path, "JPEG", quality=88)
    return save_path


@register(
    PLUGIN_NAME,
    "your_name",
    "查询 WARDOGS 游戏内金条当日价格与历史走势",
    "1.0.0",
    "",
)
class WardogsGoldPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("gold", alias={"金条", "金价", "wardogsgold"})
    async def gold(self, event: AstrMessageEvent):
        """查询 WARDOGS 金条价格。用法：/gold [天数|all]，例如 /gold 30 或 /gold all"""
        try:
            days = _parse_days(event.message_str)
            report = build_report(days)
        except ValueError:
            report = "参数无效，请输入天数（如 /gold 30）或 all（/gold all）。"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[wardogs_gold] 查询失败: {e}")
            report = f"查询金条价格失败：{e}"
        yield event.plain_result(report)

    @filter.command("goldchart", alias={"金价图", "金条走势", "goldchart"})
    async def goldchart(self, event: AstrMessageEvent):
        """生成 WARDOGS 金条价格走势图（.jpg）。用法：/goldchart [天数|all]，例如 /goldchart 90 或 /goldchart all"""
        try:
            days = _parse_days(event.message_str)
        except ValueError:
            yield event.plain_result("参数无效，请输入天数（如 /goldchart 30）或 all（/goldchart all）。")
            return

        tmp_path = os.path.join(
            tempfile.gettempdir(),
            f"wardogs_gold_{int(time.time() * 1000)}.jpg",
        )
        try:
            build_chart(days, tmp_path)
        except ImportError:
            yield event.plain_result(
                "生成走势图需要 Pillow，请先在插件目录执行：pip install Pillow"
            )
            return
        except Exception as e:  # noqa: BLE001
            logger.error(f"[wardogs_gold] 生成走势图失败: {e}")
            yield event.plain_result(f"生成走势图失败：{e}")
            return

        label = "全部历史" if days is None else f"近 {days} 天"
        yield event.chain_result(
            [Image.fromFileSystem(tmp_path), Plain(f"WARDOGS 金条价格走势图（{label}）")]
        )
