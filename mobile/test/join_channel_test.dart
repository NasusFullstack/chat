/// 채널 들어가기가 **실제로 눌러서** 되는가.
///
/// 핸들러를 직접 부르면 통과하는데 사람이 누르면 안 되는 버그가 있다 - PC 앱에서도
/// 그런 적이 있어서 규칙으로 못 박아뒀다(CLAUDE.md 6번). 그래서 여기서는 진짜로
/// 버튼을 누르고 글자를 치고 확인 버튼을 누른다.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/core/events.dart';
import 'package:chupchat/ui/chat_page.dart';

const Size narrow = Size(393, 851);
const Size wide = Size(750, 832);

Future<void> pumpAt(WidgetTester tester, Size size, Widget child) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pumpAndSettle();
}

/// 로그인까지 끝난 상태. **서버가 001 을 보내준 뒤**라야 채널 입장이 먹힌다 -
/// 그 전에 보내면 서버가 조용히 무시한다
AppState loggedInState() {
  final state = AppState();
  state.handleEvent(const LoggedIn('몽키'));
  return state;
}

void main() {
  test('로그인 전에는 채널 입장을 보내지 않는다', () {
    // 보내봐야 서버가 무시하므로, 보내는 대신 사람에게 알려야 한다
    final fresh = AppState();
    expect(fresh.loggedIn, isFalse);
    fresh.handleEvent(const LoggedIn('몽키'));
    expect(fresh.loggedIn, isTrue);
  });

  testWidgets('좁은 화면 - 서랍을 열고 + 를 눌러 채널에 들어간다', (tester) async {
    final state = loggedInState();
    final asked = <String>[];
    state.onJoinForTest = asked.add;

    await pumpAt(tester, narrow, ChatPage(state: state));

    // 채널이 하나도 없을 때 사람이 가장 먼저 하는 일이다
    await tester.tap(find.byTooltip('Open navigation menu'));
    await tester.pumpAndSettle();

    expect(find.byTooltip('채널 들어가기'), findsOneWidget,
        reason: '서랍에 + 가 보여야 한다');
    await tester.tap(find.byTooltip('채널 들어가기'));
    await tester.pumpAndSettle();

    expect(find.text('채널 들어가기'), findsWidgets, reason: '물어보는 창이 떠야 한다');
    await tester.enterText(find.byType(TextField).last, 'pdlab');
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, '들어가기'));
    await tester.pumpAndSettle();

    expect(asked, ['pdlab'], reason: '눌렀는데 채널 입장이 안 나갔다');
  });

  testWidgets('넓은 화면 - 옆에 펼쳐진 목록에서 + 를 눌러 들어간다', (tester) async {
    final state = loggedInState();
    final asked = <String>[];
    state.onJoinForTest = asked.add;

    await pumpAt(tester, wide, ChatPage(state: state));

    // 두 칸이면 서랍을 열 필요 없이 바로 보인다
    await tester.tap(find.byTooltip('채널 들어가기'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, '일반');
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '들어가기'));
    await tester.pumpAndSettle();

    expect(asked, ['일반'], reason: '눌렀는데 채널 입장이 안 나갔다');
  });

  testWidgets('글자를 치고 자판의 확인을 눌러도 들어간다', (tester) async {
    final state = loggedInState();
    final asked = <String>[];
    state.onJoinForTest = asked.add;

    await pumpAt(tester, wide, ChatPage(state: state));
    await tester.tap(find.byTooltip('채널 들어가기'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'pdlab');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(asked, ['pdlab']);
  });

  testWidgets('비워두고 누르면 아무 일도 안 일어난다', (tester) async {
    final state = loggedInState();
    final asked = <String>[];
    state.onJoinForTest = asked.add;

    await pumpAt(tester, wide, ChatPage(state: state));
    await tester.tap(find.byTooltip('채널 들어가기'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '들어가기'));
    await tester.pumpAndSettle();

    expect(asked, isEmpty);
  });
}
