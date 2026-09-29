# -*- mode: python ; coding: utf-8 -*-

# 이 앱이 안 쓰는 Qt 덩어리들. 빼는 이유는 용량이 아니라 **켜지는 속도**다 -
# 실측(2026-09-29): 설치본 129MB / 파일 244개라 백신이 매번 훑느라 창이 뜨기까지 21초.
# 그중 opengl32sw(19.7MB) / Quick+Qml(11.4MB) / Pdf(4.4MB)는 우리가 한 줄도 안 쓴다.
# **QtWidgets / QtNetwork / QtWebSockets / QtSvg 는 쓰므로 절대 빼지 말 것.**
UNUSED_QT = [
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuick3D',
    'PySide6.QtQuickControls2', 'PySide6.QtQuickTest',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSpatialAudio',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
    'PySide6.QtWebChannel', 'PySide6.QtWebView',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtDesigner', 'PySide6.QtUiTools', 'PySide6.QtHelp',
    'PySide6.QtSql', 'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
    'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtRemoteObjects',
    'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtStateMachine',
    'PySide6.QtTextToSpeech', 'PySide6.QtHttpServer',
    # 시험용 모듈. tests/ 는 소스로 돌리므로 설치본에는 필요 없다
    'PySide6.QtTest',
]

# 같이 넣을 파일들. **여기가 유일한 목록이다** - 예전에는 워크플로마다 따로 적어둬서
# 한쪽만 고치면 CI 빌드에서만 파일이 빠졌다(1번 규칙의 순환참조 사고와 같은 종류).
# 없으면 그냥 건너뛴다 - 앱이 파일 없을 때 직접 그리는 쪽으로 넘어가므로 빌드가 안 깨진다
import os

WANTED_FILES = [
    'icon.ico', 'icon.png',
    'CHANGELOG.md',              # 업데이트 뒤 "뭐가 바뀌었는지" 창이 읽는다
    'battlecruiser.png', 'mineral.png', 'gas.png',
    'battle_title.jpg',
]
DATA_FILES = [(name, '.') for name in WANTED_FILES if os.path.exists(name)]

# 정식/테스트 빌드가 이름만 다르고 나머지는 같다. 이름을 환경 변수로 받아 spec 하나로 쓴다
BUILD_NAME = os.environ.get('CHUPCHAT_BUILD_NAME', 'FriendChat_GUI')

a = Analysis(
    ['gui_client.py'],
    pathex=[],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=UNUSED_QT,
    noarchive=False,
    optimize=0,
)
# **위 excludes 만으로는 DLL이 안 빠진다.** PySide6 후크가 Qt DLL을 통째로 가져오기
# 때문에, 실제로 덩치를 줄이려면 여기서 직접 걸러내야 한다(실측: excludes만 했을 때
# 123MB -> 115MB, 여기까지 하면 훨씬 줄어든다).
# 이름이 이걸로 시작하는 파일은 뺀다. **Qt6Core/Gui/Widgets/Network/WebSockets/Svg 는
# 쓰므로 절대 넣지 말 것** - 넣으면 앱이 아예 안 켜진다.
DROP_BINARIES = (
    'opengl32sw',          # 소프트웨어 OpenGL 폴백(19.7MB). 우리는 위젯만 그린다
    'Qt6Quick', 'Qt6Qml', 'Qt6QmlModels', 'Qt6QmlWorkerScript',
    'Qt6Pdf',
    'Qt6Multimedia', 'Qt6SpatialAudio',
    'Qt6Charts', 'Qt6DataVisualization', 'Qt6Graphs',
    'Qt63D', 'Qt6WebEngine', 'Qt6WebChannel', 'Qt6WebView',
    'Qt6Designer', 'Qt6Help', 'Qt6Sql', 'Qt6Test',
    'Qt6Bluetooth', 'Qt6Nfc', 'Qt6Positioning', 'Qt6SerialPort', 'Qt6SerialBus',
    'Qt6RemoteObjects', 'Qt6Scxml', 'Qt6Sensors', 'Qt6StateMachine',
    'Qt6TextToSpeech', 'Qt6HttpServer',
)


def _keep(entry):
    name = os.path.basename(entry[0])
    return not any(name.startswith(prefix) for prefix in DROP_BINARIES)


_before = len(a.binaries)
a.binaries = [entry for entry in a.binaries if _keep(entry)]
print(f"[chupchat] 안 쓰는 Qt 파일 {_before - len(a.binaries)}개 제외")

pyz = PYZ(a.pure)

# 켜는 동안 뜨는 시작 그림. **파이썬이 시작되기도 전에** 부트로더가 띄우므로,
# 아무것도 안 보이던 20초를 이 그림이 메운다. 닫는 건 gui_client._close_splash()
splash = Splash(
    'splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    minify_script=True,
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name=BUILD_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    splash.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=BUILD_NAME,
)
