/// 얼굴(프로필 아이콘)이 **보이는가**, 그리고 **글과 가운데가 맞는가**.
///
/// 둘 다 실제 신고에서 나온 것이다:
///  - "모바일은 프로필이 안 불러와지네" - 서버에서 받아놓고 목록이 기본 아이콘만
///    그리고 있었다
///  - "프로필이 중앙이 아니라 좀 기울어져 있는 것 같기도" - 재보니 얼굴 가운데가
///    첫 줄 글 가운데보다 3px 내려앉아 있었다(CLAUDE.md 7번: 눈으로 보지 말고 재라)
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/ui/chat_page.dart';

/// 1x1 투명 PNG - 아이콘이 왔다는 것만 확인하면 되므로 가장 작은 것을 쓴다
const String tinyPng =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==';

AppState chatting() {
  final state = AppState();
  state.handleEvent(const LoggedIn('나'));
  state.handleEvent(const ChannelJoined('#일반', '입장'));
  state.handleEvent(const MessageReceived(
      channel: '#일반', sender: '두리', text: '한 줄', mine: false, isMention: false));
  return state;
}

Future<void> pumpChat(WidgetTester tester, AppState state) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = const Size(393, 851);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: ChatPage(state: state)));
  await tester.pump();
}

void main() {
  testWidgets('얼굴 가운데가 첫 줄 글 가운데와 맞는다', (tester) async {
    await pumpChat(tester, chatting());

    final face = tester.getRect(find.byType(CircleAvatar).first);
    // 말풍선 안의 글만 고른다 - 앱바 제목도 RichText 다
    final said = find.byWidgetPredicate(
        (w) => w is RichText && w.text.toPlainText().contains('두리'));
    final text = tester.getRect(said.first);

    expect((face.center.dy - text.center.dy).abs(), lessThan(0.5),
        reason: '어긋나면 이름이 얼굴보다 위에 떠 있는 것처럼 보인다 '
            '(얼굴 ${face.height}px / 첫 줄 ${text.height}px)');
  });

  testWidgets('참여자 목록이 서버에서 받아온 얼굴을 보여준다', (tester) async {
    final state = chatting();
    state.avatars['두리'] = tinyPng;
    state.handleEvent(const UserlistUpdated('#일반', ['나', '두리']));
    await pumpChat(tester, state);

    await tester.tap(find.byTooltip('참여자'));
    await tester.pumpAndSettle();

    expect(find.text('두리'), findsWidgets);
    // 받아온 아이콘이 실제로 그려졌는가 - 기본 사람 모양만 그리던 버그를 잡는다
    final faces = tester.widgetList<CircleAvatar>(find.byType(CircleAvatar));
    expect(faces.any((f) => f.backgroundImage != null), isTrue,
        reason: '아이콘을 받아놓고 안 그리면 "프로필이 안 불러와진다"가 된다');
  });
}
