/// 시작 화면 - 켜자마자 보이는 첫 장면.
///
/// ## 왜 두나
/// 앱을 켜면 새 버전을 확인하는 데 잠깐 걸린다. 그동안 로그인 화면이 떠 있으면
/// 사람이 이름을 치기 시작하는데, 그때 업데이트 안내가 위로 덮친다. PC 앱도 같은
/// 이유로 시작 화면을 먼저 보여주고 그 위에 진행 상태를 쓴다.
///
/// 겸사겸사 "이게 무슨 앱이고 몇 버전이고 누가 만들었는지"를 한 번 보여준다.
library;

import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../net/updater.dart';
import 'update_sheet.dart';

/// 로고가 너무 빨리 사라지면 오히려 뭔가 잘못된 것처럼 보인다 - 최소한 이만큼은 보여준다
const Duration minimumShow = Duration(milliseconds: 900);

/// 켜는 동안 하는 일에 주는 **한계 시간**. 넘으면 그냥 로그인으로 보낸다.
///
/// 이게 없으면 플랫폼 호출 하나가 매달리는 것만으로 시작 화면에 갇힌다(실측: 검사
/// 환경에서 `getTemporaryDirectory()`가 영영 답하지 않아 25초를 밀어도 안 넘어갔다).
/// 사람 눈에는 "앱이 안 켜진다"로만 보이고 로그인조차 해볼 수 없다 - 새 버전을
/// 놓치는 것보다 훨씬 나쁘다. 새 버전 확인 자체도 12초까지 기다리므로 그보다는 길게.
const Duration bootCeiling = Duration(seconds: 15);

const String developer = 'NasusFullstack';
const int copyrightYear = 2026;

class SplashPage extends StatefulWidget {
  const SplashPage({super.key, required this.onDone});

  /// 확인이 끝나 로그인 화면으로 넘어갈 때.
  final VoidCallback onDone;

  @override
  State<SplashPage> createState() => _SplashPageState();
}

class _SplashPageState extends State<SplashPage> {
  String _version = '';
  String _status = '시작하는 중...';

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    // 로고를 최소 이만큼은 보여준다. 시계를 두 번 읽어 남은 시간을 빼는 방식은
    // 쓰지 않는다 - 확인이 오래 걸린 경우와 구분이 안 되고, 재는 사이에 시간이
    // 어긋난다. 그냥 **같이 출발시켜** 둘 다 끝나기를 기다리면 된다
    final shown = Future<void>.delayed(minimumShow);

    // 한계 시간을 넘으면 확인을 포기하고 들어간다 - 여기서 갇히면 안 된다
    final found =
        await _lookForUpdate().timeout(bootCeiling, onTimeout: () => null);

    await shown;
    if (!mounted) return;

    if (found == null) {
      // 최신이거나 못 물어봤거나 너무 오래 걸렸다 - 어느 쪽이든 그냥 들어간다
      widget.onDone();
      return;
    }
    setState(() => _status = '새 버전 ${found.version}');
    await showUpdate(context, found);
    if (mounted) widget.onDone();
  }

  /// 버전을 읽고 새 버전이 있는지 본다. 없거나 못 물어봤으면 null.
  Future<Available?> _lookForUpdate() async {
    // 버전을 **가장 먼저** 읽는다. 이 화면이 하는 일이 그걸 보여주는 것이므로,
    // 뒷정리 같은 것을 먼저 하면 그 사이에는 버전 자리가 비어 보인다
    final info = await PackageInfo.fromPlatform();
    if (!mounted) return null;
    setState(() {
      _version = info.version;
      _status = '새 버전 확인 중...';
    });

    final updater = Updater();
    // 지난번에 받아둔 설치 파일이 있으면 치운다(50MB짜리가 남아 있을 이유가 없다)
    await updater.cleanLeftover();
    return updater.check(info.version);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Image.asset('assets/logo.png',
                        width: 128,
                        height: 128,
                        filterQuality: FilterQuality.medium),
                    const SizedBox(height: 18),
                    Text('춥채팅',
                        style: Theme.of(context).textTheme.headlineSmall),
                    const SizedBox(height: 4),
                    Text(_version.isEmpty ? '' : 'v$_version',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            )),
                    const SizedBox(height: 28),
                    SizedBox(
                      width: 180,
                      child: LinearProgressIndicator(
                        minHeight: 3,
                        backgroundColor: scheme.surfaceContainerHighest,
                      ),
                    ),
                    const SizedBox(height: 10),
                    Text(_status,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: scheme.onSurfaceVariant,
                            )),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Column(
                children: [
                  Text('made by $developer',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          )),
                  const SizedBox(height: 2),
                  Text('© $copyrightYear $developer',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: scheme.onSurfaceVariant.withValues(alpha: 0.6),
                          )),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
