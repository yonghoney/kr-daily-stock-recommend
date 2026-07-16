"""Daily recommendation engine — free data only (yfinance + news RSS)."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytz
import yaml
import yfinance as yf

from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
from tradingagents.dataflows.korean_news import get_news_korean
from tradingagents.recommend.signals import compute_tech, score_tech

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


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
    reasons: list[str] = field(default_factory=list)
    headlines: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _fetch_history(symbol: str):
    """Fetch OHLCV; if KRX suffix has thin history, try the other board."""
    hist = yf.Ticker(symbol).history(period="6mo")
    if hist is not None and len(hist) >= 25:
        return hist, symbol
    if symbol.endswith(".KQ"):
        alt = symbol[:-3] + ".KS"
    elif symbol.endswith(".KS"):
        alt = symbol[:-3] + ".KQ"
    else:
        return hist, symbol
    alt_hist = yf.Ticker(alt).history(period="6mo")
    if alt_hist is not None and len(alt_hist) > len(hist or []):
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
) -> Recommendation:
    symbol = normalize_kr_symbol(ticker or code)
    try:
        hist, symbol = _fetch_history(symbol)
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
                reasons=[],
                error="시세 데이터 부족 (25거래일 미만)",
            )
        score, reasons = score_tech(snap)
        headlines: list[str] = []
        if include_news:
            try:
                raw = get_news_korean(symbol, limit=news_limit)
                for line in raw.splitlines():
                    if line[:1].isdigit() and ". " in line:
                        headlines.append(line.split(". ", 1)[1].strip())
            except Exception as exc:
                logger.warning("news failed for %s: %s", symbol, exc)

        if headlines:
            reasons.append(f"최근 헤드라인 {len(headlines)}건 참고 (감성 점수화 없음)")

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
            reasons=reasons,
            headlines=headlines[:news_limit],
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
            reasons=[],
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
            "| 순위 | 종목 | 코드 | 액션 | 점수 | 종가 | 1일% | 5일% | RSI |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for i, r in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {r.name} | {r.code} | {r.action} | {r.score} | "
            f"{r.price:,.0f} | {r.ret_1d_pct:+.2f} | {r.ret_5d_pct:+.2f} | {r.rsi14} |"
        )

    def section(title: str, items: list[Recommendation]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not items:
            lines.append("_해당 없음_")
            return
        for r in items:
            lines.append(f"### {r.name} (`{r.code}` / {r.ticker}) — {r.action} · {r.score}")
            if r.error:
                lines.append(f"- 오류: {r.error}")
            for reason in r.reasons:
                lines.append(f"- {reason}")
            if r.headlines:
                lines.append("- 뉴스:")
                for h in r.headlines:
                    lines.append(f"  - {h}")
            lines.append("")

    section("매수관심", buy)
    section("관망", watch)
    section("주의", caution)

    lines.extend(
        [
            "## 점수 기준 (요약)",
            "",
            "- 이동평균 정배열/역배열, 5·20일 모멘텀, RSI14, 거래량 급증 여부를 가중합",
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
            f"{i}. {r.name} ({r.code}) | {r.action} | 점수 {r.score} | "
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
            lines.append(f"{r.name} ({r.code} / {r.ticker}) — {r.action} · {r.score}")
            if r.error:
                lines.append(f"  - 오류: {r.error}")
            for reason in r.reasons:
                lines.append(f"  - {reason}")
            if r.headlines:
                lines.append("  - 뉴스:")
                for h in r.headlines:
                    lines.append(f"      · {h}")
            lines.append("")

    lines.extend(
        [
            "",
            "[점수 기준]",
            "- 이동평균, 5·20일 모멘텀, RSI14, 거래량으로 가중합",
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
) -> tuple[list[Recommendation], Path]:
    """Analyze watchlist and write reports. Returns (recs, latest.txt path)."""
    as_of = datetime.now(KST).strftime("%Y-%m-%d")
    watchlist = load_watchlist(universe_path)
    if not watchlist:
        raise RuntimeError("watchlist is empty — edit config/kr_universe.yaml")

    recs = [
        analyze_ticker(
            w["code"],
            w["name"],
            w["ticker"],
            include_news=include_news,
        )
        for w in watchlist
    ]

    out = output_dir or (_project_root() / "reports" / "daily")
    out.mkdir(parents=True, exist_ok=True)
    md = render_markdown(recs, as_of=as_of)
    txt = render_plain_text(recs, as_of=as_of)

    (out / f"{as_of}.md").write_text(md, encoding="utf-8")
    (out / "latest.md").write_text(md, encoding="utf-8")
    # UTF-8 BOM so Windows Notepad shows Korean correctly
    (out / f"{as_of}.txt").write_text(txt, encoding="utf-8-sig")
    latest_txt = out / "latest.txt"
    latest_txt.write_text(txt, encoding="utf-8-sig")

    import json

    payload = {
        "as_of": as_of,
        "recommendations": [r.to_dict() for r in sorted(recs, key=lambda x: -x.score)],
    }
    (out / f"{as_of}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return recs, latest_txt
