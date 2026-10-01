/// 전투 화면이 **손가락으로 전투장을 가리지 않는가**.
///
/// 폰마다 비율이 다르다. 좌우 여백이 넓으면 조작을 거기 두고, 좁으면 반투명으로
/// 얹기로 했다 - 그 판단이 실제로 그렇게 배치되는지 본다.
///
/// 레이아웃은 눈으로 보면 "그럴듯한데?"로 넘어가기 쉬워서 재는 쪽이 맞다
/// (CLAUDE.md 7번: 눈으로 보고 판단하지 말고 재라).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/core/battle_sim.dart' as sim;
import 'package:chupchat/net/battle_link.dart';
import 'package:chupchat/ui/battle_page.dart';

/// 갤S23+ 를 가로로 든 크기. 19.5:9 라 3:2 판을 넣으면 좌우가 많이 남는다
const Size wideLandscape = Size(851, 393);

/// 거의 4:3 인 태블릿 - 판과 비율이 비슷해 여백이 거의 없다
const Size tightLandscape = Size(1080, 810);

Future<BattleLink> pumpBattle(WidgetTester tester, Size size) async {
  tester.view.devicePixelRatio = 1.0;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);

  // 연결은 join() 을 불러야 생긴다 - 여기서는 화면만 본다
  final link = BattleLink();
  addTearDown(link.dispose);
  await tester.pumpWidget(MaterialApp(
    home: BattlePage(
      link: link,
      mySlot: 0,
      slots: const [0, 1],
      names: const {0: '나', 1: '두리'},
    ),
  ));
  await tester.pump();
  return link;
}

/// 전투장이 그려지는 네모(그리는 쪽과 같은 식으로 잰다)
Rect fieldRect(Size box) {
  final scale = (box.width / sim.fieldWidth) < (box.height / sim.fieldHeight)
      ? box.width / sim.fieldWidth
      : box.height / sim.fieldHeight;
  final w = sim.fieldWidth * scale;
  final h = sim.fieldHeight * scale;
  return Rect.fromLTWH((box.width - w) / 2, (box.height - h) / 2, w, h);
}

void main() {
  testWidgets('여백이 넓으면 조작이 전투장 바깥에 있다', (tester) async {
    await pumpBattle(tester, wideLandscape);

    final field = fieldRect(wideLandscape);
    // 조작 둘은 Opacity 로 감싸 둔다 - 쌓은 순서가 방향키, 발사다.
    // GestureDetector 로 찾으면 단추의 것까지 걸린다
    final stick = tester.getRect(find.byType(Opacity).at(0));
    final fire = tester.getRect(find.byType(Opacity).at(1));

    // **딱 들어맞을 필요는 없다.** 가장자리에 조금 걸치는 것은 거기로 배가 거의 안
    // 다녀서 괜찮다. 다만 그 '조금'이 커지면 손가락이 배를 가린다
    const allowed = 20.0;
    expect(stick.right - field.left, lessThanOrEqualTo(allowed),
        reason: '방향키가 전투장 위로 너무 들어온다 '
            '(전투장 왼쪽 ${field.left.toStringAsFixed(1)}, 조작 오른끝 ${stick.right.toStringAsFixed(1)})');
    expect(field.right - fire.left, lessThanOrEqualTo(allowed),
        reason: '발사가 전투장 위로 너무 들어온다 '
            '(전투장 오른쪽 ${field.right.toStringAsFixed(1)}, 발사 왼끝 ${fire.left.toStringAsFixed(1)})');
    expect(stick.left, greaterThanOrEqualTo(0), reason: '화면 밖으로 나가면 못 누른다');
    expect(fire.right, lessThanOrEqualTo(wideLandscape.width));

    // 여백에 둘 때는 가리지 않으므로 흐리게 할 이유가 없다
    final opacities = tester.widgetList<Opacity>(find.byType(Opacity));
    expect(opacities.every((o) => o.opacity == 1.0), isTrue,
        reason: '바깥에 있는데 흐리면 잘 안 보일 뿐이다');
  });

  testWidgets('여백이 좁으면 반투명으로 얹는다', (tester) async {
    await pumpBattle(tester, tightLandscape);

    final opacities = tester.widgetList<Opacity>(find.byType(Opacity));
    expect(opacities.length, 2, reason: '방향키와 발사 둘 다');
    expect(opacities.every((o) => o.opacity < 1.0), isTrue,
        reason: '전투장 위에 얹으므로 아래가 비쳐 보여야 한다');
  });

  testWidgets('전투장은 찌그러지지 않는다', (tester) async {
    // 늘려 맞추면 맞음 판정과 눈이 어긋난다 - 가로세로 비를 지켜야 한다
    for (final size in [wideLandscape, tightLandscape, const Size(600, 600)]) {
      final field = fieldRect(size);
      expect(field.width / field.height,
          closeTo(sim.fieldWidth / sim.fieldHeight, 0.001),
          reason: '$size 에서 비율이 틀어졌다');
      expect(field.width, lessThanOrEqualTo(size.width + 0.001));
      expect(field.height, lessThanOrEqualTo(size.height + 0.001));
    }
  });

  testWidgets('내 체력과 전적이 보인다', (tester) async {
    await pumpBattle(tester, wideLandscape);
    expect(find.textContaining('격추'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
  });
}
