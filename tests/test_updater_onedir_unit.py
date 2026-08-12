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
from version import APP_VERSION


def newer_tag() -> str:
    """지금 앱 버전보다 반드시 높은 태그.

    숫자를 박아두면(예전에는 "v1.0.99"였다) 앱 버전이 그 숫자를 넘어서는 순간
    "업데이트 없음"이 정답이 되어버려서, 검사는 조용히 실패하는데 아무도 모른다.
    실제로 2.0.x가 되면서 그렇게 썩어 있었다.
    """
    major = int(APP_VERSION.split("-")[0].split(".")[0])
    return f"v{major + 1}.0.0"


NEW_TAG = newer_tag()


def make_release_json(tag, assets):
    return _json.dumps({"tag_name": tag, "assets": assets}).encode("utf-8")


orig_urlopen = updater.urllib.request.urlopen

# ---- check_for_update: zip 자산을 올바르게 찾는지 ----
def fake_urlopen_ok(req, timeout=None):
    return FakeResponse(make_release_json(NEW_TAG, [
        {"name": "FriendChat_Setup.exe", "browser_download_url": "http://x/setup.exe"},
        {"name": updater.ASSET_NAME, "browser_download_url": "http://x/update.zip"},
    ]))


# 지금 방식은 설치 파일이 기본이다(폴더 통째로 바꾸는 zip 방식은 파일이 하나라도
# 열려 있으면 통째로 실패했다). 둘 다 올라와 있으면 설치 파일을 골라야 한다
updater.urllib.request.urlopen = fake_urlopen_ok
result = updater.check_for_update()
checks.append(("둘 다 있으면 설치 파일을 고름",
               result is not None and result["download_url"] == "http://x/setup.exe"
               and result.get("kind") == "installer"))


# 설치 파일이 없는 옛 릴리즈로 돌아가야 할 때는 zip으로 물러난다
def fake_urlopen_zip_only(req, timeout=None):
    return FakeResponse(make_release_json(NEW_TAG, [
        {"name": updater.ASSET_NAME, "browser_download_url": "http://x/update.zip"},
    ]))


updater.urllib.request.urlopen = fake_urlopen_zip_only
zip_only = updater.check_for_update()
checks.append(("설치 파일이 없으면 zip으로 물러남",
               zip_only is not None and zip_only["download_url"] == "http://x/update.zip"
               and zip_only.get("kind") == "zip"))

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
