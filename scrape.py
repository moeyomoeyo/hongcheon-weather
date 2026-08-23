#!/usr/bin/env python3
"""
AccuWeather 홍천군 월별 예보를 긁어 data.json 으로 저장한다.

AccuWeather 는 데이터센터 IP(GitHub Actions 등)를 차단하는 경우가 많아
세 가지 경로를 순서대로 시도한다:
  1) 직접 HTTP 요청
  2) r.jina.ai 텍스트 리더 프록시
  3) Playwright 실제 브라우저
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))

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

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# "[27 점차 흐려짐 75° 54°](...day=36)" 또는 "[23 기록 평균52°38°](...)" 둘 다 잡는다.
DAY_RE = re.compile(
    r"\[\s*(\d{1,2})\s*(.*?)\s*(-?\d+)\s*°\s*(-?\d+)\s*°\s*\]\([^)]*?day=(\d+)\)",
    re.S,
)
# HTML 경로용
PANEL_RE = re.compile(
    r'<a[^>]*class="[^"]*monthly-daypanel[^"]*"[^>]*>(.*?)</a>', re.S | re.I
)
TAGS_RE = re.compile(r"<[^>]+>")


def f_to_c(f: float) -> int:
    return round((f - 32) * 5 / 9)


# ---------------------------------------------------------------- 수집 경로


def try_direct(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and "monthly-daypanel" in r.text:
            print("  ✓ 직접 요청 성공")
            return html_to_markdownish(r.text)
        print(f"  · 직접 요청 무응답 (status={r.status_code})")
    except Exception as e:  # noqa: BLE001
        print(f"  · 직접 요청 실패: {type(e).__name__}")
    return None


def try_jina(url: str):
    """r.jina.ai 가 페이지를 대신 열어 마크다운 텍스트로 돌려준다."""
    proxied = "https://r.jina.ai/" + url
    try:
        r = requests.get(
            proxied,
            headers={"User-Agent": UA, "Accept": "text/plain", "X-Return-Format": "markdown"},
            timeout=90,
        )
        if r.status_code == 200 and "day=" in r.text:
            print("  ✓ 리더 프록시 성공")
            return r.text
        print(f"  · 리더 프록시 무응답 (status={r.status_code})")
    except Exception as e:  # noqa: BLE001
        print(f"  · 리더 프록시 실패: {type(e).__name__}")
    return None


def try_playwright(url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  · Playwright 미설치, 건너뜀")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            ctx = browser.new_context(
                user_agent=UA, locale="ko-KR", viewport={"width": 1366, "height": 900}
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_selector(".monthly-daypanel", timeout=45000)
            html = page.content()
            browser.close()
            print("  ✓ 브라우저 성공")
            return html_to_markdownish(html)
    except Exception as e:  # noqa: BLE001
        print(f"  · 브라우저 실패: {type(e).__name__}")
    return None


def html_to_markdownish(html: str) -> str:
    """HTML 의 day 패널들을 프록시 결과와 같은 '[날짜 설명 최고° 최저°](...day=N)' 형태로 정규화."""
    out = []
    for inner in PANEL_RE.findall(html):
        href = ""
        m = re.search(r'day=(\d+)', inner)
        text = TAGS_RE.sub(" ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        # 원본 <a> 의 href 에서 day 를 찾기 위해 패널 전체를 다시 훑는다
        out.append(f"[{text}](x?day={m.group(1) if m else 0})")
    if not out:
        # href 가 <a> 태그 속성에 있는 일반적인 경우
        for m in re.finditer(
            r'<a[^>]*href="([^"]*day=(\d+))"[^>]*class="[^"]*monthly-daypanel[^"]*"[^>]*>(.*?)</a>',
            html,
            re.S | re.I,
        ):
            text = re.sub(r"\s+", " ", TAGS_RE.sub(" ", m.group(3))).strip()
            out.append(f"[{text}](x?day={m.group(2)})")
    return "\n".join(out)


def fetch(url: str) -> str:
    for fn in (try_direct, try_jina, try_playwright):
        content = fn(url)
        if content and DAY_RE.search(content):
            return content
    raise RuntimeError(
        "세 경로 모두 실패했습니다. AccuWeather 가 차단 중이거나 페이지 구조가 바뀌었습니다."
    )


# ---------------------------------------------------------------- 파싱


def parse_month(content: str):
    matches = DAY_RE.findall(content)
    if not matches:
        raise RuntimeError("날짜 항목을 찾지 못했습니다.")

    days = []
    seen_first = False
    for dnum, desc, hi_f, lo_f, _idx in matches:
        dnum = int(dnum)
        desc = re.sub(r"\s+", " ", desc).strip()

        if dnum == 1:
            if seen_first:
                break  # 다음 달 영역
            seen_first = True
        if not seen_first:
            continue  # 이전 달 꼬리

        historical = ("기록" in desc) or ("평균" in desc) or not desc
        days.append(
            {
                "day": dnum,
                "desc": desc or "기록 평균",
                "hi": f_to_c(int(hi_f)),
                "lo": f_to_c(int(lo_f)),
                "historical": historical,
            }
        )

    if not days:
        raise RuntimeError("해당 월의 날짜를 하나도 추출하지 못했습니다.")
    return days


# ---------------------------------------------------------------- 실행


def main():
    out = {
        "location": "홍천군, 강원도",
        "source": "AccuWeather",
        "updatedAt": datetime.now(KST).isoformat(timespec="minutes"),
        "months": [],
    }

    for cfg in MONTHS:
        print(f"가져오는 중: {cfg['key']}")
        content = fetch(cfg["url"])
        days = parse_month(content)
        first_weekday = datetime(cfg["year"], cfg["month"], 1).weekday()  # 월=0
        out["months"].append(
            {
                "key": cfg["key"],
                "year": cfg["year"],
                "month": cfg["month"],
                "url": cfg["url"],
                "leadingBlanks": (first_weekday + 1) % 7,  # 일요일 시작 달력
                "days": days,
            }
        )
        print(f"  → {len(days)}일 수집")

    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print("data.json 저장 완료")


if __name__ == "__main__":
    main()
