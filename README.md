# KR Daily Stock Recommend

Windows 11 + VS Code + **Python 3.12** 환경에서  
**`run_daily.py` 하나만 실행**하면, 관심 종목의 **마지막 확정 세션 종가까지**의 시세·기술지표·뉴스를 모아  
**매수관심 / 관망 / 주의** 결론과 이유를 리포트로 만들어 줍니다.

- LLM API 키 **불필요**
- 증권사(모의/실전) 연동 **없음** (직접 확인 후 투자)
- Cursor 연동 **불필요**

> 참고용 도구입니다. 투자 자문이 아니며, 손실 책임은 사용자에게 있습니다.

동작 흐름(초보자용 HTML): [`reports/how_it_works.html`](reports/how_it_works.html)

---

## 다른 PC에서 시작하기 (처음 1회)

### 1) 준비물
- Windows 11
- [VS Code](https://code.visualstudio.com/) + 확장 **Python**
- [Python 3.12](https://www.python.org/downloads/) (`Add python.exe to PATH` 체크 권장)
- 인터넷 연결

### 2) 저장소 받기

```powershell
git clone https://github.com/yonghoney/kr-daily-stock-recommend.git
cd kr-daily-stock-recommend
```

ZIP으로 받아 압축을 풀어도 됩니다: https://github.com/yonghoney/kr-daily-stock-recommend

### 3) 가상환경 + 의존성

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-daily.txt
```

VS Code에서 이 폴더를 연 뒤, 인터프리터로 `.venv\Scripts\python.exe` 를 선택하세요.  
(`.vscode/settings.json`에 이미 지정되어 있습니다.)

---

## 매일 실행 (이것만 하면 됨)

1. VS Code에서 [`run_daily.py`](run_daily.py) 열기  
2. **▶ Run Python File** 또는 **F5**  
3. 결과 확인: [`reports/daily/latest.html`](reports/daily/latest.html) (브라우저) · [`latest.txt`](reports/daily/latest.txt) (메모장)

터미널:

```powershell
.\.venv\Scripts\Activate.ps1
python run_daily.py
```

뉴스 없이 더 빠르게:

```powershell
python run_daily.py --no-news
```

실행할 때마다 **마지막 확정 세션 종가까지**의 데이터로 다시 분석합니다.  
평일 **15:30(KST) 이후**면 당일 종가 기준(폴더도 당일), 장중·주말이면 직전 거래일 기준입니다.  
**누락 보완:** 마지막 실행 이후 빠진 거래일 리포트(2025-01-01~)를 자동 생성합니다. 상태는 `reports/daily/.run_state.json`에 저장됩니다. 빠르게만 돌리려면 `python run_daily.py --no-gap-fill`.

자동으로 매일 돌아가는 스케줄러는 포함되어 있지 않습니다. (원하면 Windows 작업 스케줄러에 `run_daily.py`를 등록하세요.)

---

## 워치리스트 자동 갱신

`run_daily.py`를 실행할 때마다 KRX 기준으로 워치리스트를 **전체 교체**합니다.

코스피·코스닥 **각각**에 대해 (우선주 제외):

- 시가총액 상위 50종목
- 최근 일주일 중 **하루라도** 해당 시장 거래대금 상위 20에 들어간 종목 중, 위 시총 상위 50에 **없는** 종목

합집합(중복 제거)을 `config/kr_universe.yaml`에 저장한 뒤 분석합니다.

수동으로 고정 목록을 쓰고 싶다면 yaml을 직접 수정해도 되지만, 다음 실행 때 다시 자동 갱신됩니다.

---

## 결과가 의미하는 것

| 액션 | 점수 | 의미 |
|------|------|------|
| 매수관심 | ≥ +25 | 기술지표상 상대적으로 우호 |
| 관망 | 중간 | 뚜렷한 신호 없음 |
| 주의 | ≤ −20 | 약세·과열 등 리스크 신호 |

점수는 이동평균(20·60·120), 단기·중기 모멘텀, RSI14, 거래량, **외국인·기관 순매수(네이버)** 규칙으로 계산합니다.  
뉴스 헤드라인은 **참고용**이며 점수에는 반영하지 않습니다.

`latest.html`은 **종합 요약**이 가운데 있고, 종목을 클릭하면 왼쪽 목록 + 오른쪽 상세로 나뉩니다.  
시장(코스피/코스닥)·업종 필터로 목록을 좁힐 수 있습니다.

생성 파일:
- `reports/daily/latest.html` — 세로 스크롤 HTML 리포트 (종합 요약 + 종목별 리포트)
- `reports/daily/latest.txt` — 최신 리포트 (Windows 메모장용, UTF-8)
- `reports/daily/latest.md` — 마크다운 리포트
- `reports/daily/latest.json` — 기계 읽기용
- `reports/daily/YYYY/MM/DD/report.*` — 날짜별 보관 (html / txt / md / json)
- `reports/backtest/signals.jsonl` · `score_stats.html` — 백테스트 시그널·점수대 선수익

---

## 과거 백필 (시세·기술·수급)

2026-06-01부터 거래일마다 PIT(그 날짜 이전 데이터만)로 점수를 쌓으려면
(워치리스트도 그날 KRX 시총·거래대금 기준으로 다시 구성):

```powershell
python run_backfill.py --from 2025-01-01 --force
```

결과: `reports/daily/YYYY/MM/DD/report.json`, `reports/backtest/signals.jsonl`,  
`reports/backtest/score_stats.html` (점수대별 1·3·6개월 평균 선수익)

특정일만 다시 계산:

```powershell
python run_daily.py --as-of 2026-07-10 --no-news
```

전략 백테스트 (전일 점수 &gt; 60이면 종가 1주 매수, 전일 주의면 시가 매도):

```powershell
python run_strategy_bt.py --from 2025-01-01
```

결과: `reports/backtest/strategy_score60.html`

시장별 점수합·액션합 vs 코스피/코스닥 지수 차트(**최근 3개월**)는 리포트 상단에 포함됩니다.
시그널만으로 다시 집계:

```powershell
python scripts/update_market_pulse.py
```

---

## 프로젝트 구조 (핵심)

```
run_daily.py                 ← 실행 진입점 (이것만 실행)
requirements-daily.txt       ← 다른 PC용 최소 의존성
config/kr_universe.yaml      ← 관심 종목
tradingagents/recommend/     ← 추천 엔진
run_backfill.py              ← 과거 거래일 PIT 백필
reports/how_it_works.html    ← 동작 설명서
reports/daily/               ← latest.* + YYYY/MM/DD/ (gitignore)
reports/backtest/            ← signals.jsonl · score_stats.html
.vscode/                     ← VS Code 인터프리터·F5 설정
```

---

## 문제 해결

| 증상 | 해결 |
|------|------|
| `python` / `py` 를 찾을 수 없음 | Python 3.12 재설치, PATH 체크 후 터미널 재시작 |
| 모듈 없음 (`yfinance` 등) | `.venv` 활성화 후 `pip install -r requirements-daily.txt` |
| 시세가 비어 있음 | 인터넷 확인, 티커(`.KS`/`.KQ`) 확인 |
| 콘솔 한글 깨짐 | `latest.txt`를 메모장으로 열면 됨 (UTF-8 BOM) |

---

## 라이선스 / 출처

일일 추천 경로와 한국 시장 확장 코드가 포함되어 있습니다.  
원본 멀티에이전트 프레임워크는 [TradingAgents](https://github.com/TauricResearch/TradingAgents) ([논문](https://arxiv.org/abs/2412.20138))를 참고·포함합니다. 라이선스는 저장소의 `LICENSE`를 따릅니다.
