"""저장하는 비밀번호를 그대로 두지 않는다.

예전에는 `login_prefs.json`에 비밀번호가 **글자 그대로** 들어 있었다. 파일을 열면 바로
보이고, 백업이나 화면 공유로도 새어나간다.

윈도우에는 이런 용도의 장치가 있다(DPAPI). **지금 로그인한 윈도우 사용자만** 풀 수 있게
잠가주므로, 파일을 통째로 복사해가도 다른 계정에서는 못 읽는다. 브라우저들이 저장된
비밀번호를 다루는 방식과 같다.

다른 운영체제에서는 그런 장치가 없으므로 최소한 눈에 안 띄게만 바꿔둔다. 그건 **암호화가
아니다** - 마음먹으면 되돌릴 수 있다. 그래서 표시를 남겨 어느 방식으로 저장됐는지 알 수
있게 한다(`dpapi:` / `plain64:`).
"""
import base64
import sys

DPAPI_PREFIX = "dpapi:"
WEAK_PREFIX = "plain64:"
IS_WINDOWS = sys.platform.startswith("win")


def _dpapi(text: str, encrypt: bool) -> bytes | None:
    """윈도우가 제공하는 보호 장치를 부른다. 못 쓰면 None."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        source = text.encode("utf-8") if encrypt else base64.b64decode(text)
        buffer = ctypes.create_string_buffer(source, len(source))
        incoming = Blob(len(source), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        outgoing = Blob()
        function = (ctypes.windll.crypt32.CryptProtectData if encrypt
                    else ctypes.windll.crypt32.CryptUnprotectData)
        ok = function(ctypes.byref(incoming), None, None, None, None, 0,
                      ctypes.byref(outgoing))
        if not ok:
            return None
        result = ctypes.string_at(outgoing.pbData, outgoing.cbData)
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)
        return result
    except Exception:  # noqa: BLE001 - 보호 장치가 없거나 막혀도 앱은 돌아야 한다
        return None


def protect(text: str) -> str:
    """저장할 형태로 바꾼다. 빈 값은 그대로 둔다."""
    if not text:
        return ""
    sealed = _dpapi(text, encrypt=True)
    if sealed is not None:
        return DPAPI_PREFIX + base64.b64encode(sealed).decode("ascii")
    return WEAK_PREFIX + base64.b64encode(text.encode("utf-8")).decode("ascii")


def unprotect(stored: str) -> str:
    """저장된 값을 원래 글자로. 예전에 그대로 저장된 값도 읽어준다."""
    if not stored:
        return ""
    if stored.startswith(DPAPI_PREFIX):
        opened = _dpapi(stored[len(DPAPI_PREFIX):], encrypt=False)
        return opened.decode("utf-8", "replace") if opened else ""
    if stored.startswith(WEAK_PREFIX):
        try:
            return base64.b64decode(stored[len(WEAK_PREFIX):]).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return ""
    # 예전 버전이 글자 그대로 저장해둔 값 - 다음 저장 때 보호된 형태로 바뀐다
    return stored


def is_protected(stored: str) -> bool:
    return bool(stored) and stored.startswith((DPAPI_PREFIX, WEAK_PREFIX))
