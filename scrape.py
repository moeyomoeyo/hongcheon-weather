#!/usr/bin/env python3
"""
홍천군 10월·11월 날씨 데이터를 Open-Meteo 에서 받아 data.json 으로 저장한다.

- 예보 범위(오늘부터 16일) 안의 날짜 → 실제 예보
- 그 밖의 날짜 → 과거 10년(2015~2025) 같은 날짜의 평균값

Open-Meteo 는 무료 공개 API 로 키가 필요 없고 접속 차단도 없다.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))

# 홍천군 좌표
LAT, LON = 37.6971, 127.8889

TARGET_MONTHS = [(2026, 10), (2026, 11)]

# 평년값 계산에 쓸 과거 연도 범위
HIST_START, HIST_END = 2015, 2025

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# WMO weather code → 한국어
WMO = {
    0: "맑음", 1: "대체로 맑음", 2: "약간 흐림", 3: "흐림",
    45: "안개", 48: "짙은 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    56: "언 이슬비", 57: "강한 언 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    66: "언 비", 67: "강한 언 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈", 77: "싸락눈",
    80: "소나기", 81: "소나기", 82: "강한 소나기",
    85: "눈 소나기", 86: "강한 눈 소나기",
    95: "뇌우", 96: "우박 동반 뇌우", 99: "강한 우박 동반 뇌우",
}


def get_json(url, params):
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_forecast():
    """오늘부터 16일치 예보. {(month, day): {...}} 로 반환."""
    data = get_json(
        FORECAST_URL,
        {
            "latitude": LAT,
            "longitude": LON,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "Asia/Seoul",
            "forecast_days": 16,
        },
    )
    daily = data["daily"]
    out = {}
    for i, iso in enumerate(daily["time"]):
        d = date.fromisoformat(iso)
        code = daily["weather_code"][i]
        hi = daily["temperature_2m_max"][i]
        lo = daily["temperature_2m_min"][i]
        pop = daily.get("precipitation_probability_max", [None] * 99)[i]
        if hi is None or lo is None:
            continue
        out[(d.year, d.month, d.day)] = {
            "desc": WMO.get(code, "—"),
            "hi": round(hi),
            "lo": round(lo),
            "pop": pop,
            "historical": False,
        }
    print(f"예보 {len(out)}일 수신")
    return out


def fetch_normals():
    """과거 연도들의 10~11월 기록으로 날짜별 평균 계산."""
    data = get_json(
        ARCHIVE_URL,
        {
            "latitude": LAT,
            "longitude": LON,
            "start_date": f"{HIST_START}-10-01",
            "end_date": f"{HIST_END}-11-30",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "Asia/Seoul",
        },
    )
    daily = data["daily"]
    buckets = defaultdict(lambda: {"hi": [], "lo": [], "wet": []})

    for i, iso in enumerate(daily["time"]):
        d = date.fromisoformat(iso)
        if d.month not in (10, 11):
            continue
        hi = daily["temperature_2m_max"][i]
        lo = daily["temperature_2m_min"][i]
        pr = daily["precipitation_sum"][i]
        if hi is None or lo is None:
            continue
        b = buckets[(d.month, d.day)]
        b["hi"].append(hi)
        b["lo"].append(lo)
        if pr is not None:
            b["wet"].append(1 if pr >= 1.0 else 0)

    out = {}
    for key, b in buckets.items():
        wet_rate = round(100 * sum(b["wet"]) / len(b["wet"])) if b["wet"] else None
        out[key] = {
            "desc": "평년값",
            "hi": round(sum(b["hi"]) / len(b["hi"])),
            "lo": round(sum(b["lo"]) / len(b["lo"])),
            "pop": wet_rate,
            "historical": True,
        }
    print(f"평년값 {len(out)}일 계산 ({HIST_START}~{HIST_END})")
    return out


def days_in_month(year, month):
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - date(year, month, 1)).days


def main():
    forecast = fetch_forecast()
    normals = fetch_normals()

    out = {
        "location": "홍천군, 강원도",
        "source": "Open-Meteo (예보 16일 + 2015~2025 평년값)",
        "updatedAt": datetime.now(KST).isoformat(timespec="minutes"),
        "months": [],
    }

    for year, month in TARGET_MONTHS:
        days = []
        for dnum in range(1, days_in_month(year, month) + 1):
            rec = forecast.get((year, month, dnum)) or normals.get((month, dnum))
            if rec is None:
                continue
            days.append({"day": dnum, **rec})

        first_weekday = date(year, month, 1).weekday()  # 월=0
        out["months"].append(
            {
                "key": f"{year}-{month:02d}",
                "year": year,
                "month": month,
                "leadingBlanks": (first_weekday + 1) % 7,  # 일요일 시작 달력
                "days": days,
            }
        )
        real = sum(1 for d in days if not d["historical"])
        print(f"{year}-{month:02d}: {len(days)}일 (실제 예보 {real}일)")

    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print("data.json 저장 완료")


if __name__ == "__main__":
    main()
