/// 화면이 좁을 때와 넓을 때 둘 다 쓸 수 있는가.
///
/// 기기 수만큼 확인하지 않는다. 바 형태 폰은 전부 369~411dp라 사실상 하나이고,
/// 진짜 다른 건 폴드를 폈을 때(~832dp)뿐이다. 그 둘만 본다.
///
/// 특히 보는 것: **접었다 폈을 때 쓰던 글이 남아 있는가.** 레이아웃이 1칸↔2칸으로
/// 갈아끼워지는 순간이 위험한 자리다(PC 앱에서 창 크기를 바꿀 때 사고가 났던 것과
/// 같은 종류).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/app_state.dart';
import 'package:chupchat/ui/chat_page.dart';
import 'package:chupchat/ui/layout.dart';

/// 갤S23+ / S25+ / 폴드 접은 바깥 화면이 모두 들어가는 크기
const Size narrow = Size(393, 851);

/// 갤Z폴드 편 안쪽 화면 - 거의 정사각형이다
const Size unfolded = Size(832, 750);

Future<void> pumpAt(WidgetTester tester, Size size, Widget child) async {
  tester.view.physicalSize = size * tester.view.devicePixelRatio;
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: child));
  await tester.pump();
}

AppState sampleState() {
  final state = AppState();
  state.channels.addAll(['#일반', '#개발']);
  state.current = '#일반';
  state.members['#일반'] = ['몽키', '두리'];
  state.lines['#일반'] = [
    ChatLine.system(text: '#일반 입장 완료', at: DateTime.now()),
    ChatLine.message(
      sender: '두리',
      text: '안녕 다들 뭐해',
      mine: false,
      isMention: false,
      at: DateTime.now(),
    ),
  ];
  return state;
}

void main() {
  testWidgets('좁은 화면에서는 채널 목록을 서랍으로 숨긴다', (tester) async {
    await pumpAt(tester, narrow, ChatPage(state: sampleState()));
    // 서랍 안에 있으므로 평소에는 안 보인다
    expect(find.text('#개발'), findsNothing);
    expect(find.byTooltip('참여자'), findsOneWidget);
    expect(find.text('안녕 다들 뭐해'), findsOneWidget);
  });

  testWidgets('넓은 화면에서는 채널 목록이 옆에 펼쳐진다', (tester) async {
    await pumpAt(tester, unfolded, ChatPage(state: sampleState()));
    expect(find.text('#개발'), findsOneWidget, reason: '두 칸이면 채널이 바로 보여야 한다');
    expect(find.text('안녕 다들 뭐해'), findsOneWidget);
  });

  testWidgets('접었다 펴도 쓰던 글이 남는다', (tester) async {
    final state = sampleState();
    await pumpAt(tester, narrow, ChatPage(state: state));
    await tester.enterText(find.byType(TextField), '쓰다 만 글');
    await tester.pump();

    // 폈다
    tester.view.physicalSize = unfolded;
    await tester.pumpAndSettle();
    expect(find.text('쓰다 만 글'), findsOneWidget,
        reason: '레이아웃이 갈아끼워져도 입력 중이던 글이 날아가면 안 된다');

    // 다시 접었다
    tester.view.physicalSize = narrow;
    await tester.pumpAndSettle();
    expect(find.text('쓰다 만 글'), findsOneWidget);
  });

  testWidgets('글이 길어도 화면 밖으로 안 나간다', (tester) async {
    final state = sampleState();
    state.lines['#일반']!.add(ChatLine.message(
      sender: '몽키',
      text: '가나다라마바사' * 40,
      mine: true,
      isMention: false,
      at: DateTime.now(),
    ));
    await pumpAt(tester, narrow, ChatPage(state: state));
    await tester.pump();
    // 가로로 넘치면 Flutter 가 예외를 던진다. 여기까지 왔으면 안 넘친 것이다
    expect(tester.takeException(), isNull);
  });

  test('화면 가르는 기준이 폰과 펼친 폴드 사이에 있다', () {
    // 바 형태 폰(369~411)은 전부 좁은 쪽, 펼친 폴드(~832)만 넓은 쪽이어야 한다
    expect(wideBreakpoint, greaterThan(411));
    expect(wideBreakpoint, lessThan(750));
  });
}
