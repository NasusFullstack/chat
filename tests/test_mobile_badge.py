"""모바일로 접속한 사람이 **춥채팅 + 폰**으로 보이는가.

## 왜 이걸 묶어서 보나
모바일 앱이 "나는 ChupChat Mobile 이다"라고 답하고, PC 앱이 그 글자를 보고 판단한다.
양쪽 중 하나만 바뀌면 조용히 어긋난다 - 폰에서 접속했는데 PC에서는 그냥 춥채팅으로
보이거나, 아예 '모르는 프로그램'이 된다. 그래서 **두 쪽을 한 검사에서 같이 본다.**

## 여기서 찾은 진짜 버그
`MOBILE_TOKENS` 정규식에 낱말 경계(`\\b`) 대신 **백스페이스 문자(0x08)**가 박혀 있었다.
raw 문자열이 아닌 곳에 `\\b`를 쓰면 그렇게 된다. 그래서 `mobile` 과 `ios` 가 든 응답을
아무것도 못 잡고 있었다(아이폰 클라이언트가 폰으로 안 보였다). `BOT_TOKENS` 도 같은
상태라 "~bot" 판별도 깨져 있었다.

소스에 제어문자가 또 섞이지 않는지도 여기서 같이 본다.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, REPO)

from gui.client_badges import kind_for, resolve_spec, short_label  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


# ---------- 1) 모바일 앱이 뭐라고 답하는가 ----------
dart = io.open(os.path.join(REPO, "mobile/lib/core/irc_protocol.dart"),
               encoding="utf-8").read()
found = re.search(r"'(ChupChat Mobile [^']*)'", dart)
check("모바일 앱이 자기 이름을 밝힌다", found is not None, dart[-400:])

if found:
    # 실제로 보낼 글자(앱 버전이 들어간 모양)로 만들어 본다
    sample = found.group(1).replace(r"$appVersion", "2.6.4")
    check(f"답하는 글자({sample[:46]}...)", "ChupChat" in sample and "Mobile" in sample)

    # ---------- 2) PC가 그걸 어떻게 보는가 ----------
    spec = resolve_spec(sample, "몽키")
    check(f"춥채팅으로 알아본다({spec.label if spec else None})",
          spec is not None and spec.key == "chupchat", spec.key if spec else None)
    check(f"폰 표시도 같이 붙는다({kind_for(sample, '몽키')!r})",
          kind_for(sample, "몽키") == "phone", kind_for(sample, "몽키"))
    check(f"툴팁은 춥채팅({short_label(sample, '몽키')})",
          short_label(sample, "몽키") == "춥채팅", short_label(sample, "몽키"))

# ---------- 3) PC판은 폰 표시가 붙으면 안 된다 ----------
pc = "ChupChat 2.6.4 - https://github.com/NasusFullstack/chat"
check(f"PC판에는 폰 표시가 없다({kind_for(pc, '몽키')!r})", kind_for(pc, "몽키") == "")
check("PC판도 춥채팅으로 알아본다", resolve_spec(pc, "몽키").key == "chupchat")

# ---------- 4) 낱말 경계가 살아 있는가 ----------
# 백스페이스로 깨져 있던 자리들. 다시 깨지면 여기서 잡힌다
check(f"'mobile'이 든 응답을 잡는다({kind_for('Something Mobile 1.0', 'x')!r})",
      kind_for("Something Mobile 1.0", "x") == "phone")
check(f"'iOS'가 든 응답을 잡는다({kind_for('Palaver 2.0 (iOS 17.2)', 'x')!r})",
      kind_for("Palaver 2.0 (iOS 17.2)", "x") == "phone")
check(f"'bot'이 든 응답을 잡는다({kind_for('SomeBot 1.0', 'x')!r})",
      kind_for("SomeBot 1.0", "x") == "robot")

# 낱말 경계가 없으면 엉뚱한 것까지 잡는다 - 그것도 확인
check(f"'ios'가 낱말 안에 있으면 안 잡는다({kind_for('iosomething 1.0', 'x')!r})",
      kind_for("iosomething 1.0", "x") == "")
check(f"'bot'이 낱말 안에 있으면 안 잡는다({kind_for('robotics-client 1.0', 'x')!r})",
      kind_for("robotics-client 1.0", "x") == "")

# ---------- 5) 소스에 제어문자가 섞이지 않았는가 ----------
# 이 버그는 \b 를 raw 가 아닌 자리에 써서 백스페이스가 된 것이었다.
# 같은 일이 또 생기면 정규식이 조용히 다른 뜻이 된다
suspects = []
for root, dirs, files in os.walk(REPO):
    dirs[:] = [d for d in dirs
               if d not in {".git", "__pycache__", "build", "dist", ".dart_tool",
                            "node_modules", ".idea"}]
    for name in files:
        if not name.endswith((".py", ".dart", ".kt")):
            continue
        path = os.path.join(root, name)
        data = io.open(path, "rb").read()
        # 탭·개행·캐리지리턴은 정상. CTCP 구분자(0x01)는 이 앱이 실제로 쓰는 글자다
        bad = {b for b in data if b < 32 and b not in (1, 9, 10, 13)}
        if bad:
            suspects.append((os.path.relpath(path, REPO), sorted(hex(b) for b in bad)))

check(f"소스에 이상한 제어문자가 없다({len(suspects)}개 파일)", not suspects, suspects[:3])

print("=== 검증 결과 (모바일 참여자 표시) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print(f"\n검사 {len(checks)}개")
print("전체 통과:", all_ok)
sys.exit(0 if all_ok else 1)
