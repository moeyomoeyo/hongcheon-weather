#!/usr/bin/env python3
"""
AccuWeather 홍천군 월별 예보를 긁어 data.json 으로 저장한다.
GitHub Actions 에서 매일 1회 실행되는 것을 전제로 함 (개인 용도, 하루 1회 요청).
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))

# 여기만 바꾸면 다른 지역/다른 달로 전환됩니다.
MONTHS = [
    {
        "key": "2026-10",
        "year": 2026,
        "month": 10,
        "url": "https://www.accuweather.com/ko/kr/hongcheon-gun/223564/october-weather/223564?year=2026",
    },
    {
        "key": "2026-11",
        "year": 2026,
        "month": 11,
        "url": "https://www.accuweather.com/ko/kr/hongcheon-gun/223564/november-weather/223564?year=2026",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_html(url: str) -> str:
    """requests 로 먼저 시도하고, 차단되면 Playwright 로 재시도."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and "monthly-daypanel" in r.text:
            return r.text
        print(f"  requests 실패 (status={r.status_code}) → Playwright 로 재시도", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"  requests 예외: {e} → Playwright 로 재시도", file=sys.stderr)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent=HEADERS["User-Agent"],
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".monthly-daypanel", timeout=30000)
        html = page.content()
        browser.close()
        return html


def f_to_c(f: float) -> int:
    return round((f - 32) * 5 / 9)


DEG = re.compile(r"(-?\d+)\s*°")


def parse_month(html: str, year: int, month: int):
    """
    클래스 이름 구조에 최소한으로만 의존한다.
    각 날짜 패널의 '텍스트'에서 날짜 / 설명 / 최고 / 최저를 뽑는다.
    """
    soup = BeautifulSoup(html, "html.parser")
    panels = soup.select("a.monthly-daypanel, div.monthly-daypanel")
    if not panels:
        raise RuntimeError("monthly-daypanel 을 찾지 못했습니다. AccuWeather DOM 이 바뀌었을 수 있습니다.")

    days = []
    seen_first = False
    for panel in panels:
        parts = [t.strip() for t in panel.get_text("|", strip=True).split("|") if t.strip()]
        if not parts:
            continue

        # 첫 토큰 = 날짜 숫자
        m = re.match(r"^(\d{1,2})$", parts[0])
        if not m:
            continue
        dnum = int(m.group(1))

        temps = [int(x) for x in DEG.findall(" ".join(parts))]
        if len(temps) < 2:
            continue
        hi_f, lo_f = temps[0], temps[1]

        desc = " ".join(
            p for p in parts[1:] if not DEG.search(p) and not re.match(r"^\d{1,2}$", p)
        ).strip()
        historical = "기록" in desc or "평균" in desc or not desc

        # 달력은 앞뒤로 이웃 달 날짜를 물고 있다. 1일이 나오기 전 = 이전 달, 1일 이후 재등장 = 다음 달.
        if dnum == 1:
            if seen_first:
                break  # 다음 달 영역 진입
            seen_first = True
        if not seen_first:
            continue

        days.append(
            {
                "day": dnum,
                "desc": desc or "기록 평균",
                "hi": f_to_c(hi_f),
                "lo": f_to_c(lo_f),
                "hiF": hi_f,
                "loF": lo_f,
                "historical": historical,
            }
        )

    if not days:
        raise RuntimeError(f"{year}-{month:02d}: 날짜를 하나도 파싱하지 못했습니다.")
    return days


def main():
    out = {
        "location": "홍천군, 강원도",
        "source": "AccuWeather",
        "updatedAt": datetime.now(KST).isoformat(timespec="minutes"),
        "months": [],
    }

    for cfg in MONTHS:
        print(f"가져오는 중: {cfg['key']}")
        html = fetch_html(cfg["url"])
        days = parse_month(html, cfg["year"], cfg["month"])
        first_weekday = datetime(cfg["year"], cfg["month"], 1).weekday()  # 월=0
        out["months"].append(
            {
                "key": cfg["key"],
                "year": cfg["year"],
                "month": cfg["month"],
                "url": cfg["url"],
                "leadingBlanks": (first_weekday + 1) % 7,  # 일요일 시작 달력 기준
                "days": days,
            }
        )
        print(f"  → {len(days)}일 수집")

    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print("data.json 저장 완료")


if __name__ == "__main__":
    main()
