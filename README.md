# KR Daily Stock Recommend

Windows 11 + VS Code + **Python 3.12** 환경에서  
**`run_daily.py` 하나만 실행**하면, 관심 종목의 **최신 시세·기술지표·뉴스**를 모아  
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
3. 결과 확인: [`reports/daily/latest.txt`](reports/daily/latest.txt) (메모장) · [`latest.md`](reports/daily/latest.md)

터미널:

```powershell
.\.venv\Scripts\Activate.ps1
python run_daily.py
```

뉴스 없이 더 빠르게:

```powershell
python run_daily.py --no-news
```

실행할 때마다 **그 시점의 최신 데이터**로 다시 분석합니다.  
자동으로 매일 돌아가는 스케줄러는 포함되어 있지 않습니다. (원하면 Windows 작업 스케줄러에 `run_daily.py`를 등록하세요.)

---

## 관심 종목 바꾸기

[`config/kr_universe.yaml`](config/kr_universe.yaml) 의 `watchlist`를 수정한 뒤 다시 실행하세요.

```yaml
watchlist:
  - code: "005930"
    name: 삼성전자
    ticker: "005930.KS"
```

---

## 결과가 의미하는 것

| 액션 | 점수 | 의미 |
|------|------|------|
| 매수관심 | ≥ +25 | 기술지표상 상대적으로 우호 |
| 관망 | 중간 | 뚜렷한 신호 없음 |
| 주의 | ≤ −20 | 약세·과열 등 리스크 신호 |

점수는 이동평균, 단기·중기 모멘텀, RSI14, 거래량 규칙으로 계산합니다.  
뉴스 헤드라인은 **참고용**이며 점수에는 반영하지 않습니다.

생성 파일:
- `reports/daily/latest.txt` — 최신 리포트 (Windows 메모장용, UTF-8)
- `reports/daily/latest.md` — 마크다운 리포트
- `reports/daily/YYYY-MM-DD.txt` / `.md` / `.json` — 날짜별 보관
- `reports/daily/latest.json` — 기계 읽기용

---

## 파이프라인 요약

```
run_daily.py
  → 관심종목 목록 읽기 (kr_universe.yaml)
  → 시세 수집 (Yahoo Finance)
  → 기술지표 계산 (이평·RSI·수익률·거래량)
  → 규칙 점수 + 이유 문장
  → (선택) 한국 뉴스 헤드라인
  → 등급(매수관심/관망/주의) + 리포트 저장
  → 사람이 읽고 직접 투자 결정
```

자세한 설명: 브라우저로 `reports/how_it_works.html` 을 여세요.

---

## 프로젝트 구조 (핵심)

```
run_daily.py                 ← 실행 진입점 (이것만 실행)
requirements-daily.txt       ← 다른 PC용 최소 의존성
config/kr_universe.yaml      ← 관심 종목
tradingagents/recommend/     ← 추천 엔진
reports/how_it_works.html    ← 동작 설명서
reports/daily/               ← 실행 결과 (gitignore)
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
