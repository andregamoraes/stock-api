import os, logging, re, requests
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Optional

log = logging.getLogger(__name__)

# Mapping of MarketWatch performance labels to our internal keys
_LABEL_TO_KEY = {
    "5 Day": "five_days",
    "1 Month": "one_month",
    "3 Month": "three_months",
    "YTD": "year_to_date",
    "1 Year": "one_year",
}

# COOKIE from .app.env file change if necessary
COOKIE = os.getenv("MARKETWATCH_COOKIE", "")

def _headers(cookie: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:141.0) Gecko/20100101 Firefox/141.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Cookie": cookie,
    }


def _pct_to_float(txt: str):
    """
    Parse a percentage string into a float.
    """
    t = (txt or "").replace("\u2212", "-")
    m = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*%", t)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def _parse_market_cap(txt: str) -> Tuple[Optional[str], Optional[float]]:
    """
    Ex.: "$3.75T"      -> ("$",   3750000000000.0)
         "US$ 2.37T"   -> ("US$", 2370000000000.0)
         "₩465.45T"    -> ("₩",   465450000000000.0)
         "€512.3B"     -> ("€",   512300000000.0)
    """
    if not txt or txt.strip() in {"—", "-", "N/A"}:
        return (None, None)

    t = txt.strip().replace("\xa0", " ")
    m = re.match(r"^(?P<cur>[^\d.,-]+)?\s*(?P<num>[\d.,]+)\s*(?P<suf>[KMBT])?$", t, flags=re.I)
    if not m:
        return (None, None)

    cur = (m.group("cur") or "").strip() or None
    num = float(m.group("num").replace(",", ""))
    suf = (m.group("suf") or "").upper()
    mult = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    value = num * mult.get(suf, 1.0)

    return cur, value

def get_scrapping_data(symbol: str):
    """
    Get html from MarketWatch and parse performance and competitors data.
    """

    performance = {v: None for v in _LABEL_TO_KEY.values()}
    competitors = []

    url = f"https://www.marketwatch.com/investing/stock/{symbol.lower()}"
    html = requests.get(url, headers=_headers(COOKIE), timeout=10).text

   # Check for bot/captcha page
    if ("Please enable JS and disable any ad blocker" in html or "captcha-delivery.com" in html or "datadome" in html.lower()):
        log.error("MarketWatch antibot/captcha detectado. Atualize MARKETWATCH_COOKIE no .app.env.")
        return {"performance": performance, "competitors": competitors}

    soup = BeautifulSoup(html, "lxml")

    # Find performance box
    perf_box = soup.find(
        "div",
        class_=lambda c: c and "element--table" in c and "performance" in c
    )

    # Get performance data
    if perf_box:
        for row in perf_box.select("tr.table__row"):
            cells = row.select("td.table__cell")
            if len(cells) < 2:
                continue

            label = " ".join(cells[0].get_text(" ", strip=True).split())
            key = _LABEL_TO_KEY.get(label)

            if not key:
                continue

            value_container = cells[1].select_one("li.content__item.value") or cells[1]
            value_txt = value_container.get_text(" ", strip=True)
            performance[key] = _pct_to_float(value_txt)


    comp_table = None
    comp_head = soup.find(lambda t: t and t.name in ("h2","h3") and "Competitors" in t.get_text(" ", strip=True))
    if comp_head:
        comp_table = comp_head.find_next("table")
    if not comp_table:
        comp_table = soup.find("table", string=lambda _: False)
        for tbl in soup.find_all("table"):
            thead_txt = tbl.find("thead").get_text(" ", strip=True) if tbl.find("thead") else ""
            if "Market Cap" in thead_txt and "Name" in thead_txt:
                comp_table = tbl
                break

    if comp_table:
        for row in comp_table.select("tbody tr"):
            tds = row.find_all("td")
            if len(tds) < 1:
                continue
            name = tds[0].get_text(" ", strip=True)
            cap_txt = tds[-1].get_text(" ", strip=True) if len(tds) >= 3 else ""
            currency, value = _parse_market_cap(cap_txt)
            if name:
                competitors.append({
                    "name": name,
                    "market_cap": {"currency": currency, "value": value}
                })

    return {"performance": performance, "competitors": competitors}

