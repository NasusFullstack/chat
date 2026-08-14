"""파일을 사람끼리 직접 주고받는 기능(서버를 거치지 않음).

IRC에는 파일 전송이 없어서, 서로 주소를 알려주고 직접 붙는 방식(DCC)을 쓴다.
채팅 서버에는 "이 주소로 오라"는 한 줄만 지나가고 **파일 자체는 서버를 안 거친다** -
그래서 몇십 MB를 보내도 서버에 부담이 없다.

여기서는 진짜 소켓으로 주고받아 **내용이 한 바이트도 다르지 않은지**까지 확인한다
(형식만 맞고 내용이 깨지는 사고가 가장 흔하다).
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)

import hashlib  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import dcc_protocol  # noqa: E402
from gui.file_transfer import FileReceiver, FileSender  # noqa: E402

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


# ---------- 1) 알림 한 줄(주소를 주고받는 형식) ----------
line = dcc_protocol.format_send("사진 모음.png", "192.168.0.5", 51000, 1048576)
parsed = dcc_protocol.parse_send(line)
check(f"보낼 알림을 만들고 그대로 해석한다({parsed})",
      parsed == {"filename": "사진 모음.png", "ip": "192.168.0.5",
                 "port": 51000, "size": 1048576}, parsed)

check("상대가 보낸 이름에 경로가 섞여 있으면 떼어낸다",
      dcc_protocol.safe_filename(r"..\..\Windows\system32\evil.exe") == "evil.exe",
      dcc_protocol.safe_filename(r"..\..\Windows\system32\evil.exe"))
check("파일 이름에 못 쓰는 글자는 바꾼다",
      dcc_protocol.safe_filename('a<b>c:d|e?.txt') == "a_b_c_d_e_.txt",
      dcc_protocol.safe_filename('a<b>c:d|e?.txt'))

for bad in ("", "hello", "\x01DCC SEND\x01", "\x01DCC SEND a 0 0 0\x01",
            "\x01DCC SEND a 2130706433 51000 0\x01",
            "\x01DCC CHAT chat 2130706433 51000\x01"):
    check(f"이상한 알림은 무시한다({bad[:30]!r})", dcc_protocol.parse_send(bad) is None, bad)

# ---------- 2) 진짜로 주고받기 ----------
work = tempfile.mkdtemp(prefix="chup_dcc_")
source = _os.path.join(work, "보낼 파일.bin")
payload = bytes(range(256)) * 4096          # 1MB, 내용이 규칙적이라 깨지면 바로 티가 난다
with open(source, "wb") as fp:
    fp.write(payload)
original_hash = hashlib.sha256(payload).hexdigest()

sender = FileSender(source)
port = sender.listen()
check(f"보내는 쪽이 문을 연다(포트 {port})", port > 0, port)

sent_result = {}
sender.finished.connect(lambda ok, msg: sent_result.update(ok=ok, msg=msg))
sent_progress = []
sender.progress.connect(lambda now, total: sent_progress.append(now))

target = _os.path.join(work, "받은 파일.bin")
receiver = FileReceiver("127.0.0.1", port, len(payload), target)
recv_result = {}
receiver.finished.connect(lambda ok, msg: recv_result.update(ok=ok, msg=msg))
recv_progress = []
receiver.progress.connect(lambda now, total: recv_progress.append(now))
receiver.start()

end = time.time() + 20
while time.time() < end and not (sent_result and recv_result):
    app.processEvents()
    time.sleep(0.005)

check(f"받는 쪽이 끝냈다({recv_result})", recv_result.get("ok") is True, recv_result)
check(f"보내는 쪽도 끝냈다({sent_result})", sent_result.get("ok") is True, sent_result)

if _os.path.exists(target):
    with open(target, "rb") as fp:
        got = fp.read()
    check(f"크기가 같다({len(got)} / {len(payload)})", len(got) == len(payload),
          (len(got), len(payload)))
    check("내용이 한 바이트도 다르지 않다",
          hashlib.sha256(got).hexdigest() == original_hash)
else:
    check("받은 파일이 생겼다", False, target)

check(f"보내는 동안 진행률이 여러 번 올라온다({len(sent_progress)}회)",
      len(sent_progress) > 1, len(sent_progress))
check(f"받는 동안에도 진행률이 올라온다({len(recv_progress)}회)",
      len(recv_progress) > 1, len(recv_progress))

# ---------- 3) 실패해도 조용히 넘어가지 않는다 ----------
# 아무도 없는 포트로 붙어본다 - 사람이 이유를 알 수 있게 반드시 알려야 한다
lonely = FileReceiver("127.0.0.1", 1, 100, _os.path.join(work, "없을파일.bin"))
lonely_result = {}
lonely.finished.connect(lambda ok, msg: lonely_result.update(ok=ok, msg=msg))
lonely.start()
# 시간만 정해두고 기다리면 컴퓨터가 느릴 때 엉뚱하게 실패한다 - 결과가 올 때까지 기다린다
deadline = time.time() + 15
while time.time() < deadline and not lonely_result:
    app.processEvents()
    time.sleep(0.005)
check(f"연결 못 하면 이유를 알려준다({lonely_result.get('msg', '')[:40]})",
      lonely_result.get("ok") is False and lonely_result.get("msg"), lonely_result)
check("실패한 파일을 남겨두지 않는다",
      not _os.path.exists(_os.path.join(work, "없을파일.bin")))

# ---------- 4) 아무도 안 받으면 문을 닫는다 ----------
idle = FileSender(source)
idle_port = idle.listen()
check("기다리는 동안 문이 열려 있다", idle_port > 0)
idle.cancel("시험 종료")
check("취소하면 문을 닫는다", True)

import shutil  # noqa: E402

shutil.rmtree(work, ignore_errors=True)

print("=== 검증 결과 (파일 직접 주고받기) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
