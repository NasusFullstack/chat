/// 설정 - 접속에 관한 것을 켜고 끈다.
///
/// PC 앱의 환경설정과 같은 자리다. 한쪽에만 있는 설정을 만들지 않는다.
///
/// 고치면 **그 자리에서** 적용한다(확인 버튼이 따로 없다).
///
/// ## **지금 쓰는 쪽의 설정**만 만진다
/// IRC 설정과 서버 채팅 설정은 따로다(`login_store.dart`). 여기서 쪽을 안 보고
/// 고치면, 서버 채팅으로 들어와 있는데 IRC 쪽 설정이 바뀌고 화면에는 IRC 쪽 이름이
/// 보인다 - 사람은 자기가 무엇을 고쳤는지 알 수 없다.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/chat_port.dart';
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

  /// 지금 쓰는 쪽. 이 쪽의 설정만 보여주고 고친다
  ChatKind get _kind => widget.state.chatKind;

  @override
  void initState() {
    super.initState();
    loadLastLogin(_kind).then((loaded) {
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
            // **어느 쪽 설정인지 먼저 밝힌다.** 둘이 따로이므로, 안 밝히면 여기서
            // 고친 것이 왜 다른 쪽에 안 보이는지 알 수 없다
            _Heading('접속 - ${_kind.label}'),
            const _Note('홈으로 나가면 접속이 끊깁니다. 안드로이드가 화면에서 사라진 앱을 '
                '멈추기 때문입니다 - 앱을 다시 열면 알아서 다시 붙고, 그동안 오간 '
                '이야기도 채워집니다.\n'
                '앱을 꺼둔 동안에도 알림을 받는 방법은 따로 준비하고 있습니다.'),
            if (_kind == ChatKind.server)
              const _Note('**서버 채팅은 켤 때 알아서 들어갈 수 없습니다.** 비밀번호를 '
                  '기기에 저장하지 않기 때문입니다 - 아이디는 기억해 두고 비밀번호만 '
                  '받습니다.')
            else
              SwitchListTile(
                value: _last.auto,
                onChanged: (on) async {
                  setState(() => _last = _last.copyWith(auto: on));
                  await saveAutoLogin(on, _kind);
                },
                title: const Text('켤 때 알아서 들어가기'),
                subtitle: Text(_last.nick.isEmpty
                    ? '한 번 들어가면 그 이름을 기억합니다'
                    : '기억한 이름: ${_last.nick}'),
              ),
            const _Note('들어갔던 채널도 이름마다 따로 기억해서 다시 들어갑니다. '
                '같은 폰을 두 이름으로 쓰면 각각 따로 기억합니다.'),
            if (_kind == ChatKind.server)
              const _Note('서버 채팅에서는 지난 대화를 **서버가 들고 있습니다**(하루치). '
                  '방에 들어가면 같이 따라옵니다.')
            else
              const _Note('IRC 에서는 지난 대화를 각자 올린 것을 모아서 받아옵니다 - '
                  '아무도 없던 동안의 이야기는 남지 않습니다.'),
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
