"""업데이트 배치 스크립트 구조 검증 (프로그램을 실행하지 않으므로 창이 뜨지 않음).

실제 실행 검증은 콘솔 창을 띄울 수밖에 없어서 기본 테스트에서 뺐다. 대신 과거에 실제로
사고가 났던 지점들이 스크립트에 그대로 남아 있는지를 구조로 확인한다.

실측으로 확인한 사실(둘 다 참이라 한쪽만 보고 고치면 다른 쪽이 깨짐):
- BOM 없이 저장 -> cmd가 한글 경로를 cp949로 잘못 읽어 깨짐 ('占�' is not recognized)
- BOM 있음      -> 한글은 살지만 cmd가 BOM을 첫 명령의 일부로 읽어 첫 줄이 깨짐
그래서 BOM은 유지하고, 첫 줄은 깨져도 되는 더미로 두고 @echo off는 둘째 줄에 둔다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import os
import shutil
import sys

sys.path.insert(0, _REPO)
import updater

SP = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(SP, "batch_struct")
fails = []


def check(label, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + label + ("" if cond else f"  <- {extra}"))
    if not cond:
        fails.append(label)


KOREAN_EXE = r"C:\Users\me\AppData\Local\Programs\춥채팅\FriendChat_GUI.exe"
script = updater.build_installer_batch(r"C:\tmp\FriendChat_Setup.exe", KOREAN_EXE, 4321)
lines = script.splitlines()

print("[1] BOM에 희생될 첫 줄이 더미인가")
check("첫 줄이 rem(깨져도 무해)", lines[0].lstrip("@").lower().startswith("rem"), lines[0])
check("@echo off는 둘째 줄", lines[1].strip() == "@echo off", lines[1])
print("  -> 첫 줄에 @echo off를 두면 echo가 안 꺼져서 모든 명령이 화면에 찍힘")

print("\n[2] 한글 경로 처리")
check("chcp 65001 있음", "chcp 65001" in script)
check("설치 경로가 그대로 들어감", KOREAN_EXE in script)
non_ascii = [ln for ln in lines if not ln.isascii() and KOREAN_EXE not in ln]
check("경로 외에는 비ASCII를 안 넣음(주석은 영어)", not non_ascii, non_ascii[:2])

print("\n[3] 인스톨러를 기다리는가")
inst = [ln for ln in lines if "FriendChat_Setup.exe" in ln
        and not ln.strip().startswith(("rem", "del"))]
check("인스톨러 줄이 있음", len(inst) == 1, inst)
check("직접 호출함(=cmd가 끝날 때까지 기다림)", inst and inst[0].strip().startswith('"'), inst)
check("start를 안 씀(start /wait는 콘솔이 없어 멈추고, start만 쓰면 안 기다림)",
      inst and not inst[0].strip().lower().startswith("start"), inst)

print("\n[4] 과거 사고 지점이 남아 있는가")
check("인스톨러 뒤 안정화 대기가 있음(지웠더니 앱이 안 켜졌음)",
      "ping -n 4" in script, "대기가 사라짐")
check("timeout /t를 안 씀(콘솔 없는 환경에서 즉시 실패)", "timeout /t" not in script)
check("앱 실행에 재시도가 있음", "goto launch" in script and "RETRY" in script)
check("재시도가 무한이 아님", "LSS 10" in script or "LSS 5" in script, "상한 없음")
check("실행 뒤 인스톨러/자기 자신을 지움",
      'del "' in script and "%~f0" in script)

print("\n[5] 파일 저장 방식")
os.makedirs(WORK, exist_ok=True)
p = os.path.join(WORK, "t.bat")
updater._write_batch(p, script)
raw = open(p, "rb").read()
check("BOM으로 저장됨(한글 경로 보존에 필요)", raw[:3] == b"\xef\xbb\xbf", raw[:3])
check("줄바꿈이 CRLF", b"\r\n" in raw)
check("한글 경로가 UTF-8로 정확히 들어감",
      KOREAN_EXE.encode("utf-8") in raw, "인코딩 깨짐")
shutil.rmtree(WORK, ignore_errors=True)

print()
if fails:
    print(f"실패 {len(fails)}건: {fails}")
    sys.exit(1)
print("전부 통과")
