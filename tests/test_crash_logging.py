"""앱이 "멈추더니 꺼지는" 경우에 기록이 남는가.

실제 신고(2026-08-13, Gil_note): 노트북에서 앱이 잠깐 멈췄다가 그대로 꺼진다. 이런
종류는 파이썬 예외가 아니라 프로세스가 통째로 죽는 것이라, 예외 기록 장치(excepthook)
로는 **한 줄도 안 남는다.** 원인을 찾을 단서가 아예 없다는 뜻이다.

그래서 두 가지를 남기게 했고, 여기서 그 둘이 실제로 작동하는지 확인한다:
1. 프로세스가 죽는 순간 - faulthandler가 그때의 파이썬 스택을 파일에 찍는다
2. 화면이 멈춘 채로 시간이 지날 때 - 감시 장치가 "지금 어디에 있는지"를 찍는다

기록 장치는 "있다고 믿는 것"이 가장 위험하다. 그래서 흉내가 아니라 **진짜로 죽여보고**
확인한다(자식 프로세스에서).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_sys.path.insert(0, _REPO)

import shutil
import subprocess
import tempfile

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def run_child(body: str, data_dir: str) -> str:
    """자식 프로세스에서 돌리고, 남은 기록을 돌려준다."""
    shutil.rmtree(data_dir, ignore_errors=True)
    _os.makedirs(data_dir, exist_ok=True)
    script = _os.path.join(data_dir, "child.py")
    with open(script, "w", encoding="utf-8") as fp:
        fp.write("import sys\nsys.path.insert(0, %r)\n" % _REPO)
        fp.write("import error_log\nerror_log.install()\n")
        fp.write(body)
    env = dict(_os.environ, CHUPCHAT_DATA_DIR=data_dir, PYTHONIOENCODING="utf-8")
    subprocess.run([_sys.executable, script], env=env, capture_output=True, timeout=60)
    log = _os.path.join(data_dir, "friendchat_error.log")
    if not _os.path.exists(log):
        return ""
    with open(log, encoding="utf-8") as fp:
        return fp.read()


base = _os.path.join(tempfile.gettempdir(), "chup_crashlog_test")

# ---------- 1) 프로세스가 통째로 죽는 경우 ----------
crash_log = run_child("import faulthandler\nfaulthandler._sigsegv()\n",
                      _os.path.join(base, "crash"))
check("죽는 순간에도 기록 파일이 생긴다", bool(crash_log))
check("무엇 때문에 죽었는지 적힌다", "Fatal Python error" in crash_log, crash_log[:200])
check("어디서 죽었는지(스택)도 적힌다", "most recent call first" in crash_log,
      crash_log[:200])

# ---------- 2) 화면이 멈춘 경우 ----------
freeze_body = """
import time
error_log.FREEZE_SECONDS = 2
error_log.arm_freeze_watchdog()


def 오래_걸리는_일():
    end = time.time() + 5
    while time.time() < end:
        pass


오래_걸리는_일()
"""
freeze_log = run_child(freeze_body, _os.path.join(base, "freeze"))
check("멈춰 있으면 그 사실이 기록된다", "Timeout" in freeze_log, freeze_log[:200])
# 한글 이름은 백슬래시 uXXXX 형태로 찍히므로(faulthandler는 ASCII로만 쓴다)
# 글자 자체를 찾지 말고, **어느 파일 몇 번째 줄에서 멈췄는지**가 남았는지를 본다
frame_lines = [line for line in freeze_log.splitlines()
               if line.strip().startswith('File "') and " line " in line]
check(f"멈춘 자리(파일/줄)까지 적힌다({len(frame_lines)}줄)", bool(frame_lines),
      freeze_log[:300])

# ---------- 3) 멀쩡히 돌 때는 안 찍혀야 한다 ----------
# 살아 있는데도 계속 기록되면 진짜 멈춤을 못 알아본다
quiet_body = """
import time
error_log.FREEZE_SECONDS = 2
for _ in range(6):
    error_log.arm_freeze_watchdog()   # 화면이 살아 있으면 이렇게 갱신된다
    time.sleep(0.5)
error_log.stop_freeze_watchdog()
"""
quiet_log = run_child(quiet_body, _os.path.join(base, "quiet"))
check("살아 있는 동안에는 멈춤으로 오해하지 않는다", "Timeout" not in quiet_log,
      quiet_log[:200])

shutil.rmtree(base, ignore_errors=True)

print("=== 검증 결과 (멈춤/크래시 기록) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
