"""PC와 모바일이 따로 놀지 않게 지키는 검사.

## 왜 필요한가
앱이 둘(PC / 모바일)이 되면 **같은 기능을 서로 다른 시점에 갖게 되는 순간** 사고가 난다.
PC에서만 되는 걸 모바일 사용자가 못 쓰는 건 괜찮지만, 그 사실을 아무도 모르는 게 문제다.
여기서 지키는 것은 셋이다:

1. **버전 숫자가 한 곳에서 나온다** - `version.py`의 APP_VERSION이 출처다.
   모바일(pubspec.yaml)이 생기면 그 값과 같아야 한다
2. **변경 내역이 비어 있지 않다** - 버전을 올리고 CHANGELOG를 안 쓴 적이 실제로 있다
   (v2.4.1). 사용자는 커밋 메시지를 못 보므로 그러면 뭐가 바뀌었는지 알 길이 없다
3. **모바일이 아직 없으면 조용히 넘어간다** - 만들기 전부터 실패하면 안 된다

모바일이 생기기 전에도 1·2는 돈다.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import version  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


APP_VERSION = version.APP_VERSION
MOBILE_PUBSPEC = os.path.join(REPO, "mobile", "pubspec.yaml")


def read(path):
    with open(path, encoding="utf-8") as fp:
        return fp.read()


# ---------- 1) 버전 모양 ----------
check(f"버전이 숫자 셋으로 되어 있다({APP_VERSION})",
      re.match(r"^\d+\.\d+\.\d+(-beta\.\d+)?$", APP_VERSION) is not None, APP_VERSION)
check(f"베타 여부를 버전에서 판단한다(IS_BETA={version.IS_BETA})",
      version.IS_BETA == ("beta" in APP_VERSION.lower()))

today_ok = re.match(r"^\d{4}-\d{2}-\d{2}$", version.RELEASE_DATE) is not None
check(f"릴리즈 날짜가 적혀 있다({version.RELEASE_DATE})", today_ok, version.RELEASE_DATE)

# ---------- 2) 변경 내역 ----------
changelog = read(os.path.join(REPO, "CHANGELOG.md"))
check(f"CHANGELOG에 이번 버전 항목이 있다(## v{APP_VERSION})",
      f"## v{APP_VERSION}" in changelog,
      changelog[:200])

# 항목만 있고 내용이 비어 있으면 없는 것과 같다
section = changelog.split(f"## v{APP_VERSION}", 1)[-1].split("\n## ", 1)[0]
check(f"그 항목에 내용이 있다({len(section.strip().splitlines())}줄)",
      len([line for line in section.splitlines() if line.strip().startswith("-")]) >= 1,
      section[:200])

# ---------- 3) 모바일과 같은 버전인가 ----------
if not os.path.exists(MOBILE_PUBSPEC):
    check("모바일이 아직 없어 버전 대조는 건너뜀(만들면 저절로 켜진다)", True)
else:
    pubspec = read(MOBILE_PUBSPEC)
    found = re.search(r"^version:\s*([0-9][^\s+]*)", pubspec, re.M)
    check("모바일 pubspec.yaml에 version이 적혀 있다", found is not None, pubspec[:200])
    if found:
        mobile_version = found.group(1)
        # Flutter는 '2.6.1+7'처럼 뒤에 빌드번호를 붙일 수 있다. 앞부분만 본다
        check(f"모바일 버전이 PC와 같다(PC {APP_VERSION} / 모바일 {mobile_version})",
              mobile_version == APP_VERSION, (APP_VERSION, mobile_version))

# ---------- 4) PC 빌드가 모바일 때문에 헛돌지 않는가 ----------
workflow = read(os.path.join(REPO, ".github", "workflows", "build-exe.yml"))
check("PC 빌드가 모바일 변경에는 안 돈다(paths-ignore)",
      "mobile/**" in workflow, workflow[:300])

print("=== 검증 결과 (PC·모바일 버전 맞추기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
