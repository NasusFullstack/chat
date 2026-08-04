# 프로필 README 초안 (붙여넣기용)

GitHub 프로필 맨 위에 뜨는 소개글이다. 만드는 법:

1. 새 저장소를 만든다. 이름은 **계정명과 똑같이** — `NasusFullstack`
2. Public + "Add a README file" 체크
3. 그 `README.md`에 아래 내용을 붙여넣는다

같이 채우면 좋은 프로필 칸(설정 → Public profile):
- **Bio**: `IRC 채팅 클라이언트 만듭니다 · Python / PySide6`
- **Website**: `https://github.com/NasusFullstack/chat/releases/latest`

---

## 초안 (여기서부터 복사)

```markdown
### 안녕하세요 👋

Python으로 데스크톱 앱을 만듭니다. 실제로 쓰이는 걸 만들고, 왜 그렇게 만들었는지 남겨두는 걸 좋아합니다.

#### 만든 것

**[춥채팅](https://github.com/NasusFullstack/chat)** — IRC 채팅 GUI 클라이언트 (Windows)
Libera.Chat 같은 표준 IRC 서버에 접속하는 창 프로그램입니다. 터미널 클라이언트와 달리
프로필 아이콘·이모티콘·링크 미리보기를 IRC 위에 얹었고, 자동 업데이트와 끊김 복구가 됩니다.

- 도메인 로직을 화면에서 분리해(헥사고날) 코어 테스트는 창 없이 순수 파이썬으로 돕니다
- 회귀 테스트 48개가 실제 서버를 띄워서 돌고, 화면 작업은 픽셀 단위로 전후를 비교합니다
- 겪은 사고의 원인과 재발 방지책을 문서로 남깁니다

`Python` `PySide6 (Qt6)` `IRC (RFC 1459)` `asyncio` `TLS` `PyInstaller` `GitHub Actions`
```

---

## 고를 수 있는 Bio 문구

| 성격 | 문구 |
|---|---|
| 담백 | `IRC 채팅 클라이언트 만듭니다 · Python / PySide6` |
| 넓게 | `Python으로 데스크톱 앱 만듭니다 · Qt / asyncio` |
| 영어 | `Building an IRC chat client with Python & Qt` |

"열정적인", "성장하는" 같은 말은 정보가 없어서 오히려 비어 보인다. 만든 것과 쓰는 기술을
쓰는 편이 낫다.

---

## 저장소 About 칸 (웹에서 ⚙️ 눌러 입력)

- **Description**
  `IRC 채팅 GUI 클라이언트 — Python + PySide6로 만든 윈도우 데스크톱 앱`
- **Website**
  `https://github.com/NasusFullstack/chat/releases/latest`
- **Topics**
  `irc` `irc-client` `chat` `python` `pyside6` `qt` `desktop-app` `windows`
