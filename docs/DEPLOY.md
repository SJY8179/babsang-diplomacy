# 배포

두 가지 방법이 있습니다. 포트폴리오에 계속 열어 둘 링크라면 **A. Render 공개 데모**를 쓰세요.

| | A. Render 공개 데모 | B. 내 컴퓨터 + 임시 터널 |
|---|---|---|
| 주소 | 고정 (`https://babsang-diplomacy.onrender.com` 형태) | 켤 때마다 바뀜 (`*.trycloudflare.com`) |
| 켜져 있는 시간 | 항상 (무료 플랜은 15분 동안 접속이 없으면 잠들고, 다음 접속 때 깨어나는 데 약 1분) | 내 컴퓨터와 터미널이 켜져 있는 동안만 |
| 실제 사장님께 요청 | **불가능** (`PUBLIC_DEMO=1`로 코드에서 잠김) | 설정에 따라 가능 — 공개 주소로 들어온 요청은 차단 |
| 용도 | 포트폴리오 · 공유 | 해커톤 시연 · 실매장 테스트 |

---

## A. Render 공개 데모 (권장)

저장소에 `render.yaml`이 들어 있어서 클릭 몇 번이면 됩니다.

1. GitHub에 이 저장소를 올립니다.
2. [render.com](https://render.com)에 GitHub 계정으로 가입합니다.
3. 대시보드에서 **New → Blueprint**를 누르고 이 저장소를 고릅니다.
4. Render가 `render.yaml`을 읽어 설정을 보여 줍니다. `sync: false`로 표시된 두 값은 직접 넣습니다.
   - `YUMI_API_KEY`: 비워 두세요. 공개 데모는 데모 데이터(`YUMI_MODE=mock`)로 충분합니다.
   - `PUBLIC_BASE_URL`: 처음엔 비워 두고, 배포가 끝난 뒤 받은 주소를 넣습니다.
5. **Apply**를 누르면 빌드와 배포가 시작됩니다(2~4분).
6. 배포가 끝나면 서비스 화면 위쪽의 주소(`https://….onrender.com`)를 복사합니다.
7. **Environment** 탭에서 `PUBLIC_BASE_URL`에 그 주소를 넣고 저장합니다. 자동으로 다시 배포되고, 참석자 공유 링크가 이 주소로 만들어집니다.
8. 주소를 열어 오른쪽 위에 **"공개 데모 · 실제 요청 없음"**이 보이면 끝입니다.

이후에는 `main` 브랜치에 push할 때마다 자동으로 다시 배포됩니다.

### 공개 데모에서 달라지는 것

- 문의·예약은 `.env`나 대시보드에 무엇을 적어도 시뮬레이션으로만 동작합니다.
- 실매장 테스트 메뉴와 API 문서(`/docs`)가 사라집니다.
- 같은 사람이 짧은 시간에 너무 많이 요청하면 잠시 막힙니다(후보 찾기 분당 12회 등).
- 무료 플랜은 디스크가 유지되지 않아, 다시 시작하면 데모 데이터가 처음 상태로 돌아갑니다. 공개 데모에서는 오히려 장점입니다.

### 실제 Hey Yumi 검색을 공개 데모에 쓰려면

`YUMI_MODE=rest`와 `YUMI_API_KEY`를 대시보드에서 넣으면 검색은 실제 데이터로 바뀝니다. 다만 방문자가 누를 때마다 **내 키의 사용량이 줄어든다**는 점을 알고 쓰세요. 요청 수 제한이 걸려 있지만, 포트폴리오용이라면 데모 데이터로 두는 쪽을 권합니다.

---

## B. 내 컴퓨터 + 임시 터널 (시연용)

```bash
# 터미널 1 — 서버
uvicorn app.main:app --port 8000

# 터미널 2 — 공개 주소 (macOS Apple Silicon 기준)
curl -L -o cf.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz
tar xzf cf.tgz && chmod +x cloudflared
./cloudflared tunnel --url http://localhost:8000

# 터미널 3 — 맥이 잠들지 않게
caffeinate -d
```

- 나온 `https://….trycloudflare.com` 주소를 공유합니다.
- 터널로 들어온 요청은 실제 요청이 나갈 수 있는 동작(문의 · 예약 · 실매장 테스트)을 할 수 없습니다(403).
- 그래도 터널을 여는 동안에는 `YUMI_ACTIONS=simulate`로 두는 것을 원칙으로 합니다. 실매장 테스트는 터널을 끄고 하세요.
- 끝나면 터널 창에서 `Ctrl + C`를 누르면 주소가 바로 사라집니다.
