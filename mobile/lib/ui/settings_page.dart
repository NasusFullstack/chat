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

  Future<void> _change(void Function() edit) async {
    setState(edit);
    await widget.state.applySettings();
  }

  @override
  Widget build(BuildContext context) {
    final prefs = widget.state.prefs;
    return Scaffold(
      appBar: AppBar(title: const Text('설정')),
      body: SafeArea(
        child: ListView(
          children: [
            const _Heading('알림'),
            SwitchListTile(
              value: prefs.notify,
              onChanged: (on) => _change(() => prefs.notify = on),
              title: const Text('새 말이 오면 알림'),
              subtitle: const Text('앱을 보고 있을 때는 울리지 않습니다'),
            ),
            SwitchListTile(
              value: prefs.notifyDetail,
              // 알림을 껐으면 내용 표시를 만질 이유가 없다
              onChanged: prefs.notify
                  ? (on) => _change(() => prefs.notifyDetail = on)
                  : null,
              title: const Text('알림에 내용까지 보이기'),
              subtitle: const Text('끄면 누가 말했는지만 알립니다'),
            ),
            const _Note('알림은 **최신 하나만** 보입니다. 말이 오는 대로 쌓으면 '
                '수다 한 번에 알림이 수십 개가 되기 때문입니다.'),
            const Divider(),
            const _Heading('접속'),
            SwitchListTile(
              value: prefs.keepAlive,
              onChanged: (on) => _change(() => prefs.keepAlive = on),
              title: const Text('홈으로 나가도 접속 유지'),
              subtitle: const Text('끄면 홈으로 나가는 순간 접속이 끊기고 알림도 안 옵니다'),
            ),
            const _Note('유지하는 동안 안드로이드는 춥채팅을 "실행 중"으로 표시합니다. '
                '기기와 버전에 따라 알림으로 보이기도 하고, 설정의 '
                '"활성 앱"에만 잡히기도 합니다.\n'
                '최근 앱 목록에서 밀어서 끄면 접속도 같이 끊깁니다.'),
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
