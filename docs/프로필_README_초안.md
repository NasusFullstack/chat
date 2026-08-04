# 프로필 README 초안 (붙여넣기용)

GitHub 프로필 맨 위에 뜨는 소개글이다. 만드는 법:

1. 새 저장소를 만든다. 이름은 **계정명과 똑같이** — `NasusFullstack`
2. Public + "Add a README file" 체크
3. 그 `README.md`에 아래 내용을 붙여넣는다

같이 채우면 좋은 프로필 칸(설정 → Public profile):
- **Bio**: `Python으로 데스크톱 앱 만듭니다 · PySide6 / asyncio`
- **Website**: `https://github.com/NasusFullstack/chat/releases/latest`

---

## 초안 (여기서부터 복사)

```markdown
### 안녕하세요 👋

Python으로 데스크톱 앱을 만듭니다. 실제로 쓰이는 걸 만들고, 왜 그렇게 만들었는지 남겨두는 걸 좋아합니다.

#### 만든 것

**[춥채팅](https://github.com/NasusFullstack/chat)** — Windows 데스크톱 채팅 프로그램
직접 만든 JSON 프로토콜과 실제 IRC 서버(RFC 1459)를 같은 화면에서 지원합니다.
GitHub Releases로 자동 업데이트되고, 연결이 끊기면 스스로 복구합니다.

- 도메인 로직을 화면에서 분리해(헥사고날) 코어 테스트는 창 없이 순수 파이썬으로 돕니다
- 회귀 테스트 48개가 실제 서버를 띄워서 돌고, 화면 작업은 픽셀 단위로 전후를 비교합니다
- 겪은 사고의 원인과 재발 방지책을 문서로 남깁니다

`Python` `PySide6(Qt6)` `asyncio` `TLS` `IRC` `PyInstaller` `GitHub Actions`
```

---

## 고를 수 있는 Bio 문구

| 성격 | 문구 |
|---|---|
| 담백 | `Python으로 데스크톱 앱 만듭니다 · PySide6 / asyncio` |
| 프로젝트 강조 | `개인 프로젝트로 채팅 프로그램 만드는 중 · Python, Qt, IRC` |
| 영어 | `Building desktop apps with Python & Qt` |

"열정적인", "성장하는" 같은 말은 정보가 없어서 오히려 비어 보인다. 만든 것과 쓰는 기술을
쓰는 편이 낫다.

---

## 저장소 About 칸 (웹에서 ⚙️ 눌러 입력)

- **Description**
  `Python + PySide6로 만든 윈도우 데스크톱 채팅 프로그램 (자체 서버 + 실제 IRC 지원)`
- **Website**
  `https://github.com/NasusFullstack/chat/releases/latest`
- **Topics**
  `python` `pyside6` `qt` `desktop-app` `chat` `irc` `asyncio` `windows`
