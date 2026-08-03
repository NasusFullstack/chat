import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)
import io
import json as _json
import os
import sys

sys.path.insert(0, _REPO)
import updater

STATE_FILE = updater._update_state_path()
if os.path.exists(STATE_FILE):
    os.remove(STATE_FILE)

checks = []


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


def make_release_json(tag, assets):
    return _json.dumps({"tag_name": tag, "assets": assets}).encode("utf-8")


orig_urlopen = updater.urllib.request.urlopen


def fake_urlopen_1_0_99(req, timeout=None):
    return FakeResponse(make_release_json("v1.0.99", [
        {"name": updater.ASSET_NAME, "browser_download_url": "http://x/update.zip"},
    ]))


updater.urllib.request.urlopen = fake_urlopen_1_0_99

# ---- 처음엔 업데이트가 있다고 정상적으로 나와야 함 ----
result = updater.check_for_update()
checks.append(("첫 확인에서는 신버전이 있다고 나옴", result is not None and result["version"] == "v1.0.99"))

# ---- 3번 연속 "시도"를 기록하면(성공 여부와 무관, 이 프로세스는 결과를 알 방법이 없음) ----
updater.record_update_attempt("v1.0.99")
result2 = updater.check_for_update()
checks.append(("1번 시도 후에도 여전히 신버전으로 나옴(아직 상한 안 걸림)", result2 is not None))

updater.record_update_attempt("v1.0.99")
result3 = updater.check_for_update()
checks.append(("2번 시도 후에도 여전히 신버전으로 나옴", result3 is not None))

updater.record_update_attempt("v1.0.99")
result4 = updater.check_for_update()
checks.append(("3번(MAX_UPDATE_ATTEMPTS) 연속 시도 후에는 더 이상 업데이트로 안 잡힘(무한루프 방지)",
               result4 is None))

# ---- 더 새로운 버전(v1.0.100)이 나오면 그 버전 기준으로 새로 시작해야 함(과거 실패 이력이
#      다른 버전까지 영구히 막지는 않음) ----
def fake_urlopen_1_0_100(req, timeout=None):
    return FakeResponse(make_release_json("v1.0.100", [
        {"name": updater.ASSET_NAME, "browser_download_url": "http://x/update2.zip"},
    ]))


updater.urllib.request.urlopen = fake_urlopen_1_0_100
result5 = updater.check_for_update()
checks.append(("더 새 버전이 나오면 과거 실패 이력과 무관하게 다시 시도 대상으로 잡힘",
               result5 is not None and result5["version"] == "v1.0.100"))

updater.urllib.request.urlopen = orig_urlopen
if os.path.exists(STATE_FILE):
    os.remove(STATE_FILE)

print("\n=== 검증 결과 (같은 버전 반복 실패 시 무한루프 방지 회로차단기) ===")
all_ok = True
for name, ok in checks:
    print(f"[{'OK' if ok else 'FAIL'}] {name}")
    all_ok = all_ok and ok
print("전체 통과:", all_ok)
