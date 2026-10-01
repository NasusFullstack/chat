/// 알림이 **언제 뜨고 언제 안 뜨는가**, 그리고 **하나만 보이는가**.
///
/// 알림은 눈으로 확인하기가 번거로워서 조용히 틀린 채로 오래 묻힌다. 특히 이 셋은
/// 실제로 겪기 쉬운 고장이다:
///  - 내가 방금 친 말에 내 폰이 울린다
///  - 앱을 보고 있는데도 울린다
///  - 수다 한 번에 알림이 수십 개로 쌓인다
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/core/emoji.dart';
import 'package:chupchat/net/notifier.dart';

/// 알림 자리 **하나**를 흉내낸 가짜. 진짜도 같은 번호를 쓰므로 늘 하나만 보인다
class FakeNotifier implements Notifier {
  NotificationText? showing;
  int shows = 0;
  int clears = 0;

  @override
  Future<bool> prepare() async => true;

  @override
  Future<void> show(NotificationText what) async {
    showing = what;      // 쌓이지 않는다 - 갈아치운다
    shows += 1;
  }

  @override
  Future<void> clear() async {
    showing = null;
    clears += 1;
  }
}

/// 로그인까지 끝나고 가짜 알림이 끼워진 상태.
({AppState state, FakeNotifier fake}) ready() {
  final fake = FakeNotifier();
  final state = AppState()
    ..notifier = fake
    // 검사에서 안드로이드 서비스를 띄울 수 없다
    ..holdConnection = (() async => true)
    ..releaseConnection = (() async {});
  state.handleEvent(const LoggedIn('나'));
  state.handleEvent(const ChannelJoined('#일반', '입장'));
  return (state: state, fake: fake);
}

void main() {
  group('띄울까 말까', () {
    test('홈으로 나가 있고 남이 말했으면 띄운다', () {
      expect(
          shouldNotify(
              mine: false, isSystem: false, inForeground: false, enabled: true),
          isTrue);
    });

    test('내 말에는 안 띄운다', () {
      expect(
          shouldNotify(
              mine: true, isSystem: false, inForeground: false, enabled: true),
          isFalse,
          reason: '내가 방금 친 말에 내 폰이 울리면 안 된다');
    });

    test('앱을 보고 있으면 안 띄운다', () {
      expect(
          shouldNotify(
              mine: false, isSystem: false, inForeground: true, enabled: true),
          isFalse,
          reason: '눈앞에 이미 보인다');
    });

    test('입장·퇴장 안내에는 안 띄운다', () {
      expect(
          shouldNotify(
              mine: false, isSystem: true, inForeground: false, enabled: true),
          isFalse,
          reason: '사람이 드나들 때마다 울리면 알림을 꺼버린다');
    });

    test('설정에서 껐으면 안 띄운다', () {
      expect(
          shouldNotify(
              mine: false, isSystem: false, inForeground: false, enabled: false),
          isFalse);
    });
  });

  group('무슨 글자를 보일까', () {
    test('이모티콘은 주소가 아니라 말로 보인다', () {
      final shown = previewText('이거 봐 ${formatEmoji('https://a/b.png')}');
      expect(shown, '이거 봐 (이모티콘)',
          reason: '표시 문자를 그대로 두면 알림에 빈칸처럼 보인다');
    });

    test('올린 사진은 (사진)으로 보인다', () {
      final shown = previewText('https://jsserv.pdlab.kr/files/abc/고양이.png');
      expect(shown, '(사진)', reason: '긴 주소가 알림을 가득 채우면 안 된다');
    });

    test('올린 파일은 (파일)로 보인다', () {
      final shown = previewText('https://jsserv.pdlab.kr/files/abc/자료.zip');
      expect(shown, '(파일)');
    });

    test('남의 주소는 건드리지 않는다', () {
      const link = 'https://news.example.com/article/1';
      expect(previewText('이거 봐 $link'), '이거 봐 $link');
    });

    test('너무 길면 자른다', () {
      final shown = previewText('가' * 300);
      expect(shown.length, previewLimit + 1, reason: '자른 표시(…) 한 글자가 붙는다');
      expect(shown.endsWith('…'), isTrue);
    });

    test('내용 표시를 끄면 누가 말했는지만 알린다', () {
      final what = previewFor(
          channel: '#일반', sender: '두리', text: '비밀 이야기', detail: false);
      expect(what.title, '#일반');
      expect(what.body, '두리 님이 말했습니다');
      expect(what.body.contains('비밀'), isFalse,
          reason: '잠금화면에 내용이 드러나면 안 된다');
    });

    test('내용 표시를 켜면 보낸 사람과 내용이 같이 보인다', () {
      final what = previewFor(
          channel: '#일반', sender: '두리', text: '밥 먹자', detail: true);
      expect(what, const NotificationText('#일반', '두리: 밥 먹자'));
    });
  });

  group('실제로 띄우는가', () {
    test('홈으로 나간 뒤 남의 말이 오면 띄운다', () async {
      final it = ready();
      it.state.wentBackground();
      it.state.handleEvent(const MessageReceived(
          channel: '#일반', sender: '두리', text: '밥 먹자', mine: false,
          isMention: false));
      await Future<void>.delayed(Duration.zero);

      expect(it.fake.shows, 1);
      expect(it.fake.showing, const NotificationText('#일반', '두리: 밥 먹자'));
    });

    test('보고 있을 때는 안 띄운다', () async {
      final it = ready();
      it.state.handleEvent(const MessageReceived(
          channel: '#일반', sender: '두리', text: '밥 먹자', mine: false,
          isMention: false));
      await Future<void>.delayed(Duration.zero);

      expect(it.fake.shows, 0);
    });

    test('내 말에는 안 띄운다', () async {
      final it = ready();
      it.state.wentBackground();
      it.state.handleEvent(const MessageReceived(
          channel: '#일반', sender: '나', text: '내가 쓴 말', mine: true,
          isMention: false));
      await Future<void>.delayed(Duration.zero);

      expect(it.fake.shows, 0);
    });

    test('여러 줄이 와도 **마지막 하나만** 보인다', () async {
      final it = ready();
      it.state.wentBackground();
      for (final word in ['하나', '둘', '셋', '넷', '다섯']) {
        it.state.handleEvent(MessageReceived(
            channel: '#일반', sender: '두리', text: word, mine: false,
            isMention: false));
      }
      await Future<void>.delayed(Duration.zero);

      expect(it.fake.showing, const NotificationText('#일반', '두리: 다섯'),
          reason: '쌓이면 수다 한 번에 알림이 수십 개가 된다');
    });

    test('설정에서 알림을 끄면 안 띄운다', () async {
      final it = ready();
      it.state.prefs.notify = false;
      it.state.wentBackground();
      it.state.handleEvent(const MessageReceived(
          channel: '#일반', sender: '두리', text: '밥 먹자', mine: false,
          isMention: false));
      await Future<void>.delayed(Duration.zero);

      expect(it.fake.shows, 0);
    });

    test('앱으로 돌아오면 알림을 치운다', () async {
      final it = ready();
      it.state.wentBackground();
      it.state.handleEvent(const MessageReceived(
          channel: '#일반', sender: '두리', text: '밥 먹자', mine: false,
          isMention: false));
      await Future<void>.delayed(Duration.zero);
      expect(it.fake.showing, isNotNull);

      await it.state.cameBack();
      expect(it.fake.showing, isNull, reason: '읽을 수 있는 자리에 왔으면 치운다');
    });
  });
}
