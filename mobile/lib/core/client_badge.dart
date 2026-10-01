/// "저 사람은 무슨 프로그램으로 들어와 있나".
///
/// ## 왜 서버에서 받아오나
/// 예전에는 IRC 로 상대에게 CTCP VERSION 을 물어봤다. 그 방식은 셋이 문제였다:
///  - 서버가 폭주로 보고 거절한다(UnrealIRCd: "Multi-target messaging is not allowed")
///  - 상대 화면에 "CTCP VERSION received from ..."이 찍힌다 - 켤 때마다 실례다
///  - 다리(bridge) 봇은 자기가 쓰는 라이브러리를 답한다(실측: girc ... using go1.19.5)
///
/// 지금은 각자 **자기가 무엇인지 중계 서버에 적어두고**, 참여자 목록을 받을 때 하는
/// 프로필 조회 한 번으로 같이 받아온다. 아무에게도 묻지 않으므로 위 셋이 다 사라진다.
/// PC 앱도 같은 값을 적고 같은 값을 읽는다(서버 features/profiles.py).
library;

/// 그 사람이 쓰는 프로그램. 모르면 전부 빈 값이다.
class ClientInfo {
  const ClientInfo({this.app = '', this.version = '', this.platform = ''});

  /// 서버가 돌려준 것을 읽는다. **글자를 그대로 믿지 않는다** - 이 값은 화면에
  /// 배지로 뜨므로, 아무 글자나 그려주면 남이 적어 보낸 글이 내 화면에 뜬다.
  /// 서버도 같은 검사를 하지만, 받는 쪽에서 한 번 더 보는 것이 맞다
  factory ClientInfo.fromJson(Object? raw) {
    if (raw is! Map) return const ClientInfo();
    final app = '${raw['app'] ?? ''}';
    final version = '${raw['version'] ?? ''}';
    final platform = '${raw['platform'] ?? ''}';
    if (!_appOk.hasMatch(app)) return const ClientInfo();
    return ClientInfo(
      app: app,
      version: _versionOk.hasMatch(version) ? version : '',
      platform: platforms.contains(platform) ? platform : '',
    );
  }

  static final RegExp _appOk = RegExp(r'^[A-Za-z0-9 ._-]{1,32}$');
  static final RegExp _versionOk = RegExp(r'^[0-9A-Za-z.+-]{1,24}$');

  /// 서버가 받아주는 자리 이름. 여기 없는 것은 모르는 것으로 본다
  static const Set<String> platforms = {'pc', 'mobile', 'web', 'cli'};

  final String app;
  final String version;
  final String platform;

  bool get known => app.isNotEmpty;

  /// 우리 식구인가(춥채팅 PC/모바일).
  bool get isOurs => app.toLowerCase() == 'chupchat';

  Map<String, String> toJson() =>
      {'app': app, 'version': version, 'platform': platform};

  @override
  bool operator ==(Object other) =>
      other is ClientInfo &&
      other.app == app &&
      other.version == version &&
      other.platform == platform;

  @override
  int get hashCode => Object.hash(app, version, platform);
}

/// 우리가 서버에 적어두는 우리 자신.
ClientInfo ourClient(String version) =>
    ClientInfo(app: 'ChupChat', version: version, platform: 'mobile');

/// 참여자 목록에 한 줄로 적을 말. 모르면 빈 글자(아무것도 안 적는다).
///
/// 모르는 사람 자리에 "알 수 없음" 같은 말을 적으면 목록이 그 글자로 가득 찬다 -
/// 아는 것만 적고 모르면 비워두는 쪽이 보기 좋다.
String badgeText(ClientInfo info) {
  if (!info.known) return '';
  final name = info.isOurs ? '춥채팅' : info.app;
  final where = switch (info.platform) {
    'mobile' => '폰',
    'pc' => 'PC',
    'web' => '웹',
    'cli' => '터미널',
    _ => '',
  };
  final parts = [
    name,
    if (info.version.isNotEmpty) info.version,
  ].join(' ');
  return where.isEmpty ? parts : '$parts · $where';
}
