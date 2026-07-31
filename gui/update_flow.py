"""자동 업데이트 진행 흐름 (GUI 어댑터 쪽).

updater.py는 "무엇을 어떻게 받고 적용하는가"만 알고, 여기서는 그 진행 상황을 시작화면에
보여주는 역할만 함. 예전에는 이 로직이 gui_client.py(진입점)에 있으면서 별도 모달 창을
띄웠는데, 로그인 화면 위에 갑자기 창이 덮이는 어색한 흐름이라 시작화면에 통합함.
"""
import sys

from PySide6.QtWidgets import QApplication


def check_and_apply(startup_page) -> bool:
    """새 버전이 있으면 받아서 적용을 시작하고 True를 반환(곧 프로세스가 종료됨).

    업데이트가 없거나, 확인/다운로드/적용 중 뭐라도 실패하면 False를 반환해서 평소처럼
    앱이 계속 뜨게 함 - 업데이트 기능 때문에 실행 자체가 막히면 안 되므로.
    """
    if not getattr(sys, "frozen", False):
        return False  # 소스로 실행 중이면 git pull로 갱신하면 되므로 자동 업데이트 안 함

    import updater

    info = updater.check_for_update()
    if info is None:
        return False

    startup_page.set_status(f"새 버전 {info['version']}을(를) 받는 중...")
    startup_page.show_progress(0)
    QApplication.processEvents()

    def on_progress(read: int, total: int):
        startup_page.show_progress(int(read / total * 100) if total else 0)
        QApplication.processEvents()

    is_installer = info.get("kind") == "installer"
    try:
        package_path = updater.download_update(
            info["download_url"], progress_cb=on_progress,
            suffix=".exe" if is_installer else ".zip",
        )
    except Exception:  # noqa: BLE001
        startup_page.hide_progress()
        startup_page.set_status("업데이트를 받지 못했습니다. 현재 버전으로 시작합니다.")
        QApplication.processEvents()
        return False

    startup_page.set_status("업데이트 적용 중... 곧 다시 시작됩니다.")
    startup_page.show_progress(100)
    QApplication.processEvents()

    # 이 시도 자체를 기록해둠 - 이 프로세스는 곧 종료돼서 성공 여부를 알 수 없지만,
    # 같은 버전으로 계속 실패하면 다음 실행 때 check_for_update()가 알아서 건너뜀
    # (그래야 "업데이트 화면만 뜨고 앱은 영영 못 켜는" 무한루프에 안 빠짐)
    updater.record_update_attempt(info["version"])
    try:
        # 인스톨러 방식이 기본 - 폴더 통째 move는 파일 하나만 잠겨도 전부 실패하는데
        # 인스톨러는 파일 단위로 처리해서 그 상황에서도 성공함(실측 확인)
        if is_installer:
            updater.apply_installer_and_relaunch(package_path)
        else:
            updater.apply_update_and_relaunch(package_path)
        # 성공하면 위에서 프로세스가 끝나므로 여기 도달하지 않음
    except Exception:  # noqa: BLE001
        startup_page.hide_progress()
        startup_page.set_status("업데이트를 적용하지 못했습니다. 현재 버전으로 시작합니다.")
        QApplication.processEvents()
        return False
    return True
