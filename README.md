# 홍천 날씨 자동 갱신 페이지

AccuWeather 홍천군 월별 예보(2026년 10월·11월)를 **매일 오전 8시(KST)** 자동으로 가져와
공개 링크 하나로 보여주는 정적 페이지. 서버 없이 GitHub Actions + GitHub Pages 만 사용.

## 구성

| 파일 | 역할 |
|---|---|
| `scrape.py` | AccuWeather 월별 페이지에서 날짜·날씨·최고/최저 추출 → `data.json` (°F→°C 환산) |
| `.github/workflows/update.yml` | 매일 23:00 UTC(=08:00 KST) 실행 → 커밋 → Pages 배포 |
| `index.html` | `data.json` 을 읽어 달력으로 렌더링 |

## 설치 (10분)

1. GitHub 에서 새 저장소를 만든다 (public 이어야 Pages 가 무료).
2. 이 폴더의 파일 4개를 그대로 업로드한다. 폴더 구조 유지 필수:
   ```
   index.html
   scrape.py
   README.md
   .github/workflows/update.yml
   ```
3. 저장소 **Settings → Pages → Source** 를 `GitHub Actions` 로 변경.
4. **Actions** 탭 → "홍천 날씨 매일 업데이트" → `Run workflow` 로 첫 실행.
5. 완료되면 `https://<아이디>.github.io/<저장소이름>/` 이 내 링크. 휴대폰 홈 화면에 추가해두면 앱처럼 쓸 수 있다.

이후로는 손댈 것 없이 매일 아침 알아서 갱신된다.

## 알아둘 점

- **GitHub Actions 의 cron 은 정시 보장이 아니다.** 부하에 따라 5~30분 정도 늦게 도는 일이 흔하다.
  아침에 확인하는 용도라면 문제없지만, 정확히 8시 00분이 필요하면 `cron: "30 22 * * *"` 처럼 앞당겨 둘 것.
- **AccuWeather 가 봇 요청을 막을 수 있다.** `scrape.py` 는 먼저 일반 요청을 시도하고,
  막히면 Playwright(실제 브라우저)로 재시도한다. 그래도 실패하면 Actions 탭에 빨간 표시가 뜨니 로그를 보면 된다.
- **AccuWeather 가 페이지 구조를 바꾸면 파싱이 깨진다.** 그때는 `scrape.py` 의
  `parse_month()` 만 고치면 된다. 클래스 이름 대신 텍스트 기반으로 뽑도록 짜둬서 어지간한 변경에는 견딘다.
- 12월도 보고 싶으면 `scrape.py` 상단 `MONTHS` 리스트에 december URL 을 한 줄 추가.
- 개인 용도 하루 1회 조회 수준이므로 부담스러운 트래픽은 아니지만, 실행 주기를 더 촘촘하게 올리지는 말 것.
