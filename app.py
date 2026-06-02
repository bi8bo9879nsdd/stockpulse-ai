from __future__ import annotations

import json
import re
from math import ceil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data_provider import get_history, get_quote


APP_TITLE = "StockPulse AI"
DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "watchlist.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
ALERTS_FILE = DATA_DIR / "alerts.json"
PAPER_ACCOUNT_FILE = DATA_DIR / "paper_account.json"
PAPER_ORDERS_FILE = DATA_DIR / "paper_orders.json"
PAPER_POSITIONS_FILE = DATA_DIR / "paper_positions.json"
DEFAULT_PAPER_CASH = 100_000.0
DEFAULT_CONFIG = {
    "watchlist": ["NVDA", "MU", "MRVL", "QQQ", "AVGO"],
}
STRATEGY_TYPES = [
    "核心持仓",
    "核心波段",
    "高波动题材",
    "高风险小票",
    "短线交易",
    "周期股",
    "成长股",
    "杠杆/高波动产品",
    "中低波动持仓",
    "反转股",
    "自定义策略",
]
RISK_LEVELS = ["低", "中", "中高", "高", "极高"]
STOP_LOSS_RATES = {
    "核心持仓": {"低": 0.08, "中": 0.08, "中高": 0.08, "高": 0.08, "极高": 0.08},
    "核心波段": {"低": 0.08, "中": 0.09, "中高": 0.10, "高": 0.11, "极高": 0.12},
    "高波动题材": {"低": 0.12, "中": 0.13, "中高": 0.135, "高": 0.14, "极高": 0.15},
    "高风险小票": {"低": 0.12, "中": 0.14, "中高": 0.16, "高": 0.18, "极高": 0.20},
    "短线交易": {"低": 0.05, "中": 0.06, "中高": 0.065, "高": 0.07, "极高": 0.08},
    "周期股": {"低": 0.08, "中": 0.09, "中高": 0.10, "高": 0.11, "极高": 0.12},
    "成长股": {"低": 0.08, "中": 0.09, "中高": 0.10, "高": 0.11, "极高": 0.12},
    "杠杆/高波动产品": {"低": 0.10, "中": 0.12, "中高": 0.14, "高": 0.16, "极高": 0.18},
    "中低波动持仓": {"低": 0.06, "中": 0.07, "中高": 0.08, "高": 0.09, "极高": 0.10},
    "反转股": {"低": 0.08, "中": 0.10, "中高": 0.12, "高": 0.14, "极高": 0.16},
    "自定义策略": {"低": 0.08, "中": 0.10, "中高": 0.12, "高": 0.14, "极高": 0.16},
}
ALERT_TYPES = [
    "跌破止损线",
    "接近止损线",
    "达到第一止盈",
    "达到第二止盈",
    "保护利润",
    "高风险观察",
]
ALERT_DIRECTIONS = ["below", "above"]
REFRESH_INTERVALS = {
    "30 秒": 30_000,
    "1 分钟": 60_000,
    "5 分钟": 300_000,
}


def load_config() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return {
            "watchlist": config.get("watchlist", DEFAULT_CONFIG["watchlist"]),
        }
    except (json.JSONDecodeError, OSError):
        st.warning("本地配置文件读取失败，已使用默认自选股列表。")
        return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_portfolio() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PORTFOLIO_FILE.exists():
        save_portfolio([])
        return []

    try:
        raw_json = PORTFOLIO_FILE.read_text(encoding="utf-8").strip()
        if not raw_json:
            save_portfolio([])
            return []
        portfolio = json.loads(raw_json)
        if not isinstance(portfolio, list):
            raise ValueError("持仓配置必须是列表")
        return [validate_position(position) for position in portfolio]
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        st.warning(f"本地持仓配置读取失败：{exc}。请检查 portfolio.json。")
        return []


