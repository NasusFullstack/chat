/// 시작 화면이 **반드시 끝나는가**.
///
/// 가장 무서운 고장은 여기서 멈추는 것이다. 버전 확인이 안 되거나 인터넷이 없을 때
/// 시작 화면에 머물러 버리면 사람 눈에는 "앱이 안 켜진다"로만 보이고, 로그인조차
/// 해볼 수 없다. PC 앱에서도 같은 사고가 있었다(CLAUDE.md 2번 - 업데이트가 실패하는
/// 환경에서 앱을 한 번도 못 보여줬다).
///
/// 검사 환경에서는 인터넷이 막혀 있고, 게다가 `getTemporaryDirectory()`가 **영영
/// 답하지 않는다**(실측). 그래서 이 검사가 통과한다는 것은 곧 "플랫폼 호출 하나가
/// 매달려도 켜진다"는 뜻이다 - 시작 화면의 한계 시간(`bootCeiling`)이 그걸 지킨다.
///
/// **pumpAndSettle 을 쓰지 말 것.** 진행 막대가 끝없이 돌기 때문에 영원히 안 멈춘다
/// (실제로 타임아웃으로 세 개가 한꺼번에 실패했다). 시간을 정해 밀어주는 pump 를 쓴다.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:chupchat/ui/splash_page.dart';

/// 한계 시간까지 넉넉히 밀어준다. 남은 타이머를 비우는 데도 쓴다
/// (안 비우면 "A Timer is still pending"으로 실패한다).
Future<bool> pumpPastBoot(WidgetTester tester, bool Function() done) async {
  final until = bootCeiling + minimumShow + const Duration(seconds: 2);
  for (var spent = Duration.zero; spent < until;) {
    if (done()) return true;
    await tester.pump(const Duration(milliseconds: 250));
    spent += const Duration(milliseconds: 250);
  }
  return done();
}

void main() {
  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: '춥채팅',
      packageName: 'kr.pdlab.chupchat',
      version: '2.6.6',
      buildNumber: '1',
      buildSignature: '',
    );
  });

  testWidgets('로고와 버전과 만든 사람이 보인다', (tester) async {
    var done = false;
    await tester
        .pumpWidget(MaterialApp(home: SplashPage(onDone: () => done = true)));
    await tester.pump();  // 버전을 읽어오는 한 틱

    expect(find.byType(Image), findsOneWidget, reason: '로고가 있어야 한다');
    expect(find.text('춥채팅'), findsOneWidget);
    expect(find.text('v2.6.6'), findsOneWidget, reason: '버전은 앱이 스스로 읽는다');
    expect(find.text('made by $developer'), findsOneWidget);
    expect(find.text('© $copyrightYear $developer'), findsOneWidget);

    await pumpPastBoot(tester, () => done);
  });

  testWidgets('확인이 막혀도 로그인 화면으로 넘어간다', (tester) async {
    var done = false;
    await tester
        .pumpWidget(MaterialApp(home: SplashPage(onDone: () => done = true)));

    // 로고가 깜빡이고 사라지면 오히려 고장난 것처럼 보인다 - 최소 시간은 지켜야 한다
    await tester.pump(const Duration(milliseconds: 100));
    expect(done, isFalse, reason: '로고를 보여주기도 전에 넘어가면 깜빡인 것처럼 보인다');

    expect(await pumpPastBoot(tester, () => done), isTrue,
        reason: '시작 화면에서 멈추면 사람 눈에는 앱이 안 켜지는 것이다');
  });

  testWidgets('버전을 읽기 전에도 화면이 깨지지 않는다', (tester) async {
    // 버전은 비동기로 온다. 그 전에 그려지는 한 프레임이 반드시 있다
    var done = false;
    await tester
        .pumpWidget(MaterialApp(home: SplashPage(onDone: () => done = true)));
    expect(tester.takeException(), isNull);
    expect(find.text('춥채팅'), findsOneWidget);
    expect(find.text('v2.6.6'), findsNothing, reason: '아직 안 읽었으면 비어 있어야 한다');

    await pumpPastBoot(tester, () => done);
  });
}
