"""지난번에 들어가 있던 채널을 기억하고 다시 들어가는가.

늘 들어가는 방이 정해져 있는데 앱을 켤 때마다 채널 선택 화면에서 손으로 고르는 것은
매번 똑같은 수고다. 모바일에도 같은 기능이 있고(mobile/lib/login_store.dart) 둘이
같은 규칙을 지켜야 한다 - **닉네임마다 따로**, **서버마다 따로**.

여기서 특히 보는 것:
 - 다른 이름으로 켰을 때 남의 방에 들어가지 않는가(한 컴퓨터를 둘이 쓸 수 있다)
 - 다시 들어가는 **도중에** 기억을 덮어쓰지 않는가(그 사이에 앱이 꺼지면 나머지가
   통째로 사라진다)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 사람이 쓰는 진짜 설정 파일을 건드리지 않게 먼저 바꿔둔다(CLAUDE.md 11-2)
os.environ.setdefault("CHUPCHAT_DATA_DIR", tempfile.mkdtemp(prefix="chupchat_test_"))

import channel_store  # noqa: E402

HOST = "home.pdlab.kr"
PORT = 6697

ok = True


def check(name, got, want):
    global ok
    if got == want:
        print(f"[PASS] {name}")
        return True
    print(f"[FAIL] {name}: {got!r} != {want!r}")
    ok = False
    return False


def main():
    # 처음에는 아무것도 없다
    check("처음에는 비어 있다", channel_store.load(HOST, PORT, "mong22"), [])

    # 적어두면 순서 그대로 돌아온다
    channel_store.save(HOST, PORT, "mong22", ["#pdlab", "#일반"])
    check("순서 그대로 돌아온다",
          channel_store.load(HOST, PORT, "mong22"), ["#pdlab", "#일반"])

    # 다른 이름은 남의 방을 못 본다
    check("다른 이름은 남의 방을 못 본다",
          channel_store.load(HOST, PORT, "두리"), [])

    # 다른 서버와도 섞이지 않는다
    check("다른 서버와 섞이지 않는다",
          channel_store.load("irc.example.com", PORT, "mong22"), [])

    # IRC 닉네임은 대소문자를 가리지 않는다
    channel_store.save(HOST, PORT, "Mong22", ["#pdlab"])
    check("대소문자가 달라도 같은 사람",
          channel_store.load(HOST, PORT, "mONG22"), ["#pdlab"])

    # 다 나왔으면 빈 목록이 그대로 남아야 한다(다음에 아무 방에도 안 들어가게)
    channel_store.save(HOST, PORT, "mong22", [])
    check("다 나오면 비워둔다", channel_store.load(HOST, PORT, "mong22"), [])

    # 닉네임이 없으면 적지도 읽지도 않는다(로그인 전에 불릴 수 있다)
    channel_store.save(HOST, PORT, "", ["#아무개"])
    check("이름이 없으면 적지 않는다", channel_store.load(HOST, PORT, ""), [])

    # 상한을 넘겨도 파일이 끝없이 불어나지 않는다
    many = [f"#방{i}" for i in range(channel_store.MAX_CHANNELS + 10)]
    channel_store.save(HOST, PORT, "많이", many)
    check("채널 수 상한을 지킨다",
          len(channel_store.load(HOST, PORT, "많이")), channel_store.MAX_CHANNELS)

    print(f"\n통과: {ok}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
