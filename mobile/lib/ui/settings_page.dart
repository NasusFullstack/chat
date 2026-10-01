/// 설정 - 알림과 접속 유지를 켜고 끈다.
///
/// PC 앱의 환경설정과 같은 자리다. 한쪽에만 있는 설정을 만들지 않는다.
///
/// 고치면 **그 자리에서** 적용한다(확인 버튼이 따로 없다). 접속 유지를 껐는데
/// "실행 중" 알림이 남아 있으면 끈 것처럼 보이지 않기 때문이다.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../login_store.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.state});

  final AppState state;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  /// 기억해둔 접속 - 자동으로 들어갈지를 여기서 끈다
  LastLogin _last = const LastLogin();

  @override
  void initState() {
    super.initState();
    loadLastLogin().then((loaded) {
      if (mounted) setState(() => _last = loaded);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('설정')),
      body: SafeArea(
        child: ListView(
          children: [
            const _Heading('접속'),
            const _Note('홈으로 나가면 접속이 끊깁니다. 안드로이드가 화면에서 사라진 앱을 '
                '멈추기 때문입니다 - 앱을 다시 열면 알아서 다시 붙고, 그동안 오간 '
                '이야기도 채워집니다.\n'
                '앱을 꺼둔 동안에도 알림을 받는 방법은 따로 준비하고 있습니다.'),
            SwitchListTile(
              value: _last.auto,
              onChanged: (on) async {
                setState(() => _last = LastLogin(
                      host: _last.host,
                      port: _last.port,
                      nick: _last.nick,
                      secure: _last.secure,
                      auto: on,
                    ));
                await saveAutoLogin(on);
              },
              title: const Text('켤 때 알아서 들어가기'),
              subtitle: Text(_last.nick.isEmpty
                  ? '한 번 들어가면 그 이름을 기억합니다'
                  : '기억한 이름: ${_last.nick}'),
            ),
            const _Note('들어갔던 채널도 이름마다 따로 기억해서 다시 들어갑니다. '
                '같은 폰을 두 이름으로 쓰면 각각 따로 기억합니다.'),
          ],
        ),
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 18, 16, 6),
        child: Text(text,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: Theme.of(context).colorScheme.primary,
                )),
      );
}

class _Note extends StatelessWidget {
  const _Note(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 14),
        child: Text(text.replaceAll('**', ''),
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                )),
      );
}
