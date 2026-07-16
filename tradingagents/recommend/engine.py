"""Daily recommendation engine — free data only (yfinance + news RSS)."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz
import yaml
import yfinance as yf

from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
from tradingagents.dataflows.korean_fundamentals import fetch_fundamentals
from tradingagents.dataflows.korean_investor_flow import fetch_investor_flow
from tradingagents.dataflows.korean_news import fetch_korean_headline_items
from tradingagents.recommend.chart_svg import (
    build_chart_payload,
    render_candle_svg,
    render_score_price_svg,
)
from tradingagents.recommend.signals import (
    compute_tech,
    score_investor_flow,
    score_tech,
)

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


def _ret_pct_or_none(value: float) -> float | None:
    if value != value:  # NaN
        return None
    return round(value * 100, 2)


@dataclass
class Recommendation:
    code: str
    name: str
    ticker: str
    action: str  # 매수관심 | 관망 | 주의
    score: float
    price: float
    ret_1d_pct: float
    ret_5d_pct: float
    rsi14: float
    market: str = "코스피"  # 코스피 | 코스닥
    sector: str | None = None  # e.g. 반도체와반도체장비
    ret_10d_pct: float | None = None
    ret_20d_pct: float | None = None
    ret_60d_pct: float | None = None
    ret_120d_pct: float | None = None
    per: float | None = None
    pbr: float | None = None
    market_cap: float | None = None
    market_cap_label: str | None = None
    shares_outstanding: float | None = None
    reasons: list[str] = field(default_factory=list)
    drivers: list[dict[str, Any]] = field(default_factory=list)
    headlines: list[dict[str, str]] = field(default_factory=list)
    flow: dict[str, Any] | None = None
    chart_svg: str | None = None
    score_price_svg: str | None = None
    signal_buy_count: int = 0
    signal_caution_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # Keep JSON lean — charts live only in HTML
        data.pop("chart_svg", None)
        data.pop("score_price_svg", None)
        return data


def market_label(ticker: str) -> str:
    """Return Korean board name from Yahoo suffix."""
    t = (ticker or "").upper()
    if t.endswith(".KQ"):
        return "코스닥"
    return "코스피"


def _headline_title(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or "").strip()
    return str(item).strip()


def _headline_date(item: object) -> str | None:
    if isinstance(item, dict):
        date = str(item.get("date") or "").strip()
        return date or None
    return None


def _format_headline_line(item: object) -> str:
    title = _headline_title(item)
    date = _headline_date(item)
    if date and title:
        return f"[{date}] {title}"
    return title


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_watchlist(path: Path | None = None) -> list[dict[str, str]]:
    path = path or (_project_root() / "config" / "kr_universe.yaml")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = []
    for row in data.get("watchlist") or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("code", "")).zfill(6)
        ticker = str(row.get("ticker") or normalize_kr_symbol(code))
        items.append(
            {
                "code": code,
                "name": str(row.get("name") or code),
                "ticker": ticker,
            }
        )
    return items


def _action_from_score(score: float) -> str:
    if score >= 25:
        return "매수관심"
    if score <= -20:
        return "주의"
    return "관망"


def _normalize_hist_index(hist):
    if hist is None or getattr(hist, "empty", True):
        return hist
    df = hist.copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    df.index = idx.normalize()
    return df


def _truncate_hist(hist, as_of: str):
    """Keep bars with date <= as_of (YYYY-MM-DD)."""
    df = _normalize_hist_index(hist)
    if df is None or df.empty:
        return df
    cutoff = pd.Timestamp(as_of).normalize()
    return df[df.index <= cutoff]


def _fetch_history(symbol: str, *, period: str = "1y"):
    """Fetch OHLCV; if KRX suffix has thin history, try the other board."""
    hist = yf.Ticker(symbol).history(period=period)
    hist = _normalize_hist_index(hist)
    hist_len = 0 if hist is None or getattr(hist, "empty", True) else len(hist)
    if hist_len >= 25:
        return hist, symbol
    if symbol.endswith(".KQ"):
        alt = symbol[:-3] + ".KS"
    elif symbol.endswith(".KS"):
        alt = symbol[:-3] + ".KQ"
    else:
        return hist, symbol
    alt_hist = _normalize_hist_index(yf.Ticker(alt).history(period=period))
    alt_len = 0 if alt_hist is None or getattr(alt_hist, "empty", True) else len(alt_hist)
    if alt_len > hist_len:
        logger.info("Using alternate board %s instead of %s", alt, symbol)
        return alt_hist, alt
    return hist, symbol


def analyze_ticker(
    code: str,
    name: str,
    ticker: str,
    *,
    include_news: bool = True,
    news_limit: int = 3,
    as_of: str | None = None,
    hist=None,
    include_chart: bool = True,
    include_fundamentals: bool = True,
    chart_markers: list[dict[str, str]] | None = None,
    signal_buy_count: int = 0,
    signal_caution_count: int = 0,
    score_history: list[tuple[str, float]] | None = None,
) -> Recommendation:
    """Score one ticker. If ``as_of`` is set, only use data on/before that date."""
    symbol = normalize_kr_symbol(ticker or code)
    board = market_label(symbol)
    try:
        if hist is None:
            period = "2y" if as_of else "1y"
            hist, symbol = _fetch_history(symbol, period=period)
        else:
            hist = _normalize_hist_index(hist)
        if as_of:
            hist = _truncate_hist(hist, as_of)
        snap = compute_tech(hist)
        if snap is None:
            return Recommendation(
                code=code,
                name=name,
                ticker=symbol,
                action="관망",
                score=0.0,
                price=0.0,
                ret_1d_pct=0.0,
                ret_5d_pct=0.0,
                rsi14=50.0,
                market=board,
                reasons=[],
                signal_buy_count=signal_buy_count,
                signal_caution_count=signal_caution_count,
                error="시세 데이터 부족 (25거래일 미만)",
            )
        score, reasons, factors = score_tech(snap)

        flow_info: dict[str, Any] | None = None
        try:
            flow = fetch_investor_flow(code, lookback=5, as_of=as_of)
            if flow is not None:
                f_score, f_reasons, f_factors = score_investor_flow(flow)
                score = max(-100.0, min(100.0, score + f_score))
                reasons.extend(f_reasons)
                factors = list(factors) + list(f_factors)
                factors = sorted(factors, key=lambda f: abs(f.impact), reverse=True)
                flow_info = {
                    "as_of": flow.as_of,
                    "foreign_net_1d": flow.foreign_net_1d,
                    "organ_net_1d": flow.organ_net_1d,
                    "individual_net_1d": flow.individual_net_1d,
                    "foreign_net_5d": flow.foreign_net_5d,
                    "organ_net_5d": flow.organ_net_5d,
                    "individual_net_5d": flow.individual_net_5d,
                    "foreign_hold_ratio": flow.foreign_hold_ratio,
                    "days": flow.days,
                }
        except Exception as exc:
            logger.warning("investor flow scoring failed for %s: %s", code, exc)

        drivers = [
            {"impact": round(f.impact, 1), "label": f.label} for f in factors
        ]
        headlines: list[dict[str, str]] = []
        if include_news:
            try:
                headlines = fetch_korean_headline_items(symbol, limit=news_limit)
            except Exception as exc:
                logger.warning("news failed for %s: %s", symbol, exc)

        if headlines:
            reasons.append(f"최근 헤드라인 {len(headlines)}건 참고 (감성 점수화 없음)")

        per = pbr = market_cap = shares = None
        market_cap_label = None
        sector: str | None = None
        if include_fundamentals:
            try:
                fund = fetch_fundamentals(code)
                if fund is not None:
                    per = fund.per
                    pbr = fund.pbr
                    market_cap = fund.market_cap_krw
                    market_cap_label = fund.market_cap_label
                    sector = fund.sector or None
            except Exception as exc:
                logger.warning("fundamentals failed for %s: %s", code, exc)
            try:
                info = yf.Ticker(symbol).info or {}
                so = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
                if so:
                    shares = float(so)
                if market_cap is None and info.get("marketCap"):
                    market_cap = float(info["marketCap"])
            except Exception as exc:
                logger.debug("yfinance shares/cap failed for %s: %s", symbol, exc)
        if not sector:
            sector = "기타"

        chart_svg = None
        score_price_svg = None
        if include_chart:
            try:
                payload = build_chart_payload(hist, bars=63)
                chart_svg = render_candle_svg(payload, markers=chart_markers) or None
            except Exception as exc:
                logger.warning("chart render failed for %s: %s", symbol, exc)
            try:
                if score_history:
                    score_price_svg = (
                        render_score_price_svg(score_history, hist) or None
                    )
            except Exception as exc:
                logger.warning("score chart render failed for %s: %s", symbol, exc)

        if signal_buy_count or signal_caution_count:
            reasons.append(
                f"최근 시그널: 매수관심 {signal_buy_count}회 · 주의 {signal_caution_count}회"
            )

        return Recommendation(
            code=code,
            name=name,
            ticker=symbol,
            action=_action_from_score(score),
            score=round(score, 1),
            price=round(snap.last_close, 2),
            ret_1d_pct=round(snap.ret_1d * 100, 2),
            ret_5d_pct=round(snap.ret_5d * 100, 2),
            rsi14=round(snap.rsi14, 1),
            market=board,
            sector=sector,
            ret_10d_pct=_ret_pct_or_none(snap.ret_10d),
            ret_20d_pct=_ret_pct_or_none(snap.ret_20d),
            ret_60d_pct=_ret_pct_or_none(snap.ret_60d),
            ret_120d_pct=_ret_pct_or_none(snap.ret_120d),
            per=round(per, 2) if per is not None else None,
            pbr=round(pbr, 2) if pbr is not None else None,
            market_cap=market_cap,
            market_cap_label=market_cap_label,
            shares_outstanding=shares,
            reasons=reasons,
            drivers=drivers,
            headlines=headlines[:news_limit],
            flow=flow_info,
            chart_svg=chart_svg,
            score_price_svg=score_price_svg,
            signal_buy_count=signal_buy_count,
            signal_caution_count=signal_caution_count,
        )
    except Exception as exc:
        logger.exception("analyze failed %s", symbol)
        return Recommendation(
            code=code,
            name=name,
            ticker=symbol,
            action="관망",
            score=0.0,
            price=0.0,
            ret_1d_pct=0.0,
            ret_5d_pct=0.0,
            rsi14=50.0,
            market=board,
            reasons=[],
            signal_buy_count=signal_buy_count,
            signal_caution_count=signal_caution_count,
            error=str(exc),
        )


def render_markdown(
    recs: list[Recommendation],
    *,
    as_of: str,
    note: str | None = None,
) -> str:
    ranked = sorted(recs, key=lambda r: r.score, reverse=True)
    buy = [r for r in ranked if r.action == "매수관심"]
    watch = [r for r in ranked if r.action == "관망"]
    caution = [r for r in ranked if r.action == "주의"]

    lines = [
        f"# 일일 추천 리스트 ({as_of} KST)",
        "",
        "> LLM·증권사 API 없이 시세·기술지표·뉴스 헤드라인만으로 생성한 **참고용** 리포트입니다.",
        "> 투자 자문이 아니며, 최종 판단과 주문은 본인이 직접 하세요.",
        "",
    ]
    if note:
        lines.extend([note, ""])

    lines.extend(
        [
            "## 요약",
            "",
            f"- 매수관심: **{len(buy)}** · 관망: **{len(watch)}** · 주의: **{len(caution)}**",
            "",
            "| 순위 | 종목 | 시장 | 업종 | 코드 | 액션 | 점수 | 종가 | 1일% | 5일% | RSI |",
            "|---:|---|---|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for i, r in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {r.name} | {r.market} | {r.sector or '—'} | {r.code} | {r.action} | {r.score} | "
            f"{r.price:,.0f} | {r.ret_1d_pct:+.2f} | {r.ret_5d_pct:+.2f} | {r.rsi14} |"
        )

    def section(title: str, items: list[Recommendation]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not items:
            lines.append("_해당 없음_")
            return
        for r in items:
            lines.append(
                f"### {r.name} ({r.market} · `{r.code}` / {r.ticker}) "
                f"— {r.action} · {r.score}"
            )
            if r.error:
                lines.append(f"- 오류: {r.error}")
            if r.flow:
                f = r.flow
                lines.append(
                    f"- 수급({f.get('as_of')}): "
                    f"외인1일 {f.get('foreign_net_1d'):+,} · "
                    f"기관1일 {f.get('organ_net_1d'):+,} · "
                    f"외인{f.get('days',5)}일 {f.get('foreign_net_5d'):+,} · "
                    f"기관{f.get('days',5)}일 {f.get('organ_net_5d'):+,}"
                )
            for reason in r.reasons:
                lines.append(f"- {reason}")
            if r.headlines:
                lines.append("- 뉴스:")
                for h in r.headlines:
                    lines.append(f"  - {_format_headline_line(h)}")
            lines.append("")

    section("매수관심", buy)
    section("관망", watch)
    section("주의", caution)

    lines.extend(
        [
            "## 점수 기준 (요약)",
            "",
            "- 이동평균(20·60·120) 정배열/역배열, 5·20일 모멘텀, RSI14, 거래량, 외국인·기관 순매수 가중합",
            "- **매수관심** ≥ +25 · **주의** ≤ -20 · 그 외 **관망**",
            "",
        ]
    )
    return "\n".join(lines)


def render_plain_text(
    recs: list[Recommendation],
    *,
    as_of: str,
) -> str:
    """Notepad-friendly plain text (no markdown ornaments)."""
    ranked = sorted(recs, key=lambda r: r.score, reverse=True)
    lines = [
        f"일일 추천 리스트 ({as_of} KST)",
        "=" * 48,
        "참고용 리포트입니다. 투자 자문이 아닙니다.",
        "최종 판단과 주문은 본인이 직접 하세요.",
        "",
        "[요약]",
    ]
    for i, r in enumerate(ranked, 1):
        lines.append(
            f"{i}. {r.name} ({r.market} · {r.sector or '—'} · {r.code}) | {r.action} | 점수 {r.score} | "
            f"종가 {r.price:,.0f} | 1일 {r.ret_1d_pct:+.2f}% | "
            f"5일 {r.ret_5d_pct:+.2f}% | RSI {r.rsi14}"
        )

    for action in ("매수관심", "관망", "주의"):
        items = [r for r in ranked if r.action == action]
        lines.extend(["", f"[{action}]", "-" * 48])
        if not items:
            lines.append("(해당 없음)")
            continue
        for r in items:
            lines.append(
                f"{r.name} ({r.market} · {r.code} / {r.ticker}) — {r.action} · {r.score}"
            )
            if r.error:
                lines.append(f"  - 오류: {r.error}")
            for reason in r.reasons:
                lines.append(f"  - {reason}")
            if r.headlines:
                lines.append("  - 뉴스:")
                for h in r.headlines:
                    lines.append(f"      · {_format_headline_line(h)}")
            lines.append("")

    lines.extend(
        [
            "",
            "[점수 기준]",
            "- 이동평균(20·60·120), 5·20일 모멘텀, RSI14, 거래량, 외국인·기관 순매수로 가중합",
            "- 매수관심 ≥ +25 / 주의 ≤ -20 / 그 외 관망",
            "",
        ]
    )
    return "\n".join(lines)


def run_daily_recommendations(
    *,
    universe_path: Path | None = None,
    output_dir: Path | None = None,
    include_news: bool = True,
    as_of: str | None = None,
    update_latest: bool = True,
    include_chart: bool = True,
    include_fundamentals: bool = True,
    record_backtest: bool = True,
    watchlist: list[dict] | None = None,
    recommendations: list[Recommendation] | None = None,
) -> tuple[list[Recommendation], Path]:
    """Analyze watchlist and write reports. Returns (recs, html path).

    ``as_of`` (YYYY-MM-DD): point-in-time cut — only data on/before that date.
    ``update_latest``: when False (backfill), only write dated folder files.
    ``watchlist`` / ``recommendations``: skip load/analyze when precomputed (gap fill).
    """
    from tradingagents.recommend.backtest import (
        append_day_signals,
        score_history_index,
        signal_counts_for,
        signal_markers_for,
    )

    as_of = as_of or datetime.now(KST).strftime("%Y-%m-%d")

    if recommendations is not None:
        recs = recommendations
    else:
        watchlist = watchlist if watchlist is not None else load_watchlist(universe_path)
        if not watchlist:
            raise RuntimeError("watchlist is empty — edit config/kr_universe.yaml")

        # Chart window start ≈ 90 calendar days; score trend ≈ 6 months
        chart_start = (pd.Timestamp(as_of) - pd.Timedelta(days=100)).strftime("%Y-%m-%d")
        score_start = (pd.Timestamp(as_of) - pd.Timedelta(days=183)).strftime("%Y-%m-%d")
        score_by_code = (
            score_history_index(start=score_start, end=as_of) if include_chart else {}
        )

        recs = []
        for w in watchlist:
            buy_n, caution_n = signal_counts_for(w["code"], as_of=as_of)
            markers = (
                signal_markers_for(w["code"], start=chart_start, end=as_of)
                if include_chart
                else None
            )
            recs.append(
                analyze_ticker(
                    w["code"],
                    w["name"],
                    w["ticker"],
                    include_news=include_news,
                    as_of=as_of,
                    include_chart=include_chart,
                    include_fundamentals=include_fundamentals,
                    chart_markers=markers,
                    signal_buy_count=buy_n,
                    signal_caution_count=caution_n,
                    score_history=score_by_code.get(str(w["code"]).zfill(6)),
                )
            )

    out = output_dir or (_project_root() / "reports" / "daily")
    out.mkdir(parents=True, exist_ok=True)
    from tradingagents.recommend.paths import dated_report_dir

    dated_dir = dated_report_dir(as_of, output_dir=out)
    dated_dir.mkdir(parents=True, exist_ok=True)

    md = render_markdown(recs, as_of=as_of)
    txt = render_plain_text(recs, as_of=as_of)
    from tradingagents.recommend.html_report import render_html

    # latest.html is under reports/daily/; dated HTML is under YYYY/MM/DD/
    html_dated = render_html(
        recs,
        as_of=as_of,
        backtest_href="../../../../backtest/score_stats.html",
    )
    html_latest = (
        render_html(recs, as_of=as_of, backtest_href="../backtest/score_stats.html")
        if update_latest
        else html_dated
    )

    (dated_dir / "report.md").write_text(md, encoding="utf-8")
    (dated_dir / "report.txt").write_text(txt, encoding="utf-8-sig")
    dated_html = dated_dir / "report.html"
    dated_html.write_text(html_dated, encoding="utf-8")

    import json

    payload = {
        "as_of": as_of,
        "recommendations": [r.to_dict() for r in sorted(recs, key=lambda x: -x.score)],
    }
    if recommendations is not None and watchlist is not None:
        payload["mode"] = "pit_gap_fill"
        payload["watchlist_count"] = len(watchlist)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    (dated_dir / "report.json").write_text(json_text, encoding="utf-8")

    latest_html = out / "latest.html"
    if update_latest:
        (out / "latest.md").write_text(md, encoding="utf-8")
        (out / "latest.txt").write_text(txt, encoding="utf-8-sig")
        latest_html.write_text(html_latest, encoding="utf-8")
        (out / "latest.json").write_text(json_text, encoding="utf-8")

    if record_backtest:
        try:
            append_day_signals(as_of, recs)
        except Exception as exc:
            logger.warning("backtest append failed: %s", exc)

    return recs, latest_html if update_latest else dated_html
