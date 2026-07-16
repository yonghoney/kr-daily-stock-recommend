"""HTML vertical-scroll daily report renderer."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.recommend.engine import Recommendation


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _action_class(action: str) -> str:
    if action == "매수관심":
        return "buy"
    if action == "주의":
        return "caution"
    return "watch"


def _fmt_impact(impact: float) -> str:
    sign = "+" if impact > 0 else ""
    return f"{sign}{impact:.0f}"


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
    brief = " · ".join(brief_parts)
    if len(brief) > 140:
        brief = brief[:137] + "..."

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
                <p class="news-brief">{_esc(brief)}</p>
                <ul>{"".join(rows)}</ul>
              </div>
            """


def render_html(
    recs: list[Recommendation],
    *,
    as_of: str,
) -> str:
    ranked = sorted(recs, key=lambda r: r.score, reverse=True)
    buy_n = sum(1 for r in ranked if r.action == "매수관심")
    watch_n = sum(1 for r in ranked if r.action == "관망")
    caution_n = sum(1 for r in ranked if r.action == "주의")

    summary_rows: list[str] = []
    detail_sections: list[str] = []

    for i, r in enumerate(ranked, 1):
        anchor = f"stock-{_esc(r.code)}"
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
            <article class="sum-row">
              <div class="rank">{i}</div>
              <div class="sum-main">
                <div class="sum-title">
                  <strong>{_esc(r.name)}</strong>
                  <span class="market">{_esc(r.market)}</span>
                  <span class="code">{_esc(r.code)}</span>
                  <span class="badge {_action_class(r.action)}">{_esc(r.action)}</span>
                </div>
                <div class="drivers">{drivers_html}</div>
              </div>
              <div class="sum-side">
                <div class="score {_action_class(r.action)}">{_esc(r.score)}</div>
                <a class="btn" href="#{anchor}">종목 리포트</a>
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
            days = _esc(flow.get("days", 5))
            flow_html = f"""
              <div class="block">
                <h3>외국인·기관 수급 ({_esc(flow.get('as_of', '-'))})</h3>
                <div class="metrics flow">
                  <div><span>외인 1일</span><strong>{_esc(_sh('foreign_net_1d'))}</strong></div>
                  <div><span>기관 1일</span><strong>{_esc(_sh('organ_net_1d'))}</strong></div>
                  <div><span>외인 {days}일</span><strong>{_esc(_sh('foreign_net_5d'))}</strong></div>
                  <div><span>기관 {days}일</span><strong>{_esc(_sh('organ_net_5d'))}</strong></div>
                  <div><span>외인 지분</span><strong>{_esc(hold_txt)}</strong></div>
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
            <section class="stock" id="{anchor}">
              <header class="stock-head">
                <div>
                  <p class="eyebrow">종목 리포트 · {_esc(i)}위 · {_esc(r.market)}</p>
                  <h2>{_esc(r.name)} <span class="code">{_esc(r.code)}</span></h2>
                  <p class="meta">
                    <span class="market">{_esc(r.market)}</span>
                    · {_esc(r.ticker)} ·
                    <span class="badge {_action_class(r.action)}">{_esc(r.action)}</span>
                    · 점수 <strong>{_esc(r.score)}</strong>
                  </p>
                </div>
                <a class="btn ghost" href="#summary">종합 요약</a>
              </header>
              {error_html}
              <div class="metrics">
                <div><span>종가</span><strong>{r.price:,.0f}</strong></div>
                <div><span>1일</span><strong>{r.ret_1d_pct:+.2f}%</strong></div>
                <div><span>5일</span><strong>{r.ret_5d_pct:+.2f}%</strong></div>
                <div><span>RSI14</span><strong>{_esc(r.rsi14)}</strong></div>
              </div>
              {f'<div class="block chart">{r.chart_svg}</div>' if r.chart_svg else ''}
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
      --max: 920px;
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
      margin: 0;
      color: var(--muted);
      max-width: 42rem;
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
    #summary {{
      scroll-margin-top: 1rem;
      margin-top: 1.75rem;
      animation: rise 0.8s ease 0.08s both;
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
      padding: 0.9rem 1rem 0.5rem;
    }}
    .board-head h2 {{
      margin: 0;
      font-family: "Fraunces", Georgia, serif;
      font-size: 1.35rem;
    }}
    .board-head span {{ color: var(--muted); font-size: 0.9rem; }}
    .sum-row {{
      display: grid;
      grid-template-columns: 2.2rem 1fr auto;
      gap: 0.75rem;
      align-items: start;
      padding: 0.95rem 1rem;
      border-top: 1px solid var(--line);
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
    }}
    .btn:hover {{ transform: translateY(-1px); background: #1c3340; }}
    .btn.ghost {{
      background: transparent;
      color: var(--ink);
      border-color: var(--line);
    }}
    .btn.ghost:hover {{ background: rgba(255,255,255,0.7); }}
    .stock {{
      margin-top: 1.4rem;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 1.2rem 1.15rem 1.35rem;
      scroll-margin-top: 1rem;
      backdrop-filter: blur(10px);
      animation: rise 0.75s ease both;
    }}
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
      margin-bottom: 1rem;
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
      font-size: 1.05rem;
      font-variant-numeric: tabular-nums;
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
    .metrics.flow {{
      grid-template-columns: repeat(3, 1fr);
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
      <p>{_esc(as_of)} KST · LLM·증권사 API 없이 시세·기술지표·뉴스 헤드라인으로 만든 참고용 리포트입니다. 투자 자문이 아니며, 최종 판단은 본인에게 있습니다.</p>
      <div class="stats">
        <div class="stat">전체 <b>{len(ranked)}</b></div>
        <div class="stat">매수관심 <b class="buy">{buy_n}</b></div>
        <div class="stat">관망 <b class="watch">{watch_n}</b></div>
        <div class="stat">주의 <b class="caution">{caution_n}</b></div>
      </div>
    </header>

    <section id="summary">
      <div class="board">
        <div class="board-head">
          <h2>종합 요약</h2>
          <span>점수 내림차순 · 영향 큰 요인 표시</span>
        </div>
        {"".join(summary_rows)}
      </div>
    </section>

    {"".join(detail_sections)}

    <p class="note">점수 기준: 이동평균(20·60·120)·모멘텀·RSI14·거래량·외국인/기관 순매수 가중합. 매수관심 ≥ +25 · 주의 ≤ −20 · 그 외 관망.</p>
  </div>
</body>
</html>
"""
