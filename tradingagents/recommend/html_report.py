"""HTML vertical-scroll daily report renderer."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.recommend.engine import Recommendation


# Beginner glossary for click-to-open notes
TERM_TIPS: dict[str, str] = {
    "종가": "그날(또는 마지막 거래)에서 마지막으로 체결된 가격입니다. 장중에는 아직 확정되지 않은 당일 시세일 수 있습니다.",
    "1일": "1거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다.",
    "5일": "5거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다.",
    "10일": "10거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다. 표시용이며 점수에는 직접 넣지 않습니다.",
    "20일": "20거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다.",
    "60일": "60거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다. 표시용이며 점수에는 직접 넣지 않습니다.",
    "120일": "120거래일 전 종가 대비 지금 종가가 몇 % 올랐거나 내렸는지입니다. 표시용이며 점수에는 직접 넣지 않습니다.",
    "RSI14": "최근 14일 상승·하락 강도를 0~100으로 요약한 지표입니다. 높으면 과열(과매수), 낮으면 과매도 성향으로 봅니다.",
    "PER": "주가 ÷ 주당순이익. 회사가 번 이익에 비해 주가가 비싼지 싼지 참고하는 값입니다. 점수에는 넣지 않습니다.",
    "PBR": "주가 ÷ 주당순자산. 회사 자산 대비 주가 수준을 참고하는 값입니다. 점수에는 넣지 않습니다.",
    "시가총액": "주가 × 발행주식수. 시장이 매긴 회사 규모입니다. 점수에는 넣지 않습니다.",
    "발행주식수": "시장에 나와 있는 주식의 총수입니다. 점수에는 넣지 않습니다.",
    "외인 1일": "외국인 투자자가 전일(최근 1거래일) 순매수한 주식 수입니다. +면 순매수, −면 순매도.",
    "기관 1일": "기관(펀드·연기금 등)이 전일(최근 1거래일) 순매수한 주식 수입니다. +면 순매수, −면 순매도.",
    "외인 지분": "외국인이 보유한 비율(%)입니다. 수급 참고용입니다.",
    "매수관심": "규칙 점수가 +25 이상일 때 붙는 라벨입니다. ‘반드시 사라’는 뜻이 아닙니다.",
    "관망": "규칙 점수가 중간일 때 붙는 라벨입니다. 뚜렷한 매수·주의 신호가 없다는 뜻입니다.",
    "주의": "규칙 점수가 −20 이하일 때 붙는 라벨입니다. 약세·과열 등 리스크 신호가 있다는 뜻입니다.",
    "점수": "이동평균·모멘텀·RSI·거래량·외인/기관 수급 규칙을 더한 값(−100~+100)입니다. AI 판단이 아닙니다.",
    "이동평균": "최근 N일 종가의 평균 가격(이평선)입니다. 주가가 이보다 위/아래인지를 추세 판별에 씁니다.",
    "모멘텀": "최근 기간 주가가 오른/내린 ‘힘’입니다. 이 리포트에서는 주로 5일·20일 수익률로 봅니다.",
    "거래량": "그날 거래된 주식 수입니다. 평소보다 크게 늘면 관심이 커진 신호로 봅니다.",
    "순매수": "산 수량 − 판 수량입니다. +면 순매수, −면 순매도입니다.",
    "양봉": "종가가 시가보다 같거나 높은 날의 봉(국내 차트에서는 보통 빨강)입니다.",
    "음봉": "종가가 시가보다 낮은 날의 봉(국내 차트에서는 보통 파랑)입니다.",
    "시장": "코스피(유가증권) 또는 코스닥 시장 구분입니다.",
    "업종": "네이버 기준 산업 분류 이름입니다. 같은 업종끼리 묶어 볼 때 씁니다.",
    "시그널": "최근 90일 동안 규칙 점수가 매수관심(≥+25) 또는 주의(≤−20)로 나온 횟수입니다.",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _term(label: str, tip: str | None = None) -> str:
    """Clickable glossary term that opens a small note."""
    text = tip if tip is not None else TERM_TIPS.get(label, "")
    if not text:
        return _esc(label)
    return (
        f'<button type="button" class="term" aria-expanded="false" '
        f'data-tip="{_esc(text)}">{_esc(label)}</button>'
    )


def _term_flow_days(days: object, who: str) -> str:
    """Label like '외인 5일' with a tip that includes the day count."""
    d = _esc(days)
    label = f"{who} {days}일"
    tip = (
        f"{'외국인' if who == '외인' else '기관'}이 최근 약 {d}거래일 동안 "
        f"순매수한 누적 수량입니다. +면 순매수, −면 순매도."
    )
    return _term(label, tip)


def _action_class(action: str) -> str:
    if action == "매수관심":
        return "buy"
    if action == "주의":
        return "caution"
    return "watch"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _fmt_shares(value: float | None) -> str:
    if value is None:
        return "—"
    n = float(value)
    if n >= 1e8:
        return f"{n / 1e8:.2f}억주"
    if n >= 1e4:
        return f"{n / 1e4:,.0f}만주"
    return f"{n:,.0f}주"


def _fmt_impact(impact: float) -> str:
    sign = "+" if impact > 0 else ""
    return f"{sign}{impact:.0f}"


def _extra_metrics_html(r: Recommendation) -> str:
    cap = r.market_cap_label or (
        f"{r.market_cap/1e12:.2f}조" if r.market_cap and r.market_cap >= 1e12
        else f"{r.market_cap/1e8:.0f}억" if r.market_cap
        else "—"
    )
    return f"""
              <div class="metrics signals">
                <div><span>{_term("시그널")} 매수관심</span><strong>{_esc(r.signal_buy_count)}</strong></div>
                <div><span>{_term("시그널")} 주의</span><strong>{_esc(r.signal_caution_count)}</strong></div>
              </div>
              <div class="metrics">
                <div><span>{_term("종가")}</span><strong>{r.price:,.0f}</strong></div>
                <div><span>{_term("1일")}</span><strong>{r.ret_1d_pct:+.2f}%</strong></div>
                <div><span>{_term("5일")}</span><strong>{r.ret_5d_pct:+.2f}%</strong></div>
                <div><span>{_term("RSI14")}</span><strong>{_esc(r.rsi14)}</strong></div>
              </div>
              <div class="metrics extras">
                <div><span>{_term("10일")}</span><strong>{_esc(_fmt_pct(r.ret_10d_pct))}</strong></div>
                <div><span>{_term("20일")}</span><strong>{_esc(_fmt_pct(r.ret_20d_pct))}</strong></div>
                <div><span>{_term("60일")}</span><strong>{_esc(_fmt_pct(r.ret_60d_pct))}</strong></div>
                <div><span>{_term("120일")}</span><strong>{_esc(_fmt_pct(r.ret_120d_pct))}</strong></div>
              </div>
              <div class="metrics extras">
                <div><span>{_term("PER")}</span><strong>{_esc(_fmt_ratio(r.per))}</strong></div>
                <div><span>{_term("PBR")}</span><strong>{_esc(_fmt_ratio(r.pbr))}</strong></div>
                <div><span>{_term("시가총액")}</span><strong>{_esc(cap)}</strong></div>
                <div><span>{_term("발행주식수")}</span><strong>{_esc(_fmt_shares(r.shares_outstanding))}</strong></div>
              </div>
            """


def _news_block(headlines: list) -> str:
    """Always-visible compact news summary for a stock section."""
    items: list[tuple[str | None, str]] = []
    for h in headlines or []:
        if isinstance(h, dict):
            title = str(h.get("title") or "").strip()
            date = str(h.get("date") or "").strip() or None
        else:
            title = str(h).strip()
            date = None
        if title:
            items.append((date, title))

    # Newest first; undated last
    items.sort(key=lambda row: row[0] or "0000-00-00", reverse=True)

    if not items:
        return """
              <div class="block news">
                <h3>뉴스 요약</h3>
                <p class="news-brief muted">최근 관련 헤드라인을 찾지 못했습니다.</p>
              </div>
            """

    brief_parts = [t for _, t in items[:2]]
    brief_html = "<br>".join(_esc(t) for t in brief_parts)

    rows = []
    for date, title in items[:3]:
        date_txt = _esc(date) if date else "—"
        rows.append(
            f'<li><span class="news-date">{date_txt}</span>'
            f'<span class="news-title">{_esc(title)}</span></li>'
        )
    return f"""
              <div class="block news">
                <h3>뉴스 요약</h3>
                <p class="news-brief">{brief_html}</p>
                <ul>{"".join(rows)}</ul>
              </div>
            """


def render_html(
    recs: list[Recommendation],
    *,
    as_of: str,
    backtest_href: str = "../backtest/score_stats.html",
    market_pulse_months: int = 3,
) -> str:
    ranked = sorted(recs, key=lambda r: r.score, reverse=True)
    buy_n = sum(1 for r in ranked if r.action == "매수관심")
    watch_n = sum(1 for r in ranked if r.action == "관망")
    caution_n = sum(1 for r in ranked if r.action == "주의")

    pulse_html = ""
    try:
        import pandas as pd

        from tradingagents.recommend.market_pulse import (
            load_or_build_market_pulse,
            render_market_pulse_html,
        )

        pulse_start = (
            pd.Timestamp(as_of) - pd.DateOffset(months=market_pulse_months)
        ).strftime("%Y-%m-%d")
        pulse = load_or_build_market_pulse(
            start=pulse_start, end=as_of, rebuild=False
        )
        pulse_html = render_market_pulse_html(pulse)
    except Exception:
        pulse_html = ""

    sectors = sorted(
        {(r.sector or "기타") for r in ranked},
        key=lambda s: (s == "기타", s),
    )
    sector_options = "".join(
        f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in sectors
    )

    summary_rows: list[str] = []
    detail_sections: list[str] = []

    for i, r in enumerate(ranked, 1):
        sector = r.sector or "기타"
        code_esc = _esc(r.code)
        market_esc = _esc(r.market)
        sector_esc = _esc(sector)
        drivers = (r.drivers or [])[:3]
        if not drivers and r.error:
            drivers_html = f'<span class="driver muted">오류: {_esc(r.error)}</span>'
        elif not drivers:
            drivers_html = '<span class="driver muted">특이 요인 없음</span>'
        else:
            chips = []
            for d in drivers:
                impact = float(d.get("impact", 0))
                cls = "pos" if impact > 0 else "neg"
                chips.append(
                    '<span class="driver '
                    + cls
                    + '"><b>'
                    + _esc(_fmt_impact(impact))
                    + "</b> "
                    + _esc(d.get("label", ""))
                    + "</span>"
                )
            drivers_html = "".join(chips)

        summary_rows.append(
            f"""
            <article class="sum-row" role="button" tabindex="0"
              data-code="{code_esc}" data-market="{market_esc}" data-sector="{sector_esc}">
              <div class="rank">{i}</div>
              <div class="sum-main">
                <div class="sum-title">
                  <strong>{_esc(r.name)}</strong>
                  <span class="market">{_term("시장")}: {market_esc}</span>
                  <span class="sector">{_term("업종")}: {sector_esc}</span>
                  <span class="code">{code_esc}</span>
                  <span class="badge {_action_class(r.action)}">{_term(r.action)}</span>
                </div>
                <div class="drivers">{drivers_html}</div>
              </div>
              <div class="sum-side">
                <div class="score {_action_class(r.action)}">{_esc(r.score)}</div>
                <span class="btn open-hint">보기</span>
              </div>
            </article>
            """
        )

        reasons_html = (
            "".join(f"<li>{_esc(reason)}</li>" for reason in r.reasons)
            if r.reasons
            else "<li class='muted'>사유 없음</li>"
        )
        headlines_html = _news_block(r.headlines)
        error_html = (
            f'<p class="error">오류: {_esc(r.error)}</p>' if r.error else ""
        )
        flow = r.flow or {}
        flow_html = ""
        if flow:
            def _sh(key: str) -> str:
                val = int(flow.get(key) or 0)
                sign = "+" if val > 0 else ""
                return f"{sign}{val:,}"

            hold = flow.get("foreign_hold_ratio")
            hold_txt = f"{hold:.2f}%" if isinstance(hold, (int, float)) else "-"
            days_raw = flow.get("days", 5)
            flow_html = f"""
              <div class="block">
                <h3>외국인·기관 {_term("순매수")} ({_esc(flow.get('as_of', '-'))})</h3>
                <div class="metrics flow">
                  <div><span>{_term("외인 1일")}</span><strong>{_esc(_sh('foreign_net_1d'))}</strong></div>
                  <div><span>{_term("기관 1일")}</span><strong>{_esc(_sh('organ_net_1d'))}</strong></div>
                  <div><span>{_term_flow_days(days_raw, "외인")}</span><strong>{_esc(_sh('foreign_net_5d'))}</strong></div>
                  <div><span>{_term_flow_days(days_raw, "기관")}</span><strong>{_esc(_sh('organ_net_5d'))}</strong></div>
                  <div><span>{_term("외인 지분")}</span><strong>{_esc(hold_txt)}</strong></div>
                </div>
              </div>
            """

        factor_rows = ""
        for d in r.drivers or []:
            impact = float(d.get("impact", 0))
            cls = "pos" if impact > 0 else "neg"
            factor_rows += (
                f'<tr><td class="num {cls}">{_esc(_fmt_impact(impact))}</td>'
                f"<td>{_esc(d.get('label', ''))}</td></tr>"
            )
        if not factor_rows:
            factor_rows = '<tr><td colspan="2" class="muted">요인 없음</td></tr>'

        detail_sections.append(
            f"""
            <section class="stock" data-code="{code_esc}" data-market="{market_esc}"
              data-sector="{sector_esc}" hidden>
              <header class="stock-head">
                <div>
                  <p class="eyebrow">종목 리포트 · {_esc(i)}위 · {market_esc}</p>
                  <h2>{_esc(r.name)} <span class="code">{code_esc}</span></h2>
                  <p class="meta">
                    <span class="market">{market_esc}</span>
                    · <span class="sector">{sector_esc}</span>
                    · {_esc(r.ticker)} ·
                    <span class="badge {_action_class(r.action)}">{_term(r.action)}</span>
                    · {_term("점수")} <strong>{_esc(r.score)}</strong>
                  </p>
                </div>
                <button type="button" class="btn ghost close-detail">목록으로</button>
              </header>
              {error_html}
              {_extra_metrics_html(r)}
              {f'<div class="block chart">{r.chart_svg}</div>' if r.chart_svg else ''}
              {f'<div class="block chart score-price">{r.score_price_svg}</div>' if getattr(r, "score_price_svg", None) else ''}
              {headlines_html}
              {flow_html}
              <div class="block">
                <h3>점수 기여 요인</h3>
                <table class="factors">
                  <thead><tr><th>영향</th><th>요인</th></tr></thead>
                  <tbody>{factor_rows}</tbody>
                </table>
              </div>
              <div class="block">
                <h3>판단 이유</h3>
                <ul>{reasons_html}</ul>
              </div>
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>일일 추천 리포트 ({_esc(as_of)})</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&family=Fraunces:opsz,wght@9..144,500;9..144,700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --ink: #12212b;
      --muted: #5a6d78;
      --line: rgba(18, 33, 43, 0.12);
      --paper: #edf3f6;
      --panel: rgba(255, 255, 255, 0.72);
      --buy: #0b7a63;
      --watch: #4a5d6a;
      --caution: #c2410c;
      --accent: #0e7490;
      --sector: #6d28d9;
      --max: 920px;
      --max-open: 1180px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "IBM Plex Sans KR", sans-serif;
      line-height: 1.55;
      background:
        radial-gradient(900px 420px at 0% -10%, rgba(14, 116, 144, 0.16), transparent 55%),
        radial-gradient(700px 380px at 100% 8%, rgba(11, 122, 99, 0.12), transparent 50%),
        linear-gradient(180deg, #e7eef3 0%, var(--paper) 45%, #e4ece8 100%);
      min-height: 100vh;
    }}
    .wrap {{
      width: min(100% - 1.5rem, var(--max));
      margin: 0 auto;
      padding: 2.5rem 0 5rem;
      transition: width 0.25s ease;
    }}
    body.detail-open .wrap {{
      width: min(100% - 1.5rem, var(--max-open));
    }}
    .hero {{
      margin-bottom: 1.5rem;
      animation: rise 0.7s ease both;
    }}
    .hero h1 {{
      font-family: "Fraunces", Georgia, serif;
      font-weight: 700;
      font-size: clamp(1.8rem, 4vw, 2.6rem);
      letter-spacing: -0.02em;
      margin: 0.2rem 0 0.6rem;
    }}
    .hero p {{
      margin: 0 0 0.4rem;
      color: var(--muted);
      max-width: 42rem;
      line-height: 1.55;
    }}
    .hero p:last-of-type {{
      margin-bottom: 0;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      margin-top: 1rem;
    }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 0.35rem 0.85rem;
      font-size: 0.92rem;
      backdrop-filter: blur(8px);
    }}
    .stat b.buy {{ color: var(--buy); }}
    .stat b.watch {{ color: var(--watch); }}
    .stat b.caution {{ color: var(--caution); }}
    .workspace {{
      display: block;
      animation: rise 0.8s ease 0.08s both;
    }}
    .market-pulse {{
      margin: 0 0 1.1rem;
      animation: rise 0.7s ease both;
    }}
    body.detail-open .market-pulse {{
      display: none;
    }}
    .pulse-head {{
      margin: 0 0 0.75rem;
    }}
    .pulse-head h2 {{
      margin: 0 0 0.25rem;
      font-size: 1.15rem;
    }}
    .pulse-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
      max-width: 46rem;
    }}
    .pulse-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.85rem;
    }}
    .pulse-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 0.75rem 0.85rem 0.9rem;
      backdrop-filter: blur(10px);
    }}
    .pulse-card h3 {{
      margin: 0 0 0.55rem;
      font-size: 1rem;
    }}
    .pulse-charts {{
      display: grid;
      gap: 0.55rem;
    }}
    .block.chart.pulse {{
      margin-top: 0;
    }}
    @media (max-width: 900px) {{
      .pulse-grid {{ grid-template-columns: 1fr; }}
    }}
    body.detail-open .workspace {{
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 1rem;
      align-items: start;
    }}
    #panel-detail {{
      display: none;
      min-width: 0;
    }}
    body.detail-open #panel-detail {{
      display: block;
    }}
    .board {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 0.4rem;
      backdrop-filter: blur(10px);
      box-shadow: 0 16px 40px rgba(18, 33, 43, 0.06);
    }}
    .board-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 1rem;
      padding: 0.9rem 1rem 0.35rem;
    }}
    .board-head h2 {{
      margin: 0;
      font-family: "Fraunces", Georgia, serif;
      font-size: 1.35rem;
    }}
    .board-head span {{ color: var(--muted); font-size: 0.9rem; }}
    .filters {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      padding: 0.35rem 1rem 0.75rem;
    }}
    .filters label {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.84rem;
      color: var(--muted);
    }}
    .filters select {{
      appearance: none;
      background: rgba(255,255,255,0.75);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 0.35rem 1.75rem 0.35rem 0.85rem;
      font: inherit;
      font-size: 0.84rem;
      color: var(--ink);
      cursor: pointer;
      background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%),
        linear-gradient(135deg, var(--muted) 50%, transparent 50%);
      background-position: calc(100% - 14px) 55%, calc(100% - 9px) 55%;
      background-size: 5px 5px, 5px 5px;
      background-repeat: no-repeat;
    }}
    .filters select:focus {{
      outline: 2px solid rgba(14, 116, 144, 0.35);
      outline-offset: 1px;
    }}
    .sum-list {{
      max-height: none;
    }}
    body.detail-open .sum-list {{
      max-height: min(70vh, 720px);
      overflow-y: auto;
    }}
    .filter-empty {{
      margin: 0;
      padding: 1.1rem 1rem 1.25rem;
      color: var(--muted);
      font-size: 0.92rem;
      border-top: 1px solid var(--line);
    }}
    .filter-empty[hidden] {{ display: none; }}
    .sum-row {{
      display: grid;
      grid-template-columns: 2.2rem 1fr auto;
      gap: 0.75rem;
      align-items: start;
      padding: 0.95rem 1rem;
      border-top: 1px solid var(--line);
      cursor: pointer;
      transition: background 0.15s ease;
    }}
    .sum-row:hover {{
      background: rgba(255,255,255,0.45);
    }}
    .sum-row.active {{
      background: rgba(14, 116, 144, 0.1);
      box-shadow: inset 3px 0 0 var(--accent);
    }}
    .sum-row.filtered-out,
    .stock.filtered-out {{
      display: none;
    }}
    .rank {{
      font-family: "Fraunces", Georgia, serif;
      font-size: 1.15rem;
      color: var(--muted);
      padding-top: 0.15rem;
    }}
    .sum-title {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.45rem;
      margin-bottom: 0.45rem;
    }}
    .sum-title strong {{ font-size: 1.05rem; }}
    .code {{
      color: var(--muted);
      font-size: 0.86rem;
      font-variant-numeric: tabular-nums;
    }}
    .market {{
      display: inline-flex;
      align-items: center;
      border-radius: 6px;
      padding: 0.1rem 0.45rem;
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--accent);
      background: rgba(14, 116, 144, 0.1);
      border: 1px solid rgba(14, 116, 144, 0.22);
    }}
    .sector {{
      display: inline-flex;
      align-items: center;
      border-radius: 6px;
      padding: 0.1rem 0.45rem;
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--sector);
      background: rgba(109, 40, 217, 0.1);
      border: 1px solid rgba(109, 40, 217, 0.22);
      max-width: 12rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      border-radius: 6px;
      padding: 0.12rem 0.45rem;
      font-size: 0.78rem;
      font-weight: 600;
      border: 1px solid transparent;
    }}
    .badge.buy {{ color: var(--buy); background: rgba(11,122,99,0.1); border-color: rgba(11,122,99,0.2); }}
    .badge.watch {{ color: var(--watch); background: rgba(74,93,106,0.1); border-color: rgba(74,93,106,0.2); }}
    .badge.caution {{ color: var(--caution); background: rgba(194,65,12,0.1); border-color: rgba(194,65,12,0.22); }}
    .drivers {{
      display: flex;
      flex-direction: column;
      gap: 0.28rem;
    }}
    .driver {{
      font-size: 0.86rem;
      color: var(--ink);
    }}
    .driver b {{ font-variant-numeric: tabular-nums; margin-right: 0.15rem; }}
    .driver.pos b {{ color: var(--buy); }}
    .driver.neg b {{ color: var(--caution); }}
    .driver.muted, .muted {{ color: var(--muted); }}
    .sum-side {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 0.45rem;
      min-width: 6.5rem;
    }}
    .score {{
      font-family: "Fraunces", Georgia, serif;
      font-size: 1.55rem;
      font-weight: 700;
      line-height: 1;
    }}
    .score.buy {{ color: var(--buy); }}
    .score.watch {{ color: var(--watch); }}
    .score.caution {{ color: var(--caution); }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      color: #fff;
      background: var(--ink);
      border: 1px solid var(--ink);
      border-radius: 999px;
      padding: 0.42rem 0.85rem;
      font-size: 0.82rem;
      font-weight: 600;
      white-space: nowrap;
      transition: transform 0.15s ease, background 0.15s ease;
      cursor: pointer;
      font-family: inherit;
    }}
    .btn:hover {{ transform: translateY(-1px); background: #1c3340; }}
    .btn.ghost {{
      background: transparent;
      color: var(--ink);
      border-color: var(--line);
    }}
    .btn.ghost:hover {{ background: rgba(255,255,255,0.7); }}
    .open-hint {{
      pointer-events: none;
    }}
    .stock {{
      margin: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 1.2rem 1.15rem 1.35rem;
      backdrop-filter: blur(10px);
      animation: rise 0.45s ease both;
    }}
    .stock[hidden] {{ display: none; }}
    .stock-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 1rem;
    }}
    .eyebrow {{
      margin: 0;
      color: var(--muted);
      font-size: 0.8rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .stock-head h2 {{
      margin: 0.2rem 0 0.35rem;
      font-family: "Fraunces", Georgia, serif;
      font-size: clamp(1.35rem, 3vw, 1.7rem);
    }}
    .meta {{ margin: 0; color: var(--muted); }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.55rem;
      margin-bottom: 0.55rem;
    }}
    .metrics.signals {{
      grid-template-columns: repeat(2, 1fr);
    }}
    .metrics.extras {{
      margin-bottom: 0.55rem;
    }}
    .metrics div {{
      background: rgba(255,255,255,0.55);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.65rem 0.7rem;
    }}
    .metrics span {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      margin-bottom: 0.15rem;
    }}
    .metrics strong {{
      font-size: 1.02rem;
      font-variant-numeric: tabular-nums;
    }}
    .term {{
      appearance: none;
      background: none;
      border: none;
      padding: 0;
      margin: 0;
      font: inherit;
      color: inherit;
      cursor: help;
      border-bottom: 1px dashed rgba(14, 116, 144, 0.55);
      text-align: inherit;
      line-height: inherit;
    }}
    .term:hover,
    .term[aria-expanded="true"] {{
      color: var(--accent);
      border-bottom-color: var(--accent);
    }}
    .badge .term {{
      border-bottom-color: currentColor;
      opacity: 0.95;
    }}
    .term-note {{
      position: fixed;
      z-index: 200;
      max-width: min(280px, calc(100vw - 1.5rem));
      padding: 0.8rem 0.95rem;
      border-radius: 12px;
      background: #fffef8;
      border: 1px solid rgba(18, 33, 43, 0.14);
      box-shadow: 0 14px 36px rgba(18, 33, 43, 0.16);
      font-size: 0.86rem;
      line-height: 1.45;
      color: var(--ink);
      pointer-events: auto;
    }}
    .term-note[hidden] {{ display: none; }}
    .term-hint {{
      margin: 0.65rem 0 0;
      font-size: 0.84rem;
      color: var(--muted);
      line-height: 1.55;
    }}
    .block h3 {{
      margin: 0 0 0.5rem;
      font-size: 0.95rem;
    }}
    .block {{ margin-top: 1rem; }}
    .block ul {{
      margin: 0;
      padding-left: 1.15rem;
    }}
    .block li {{ margin: 0.25rem 0; }}
    .factors {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    .factors th, .factors td {{
      text-align: left;
      padding: 0.45rem 0.35rem;
      border-bottom: 1px solid var(--line);
    }}
    .factors th {{ color: var(--muted); font-weight: 500; }}
    .factors .num {{ width: 3.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
    .factors .pos {{ color: var(--buy); }}
    .factors .neg {{ color: var(--caution); }}
    .error {{
      color: var(--caution);
      background: rgba(194,65,12,0.08);
      border: 1px solid rgba(194,65,12,0.2);
      border-radius: 10px;
      padding: 0.6rem 0.75rem;
    }}
    .note {{
      margin-top: 2rem;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.55;
      max-width: 42rem;
    }}
    @keyframes rise {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .block.news .news-brief {{
      margin: 0 0 0.45rem;
      font-size: 0.92rem;
      color: var(--ink);
    }}
    .block.news ul {{
      margin: 0;
      padding-left: 0;
      list-style: none;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .block.news li {{
      display: grid;
      grid-template-columns: 6.2rem 1fr;
      gap: 0.55rem;
      align-items: start;
      margin: 0.28rem 0;
    }}
    .block.news .news-date {{
      font-variant-numeric: tabular-nums;
      color: var(--accent);
      font-weight: 600;
      white-space: nowrap;
    }}
    .block.news .news-title {{
      color: var(--ink-soft, var(--ink));
    }}
    .block.chart {{
      margin-top: 0.85rem;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: rgba(255,255,255,0.55);
    }}
    .block.chart svg {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .block.chart.score-price {{
      margin-top: 0.55rem;
    }}
    .metrics.flow {{
      grid-template-columns: repeat(3, 1fr);
    }}
    @media (max-width: 900px) {{
      body.detail-open .workspace {{
        grid-template-columns: 1fr;
      }}
      body.detail-open #panel-list {{
        display: none;
      }}
      body.detail-open #panel-detail {{
        display: block;
      }}
    }}
    @media (max-width: 720px) {{
      .sum-row {{
        grid-template-columns: 1.6rem 1fr;
      }}
      .sum-side {{
        grid-column: 2;
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
        min-width: 0;
      }}
      .metrics {{ grid-template-columns: repeat(2, 1fr); }}
      .metrics.flow {{ grid-template-columns: repeat(2, 1fr); }}
      .stock-head {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <p class="eyebrow">KR Daily Stock Recommend</p>
      <h1>일일 추천 리포트</h1>
      <p>{_esc(as_of)} 종가 기준 · 확정된 세션 종가 데이터만 사용합니다.<br>
      평일 15:30(KST) 이후 실행 시 당일까지, 장중·주말은 직전 거래일까지 반영됩니다.<br>
      LLM·증권사 API 없이 시세·기술지표·뉴스 헤드라인으로 만든 참고용 리포트입니다.<br>
      투자 자문이 아니며, 최종 판단은 본인에게 있습니다.</p>
      <p class="term-hint">요약 행을 <strong>클릭</strong>하면 오른쪽에 종목 리포트가 열립니다.<br>
        점선 밑줄 용어를 클릭하면 초보자용 설명이 뜹니다.<br>
        점수대별 향후 수익률: <a href="{_esc(backtest_href)}">score_stats.html</a></p>
      <div class="stats">
        <div class="stat">전체 <b>{len(ranked)}</b></div>
        <div class="stat">{_term("매수관심")} <b class="buy">{buy_n}</b></div>
        <div class="stat">{_term("관망")} <b class="watch">{watch_n}</b></div>
        <div class="stat">{_term("주의")} <b class="caution">{caution_n}</b></div>
      </div>
    </header>

    {pulse_html}

    <div class="workspace">
      <div id="panel-list">
        <div class="board">
          <div class="board-head">
            <h2>종합 요약</h2>
            <span>점수 내림차순 · 행 클릭으로 상세</span>
          </div>
          <div class="filters">
            <label>시장
              <select id="filter-market" aria-label="시장 필터">
                <option value="">전체</option>
                <option value="코스피">코스피</option>
                <option value="코스닥">코스닥</option>
              </select>
            </label>
            <label>업종
              <select id="filter-sector" aria-label="업종 필터">
                <option value="">전체</option>
                {sector_options}
              </select>
            </label>
          </div>
          <div class="sum-list">
            {"".join(summary_rows)}
          </div>
          <p class="filter-empty" id="filter-empty" hidden>조건에 맞는 종목이 없습니다.</p>
        </div>
      </div>
      <div id="panel-detail">
        {"".join(detail_sections)}
      </div>
    </div>

    <p class="note">점수 기준: {_term("이동평균")}(20·60·120)·{_term("모멘텀")}·{_term("RSI14")}·{_term("거래량")}·외국인/기관 {_term("순매수")} 가중합.<br>
      {_term("매수관심")} ≥ +25 · {_term("주의")} ≤ −20 · 그 외 {_term("관망")}.</p>
  </div>
  <div class="term-note" id="term-note" hidden role="tooltip"></div>
  <script>
    (function () {{
      const note = document.getElementById("term-note");
      const marketSel = document.getElementById("filter-market");
      const sectorSel = document.getElementById("filter-sector");
      const filterEmpty = document.getElementById("filter-empty");
      let openBtn = null;
      let activeCode = null;

      function place(btn) {{
        const tip = btn.getAttribute("data-tip") || "";
        note.textContent = tip;
        note.hidden = false;
        const r = btn.getBoundingClientRect();
        const pad = 10;
        const w = note.offsetWidth;
        const h = note.offsetHeight;
        let left = r.left;
        if (left + w > window.innerWidth - pad) left = window.innerWidth - w - pad;
        if (left < pad) left = pad;
        let top = r.bottom + 8;
        if (top + h > window.innerHeight - pad) top = Math.max(pad, r.top - h - 8);
        note.style.left = left + "px";
        note.style.top = top + "px";
      }}

      function closeNote() {{
        if (openBtn) openBtn.setAttribute("aria-expanded", "false");
        openBtn = null;
        note.hidden = true;
      }}

      function openDetail(code) {{
        if (!code) return;
        activeCode = code;
        document.body.classList.add("detail-open");
        document.querySelectorAll(".sum-row").forEach(function (row) {{
          row.classList.toggle("active", row.getAttribute("data-code") === code);
        }});
        document.querySelectorAll("#panel-detail .stock").forEach(function (sec) {{
          const match = sec.getAttribute("data-code") === code;
          sec.hidden = !match;
          if (match) sec.scrollTop = 0;
        }});
        const panel = document.getElementById("panel-detail");
        if (panel) panel.scrollTop = 0;
        window.scrollTo({{ top: 0, behavior: "smooth" }});
      }}

      function closeDetail() {{
        activeCode = null;
        document.body.classList.remove("detail-open");
        document.querySelectorAll(".sum-row").forEach(function (row) {{
          row.classList.remove("active");
        }});
        document.querySelectorAll("#panel-detail .stock").forEach(function (sec) {{
          sec.hidden = true;
        }});
      }}

      function applyFilters() {{
        const m = marketSel.value;
        const s = sectorSel.value;
        let visible = 0;
        document.querySelectorAll(".sum-row").forEach(function (row) {{
          const okM = !m || row.getAttribute("data-market") === m;
          const okS = !s || row.getAttribute("data-sector") === s;
          const show = okM && okS;
          row.classList.toggle("filtered-out", !show);
          if (show) visible += 1;
        }});
        document.querySelectorAll("#panel-detail .stock").forEach(function (sec) {{
          const okM = !m || sec.getAttribute("data-market") === m;
          const okS = !s || sec.getAttribute("data-sector") === s;
          sec.classList.toggle("filtered-out", !(okM && okS));
        }});
        if (filterEmpty) filterEmpty.hidden = visible > 0;
        if (activeCode) {{
          const active = document.querySelector('.sum-row[data-code="' + activeCode + '"]');
          if (!active || active.classList.contains("filtered-out")) closeDetail();
        }}
      }}

      document.addEventListener("click", function (e) {{
        const term = e.target.closest(".term");
        if (term) {{
          e.preventDefault();
          e.stopPropagation();
          if (openBtn === term) {{ closeNote(); return; }}
          if (openBtn) openBtn.setAttribute("aria-expanded", "false");
          openBtn = term;
          term.setAttribute("aria-expanded", "true");
          place(term);
          return;
        }}
        if (!e.target.closest(".term-note")) closeNote();

        const closeBtn = e.target.closest(".close-detail");
        if (closeBtn) {{
          e.preventDefault();
          closeDetail();
          return;
        }}

        const row = e.target.closest(".sum-row");
        if (row && !e.target.closest(".term")) {{
          openDetail(row.getAttribute("data-code"));
        }}
      }});

      document.addEventListener("keydown", function (e) {{
        if (e.key === "Escape") {{
          closeNote();
          closeDetail();
          return;
        }}
        const row = e.target.closest && e.target.closest(".sum-row");
        if (row && (e.key === "Enter" || e.key === " ")) {{
          e.preventDefault();
          openDetail(row.getAttribute("data-code"));
        }}
      }});

      marketSel.addEventListener("change", applyFilters);
      sectorSel.addEventListener("change", applyFilters);
      window.addEventListener("scroll", closeNote, {{ passive: true }});
      window.addEventListener("resize", closeNote);
    }})();
  </script>
</body>
</html>
"""
