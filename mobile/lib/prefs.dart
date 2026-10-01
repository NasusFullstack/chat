/// 앱 설정 - 사람이 켜고 끄는 것들.
///
/// PC 앱의 `app_prefs.py`에 해당한다. 같은 것을 같은 이름으로 둬서, 한쪽에만 있는
/// 설정이 생기지 않게 한다.
///
/// **읽을 때도 자료형을 지켜야 한다.** PC 앱에서 저장된 값을 전부 `bool()`로 바꿔버려
/// 글자 설정이 재시작마다 뭉개진 적이 있다(CLAUDE.md 9-3). 여기서는 `getBool`로
/// 받아 null 이면 기본값을 쓴다 - 그러면 자료형이 섞일 자리가 없다.
library;

import 'package:shared_preferences/shared_preferences.dart';

/// 설정 하나 - 이름과 기본값.
class _Flag {
  const _Flag(this.key, this.fallback);

  final String key;
  final bool fallback;
}

const _Flag _notify = _Flag('notify', true);
const _Flag _notifyDetail = _Flag('notify_detail', true);
const _Flag _keepAlive = _Flag('keep_alive', true);

/// 사람이 고른 설정. 기본값은 "켜져 있음" - 알림을 받으러 깔았을 것이다.
class Prefs {
  Prefs({
    this.notify = true,
    this.notifyDetail = true,
    this.keepAlive = true,
  });

  /// 알림을 띄울까.
  bool notify;

  /// 알림에 **내용**까지 보일까. 끄면 누가 말했는지만 알린다
  bool notifyDetail;

  /// 홈으로 나가도 접속을 **유지**할까.
  ///
  /// 유지하려면 안드로이드가 요구하는 대로 "실행 중" 알림이 하나 떠 있어야 한다.
  /// 그게 싫은 사람은 끌 수 있어야 하므로 설정으로 둔다 - 끄면 홈으로 나가는 순간
  /// 접속이 끊기고 알림도 안 온다.
  bool keepAlive;

  static Future<Prefs> load() async {
    try {
      final store = await SharedPreferences.getInstance();
      return Prefs(
        notify: store.getBool(_notify.key) ?? _notify.fallback,
        notifyDetail: store.getBool(_notifyDetail.key) ?? _notifyDetail.fallback,
        keepAlive: store.getBool(_keepAlive.key) ?? _keepAlive.fallback,
      );
    } on Object {
      // 설정을 못 읽는다고 앱이 안 켜지면 안 된다 - 기본값으로 간다
      return Prefs();
    }
  }

  Future<void> save() async {
    try {
      final store = await SharedPreferences.getInstance();
      await store.setBool(_notify.key, notify);
      await store.setBool(_notifyDetail.key, notifyDetail);
      await store.setBool(_keepAlive.key, keepAlive);
    } on Object {
      // 못 저장해도 이번 실행에는 적용되어 있다
    }
  }
}
