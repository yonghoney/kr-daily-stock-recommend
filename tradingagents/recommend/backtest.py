"""Backtest signal store, forward-return stats, and helpers."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pytz

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

HORIZONS = {
    "1M": 21,  # trading days ≈ 1 month
    "3M": 63,
    "6M": 126,
}

BUCKETS = (
    ("주의 (≤−20)", lambda s: s <= -20),
    ("관망 (−19~+24)", lambda s: -20 < s < 25),
    ("매수관심 (≥+25)", lambda s: s >= 25),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def backtest_dir() -> Path:
    d = _project_root() / "reports" / "backtest"
    d.mkdir(parents=True, exist_ok=True)
    return d


def signals_path() -> Path:
    return backtest_dir() / "signals.jsonl"


def stats_json_path() -> Path:
    return backtest_dir() / "score_stats.json"


def stats_html_path() -> Path:
    return backtest_dir() / "score_stats.html"


def append_day_signals(
    as_of: str,
    recs: Iterable[Any],
    *,
    path: Path | None = None,
    rewrite: bool = False,
) -> int:
    """Append one day's recommendations to the JSONL store. Returns rows written.

    Default is append-only (fast/safe for long backfills).
    Set ``rewrite=True`` to drop existing rows for the same ``as_of`` first
    (loads whole file — avoid in tight loops).
    """
    out = path or signals_path()
    out.parent.mkdir(parents=True, exist_ok=True)

    def _field(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    new_rows: list[dict[str, Any]] = []
    for r in recs:
        new_rows.append(
            {
                "as_of": as_of,
                "code": _field(r, "code"),
                "name": _field(r, "name"),
                "ticker": _field(r, "ticker"),
                "market": _field(r, "market"),
                "sector": _field(r, "sector"),
                "action": _field(r, "action"),
                "score": float(_field(r, "score") or 0),
                "price": float(_field(r, "price") or 0),
            }
        )

    if rewrite:
        existing = [r for r in load_signals(path=out) if r.get("as_of") != as_of]
        with open(out, "w", encoding="utf-8") as f:
            for row in existing + new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        with open(out, "a", encoding="utf-8") as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(new_rows)


def load_signals(*, path: Path | None = None) -> list[dict[str, Any]]:
    p = path or signals_path()
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def rebuild_signals_from_daily_reports(
    *,
    start: str,
    end: str,
    daily_dir: Path | None = None,
    path: Path | None = None,
) -> int:
    """Rebuild signals.jsonl from dated report.json files (deduped by as_of+code)."""
    from tradingagents.recommend.paths import iter_dated_report_jsons

    out = path or signals_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for as_of, report in iter_dated_report_jsons(
        start=start, end=end, output_dir=daily_dir
    ):
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("skip bad report %s: %s", report, exc)
            continue
        day = str(payload.get("as_of") or as_of)
        for r in payload.get("recommendations") or []:
            if not isinstance(r, dict):
                continue
            rows.append(
                {
                    "as_of": day,
                    "code": r.get("code"),
                    "name": r.get("name"),
                    "ticker": r.get("ticker"),
                    "market": r.get("market"),
                    "sector": r.get("sector"),
                    "action": r.get("action"),
                    "score": float(r.get("score") or 0),
                    "price": float(r.get("price") or 0),
                }
            )
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)

def signal_markers_for(
    code: str,
    *,
    start: str | None = None,
    end: str | None = None,
    actions: tuple[str, ...] = ("매수관심", "주의"),
) -> list[dict[str, str]]:
    code6 = str(code).zfill(6)
    out: list[dict[str, str]] = []
    for r in load_signals():
        if str(r.get("code", "")).zfill(6) != code6:
            continue
        action = str(r.get("action") or "")
        if action not in actions:
            continue
        day = str(r.get("as_of") or "")
        if start and day < start:
            continue
        if end and day > end:
            continue
        out.append({"date": day, "action": action})
    return out


def signal_counts_for(
    code: str,
    *,
    lookback_calendar_days: int = 90,
    as_of: str | None = None,
) -> tuple[int, int]:
    """Return (buy_count, caution_count) in the lookback window ending at as_of."""
    code6 = str(code).zfill(6)
    end = as_of or datetime.now(KST).strftime("%Y-%m-%d")
    end_ts = pd.Timestamp(end)
    start_ts = end_ts - pd.Timedelta(days=lookback_calendar_days)
    start = start_ts.strftime("%Y-%m-%d")
    buy = caution = 0
    for r in load_signals():
        if str(r.get("code", "")).zfill(6) != code6:
            continue
        day = str(r.get("as_of") or "")
        if day < start or day > end:
            continue
        if r.get("action") == "매수관심":
            buy += 1
        elif r.get("action") == "주의":
            caution += 1
    return buy, caution


def score_history_index(
    *,
    start: str,
    end: str,
    path: Path | None = None,
) -> dict[str, list[tuple[str, float]]]:
    """Map code -> [(as_of, score), ...] sorted by date within [start, end]."""
    by_code: dict[str, dict[str, float]] = defaultdict(dict)
    for r in load_signals(path=path):
        day = str(r.get("as_of") or "")
        if day < start or day > end:
            continue
        code6 = str(r.get("code") or "").zfill(6)
        if not code6 or code6 == "000000":
            continue
        try:
            score = float(r.get("score") or 0)
        except (TypeError, ValueError):
            continue
        by_code[code6][day] = score
    out: dict[str, list[tuple[str, float]]] = {}
    for code, day_map in by_code.items():
        out[code] = sorted(day_map.items(), key=lambda x: x[0])
    return out


@dataclass
class BucketStat:
    label: str
    n: int
    ret_1m: float | None
    ret_3m: float | None
    ret_6m: float | None
    n_1m: int
    n_3m: int
    n_6m: int


def _forward_return(close: pd.Series, day: str, horizon: int) -> float | None:
    """Return close[t+horizon]/close[t]-1 using trading-day index."""
    if close is None or close.empty:
        return None
    idx = close.index
    # Normalize to date strings
    dates = pd.DatetimeIndex(pd.to_datetime(idx)).tz_localize(None).normalize()
    close = pd.Series(close.to_numpy(dtype=float), index=dates)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    target = pd.Timestamp(day).normalize()
    if target not in close.index:
        # nearest prior session
        prior = close.index[close.index <= target]
        if len(prior) == 0:
            return None
        target = prior[-1]
    pos = close.index.get_loc(target)
    if isinstance(pos, slice):
        pos = pos.start
    fut = pos + horizon
    if fut >= len(close):
        return None
    p0 = float(close.iloc[pos])
    p1 = float(close.iloc[fut])
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


def compute_bucket_stats(
    signals: list[dict[str, Any]],
    price_by_ticker: dict[str, pd.DataFrame],
) -> list[BucketStat]:
    """Aggregate forward returns by score action buckets."""
    by_bucket: dict[str, list[dict[str, float | None]]] = {label: [] for label, _ in BUCKETS}

    for row in signals:
        score = float(row.get("score") or 0)
        ticker = str(row.get("ticker") or "")
        day = str(row.get("as_of") or "")
        hist = price_by_ticker.get(ticker)
        if hist is None or hist.empty or "Close" not in hist.columns:
            continue
        close = hist["Close"]
        rets = {
            k: _forward_return(close, day, h) for k, h in HORIZONS.items()
        }
        for label, pred in BUCKETS:
            if pred(score):
                by_bucket[label].append(rets)
                break

    stats: list[BucketStat] = []
    for label, _ in BUCKETS:
        rows = by_bucket[label]

        def _avg(key: str) -> tuple[float | None, int]:
            vals = [float(r[key]) for r in rows if r.get(key) is not None]
            if not vals:
                return None, 0
            return sum(vals) / len(vals), len(vals)

        a1, n1 = _avg("1M")
        a3, n3 = _avg("3M")
        a6, n6 = _avg("6M")
        stats.append(
            BucketStat(
                label=label,
                n=len(rows),
                ret_1m=a1,
                ret_3m=a3,
                ret_6m=a6,
                n_1m=n1,
                n_3m=n3,
                n_6m=n6,
            )
        )
    return stats


def render_stats_html(stats: list[BucketStat], *, as_of: str, note: str = "") -> str:
    def pct(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v * 100:+.2f}%"

    rows = []
    for s in stats:
        rows.append(
            f"<tr><td>{s.label}</td><td>{s.n}</td>"
            f"<td>{pct(s.ret_1m)} <span class='n'>(n={s.n_1m})</span></td>"
            f"<td>{pct(s.ret_3m)} <span class='n'>(n={s.n_3m})</span></td>"
            f"<td>{pct(s.ret_6m)} <span class='n'>(n={s.n_6m})</span></td></tr>"
        )
    note_html = f"<p class='note'>{note}</p>" if note else ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>점수대별 향후 수익률 ({as_of})</title>
  <style>
    body {{ font-family: "IBM Plex Sans KR", sans-serif; margin: 2rem; color: #12212b;
      background: linear-gradient(180deg, #e7eef3, #edf3f6); }}
    h1 {{ font-family: Georgia, serif; }}
    table {{ border-collapse: collapse; width: min(100%, 720px); background: #fff;
      border-radius: 12px; overflow: hidden; box-shadow: 0 8px 24px rgba(0,0,0,.06); }}
    th, td {{ padding: 0.75rem 0.9rem; border-bottom: 1px solid #d7e0e6; text-align: left; }}
    th {{ background: #f0f5f8; color: #5a6d78; font-size: 0.85rem; }}
    .n {{ color: #5a6d78; font-size: 0.8rem; }}
    .note {{ color: #5a6d78; max-width: 40rem; }}
  </style>
</head>
<body>
  <h1>점수대별 향후 수익률</h1>
  <p>집계 기준일: {as_of}<br>
  시그널 당일 종가 대비 이후 약 1·3·6개월(거래일 21/63/126) 수익률 평균</p>
  {note_html}
  <table>
    <thead><tr><th>점수대</th><th>표본</th><th>1개월</th><th>3개월</th><th>6개월</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  <p class="note">참고용 통계입니다. 미래 수익을 보장하지 않으며, 표본이 적으면 해석에 주의하세요.<br>
  수급(외인·기관)은 네이버가 최근 구간만 제공하므로 오래된 as_of에서는 기술지표 위주로 채점됩니다.</p>
  <p>전략 테스트(점수&gt;60 매수 → 주의 매도): <a href="strategy_score60.html">strategy_score60.html</a></p>
</body>
</html>
"""


def write_stats(
    stats: list[BucketStat],
    *,
    as_of: str | None = None,
    note: str = "",
) -> Path:
    as_of = as_of or datetime.now(KST).strftime("%Y-%m-%d")
    payload = {
        "as_of": as_of,
        "buckets": [
            {
                "label": s.label,
                "n": s.n,
                "ret_1m": s.ret_1m,
                "ret_3m": s.ret_3m,
                "ret_6m": s.ret_6m,
                "n_1m": s.n_1m,
                "n_3m": s.n_3m,
                "n_6m": s.n_6m,
            }
            for s in stats
        ],
    }
    stats_json_path().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    html_path = stats_html_path()
    html_path.write_text(
        render_stats_html(stats, as_of=as_of, note=note), encoding="utf-8"
    )
    return html_path


def trading_days(start: str, end: str) -> list[str]:
    """Weekday calendar between start and end inclusive (approx KR sessions)."""
    idx = pd.bdate_range(start=start, end=end)
    return [d.strftime("%Y-%m-%d") for d in idx]