def save_portfolio(portfolio: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(
        json.dumps(portfolio, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_alerts() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not ALERTS_FILE.exists():
        save_alerts([])
        return []

    try:
        raw_json = ALERTS_FILE.read_text(encoding="utf-8").strip()
        if not raw_json:
            save_alerts([])
            return []
        alerts = json.loads(raw_json)
        if not isinstance(alerts, list):
            raise ValueError("提醒配置必须是列表")
        return [validate_alert(alert) for alert in alerts]
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        st.warning(f"本地提醒配置读取失败：{exc}。请检查 alerts.json。")
        return []


def save_alerts(alerts: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ALERTS_FILE.write_text(
        json.dumps(alerts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json_file(path: Path, default: Any) -> Any:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        save_json_file(path, default)
        return default
    try:
        raw_json = path.read_text(encoding="utf-8").strip()
        if not raw_json:
            save_json_file(path, default)
            return default
        return json.loads(raw_json)
    except json.JSONDecodeError as exc:
        st.warning(f"{path.name} JSON 解析失败：{exc}。已使用默认值。")
        return default
    except OSError as exc:
        st.warning(f"本地文件读取失败：{path.name}（{exc}）。已使用默认值。")
        return default


def save_json_file(path: Path, data: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_paper_account() -> dict[str, float]:
    account = load_json_file(
        PAPER_ACCOUNT_FILE,
        {
            "initial_cash": DEFAULT_PAPER_CASH,
            "cash": DEFAULT_PAPER_CASH,
            "total_equity": DEFAULT_PAPER_CASH,
            "realized_pnl": 0.0,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    return {
        "initial_cash": float(account.get("initial_cash", DEFAULT_PAPER_CASH)),
        "cash": float(account.get("cash", DEFAULT_PAPER_CASH)),
        "total_equity": float(
            account.get("total_equity", account.get("total_assets", DEFAULT_PAPER_CASH))
        ),
        "realized_pnl": float(account.get("realized_pnl", 0.0)),
        "updated_at": str(
            account.get(
                "updated_at",
                datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        ),
    }


def save_paper_account(account: dict[str, float]) -> None:
    save_json_file(PAPER_ACCOUNT_FILE, account)


def load_paper_positions() -> list[dict[str, Any]]:
    return load_json_file(PAPER_POSITIONS_FILE, [])


def save_paper_positions(positions: list[dict[str, Any]]) -> None:
    save_json_file(PAPER_POSITIONS_FILE, positions)


def load_paper_orders() -> list[dict[str, Any]]:
    return load_json_file(PAPER_ORDERS_FILE, [])


def save_paper_orders(orders: list[dict[str, Any]]) -> None:
    save_json_file(PAPER_ORDERS_FILE, orders)


def validate_alert(alert: dict[str, Any]) -> dict[str, Any]:
    required_fields = {"ticker", "alert_type", "target_price", "direction"}
    missing_fields = required_fields - alert.keys()
    if missing_fields:
        raise ValueError(f"缺少必填字段：{', '.join(sorted(missing_fields))}")
    enabled = alert.get("enabled", True)
    if isinstance(enabled, str):
        if enabled.lower() not in {"true", "false"}:
            raise ValueError(f"{alert['ticker']} 的 enabled 必须为 true 或 false")
        enabled = enabled.lower() == "true"
    normalized = {
        "ticker": str(alert["ticker"]).strip().upper(),
        "alert_type": str(alert["alert_type"]),
        "target_price": float(alert["target_price"]),
        "direction": str(alert["direction"]).lower(),
        "message": str(alert.get("message", "")).strip(),
        "enabled": bool(enabled),
    }
    if not normalized["ticker"]:
        raise ValueError("股票代码不能为空")
    if normalized["target_price"] <= 0:
        raise ValueError(f"{normalized['ticker']} 的目标价格必须大于 0")
    if normalized["alert_type"] not in ALERT_TYPES:
        raise ValueError(f"{normalized['ticker']} 的提醒类型无效")
    if normalized["direction"] not in ALERT_DIRECTIONS:
        raise ValueError(f"{normalized['ticker']} 的触发方向无效")
    return normalized


def parse_alerts_json(raw_json: str) -> list[dict[str, Any]]:
    if not raw_json.strip():
        raise ValueError("请先粘贴提醒规则 JSON。")
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无法解析，请检查格式：第 {exc.lineno} 行第 {exc.colno} 列。") from exc
    if not isinstance(payload, list):
        raise ValueError("提醒规则 JSON 必须是数组格式。")

    alerts_by_key = {}
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 项必须是 JSON 对象。")
        try:
            alert = validate_alert(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 项校验失败：{exc}") from exc
        key = (alert["ticker"], alert["alert_type"], alert["direction"])
        alerts_by_key[key] = alert
    return list(alerts_by_key.values())


def validate_position(position: dict[str, Any]) -> dict[str, Any]:
    required_fields = {"ticker", "shares", "cost_basis"}
    missing_fields = required_fields - position.keys()
    if missing_fields:
        raise ValueError(f"缺少必填字段：{', '.join(sorted(missing_fields))}")
    normalized = {
        "ticker": str(position["ticker"]).strip().upper(),
        "shares": float(position["shares"]),
        "cost_basis": float(position["cost_basis"]),
        "risk_level": str(position.get("risk_level", "中")),
        "strategy_type": str(position.get("strategy_type", "核心持仓")),
        "notes": str(position.get("notes", "")).strip(),
    }
    if not normalized["ticker"]:
        raise ValueError("股票代码不能为空")
    if normalized["shares"] <= 0 or normalized["cost_basis"] <= 0:
        raise ValueError(f"{normalized['ticker']} 的持仓股数和成本价必须大于 0")
    if normalized["risk_level"] not in RISK_LEVELS:
        raise ValueError(f"{normalized['ticker']} 的风险等级无效")
    if normalized["strategy_type"] not in STRATEGY_TYPES:
        raise ValueError(f"{normalized['ticker']} 的策略类型无效")
    return normalized


def parse_portfolio_json(raw_json: str) -> list[dict[str, Any]]:
    portfolio, _ = parse_portfolio_json_with_mappings(raw_json)
    return portfolio


def parse_portfolio_json_with_mappings(
    raw_json: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not raw_json.strip():
        raise ValueError("请先粘贴持仓 JSON。")
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无法解析，请检查格式：第 {exc.lineno} 行第 {exc.colno} 列。") from exc
    if not isinstance(payload, list):
        raise ValueError("持仓 JSON 必须是数组格式。")

    positions_by_ticker = {}
    mapped_strategy_tickers = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 项必须是 JSON 对象。")
        normalized_item = item.copy()
        ticker = str(normalized_item.get("ticker", "")).strip().upper()
        if normalized_item.get("strategy_type", "核心持仓") not in STRATEGY_TYPES:
            normalized_item["strategy_type"] = "自定义策略"
            if ticker:
                mapped_strategy_tickers.append(ticker)
        if normalized_item.get("risk_level", "中") not in RISK_LEVELS:
            normalized_item["risk_level"] = "中"
        try:
            position = validate_position(normalized_item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {index} 项校验失败：{exc}") from exc
        positions_by_ticker[position["ticker"]] = position
    return list(positions_by_ticker.values()), list(dict.fromkeys(mapped_strategy_tickers))


def parse_symbols(raw_symbols: str) -> list[str]:
    symbols = re.split(r"[\s,，;；]+", raw_symbols.upper().strip())
    return list(dict.fromkeys(symbol for symbol in symbols if symbol))


def calculate_rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    average_gain = gain.iloc[-1]
    average_loss = loss.iloc[-1]
    if pd.isna(average_gain) or pd.isna(average_loss):
        return None
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return float(100 - (100 / (1 + relative_strength)))


@st.cache_data(ttl=120, show_spinner=False)
def fetch_stock_data(symbol: str) -> dict[str, Any]:
    quote = get_quote(symbol)
    history = get_history(symbol)

    close = history["Close"].dropna()
    if len(close) < 2:
        raise ValueError("历史行情不足")

    volumes = history["Volume"].dropna() if "Volume" in history else pd.Series(dtype=float)
    history_volume = int(volumes.iloc[-1]) if not volumes.empty else None

    return {
        "symbol": symbol,
        "price": quote["price"],
        "daily_change": quote["change_percent"] or 0.0,
        "volume": quote["volume"] or history_volume,
        "source": quote["source"],
        "data_status": quote["data_status"],
        "ma5": float(close.rolling(5).mean().iloc[-1]) if len(close) >= 5 else None,
        "ma20": float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None,
        "rsi": calculate_rsi(close),
    }


def fetch_watchlist_data(symbols: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    records = []
    errors = []
    for symbol in symbols:
        try:
            records.append(fetch_stock_data(symbol))
        except Exception as exc:
            errors.append(f"{symbol}：{exc}")
    return records, errors


def evaluate_alert(alert: dict[str, Any], stock: dict[str, Any]) -> bool:
    target = alert["target_price"]
    if stock["price"] is None:
        return False
    if alert["direction"] == "below":
        return stock["price"] <= target
    if alert["direction"] == "above":
        return stock["price"] >= target
    return False


def alert_description(alert: dict[str, Any]) -> str:
    direction_name = "跌破" if alert["direction"] == "below" else "达到"
    return (
        f'{alert["ticker"]} {alert["alert_type"]}：'
        f'{direction_name} {alert["target_price"]:g} 美元'
    )


def build_research_brief(records: list[dict[str, Any]]) -> str:
    if not records:
        return "暂无可用行情，暂时无法生成投研简报。"

    strongest = max(records, key=lambda stock: stock["daily_change"])
    weakest = min(records, key=lambda stock: stock["daily_change"])
    rising_count = sum(stock["daily_change"] > 0 for stock in records)
    falling_count = sum(stock["daily_change"] < 0 for stock in records)
    overbought = [
        stock["symbol"]
        for stock in records
        if stock["rsi"] is not None and stock["rsi"] >= 70
    ]
    oversold = [
        stock["symbol"]
        for stock in records
        if stock["rsi"] is not None and stock["rsi"] <= 30
    ]
    above_ma20 = [
        stock["symbol"]
        for stock in records
        if stock["ma20"] is not None
        and stock["price"] is not None
        and stock["price"] >= stock["ma20"]
    ]

    sections = [
        f"今日自选股中，上涨 {rising_count} 只，下跌 {falling_count} 只。",
        (
            f"表现最强的是 {strongest['symbol']}，日涨跌幅为 "
            f"{strongest['daily_change']:+.2f}%；表现较弱的是 {weakest['symbol']}，"
            f"日涨跌幅为 {weakest['daily_change']:+.2f}%。"
        ),
        f"共有 {len(above_ma20)} 只标的位于 MA20 上方，短中期趋势相对占优。",
    ]
    if overbought:
        sections.append(f"RSI 偏高的标的：{', '.join(overbought)}，请留意短线回撤风险。")
    if oversold:
        sections.append(f"RSI 偏低的标的：{', '.join(oversold)}，可关注是否出现企稳信号。")
    if not overbought and not oversold:
        sections.append("当前没有 RSI 超买或超卖信号。")
    sections.append("以上内容由规则模板生成，仅供投研参考，不构成投资建议。")
    return "\n\n".join(sections)


def calculate_stop_loss(position: dict[str, Any], ma20: float | None) -> float:
    cost_basis = position["cost_basis"]
    risk_level = position["risk_level"]
    strategy_type = position["strategy_type"]
    if strategy_type == "核心持仓":
        cost_stop = cost_basis * 0.92
        return max(cost_stop, ma20) if ma20 is not None else cost_stop
    return cost_basis * (1 - STOP_LOSS_RATES[strategy_type][risk_level])


def build_profit_loss_plan(
    portfolio: list[dict[str, Any]], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    plans = []
    for position in portfolio:
        stock = stocks_by_symbol.get(position["ticker"])
        if not stock or stock["price"] is None:
            continue
        cost_basis = position["cost_basis"]
        stop_loss = calculate_stop_loss(position, stock["ma20"])
        plans.append(
            {
                **position,
                "price": stock["price"],
                "profit_loss": (stock["price"] - cost_basis) * position["shares"],
                "profit_loss_percent": (stock["price"] - cost_basis) / cost_basis * 100,
                "stop_loss": stop_loss,
                "take_profit_1": cost_basis * 1.10,
                "take_profit_2": cost_basis * 1.20,
                "take_profit_3": cost_basis * 1.30,
            }
        )
    return plans


def calculate_draft_quantity(shares: float, ratio: float) -> float:
    return min(shares, max(1.0, float(ceil(shares * ratio))))


def build_trade_plan_drafts(
    portfolio: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    plans = build_profit_loss_plan(portfolio, records)
    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    enabled_alerts_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for alert in alerts:
        if alert["enabled"]:
            enabled_alerts_by_ticker.setdefault(alert["ticker"], []).append(alert)

    drafts = []
    for plan in plans:
        ticker = plan["ticker"]
        price = plan["price"]
        shares = plan["shares"]
        stock = stocks_by_symbol[ticker]
        triggered_alerts = [
            alert
            for alert in enabled_alerts_by_ticker.get(ticker, [])
            if evaluate_alert(alert, stock)
        ]
        triggered_types = {alert["alert_type"] for alert in triggered_alerts}

        if price <= plan["stop_loss"] or "跌破止损线" in triggered_types:
            action = "STOP_LOSS"
            quantity = shares
            limit_price = plan["stop_loss"]
            reason = "当前价已触及止损线，建议优先评估退出或降低风险敞口。"
        elif price >= plan["take_profit_2"] or "达到第二止盈" in triggered_types:
            action = "TAKE_PROFIT"
            quantity = calculate_draft_quantity(shares, 0.50)
            limit_price = plan["take_profit_2"]
            reason = "已达到第二止盈区，建议评估锁定部分利润。"
        elif price >= plan["take_profit_1"] or "达到第一止盈" in triggered_types:
            action = "TAKE_PROFIT"
            quantity = calculate_draft_quantity(shares, 0.25)
            limit_price = plan["take_profit_1"]
            reason = "已达到第一止盈区，建议评估分批止盈。"
        elif (
            price <= plan["stop_loss"] * 1.03
            or "接近止损线" in triggered_types
            or "保护利润" in triggered_types
            or "高风险观察" in triggered_types
        ):
            action = "REDUCE"
            quantity = calculate_draft_quantity(shares, 0.25)
            limit_price = price
            reason = "已接近风险区或触发保护提醒，建议评估降低仓位。"
        else:
            action = "WATCH"
            quantity = 0.0
            limit_price = price
            reason = "当前未触发止盈止损条件，继续观察。"

        alert_messages = [
            alert["message"] for alert in triggered_alerts if alert["message"]
        ]
        if alert_messages:
            reason += f" 已触发提醒：{'；'.join(alert_messages)}"

        drafts.append(
            {
                "ticker": ticker,
                "action": action,
                "quantity": quantity,
                "order_type": "LIMIT_DRAFT" if action != "WATCH" else "WATCH_ONLY",
                "limit_price": round(limit_price, 2),
                "reason": reason,
                "risk_level": plan["risk_level"],
            }
        )
    return drafts


def trade_plan_to_markdown(drafts: list[dict[str, Any]]) -> str:
    lines = [
        "# StockPulse AI 交易计划草稿",
        "",
        "> 系统仅生成交易计划，不连接券商账户，不自动下单。所有草稿必须由用户手动确认后，自行在券商 App 中执行。",
        "",
        "| 股票代码 | 动作 | 数量 | 订单类型 | 限价 | 风险等级 | 原因 |",
        "| --- | --- | ---: | --- | ---: | --- | --- |",
    ]
    for draft in drafts:
        reason = draft["reason"].replace("|", "｜")
        lines.append(
            f"| {draft['ticker']} | {draft['action']} | {draft['quantity']:g} | "
            f"{draft['order_type']} | {draft['limit_price']:.2f} | "
            f"{draft['risk_level']} | {reason} |"
        )
    return "\n".join(lines)


def update_paper_account_metrics(
    account: dict[str, float],
    positions: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, float]:
    prices = {stock["symbol"]: stock["price"] for stock in records}
    market_value = 0.0
    unrealized_pnl = 0.0
    for position in positions:
        current_price = prices.get(position["ticker"]) or position["avg_cost"]
        position["market_value"] = position["shares"] * current_price
        position["unrealized_pnl"] = (
            current_price - position["avg_cost"]
        ) * position["shares"]
        position["unrealized_pnl_pct"] = (
            (current_price - position["avg_cost"]) / position["avg_cost"] * 100
            if position["avg_cost"]
            else 0.0
        )
        market_value += position["market_value"]
        unrealized_pnl += position["unrealized_pnl"]
    account["total_equity"] = account["cash"] + market_value
    account["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return account


def build_paper_statistics(
    account: dict[str, float],
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> dict[str, float]:
    updated_account = update_paper_account_metrics(account.copy(), positions, records)
    filled_sell_orders = [
        order
        for order in orders
        if order["status"] == "FILLED" and order["action"] == "SELL"
    ]
    winning_orders = [
        order for order in filled_sell_orders if order.get("realized_pnl", 0.0) > 0
    ]
    win_rate = (
        len(winning_orders) / len(filled_sell_orders) * 100
        if filled_sell_orders
        else 0.0
    )
    initial_cash = updated_account["initial_cash"]
    cumulative_return = (
        (updated_account["total_equity"] - initial_cash) / initial_cash * 100
        if initial_cash
        else 0.0
    )
    market_value = sum(position.get("market_value", 0.0) for position in positions)
    unrealized_pnl = sum(position.get("unrealized_pnl", 0.0) for position in positions)
    return {
        "total_equity": updated_account["total_equity"],
        "cash": updated_account["cash"],
        "market_value": market_value,
        "realized_pnl": updated_account["realized_pnl"],
        "unrealized_pnl": unrealized_pnl,
        "cumulative_return": cumulative_return,
        "win_rate": win_rate,
    }


def execute_paper_limit_order(
    ticker: str,
    action: str,
    quantity: float,
    limit_price: float,
    records: list[dict[str, Any]],
    reason: str = "",
    source: str = "MANUAL",
    alert_type: str = "",
) -> dict[str, Any]:
    normalized_ticker = ticker.strip().upper()
    normalized_action = action.upper()
    if normalized_action not in {"BUY", "SELL"}:
        raise ValueError("模拟交易动作只支持 BUY 或 SELL")
    if quantity <= 0 or limit_price <= 0:
        raise ValueError("模拟订单数量和限价必须大于 0")

    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    stock = stocks_by_symbol.get(normalized_ticker)
    current_price = stock["price"] if stock else None
    order = {
        "order_id": uuid4().hex,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ticker": normalized_ticker,
        "action": normalized_action,
        "quantity": float(quantity),
        "order_type": "LIMIT",
        "limit_price": float(limit_price),
        "filled_price": None,
        "status": "PENDING",
        "reason": reason or "用户手动提交本地模拟订单",
        "source": source,
        "alert_type": alert_type,
    }
    orders = load_paper_orders()
    positions = load_paper_positions()
    account = load_paper_account()

    if current_price is None:
        order["reason"] += "；当前行情不可用，订单未成交"
    elif normalized_action == "BUY" and current_price > limit_price:
        order["reason"] += "；当前价高于买入限价，订单未成交"
    elif normalized_action == "SELL" and current_price < limit_price:
        order["reason"] += "；当前价低于卖出限价，订单未成交"
    else:
        fill_price = float(current_price)
        position = next(
            (item for item in positions if item["ticker"] == normalized_ticker),
            None,
        )
        if normalized_action == "BUY":
            cost = fill_price * quantity
            if account["cash"] < cost:
                order["reason"] += "；模拟账户现金不足，订单未成交"
            else:
                if position is None:
                    position = {
                        "ticker": normalized_ticker,
                        "shares": 0.0,
                        "avg_cost": 0.0,
                        "market_value": 0.0,
                        "unrealized_pnl": 0.0,
                        "unrealized_pnl_pct": 0.0,
                    }
                    positions.append(position)
                total_cost = position["avg_cost"] * position["shares"] + cost
                position["shares"] += quantity
                position["avg_cost"] = total_cost / position["shares"]
                account["cash"] -= cost
                order["status"] = "FILLED"
        elif position is None or position["shares"] < quantity:
            order["reason"] += "；模拟持仓不足，订单未成交"
        else:
            realized_pnl = (fill_price - position["avg_cost"]) * quantity
            position["shares"] -= quantity
            position["realized_pnl"] = position.get("realized_pnl", 0.0) + realized_pnl
            account["cash"] += fill_price * quantity
            account["realized_pnl"] += realized_pnl
            order["status"] = "FILLED"
            order["realized_pnl"] = realized_pnl
            if position["shares"] == 0:
                positions.remove(position)

        if order["status"] == "FILLED":
            order["filled_price"] = fill_price
            order["reason"] += f"；已按当前行情 {fill_price:.2f} 美元模拟成交"

    orders.append(order)
    account = update_paper_account_metrics(account, positions, records)
    save_paper_account(account)
    save_paper_positions(positions)
    save_paper_orders(orders)
    return order


def reset_paper_account(initial_cash: float) -> None:
    if initial_cash <= 0:
        raise ValueError("初始模拟资金必须大于 0")
    save_paper_account(
        {
            "initial_cash": float(initial_cash),
            "cash": float(initial_cash),
            "total_equity": float(initial_cash),
            "realized_pnl": 0.0,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    save_paper_positions([])
    save_paper_orders([])


def initialize_paper_positions_from_portfolio(
    portfolio: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    account = load_paper_account()
    total_cost = sum(position["shares"] * position["cost_basis"] for position in portfolio)
    if total_cost > account["initial_cash"]:
        raise ValueError("真实持仓成本总额超过初始模拟资金，无法初始化模拟持仓。")
    positions = [
        {
            "ticker": position["ticker"],
            "shares": float(position["shares"]),
            "avg_cost": float(position["cost_basis"]),
            "market_value": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
        }
        for position in portfolio
    ]
    account["cash"] = account["initial_cash"] - total_cost
    account["realized_pnl"] = 0.0
    account = update_paper_account_metrics(account, positions, records)
    save_paper_account(account)
    save_paper_positions(positions)
    save_paper_orders([])


def record_paper_signal(
    ticker: str,
    action: str,
    reason: str,
    source: str = "AUTO",
    alert_type: str = "",
) -> dict[str, Any]:
    order = {
        "order_id": uuid4().hex,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ticker": ticker,
        "action": action,
        "quantity": 0.0,
        "order_type": "LIMIT",
        "limit_price": None,
        "filled_price": None,
        "status": "WATCH" if action == "WATCH" else "SKIPPED",
        "reason": reason,
        "source": source,
        "alert_type": alert_type,
    }
    orders = load_paper_orders()
    orders.append(order)
    save_paper_orders(orders)
    return order


def execute_automatic_paper_trades(
    portfolio: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    positions = load_paper_positions()
    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    active_alerts = [alert for alert in alerts if alert["enabled"]]
    plans_by_ticker = {
        plan["ticker"]: plan for plan in build_profit_loss_plan(portfolio, records)
    }
    today = datetime.now().astimezone().date().isoformat()
    executed_alert_keys = {
        (order["ticker"], order.get("alert_type"))
        for order in load_paper_orders()
        if str(order.get("timestamp", "")).startswith(today)
        and order.get("source") == "AUTO"
        and order.get("alert_type")
    }
    generated_orders = []

    for position in list(positions):
        ticker = position["ticker"]
        stock = stocks_by_symbol.get(ticker)
        if not stock or stock["price"] is None:
            generated_orders.append(
                record_paper_signal(ticker, "SKIP", "当前行情不可用，跳过自动模拟交易。")
            )
            continue

        ticker_alerts = [alert for alert in active_alerts if alert["ticker"] == ticker]
        triggered_alerts = [
            alert for alert in ticker_alerts if evaluate_alert(alert, stock)
        ]
        price = float(stock["price"])
        plan = plans_by_ticker.get(ticker)
        for alert in triggered_alerts:
            alert_type = alert["alert_type"]
            alert_key = (ticker, alert_type)
            if alert_key in executed_alert_keys:
                continue
            if alert_type == "高风险观察":
                generated_orders.append(
                    record_paper_signal(
                        ticker,
                        "WATCH",
                        "触发高风险观察，仅记录 WATCH 信号。",
                        alert_type=alert_type,
                    )
                )
                executed_alert_keys.add(alert_key)
                continue
            if alert_type not in {"跌破止损线", "达到第一止盈", "达到第二止盈"}:
                continue
            current_positions = load_paper_positions()
            active_position = next(
                (item for item in current_positions if item["ticker"] == ticker),
                None,
            )
            if active_position is None or active_position["shares"] < 1:
                generated_orders.append(
                    record_paper_signal(
                        ticker,
                        "SKIP",
                        "模拟持仓股数不足 1 股，跳过自动交易。",
                        alert_type=alert_type,
                    )
                )
                executed_alert_keys.add(alert_key)
                continue

            ratios = {
                "跌破止损线": 0.50,
                "达到第一止盈": 0.30,
                "达到第二止盈": 0.30,
            }
            reasons = {
                "跌破止损线": "触发止损线，模拟减仓控制风险",
                "达到第一止盈": "达到第一止盈，模拟分批止盈",
                "达到第二止盈": "达到第二止盈，模拟锁定利润",
            }
            plan_text = (
                f"；计划止损线 {plan['stop_loss']:.2f}，"
                f"第一止盈线 {plan['take_profit_1']:.2f}，"
                f"第二止盈线 {plan['take_profit_2']:.2f}"
                if plan
                else ""
            )
            quantity = min(
                active_position["shares"],
                max(1.0, float(ceil(active_position["shares"] * ratios[alert_type]))),
            )
            generated_orders.append(
                execute_paper_limit_order(
                    ticker,
                    "SELL",
                    quantity,
                    price,
                    records,
                    reason=f"{reasons[alert_type]}{plan_text}",
                    source="AUTO",
                    alert_type=alert_type,
                )
            )
            executed_alert_keys.add(alert_key)
    return generated_orders


def build_paper_review(
    account: dict[str, float],
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> str:
    today = datetime.now().astimezone().date().isoformat()
    today_orders = [
        order for order in orders if str(order.get("timestamp", "")).startswith(today)
    ]
    filled_orders = [order for order in today_orders if order["status"] == "FILLED"]
    take_profit_orders = [
        order for order in filled_orders if "止盈" in order.get("reason", "")
    ]
    stop_loss_orders = [
        order for order in filled_orders if "止损" in order.get("reason", "")
    ]
    cumulative_return = (
        (account["total_equity"] - account["initial_cash"]) / account["initial_cash"] * 100
        if account["initial_cash"]
        else 0.0
    )
    riskiest = max(
        positions,
        key=lambda position: abs(position.get("market_value", 0.0)),
        default=None,
    )
    riskiest_text = (
        f"{riskiest['ticker']}，市值 {riskiest.get('market_value', 0.0):,.2f} 美元"
        if riskiest
        else "暂无模拟持仓"
    )
    return "\n\n".join(
        [
            f"今日共记录 {len(today_orders)} 条模拟信号或订单，其中 {len(filled_orders)} 条模拟成交。",
            f"止盈成交：{', '.join(order['ticker'] for order in take_profit_orders) or '无'}。",
            f"止损成交：{', '.join(order['ticker'] for order in stop_loss_orders) or '无'}。",
            f"当前模拟账户累计收益率为 {cumulative_return:+.2f}%。",
            f"当前最大风险仓位：{riskiest_text}。",
        ]
    )


def paper_review_to_markdown(
    account: dict[str, float],
    positions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> str:
    return "\n".join(
        [
            "# StockPulse AI 模拟交易复盘报告",
            "",
            "> 这是本地模拟交易，不连接真实券商账户，不产生真实订单，不构成投资建议。",
            "",
            build_paper_review(account, positions, orders),
            "",
            "## 模拟订单记录",
            "",
            "```json",
            json.dumps(orders, ensure_ascii=False, indent=2),
            "```",
        ]
    )


def render_profit_loss_plan(
    portfolio: list[dict[str, Any]], records: list[dict[str, Any]]
) -> None:
    st.subheader("止盈止损计划")
    st.caption("止盈止损线由持仓策略和风险等级自动生成，仅用于投研信息整理。")
    plans = build_profit_loss_plan(portfolio, records)
    if not plans:
        st.info("暂无可展示的持仓计划。请检查本地持仓配置或行情数据。")
        return

    rows = [
        {
            "股票代码": plan["ticker"],
            "策略类型": plan["strategy_type"],
            "当前价（美元）": plan["price"],
            "成本价（美元）": plan["cost_basis"],
            "持仓股数": plan["shares"],
            "浮盈浮亏（美元）": plan["profit_loss"],
            "浮盈浮亏（%）": plan["profit_loss_percent"],
            "止损线（美元）": plan["stop_loss"],
            "第一止盈线（美元）": plan["take_profit_1"],
            "第二止盈线（美元）": plan["take_profit_2"],
            "风险等级": plan["risk_level"],
        }
        for plan in plans
    ]
    table = pd.DataFrame(rows)
    st.dataframe(
        table.style.format(
            {
                "当前价（美元）": "{:.2f}",
                "成本价（美元）": "{:.2f}",
                "持仓股数": "{:,.0f}",
                "浮盈浮亏（美元）": "{:+,.2f}",
                "浮盈浮亏（%）": "{:+.2f}",
                "止损线（美元）": "{:.2f}",
                "第一止盈线（美元）": "{:.2f}",
                "第二止盈线（美元）": "{:.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    for plan in plans:
        if plan["price"] <= plan["stop_loss"] * 1.03:
            st.error(
                f"{plan['ticker']} 当前价已接近或触及止损线，请及时评估持仓风险。"
            )
        if plan["price"] >= plan["take_profit_1"]:
            st.warning(f"{plan['ticker']} 已达到第一止盈线，建议考虑分批止盈。")


def render_trade_plan_drafts(
    portfolio: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    st.subheader("交易计划草稿")
    st.warning("系统仅生成交易计划，不连接券商账户，不自动下单。")
    st.info("所有交易计划必须由用户手动确认后，自行在券商 App 中执行。")
    drafts = build_trade_plan_drafts(portfolio, alerts, records)
    if not drafts:
        st.info("暂无可生成的交易计划草稿。请先录入持仓并获取行情。")
        return

    rows = [
        {
            "股票代码": draft["ticker"],
            "动作": draft["action"],
            "建议数量": draft["quantity"],
            "订单类型": draft["order_type"],
            "草稿限价（美元）": draft["limit_price"],
            "原因": draft["reason"],
            "风险等级": draft["risk_level"],
        }
        for draft in drafts
    ]
    st.dataframe(
        pd.DataFrame(rows).style.format(
            {
                "建议数量": "{:,.2f}",
                "草稿限价（美元）": "{:.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    export_columns = st.columns(2)
    export_columns[0].download_button(
        "导出交易计划为 Markdown",
        data=trade_plan_to_markdown(drafts),
        file_name="stockpulse_trade_plan.md",
        mime="text/markdown",
        use_container_width=True,
    )
    export_columns[1].download_button(
        "导出交易计划为 JSON",
        data=json.dumps(drafts, ensure_ascii=False, indent=2),
        file_name="stockpulse_trade_plan.json",
        mime="application/json",
        use_container_width=True,
    )


def render_paper_trading(
    portfolio: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    st.subheader("模拟交易 / Paper Trading")
    st.warning("这是本地模拟交易，不连接真实券商账户，不产生真实订单，不构成投资建议。")
    st.caption("自动模拟交易和手动限价单都只写入本地 JSON 文件，仅用于练习和复盘。")

    account = load_paper_account()
    positions = load_paper_positions()
    orders = load_paper_orders()
    account = update_paper_account_metrics(account, positions, records)
    save_paper_account(account)
    statistics = build_paper_statistics(account, positions, orders, records)

    metrics = st.columns(6)
    metrics[0].metric("模拟账户总资产", f"{statistics['total_equity']:,.2f}")
    metrics[1].metric("现金（美元）", f"{statistics['cash']:,.2f}")
    metrics[2].metric("持仓市值（美元）", f"{statistics['market_value']:,.2f}")
    metrics[3].metric("已实现盈亏", f"{statistics['realized_pnl']:+,.2f}")
    metrics[4].metric("未实现盈亏", f"{statistics['unrealized_pnl']:+,.2f}")
    metrics[5].metric("累计收益率", f"{statistics['cumulative_return']:+.2f}%")

    with st.expander("初始化模拟账户", expanded=False):
        with st.form("paper_account_form"):
            initial_cash = st.number_input(
                "初始模拟资金（美元）",
                min_value=1.0,
                value=float(account["initial_cash"]),
                step=1_000.0,
            )
            reset_submitted = st.form_submit_button("初始化模拟账户", use_container_width=True)
            if reset_submitted:
                reset_paper_account(initial_cash)
                st.session_state["paper_message"] = "模拟账户已初始化。"
                st.rerun()
        st.caption("修改初始资金会清空模拟订单与模拟持仓。")

    if message := st.session_state.pop("paper_message", None):
        st.success(message)

    action_columns = st.columns(2)
    if action_columns[0].button("从真实持仓初始化模拟持仓", use_container_width=True):
        try:
            initialize_paper_positions_from_portfolio(portfolio, records)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["paper_message"] = "已根据真实持仓初始化模拟持仓。"
            st.rerun()
    if action_columns[1].button("自动执行模拟交易", use_container_width=True):
        generated_orders = execute_automatic_paper_trades(portfolio, alerts, records)
        filled_count = sum(order["status"] == "FILLED" for order in generated_orders)
        st.session_state["paper_message"] = (
            f"自动模拟交易完成：记录 {len(generated_orders)} 条信号或订单，"
            f"其中 {filled_count} 条模拟成交。"
        )
        st.rerun()

    tradable_symbols = sorted(
        {
            stock["symbol"]
            for stock in records
            if stock["price"] is not None
        }
        | {position["ticker"] for position in positions}
    )
    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    with st.expander("提交本地模拟限价单", expanded=False):
        if not tradable_symbols:
            st.info("暂无可用行情，暂时无法提交模拟订单。")
        else:
            with st.form("paper_order_form", clear_on_submit=True):
                ticker = st.selectbox("股票代码", tradable_symbols)
                action = st.selectbox("模拟交易动作", ["BUY", "SELL"])
                quantity = st.number_input("模拟交易数量", min_value=0.01, value=1.0, step=1.0)
                st.selectbox("模拟订单类型", ["LIMIT"], disabled=True)
                current_price = stocks_by_symbol.get(ticker, {}).get("price")
                if current_price is None:
                    st.warning("当前行情不可用，提交后模拟订单将保持未成交。")
                    current_price = 0.01
                limit_price = st.number_input(
                    "模拟限价（美元）",
                    min_value=0.01,
                    value=float(current_price),
                    step=0.01,
                )
                submitted = st.form_submit_button("提交模拟订单", use_container_width=True)
                if submitted:
                    order = execute_paper_limit_order(
                        ticker,
                        action,
                        quantity,
                        limit_price,
                        records,
                    )
                    st.session_state["paper_message"] = (
                        f"模拟订单已记录：{order['ticker']} {order['action']}，"
                        f"状态 {order['status']}。"
                    )
                    st.rerun()

    positions = load_paper_positions()
    orders = load_paper_orders()
    account = update_paper_account_metrics(load_paper_account(), positions, records)
    save_paper_account(account)
    st.markdown("#### 模拟持仓")
    if not positions:
        st.info("暂无模拟持仓。")
    else:
        position_rows = []
        for position in positions:
            current_price = stocks_by_symbol.get(position["ticker"], {}).get(
                "price", position["avg_cost"]
            )
            current_price = current_price or position["avg_cost"]
            market_value = position["shares"] * current_price
            profit_loss = (current_price - position["avg_cost"]) * position["shares"]
            position_rows.append(
                {
                    "股票代码": position["ticker"],
                    "模拟持仓股数": position["shares"],
                    "平均成本（美元）": position["avg_cost"],
                    "当前价（美元）": current_price,
                    "持仓市值（美元）": market_value,
                    "浮盈浮亏（美元）": profit_loss,
                    "浮盈浮亏（%）": position.get("unrealized_pnl_pct", 0.0),
                }
            )
        st.dataframe(
            pd.DataFrame(position_rows).style.format(
                {
                    "模拟持仓股数": "{:,.2f}",
                    "平均成本（美元）": "{:.2f}",
                    "当前价（美元）": "{:.2f}",
                    "持仓市值（美元）": "{:,.2f}",
                    "浮盈浮亏（美元）": "{:+,.2f}",
                    "浮盈浮亏（%）": "{:+.2f}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 模拟订单历史")
    if not orders:
        st.info("暂无模拟订单。")
    else:
        st.dataframe(
            pd.DataFrame(orders),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 模拟交易复盘报告")
    st.write(build_paper_review(account, positions, orders))
    export_columns = st.columns(2)
    export_columns[0].download_button(
        "导出模拟交易记录 JSON",
        data=json.dumps(orders, ensure_ascii=False, indent=2),
        file_name="stockpulse_paper_orders.json",
        mime="application/json",
        use_container_width=True,
    )
    export_columns[1].download_button(
        "导出 Markdown 交易复盘报告",
        data=paper_review_to_markdown(account, positions, orders),
        file_name="stockpulse_paper_review.md",
        mime="text/markdown",
        use_container_width=True,
    )


def render_portfolio_table(
    portfolio: list[dict[str, Any]], records: list[dict[str, Any]]
) -> None:
    st.subheader("我的真实持仓表")
    st.caption("持仓数据由用户手动录入并保存在本地 portfolio.json，不连接券商账户，不执行任何交易。")
    if not portfolio:
        st.info("暂无持仓，请在左侧粘贴 JSON 后导入。")
        return

    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    rows = []
    for position in portfolio:
        stock = stocks_by_symbol.get(position["ticker"])
        price = stock["price"] if stock else None
        market_value = price * position["shares"] if price is not None else None
        profit_loss = (
            (price - position["cost_basis"]) * position["shares"]
            if price is not None
            else None
        )
        return_rate = (
            (price - position["cost_basis"]) / position["cost_basis"] * 100
            if price is not None
            else None
        )
        rows.append(
            {
                "股票代码": position["ticker"],
                "持仓股数": position["shares"],
                "成本价（美元）": position["cost_basis"],
                "当前价（美元）": price,
                "持仓市值（美元）": market_value,
                "浮盈浮亏（美元）": profit_loss,
                "收益率（%）": return_rate,
                "策略类型": position["strategy_type"],
                "风险等级": position["risk_level"],
                "备注": position["notes"],
            }
        )

    table = pd.DataFrame(rows)
    st.dataframe(
        table.style.format(
            {
                "持仓股数": "{:,.2f}",
                "成本价（美元）": "{:.2f}",
                "当前价（美元）": "{:.2f}",
                "持仓市值（美元）": "{:,.2f}",
                "浮盈浮亏（美元）": "{:+,.2f}",
                "收益率（%）": "{:+.2f}",
            },
            na_rep="-",
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_portfolio_editor(portfolio: list[dict[str, Any]]) -> None:
    st.sidebar.divider()
    st.sidebar.header("批量导入真实持仓 JSON")
    st.sidebar.caption("粘贴 JSON 数组后，可一次覆盖保存全部真实持仓。")
    if message := st.session_state.pop("portfolio_message", None):
        st.sidebar.success(message)
    with st.sidebar.form("portfolio_import_form", clear_on_submit=False):
        raw_json = st.text_area("持仓 JSON", height=320, key="portfolio_json_input")
        import_submitted = st.form_submit_button("导入并保存持仓", use_container_width=True)
        if import_submitted:
            try:
                imported_portfolio, mapped_strategy_tickers = (
                    parse_portfolio_json_with_mappings(raw_json)
                )
            except ValueError as exc:
                st.error(f"导入失败：{exc}")
            else:
                save_portfolio(imported_portfolio)
                message = f"导入成功，共导入 {len(imported_portfolio)} 只持仓"
                if mapped_strategy_tickers:
                    message += (
                        "。以下股票的策略类型已自动映射为“自定义策略”："
                        f"{', '.join(mapped_strategy_tickers)}"
                    )
                st.session_state["portfolio_message"] = message
                st.rerun()

    if st.sidebar.button("清空当前持仓", use_container_width=True):
        save_portfolio([])
        st.session_state["portfolio_message"] = "当前持仓已清空。"
        st.rerun()

    with st.sidebar.expander("单只持仓添加/更新", expanded=False):
        st.caption("同一股票代码再次提交时，将更新原有持仓。")
        with st.form("portfolio_form", clear_on_submit=True):
            ticker = st.text_input("股票代码")
            shares = st.number_input("持仓股数", min_value=0.01, value=1.0, step=1.0)
            cost_basis = st.number_input("成本价（美元）", min_value=0.01, value=1.0, step=0.01)
            strategy_type = st.selectbox("策略类型", STRATEGY_TYPES)
            risk_level = st.selectbox("风险等级", RISK_LEVELS, index=1)
            notes = st.text_area("备注", height=80)
            submitted = st.form_submit_button("添加/更新持仓", use_container_width=True)
            if submitted:
                if not ticker.strip():
                    st.error("请输入股票代码。")
                else:
                    position = validate_position(
                        {
                            "ticker": ticker,
                            "shares": shares,
                            "cost_basis": cost_basis,
                            "strategy_type": strategy_type,
                            "risk_level": risk_level,
                            "notes": notes,
                        }
                    )
                    updated_portfolio = [
                        item for item in portfolio if item["ticker"] != position["ticker"]
                    ]
                    updated_portfolio.append(position)
                    save_portfolio(updated_portfolio)
                    st.rerun()

        if portfolio:
            with st.form("portfolio_delete_form"):
                ticker_to_delete = st.selectbox(
                    "选择要删除的持仓",
                    [position["ticker"] for position in portfolio],
                )
                delete_submitted = st.form_submit_button("删除持仓", use_container_width=True)
                if delete_submitted:
                    save_portfolio(
                        [
                            position
                            for position in portfolio
                            if position["ticker"] != ticker_to_delete
                        ]
                    )
                    st.rerun()


def render_alert_editor(alerts: list[dict[str, Any]], symbols: list[str]) -> None:
    st.sidebar.divider()
    st.sidebar.header("批量导入价格提醒 JSON")
    st.sidebar.caption("粘贴 JSON 数组后，可一次覆盖保存全部价格提醒规则。")
    if message := st.session_state.pop("alerts_message", None):
        st.sidebar.success(message)
    with st.sidebar.form("alerts_import_form", clear_on_submit=False):
        raw_json = st.text_area("价格提醒 JSON", height=280, key="alerts_json_input")
        import_submitted = st.form_submit_button("导入并保存提醒", use_container_width=True)
        if import_submitted:
            try:
                imported_alerts = parse_alerts_json(raw_json)
            except ValueError as exc:
                st.error(f"导入失败：{exc}")
            else:
                save_alerts(imported_alerts)
                st.session_state["alerts_message"] = (
                    f"导入成功，共导入 {len(imported_alerts)} 条提醒"
                )
                st.rerun()

    if st.sidebar.button("清空当前提醒", use_container_width=True):
        save_alerts([])
        st.session_state["alerts_message"] = "当前提醒已清空。"
        st.rerun()

    with st.sidebar.expander("单条价格提醒添加", expanded=False):
        if not symbols:
            st.info("请先添加自选股或持仓。")
            return
        with st.form("alert_form", clear_on_submit=True):
            ticker = st.selectbox("股票代码", symbols)
            alert_type = st.selectbox("提醒类型", ALERT_TYPES)
            target_price = st.number_input("目标价格（美元）", min_value=0.01, value=5.0, step=0.5)
            direction = st.selectbox("触发方向", ALERT_DIRECTIONS)
            message = st.text_area("提醒文案", height=80)
            enabled = st.checkbox("启用提醒", value=True)
            submitted = st.form_submit_button("添加/更新提醒", use_container_width=True)
            if submitted:
                alert = validate_alert(
                    {
                        "ticker": ticker,
                        "alert_type": alert_type,
                        "target_price": target_price,
                        "direction": direction,
                        "message": message,
                        "enabled": enabled,
                    }
                )
                key = (alert["ticker"], alert["alert_type"], alert["direction"])
                updated_alerts = [
                    item
                    for item in alerts
                    if (item["ticker"], item["alert_type"], item["direction"]) != key
                ]
                updated_alerts.append(alert)
                save_alerts(updated_alerts)
                st.rerun()

        if alerts:
            with st.form("alert_delete_form"):
                options = {
                    alert_description(alert): index for index, alert in enumerate(alerts)
                }
                description = st.selectbox("选择要删除的提醒", list(options))
                delete_submitted = st.form_submit_button("删除提醒", use_container_width=True)
                if delete_submitted:
                    save_alerts(
                        [
                            alert
                            for index, alert in enumerate(alerts)
                            if index != options[description]
                        ]
                    )
                    st.rerun()


def render_sidebar(
    config: dict[str, Any],
    portfolio: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
) -> tuple[bool, int, bool, int]:
    st.sidebar.caption(
        "公网部署提示：JSON 数据保存在当前运行实例中。请勿在公开应用中录入敏感持仓；"
        "云端重启或重新部署后数据可能重置。"
    )
    st.sidebar.header("自选股设置")
    raw_symbols = st.sidebar.text_area(
        "输入股票代码，用逗号、空格或换行分隔",
        value=", ".join(config["watchlist"]),
        height=120,
    )
    if st.sidebar.button("保存自选股", use_container_width=True):
        symbols = parse_symbols(raw_symbols)
        if symbols:
            config["watchlist"] = symbols
            save_config(config)
            st.sidebar.success("自选股列表已保存。")
            st.rerun()
        else:
            st.sidebar.error("请至少输入一个股票代码。")

    if st.sidebar.button("刷新行情", use_container_width=True):
        fetch_stock_data.clear()
        st.rerun()

    auto_refresh_enabled = st.sidebar.toggle("自动刷新行情", value=False)
    refresh_interval_name = st.sidebar.selectbox(
        "刷新间隔",
        list(REFRESH_INTERVALS),
        disabled=not auto_refresh_enabled,
    )
    auto_paper_enabled = st.sidebar.toggle("开启自动模拟交易", value=False)
    paper_interval_name = st.sidebar.selectbox(
        "自动模拟交易检查间隔",
        list(REFRESH_INTERVALS),
        disabled=not auto_paper_enabled,
    )

    sidebar_symbols = list(
        dict.fromkeys(config["watchlist"] + [position["ticker"] for position in portfolio])
    )
    render_alert_editor(alerts, sidebar_symbols)
    render_portfolio_editor(portfolio)
    return (
        auto_refresh_enabled,
        REFRESH_INTERVALS[refresh_interval_name],
        auto_paper_enabled,
        REFRESH_INTERVALS[paper_interval_name],
    )


def configure_auto_refresh(
    enabled: bool,
    interval: int,
    component_key: str = "stockpulse_market_autorefresh",
    state_key: str = "market_autorefresh_count",
) -> bool:
    if not enabled:
        return False
    refresh_count = st_autorefresh(
        interval=interval,
        limit=None,
        key=component_key,
    )
    previous_count = st.session_state.get(state_key, refresh_count)
    is_new_tick = refresh_count != previous_count
    if refresh_count != previous_count:
        fetch_stock_data.clear()
    st.session_state[state_key] = refresh_count
    return is_new_tick


def render_market_table(records: list[dict[str, Any]]) -> None:
    rows = [
        {
            "股票代码": stock["symbol"],
            "当前价格（美元）": stock["price"],
            "日涨跌幅（%）": stock["daily_change"],
            "成交量": stock["volume"],
            "MA5": stock["ma5"],
            "MA20": stock["ma20"],
            "RSI（14）": stock["rsi"],
            "数据源": stock["source"],
            "数据状态": stock["data_status"],
        }
        for stock in records
    ]
    table = pd.DataFrame(rows)
    st.dataframe(
        table.style.format(
            {
                "当前价格（美元）": "{:.2f}",
                "日涨跌幅（%）": "{:+.2f}",
                "成交量": "{:,.0f}",
                "MA5": "{:.2f}",
                "MA20": "{:.2f}",
                "RSI（14）": "{:.2f}",
            },
            na_rep="-",
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_alerts(alerts: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    st.subheader("风险提醒")
    if not alerts:
        st.info("暂无提醒规则，请在左侧粘贴 JSON 后导入。")
        return

    stocks_by_symbol = {stock["symbol"]: stock for stock in records}
    triggered = []
    pending = []
    unavailable = []
    for alert in alerts:
        if not alert["enabled"]:
            continue
        stock = stocks_by_symbol.get(alert["ticker"])
        description = alert_description(alert)
        if not stock:
            unavailable.append(description)
        elif evaluate_alert(alert, stock):
            triggered.append(
                f"{alert['ticker']}：当前价 {stock['price']:.2f} 美元，"
                f"目标价 {alert['target_price']:.2f} 美元，"
                f"提醒类型：{alert['alert_type']}，"
                f"提醒文案：{alert['message'] or '无'}"
            )
        else:
            pending.append(description)

    for message in triggered:
        st.error(f"已触发：{message}")
    for message in pending:
        st.success(f"监控中：{message}")
    for message in unavailable:
        st.warning(f"暂时无法检查：{message}")


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    config = load_config()
    portfolio = load_portfolio()
    alerts = load_alerts()
    paper_positions = load_paper_positions()
    (
        auto_refresh_enabled,
        refresh_interval,
        auto_paper_enabled,
        paper_interval,
    ) = render_sidebar(config, portfolio, alerts)
    configure_auto_refresh(auto_refresh_enabled, refresh_interval)
    auto_paper_tick = configure_auto_refresh(
        auto_paper_enabled,
        paper_interval,
        component_key="stockpulse_paper_autorefresh",
        state_key="paper_autorefresh_count",
    )

    st.title("StockPulse AI")
    st.caption("美股实时投研与风险提醒助手")
    st.info("当前 MVP 优先使用 Finnhub 获取报价，并由 yfinance 提供备用行情与历史数据。数据可能存在延迟，仅供投研参考。")

    with st.spinner("正在获取美股行情..."):
        symbols = list(
            dict.fromkeys(
                config["watchlist"]
                + [position["ticker"] for position in portfolio]
                + [alert["ticker"] for alert in alerts if alert["enabled"]]
                + [position["ticker"] for position in paper_positions]
            )
        )
        records, errors = fetch_watchlist_data(symbols)
    st.session_state["last_market_refresh_at"] = datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )
    st.caption(f"最近一次刷新时间：{st.session_state['last_market_refresh_at']}")
    if auto_paper_tick:
        generated_orders = execute_automatic_paper_trades(portfolio, alerts, records)
        st.session_state["last_paper_auto_check_at"] = (
            datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        )
        st.session_state["paper_message"] = (
            f"自动模拟交易检查完成：记录 {len(generated_orders)} 条信号或订单。"
        )
    last_paper_auto_check_at = st.session_state.get("last_paper_auto_check_at")
    if last_paper_auto_check_at:
        st.caption(f"最近一次自动检查时间：{last_paper_auto_check_at}")
    elif auto_paper_enabled:
        st.caption("最近一次自动检查时间：等待首次轮询")

    st.subheader("自选股行情")
    if records:
        render_market_table(records)
    else:
        st.warning("暂无可展示的行情数据。")
    for error in errors:
        st.warning(f"行情获取失败：{error}")

    st.subheader("AI 投研简报")
    st.write(build_research_brief(records))
    render_portfolio_table(portfolio, records)
    render_profit_loss_plan(portfolio, records)
    render_trade_plan_drafts(portfolio, alerts, records)
    render_paper_trading(portfolio, alerts, records)
    render_alerts(alerts, records)


if __name__ == "__main__":
    main()
