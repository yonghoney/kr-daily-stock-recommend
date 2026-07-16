"""Korea Investment & Securities (KIS) Open API adapter.

Supports paper (모의투자) by default and live when TRADING_MODE=live with
explicit acceptance. Docs: https://apiportal.koreainvestment.com
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

from tradingagents.dataflows.kr_symbols import kr_base_code, normalize_kr_symbol
from tradingagents.execution.types import (
    Balance,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    Side,
)

logger = logging.getLogger(__name__)

_PAPER_BASE = "https://openapivts.koreainvestment.com:29443"
_LIVE_BASE = "https://openapi.koreainvestment.com:9443"

# tr_id: paper vs live cash order
_TR_BUY = {"paper": "VTTC0802U", "live": "TTTC0802U"}
_TR_SELL = {"paper": "VTTC0801U", "live": "TTTC0801U"}
_TR_BALANCE = {"paper": "VTTC8434R", "live": "TTTC8434R"}
_TR_POSITIONS = {"paper": "VTTC8434R", "live": "TTTC8434R"}


class KisBroker:
    name = "kis"

    def __init__(
        self,
        *,
        app_key: str | None = None,
        app_secret: str | None = None,
        account_no: str | None = None,
        account_product_code: str | None = None,
        paper: bool = True,
    ):
        self.app_key = (app_key or os.environ.get("KIS_APP_KEY", "")).strip()
        self.app_secret = (app_secret or os.environ.get("KIS_APP_SECRET", "")).strip()
        self.cano = (account_no or os.environ.get("KIS_ACCOUNT_NO", "")).strip()
        self.acnt_prdt_cd = (
            account_product_code or os.environ.get("KIS_ACCOUNT_PRODUCT_CODE", "01")
        ).strip()
        self.paper = paper
        self.base_url = _PAPER_BASE if paper else _LIVE_BASE
        self._token: str | None = None
        self._token_expiry: float = 0.0

        if not self.app_key or not self.app_secret:
            raise ValueError("KIS_APP_KEY and KIS_APP_SECRET are required for KisBroker")
        if not self.cano:
            raise ValueError("KIS_ACCOUNT_NO is required for KisBroker")

    def _mode(self) -> str:
        return "paper" if self.paper else "live"

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        url = f"{self.base_url}/oauth2/tokenP"
        resp = requests.post(
            url,
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"KIS token failed: {data}")
        # expires_in is seconds (often ~86400)
        expires_in = int(data.get("expires_in", 86400))
        self._token = token
        self._token_expiry = time.time() + expires_in
        return token

    def _headers(self, tr_id: str, *, hashkey: str | None = None) -> dict[str, str]:
        token = self._ensure_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def _hashkey(self, body: dict[str, Any]) -> str:
        url = f"{self.base_url}/uapi/hashkey"
        resp = requests.post(
            url,
            headers={
                "content-type": "application/json; charset=utf-8",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            json=body,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json().get("HASH", "")

    def get_balance(self) -> Balance:
        """Inquire account balance (cash)."""
        tr_id = _TR_BALANCE[self._mode()]
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=20)
        data = resp.json()
        if not resp.ok:
            raise RuntimeError(f"KIS balance HTTP {resp.status_code}: {data}")
        output2 = data.get("output2") or [{}]
        row = output2[0] if isinstance(output2, list) else output2
        cash = float(row.get("dnca_tot_amt") or row.get("nxdy_excc_amt") or 0)
        return Balance(cash=cash, currency="KRW", buying_power=cash, raw=data)

    def get_positions(self) -> list[Position]:
        tr_id = _TR_POSITIONS[self._mode()]
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "01",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._headers(tr_id), params=params, timeout=20)
        data = resp.json()
        if not resp.ok:
            raise RuntimeError(f"KIS positions HTTP {resp.status_code}: {data}")
        positions: list[Position] = []
        for row in data.get("output1") or []:
            qty = int(float(row.get("hldg_qty") or 0))
            if qty == 0:
                continue
            code = row.get("pdno") or ""
            positions.append(
                Position(
                    symbol=normalize_kr_symbol(code) if code else code,
                    quantity=qty,
                    avg_price=float(row.get("pchs_avg_pric") or 0),
                    market_value=float(row.get("evlu_amt") or 0),
                    raw=row,
                )
            )
        return positions

    def place_order(self, order: OrderRequest) -> OrderResult:
        code = kr_base_code(order.symbol) or kr_base_code(normalize_kr_symbol(order.symbol))
        if not code:
            return OrderResult(False, None, f"Not a KRX symbol: {order.symbol}")

        if order.side == Side.BUY:
            tr_id = _TR_BUY[self._mode()]
            side_code = "02"  # buy
        else:
            tr_id = _TR_SELL[self._mode()]
            side_code = "01"  # sell

        # 01=limit, 01 market uses ord_dvsn 01 with unpr 0 for market in KIS:
        # ord_dvsn: 01 지정가, 01... actually 01=지정가, 01; market is "01" vs "01"
        # Common: "01" 지정가, "01"; market order ord_dvsn="01" is wrong.
        # KIS: ord_dvsn "01"=지정가, "01"; "01" — market is "01" no:
        # Official: 00=지정가, 01=시장가
        if order.order_type == OrderType.MARKET:
            ord_dvsn = "01"
            price = "0"
        else:
            ord_dvsn = "00"
            if order.limit_price is None:
                return OrderResult(False, None, "LIMIT order requires limit_price")
            price = str(int(order.limit_price))

        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(int(order.quantity)),
            "ORD_UNPR": price,
        }
        # SLL_BUY_DVSN_CD is sometimes in body for newer APIs; classic cash order
        # uses separate tr_id per side, so no side field required.

        try:
            hashkey = self._hashkey(body)
            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
            resp = requests.post(
                url,
                headers=self._headers(tr_id, hashkey=hashkey),
                json=body,
                timeout=20,
            )
            data = resp.json()
        except Exception as exc:
            logger.exception("KIS place_order failed")
            return OrderResult(False, None, f"KIS request error: {exc}")

        rt_cd = str(data.get("rt_cd", ""))
        if rt_cd != "0":
            msg = data.get("msg1") or data.get("msg_cd") or str(data)
            return OrderResult(False, None, f"KIS reject: {msg}", raw=data)

        output = data.get("output") or {}
        order_id = output.get("ODNO") or output.get("odno")
        return OrderResult(
            True,
            order_id,
            data.get("msg1") or "KIS order accepted",
            filled_qty=0,  # acceptance ≠ fill
            raw={"side": side_code, **data},
        )

    def cancel_order(self, order_id: str) -> None:
        # Minimal stub — full cancel needs orgn_odno + qty; raise to signal unsupported.
        raise NotImplementedError(
            "KisBroker.cancel_order is not implemented in MVP; cancel via HTS/KIS portal."
        )
