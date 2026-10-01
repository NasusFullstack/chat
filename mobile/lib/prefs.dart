/// 앱 설정 - 사람이 켜고 끄는 것들.
///
/// PC 앱의 `app_prefs.py`에 해당한다. **지금은 비어 있다** - 알림을 들어내면서
/// 켜고 끌 것이 없어졌다(왜 들어냈는지는 mobile/README.md).
///
/// 자리를 남겨두는 이유: 설정이 다시 생길 때 어디에 넣을지 찾아다니지 않게.
/// 로그인 관련(이름 기억·자동 들어가기)은 `login_store.dart`가 따로 맡는다.
///
/// 설정을 다시 추가할 때 지킬 것: **읽을 때도 자료형을 지켜야 한다.** PC 앱에서
/// 저장된 값을 전부 `bool()`로 바꿔버려 글자 설정이 재시작마다 뭉개진 적이 있다
/// (CLAUDE.md 9-3). `getBool`로 받아 null 이면 기본값을 쓰면 그럴 자리가 없다.
library;

class Prefs {
  Prefs();

  /// 지금은 읽을 것이 없다. 설정이 생기면 여기서 읽는다
  static Future<Prefs> load() async => Prefs();

  /// 지금은 적을 것이 없다.
  Future<void> save() async {}
}
