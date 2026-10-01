/// "저 사람은 무슨 프로그램인가"를 **서버에서 받아온 값으로** 판단하는가.
///
/// IRC 로 물어보던 방식을 버린 이유는 `lib/core/client_badge.dart`에 적어뒀다.
/// 여기서 특히 보는 것은 **안 믿는 것**이다 - 이 값은 화면에 글자로 뜨므로, 아무
/// 글자나 그대로 그리면 남이 적어 보낸 글이 내 화면에 뜨는 길이 된다.
/// 서버도 같은 검사를 하지만 받는 쪽에서 한 번 더 본다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/client_badge.dart';

void main() {
  group('서버가 준 것을 읽는다', () {
    test('우리 앱이면 춥채팅으로 알아본다', () {
      final info = ClientInfo.fromJson(
          {'app': 'ChupChat', 'version': '2.6.6', 'platform': 'mobile'});
      expect(info.isOurs, isTrue);
      expect(badgeText(info), '춥채팅 2.6.6 · 폰');
    });

    test('PC 에서 들어온 사람도 구분된다', () {
      final info = ClientInfo.fromJson(
          {'app': 'ChupChat', 'version': '2.6.6', 'platform': 'pc'});
      expect(badgeText(info), '춥채팅 2.6.6 · PC');
    });

    test('남의 프로그램은 이름을 그대로 보여준다', () {
      final info = ClientInfo.fromJson(
          {'app': 'WeeChat', 'version': '4.4.2', 'platform': 'cli'});
      expect(info.isOurs, isFalse);
      expect(badgeText(info), 'WeeChat 4.4.2 · 터미널');
    });

    test('모르는 사람은 아무것도 안 적는다', () {
      expect(badgeText(const ClientInfo()), isEmpty,
          reason: '"알 수 없음"을 적으면 목록이 그 글자로 가득 찬다');
    });
  });

  group('이상한 값을 안 믿는다', () {
    test('프로그램 이름에 글자 아닌 것이 섞이면 모르는 것으로 본다', () {
      final info = ClientInfo.fromJson(
          {'app': '<b>나쁜</b>', 'version': '1.0', 'platform': 'pc'});
      expect(info.known, isFalse);
      expect(badgeText(info), isEmpty);
    });

    test('모르는 자리는 버린다', () {
      final info = ClientInfo.fromJson(
          {'app': 'ChupChat', 'version': '1.0', 'platform': '냉장고'});
      expect(info.platform, isEmpty, reason: '아는 자리만 받는다');
      expect(badgeText(info), '춥채팅 1.0');
    });

    test('버전이 이상하면 버전만 버린다', () {
      final info = ClientInfo.fromJson(
          {'app': 'ChupChat', 'version': '1.0 <script>', 'platform': 'pc'});
      expect(info.version, isEmpty);
      expect(badgeText(info), '춥채팅 · PC');
    });

    test('아주 긴 이름은 모르는 것으로 본다', () {
      final info = ClientInfo.fromJson({'app': 'A' * 300});
      expect(info.known, isFalse, reason: '목록 한 줄이 글자로 터지면 안 된다');
    });

    test('모양이 아예 다르면 조용히 비운다', () {
      expect(ClientInfo.fromJson('이건 글자'), const ClientInfo());
      expect(ClientInfo.fromJson(null), const ClientInfo());
      expect(ClientInfo.fromJson(42), const ClientInfo());
    });
  });

  test('우리가 적는 우리 자신', () {
    final me = ourClient('2.6.6');
    expect(me.toJson(),
        {'app': 'ChupChat', 'version': '2.6.6', 'platform': 'mobile'});
    // PC 앱도 같은 모양으로 적는다(gui/client_badges.py 의 my_client_info)
    expect(ClientInfo.platforms.contains(me.platform), isTrue);
  });
}
