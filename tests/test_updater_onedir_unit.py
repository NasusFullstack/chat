import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import io
import os
import sys

sys.path.insert(0, _REPO)
import updater

checks = []

# ---- _parse_version ----
checks.append(("v1.2.3 -> (1,2,3)", updater._parse_version("v1.2.3") == (1, 2, 3)))
checks.append(("버전 비교: v1.2.3 < v1.10.0", updater._parse_version("v1.2.3") < updater._parse_version("v1.10.0")))


class FakeResponse:
    def __init__(self, payload_bytes, headers=None):
        self._buf = io.BytesIO(payload_bytes)
        self.headers = headers or {}

    def read(self, n=-1):
        return self._buf.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


import json as _json


def make_release_json(tag, assets):
    return _json.dumps({"tag_name": tag, "assets": assets}).encode("utf-8")


orig_urlopen = updater.urllib.request.urlopen

# ---- check_for_update: zip 자산을 올바르게 찾는지 ----
def fake_urlopen_ok(req, timeout=None):
    return FakeResponse(make_release_json("v1.2.0", [
        {"name": "FriendChat_Setup.exe", "browser_download_url": "http://x/setup.exe"},
        {"name": updater.ASSET_NAME, "browser_download_url": "http://x/update.zip"},
    ]))


updater.urllib.request.urlopen = fake_urlopen_ok
result = updater.check_for_update()
checks.append(("설치 인스톨러(exe) 말고 업데이트용 zip 자산을 정확히 골라냄",
               result is not None and result["download_url"] == "http://x/update.zip"))

# ---- download_update: 정상 다운로드 ----
big_payload = b"Z" * (updater.MIN_VALID_PACKAGE_BYTES + 500_000)


def fake_urlopen_download(req, timeout=None):
    return FakeResponse(big_payload, headers={"Content-Length": str(len(big_payload))})


updater.urllib.request.urlopen = fake_urlopen_download
path = updater.download_update("http://x/update.zip")
checks.append(("정상 다운로드 시 파일이 생성되고 크기가 일치함", os.path.exists(path) and os.path.getsize(path) == len(big_payload)))
checks.append(("다운로드 확장자가 .zip임", path.endswith(".zip")))
os.remove(path)

# ---- download_update: 너무 작은 다운로드는 거부 ----
def fake_urlopen_small(req, timeout=None):
    small = b"tiny"
    return FakeResponse(small, headers={"Content-Length": str(len(small))})


updater.urllib.request.urlopen = fake_urlopen_small
raised = False
try:
    updater.download_update("http://x/update.zip")
except ValueError:
    raised = True
checks.append(("패키지 최소 크기(20MB) 미만이면 예외 발생", raised))

updater.urllib.request.urlopen = orig_urlopen

print("\n=== 검증 결과 (updater.py onedir 재설계 단위 테스트) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
