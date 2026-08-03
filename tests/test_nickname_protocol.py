"""커스텀 프로토콜 닉네임(표시 이름) 동기화 검증 - 순수 소켓, GUI 없이 서버와 직접 JSON 라인 교환.
server.py를 미리 127.0.0.1:17667(평문)/17697(SSL)로 띄워둔 상태에서 실행.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

import json
import socket
import ssl
import time

HOST = "127.0.0.1"
PORT = 17667


def connect():
    s = socket.create_connection((HOST, PORT), timeout=5)
    return s


def send(s, obj):
    s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))


def recv_until(s, predicate, timeout=5):
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s.settimeout(max(0.1, deadline - time.monotonic()))
            chunk = s.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            msg = json.loads(line.decode("utf-8"))
            if predicate(msg):
                return msg
    return None


def drain_all(s, duration=0.5):
    msgs = []
    deadline = time.monotonic() + duration
    buf = b""
    s.settimeout(0.1)
    while time.monotonic() < deadline:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                msgs.append(json.loads(line.decode("utf-8")))
    return msgs


checks = []
suffix = str(int(time.time()))
uidA, uidB, uidC = f"nickA{suffix}", f"nickB{suffix}", f"nickC{suffix}"
channel = f"#nicktest{suffix}"

sA = connect()
sB = connect()

for s, uid in [(sA, uidA), (sB, uidB)]:
    send(s, {"cmd": "register", "id": uid, "pw": "pw1234"})
    recv_until(s, lambda m: m.get("type") == "auth_result")
    send(s, {"cmd": "login", "id": uid, "pw": "pw1234"})
    recv_until(s, lambda m: m.get("type") == "auth_result")

send(sA, {"cmd": "create_channel", "channel": channel, "key": ""})
recv_until(sA, lambda m: m.get("type") == "channel_result")
send(sA, {"cmd": "join", "channel": channel, "key": ""})
recv_until(sA, lambda m: m.get("type") == "channel_result" and m.get("ok"))
drain_all(sA, 0.3)

send(sB, {"cmd": "join", "channel": channel, "key": ""})
recv_until(sB, lambda m: m.get("type") == "channel_result" and m.get("ok"))
drain_all(sA, 0.3)
drain_all(sB, 0.3)

# ---- A가 닉네임 설정 -> B는 브로드캐스트로 받고 A 자신은 못 받음(exclude) ----
send(sA, {"cmd": "set_nickname", "nickname": "에이닉네임"})
gotB = recv_until(sB, lambda m: m.get("type") == "member_nickname" and m.get("user_id") == uidA)
checks.append(("B가 A의 닉네임 변경을 브로드캐스트로 수신", gotB is not None and gotB.get("nickname") == "에이닉네임"))

self_echo = drain_all(sA, 0.4)
checks.append(("A 자신은 본인 닉네임 변경 브로드캐스트를 다시 못 받음(exclude)",
               not any(m.get("type") == "member_nickname" and m.get("user_id") == uidA for m in self_echo)))

# ---- C가 나중에 입장 -> A의 기존 닉네임을 캐치업으로 받음 ----
sC = connect()
send(sC, {"cmd": "register", "id": uidC, "pw": "pw1234"})
recv_until(sC, lambda m: m.get("type") == "auth_result")
send(sC, {"cmd": "login", "id": uidC, "pw": "pw1234"})
recv_until(sC, lambda m: m.get("type") == "auth_result")
send(sC, {"cmd": "join", "channel": channel, "key": ""})
recv_until(sC, lambda m: m.get("type") == "channel_result" and m.get("ok"))
catchup = recv_until(sC, lambda m: m.get("type") == "member_nickname" and m.get("user_id") == uidA, timeout=2)
checks.append(("나중에 입장한 C가 A의 닉네임을 캐치업으로 받음", catchup is not None and catchup.get("nickname") == "에이닉네임"))
drain_all(sA, 0.3)
drain_all(sB, 0.3)

# ---- 닉네임 최대 길이 초과 시 error 응답, 저장 안 됨 ----
send(sB, {"cmd": "set_nickname", "nickname": "가" * 30})
err = recv_until(sB, lambda m: m.get("type") == "error", timeout=2)
checks.append(("닉네임 길이 초과 시 error 응답", err is not None))

# ---- 빈 문자열로 설정 시 초기화(리셋)되고, 다른 사람에게도 nickname=None으로 전파 ----
send(sA, {"cmd": "set_nickname", "nickname": ""})
resetB = recv_until(sB, lambda m: m.get("type") == "member_nickname" and m.get("user_id") == uidA, timeout=2)
checks.append(("빈 문자열로 설정하면 초기화되어 nickname이 비어있게 전파됨",
               resetB is not None and not resetB.get("nickname")))

print("\n=== 검증 결과 (커스텀 프로토콜 닉네임 동기화) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)

for s in (sA, sB, sC):
    s.close()
