"""#pdlab에 잠깐 붙어서 Gil_note에게 무슨 일이 생기는지 보기만 한다(아무 말도 안 함)."""
import socket, time, sys

HOST, PORT, CH = "home.pdlab.kr", 6667, "#pdlab"
NICK = "chupdiag"
DURATION = 240

s = socket.create_connection((HOST, PORT), timeout=10)
s.settimeout(1.0)


def send(line):
    s.sendall((line + "\r\n").encode("utf-8"))


send(f"NICK {NICK}")
send(f"USER {NICK} 0 * :chup diagnose")
buf = b""
start = time.time()
joined = False
while time.time() - start < DURATION:
    try:
        chunk = s.recv(4096)
        if not chunk:
            print("서버가 연결을 끊음"); break
        buf += chunk
    except socket.timeout:
        continue
    while b"\r\n" in buf:
        line, buf = buf.split(b"\r\n", 1)
        text = line.decode("utf-8", "replace")
        if text.startswith("PING"):
            send("PONG " + text.split(" ", 1)[1]); continue
        if " 001 " in text and not joined:
            send(f"JOIN {CH}"); joined = True
            print("[접속됨] 지켜보는 중...", flush=True)
            continue
        low = text.lower()
        if "gil" in low or " quit " in low or " kill " in low or "error" in low:
            stamp = time.strftime("%H:%M:%S")
            print(f"{stamp} {text[:220]}", flush=True)
send("QUIT :진단 끝")
time.sleep(0.5)
s.close()
print("관찰 종료")
