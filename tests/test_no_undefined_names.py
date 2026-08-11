"""함수 안에서 쓰는 이름이 실제로 정의돼 있는지 전부 확인한다.

실제 사고(2026-08-11, v2.1.0): `gui_client.main()`에서 `SingleInstance`를 쓰는데 임포트
한 줄이 안 들어가 있었다. **모듈을 임포트할 때는 아무 문제가 없었고**(그 이름은 함수가
실행될 때 비로소 찾는다), 테스트도 임포트만 해봤기 때문에 통과했다. 그래서 릴리즈된 앱이
켜지자마자 `NameError: name 'SingleInstance' is not defined`로 죽었다.

여기서는 파이썬이 만든 바이트코드를 읽어 **함수가 전역에서 찾을 이름**(LOAD_GLOBAL)을
모두 뽑고, 그 이름이 모듈 전역이나 내장에 실제로 있는지 확인한다. 함수를 실행하지 않고도
이런 종류의 오타/누락 임포트를 전부 잡는다.
"""
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_REPO = _os.path.dirname(_HERE)

_os.environ["QT_QPA_PLATFORM"] = "offscreen"
_sys.path.insert(0, _REPO)
_sys.path.insert(0, _HERE)

import builtins
import dis
import importlib
import pkgutil
import types

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

# 검사할 모듈. 여기 있는 것들이 실제로 배포되는 코드다
TOP_LEVEL = [
    "gui_client", "cli_client", "app_prefs", "avatar_store", "client_version_store",
    "emoji_store", "error_log", "history_store", "irc_protocol", "link_meta",
    "login_prefs", "server_registry", "single_instance", "updater", "version",
]
PACKAGES = ["gui", "chat_core"]

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def module_names() -> list:
    names = list(TOP_LEVEL)
    for package_name in PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(package.__path__, package_name + "."):
            names.append(info.name)
    return names


def functions_in(module):
    """모듈 안의 함수와 메서드를 모두 훑는다(클래스 안까지)."""
    seen = set()
    for value in vars(module).values():
        if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
            if value.__qualname__ not in seen:
                seen.add(value.__qualname__)
                yield value
        elif isinstance(value, type) and value.__module__ == module.__name__:
            for attr in vars(value).values():
                func = attr.__func__ if isinstance(attr, (staticmethod, classmethod)) else attr
                if isinstance(func, types.FunctionType):
                    if func.__qualname__ not in seen:
                        seen.add(func.__qualname__)
                        yield func


def undefined_globals(func, module) -> list:
    """그 함수가 전역에서 찾을 이름 중, 어디에도 없는 것들."""
    missing = []
    for instruction in dis.get_instructions(func):
        if instruction.opname != "LOAD_GLOBAL":
            continue
        name = instruction.argval
        if name in vars(module) or hasattr(builtins, name):
            continue
        if name in getattr(func, "__globals__", {}):
            continue
        missing.append(name)
    return sorted(set(missing))


bad = []
failed_import = []
checked_modules = 0
checked_functions = 0

for name in module_names():
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - 임포트 자체가 실패하는 것도 알아야 한다
        failed_import.append(f"{name}: {type(exc).__name__} {exc}")
        continue
    checked_modules += 1
    for func in functions_in(module):
        checked_functions += 1
        # 함수 안에서 지연 임포트하는 이름은 지역 변수가 되므로 여기 안 잡힌다.
        # 잡히는 건 진짜로 어디에도 없는 이름뿐이다
        for missing in undefined_globals(func, module):
            bad.append(f"{name}.{func.__qualname__} -> {missing}")

check(f"모든 모듈이 임포트된다({checked_modules}개)", not failed_import, failed_import)
check(f"정의되지 않은 이름을 쓰는 곳이 없다(함수 {checked_functions}개 검사)",
      not bad, bad[:10])

# 이 검사가 실제로 그 사고를 잡는지 확인한다 - 안 잡히면 검사가 있으나 마나다
import gui_client  # noqa: E402


def _fake_broken():
    return SomeNameThatDoesNotExistAnywhere  # noqa: F821


check("일부러 만든 '없는 이름'은 잡아낸다",
      undefined_globals(_fake_broken, gui_client) == ["SomeNameThatDoesNotExistAnywhere"],
      undefined_globals(_fake_broken, gui_client))

# 앱을 켜는 진짜 경로(main)에 특히 신경 쓴다 - 여기가 깨지면 아무도 앱을 못 켠다
check("앱 시작 함수(main)가 쓰는 이름이 전부 정의돼 있다",
      not undefined_globals(gui_client.main, gui_client),
      undefined_globals(gui_client.main, gui_client))

print("=== 검증 결과 (정의되지 않은 이름) ===")
all_ok = True
for name, ok, *detail in checks:
    extra = f"  <- {detail[0]}" if detail and detail[0] and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}{extra}")
    all_ok = all_ok and ok
print("\n전체 통과:", all_ok)
_sys.exit(0 if all_ok else 1)
