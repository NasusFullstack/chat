/// 대기방 - 사람이 모이기를 기다렸다가 전투 화면으로 넘어간다.
///
/// PC 의 `gui/battle/lobby.py` 가 하는 일 중 **꼭 필요한 것만** 옮겼다.
/// 색 고르기와 연습 상대(AI) 넣기는 아직 없다 - 폰에서 처음 필요한 것은 "들어가서
/// 같이 싸우는 것"이고, 그 둘은 PC 에서 방을 열 때 정하면 모두에게 그대로 적용된다.
///
/// 시작은 **방을 연 사람만** 누를 수 있다(서버가 확인한다). 손님이 눌러도 서버가
/// 무시하므로, 애초에 단추를 안 보여준다 - 눌러도 아무 일이 없으면 고장으로 보인다.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../net/battle_link.dart';
import 'battle_page.dart';

class BattleLobbyPage extends StatefulWidget {
  const BattleLobbyPage({
    super.key,
    required this.room,
    required this.nick,
    required this.isHost,
  });

  final String room;
  final String nick;

  /// 방을 연 사람인가. 시작을 누를 수 있다
  final bool isHost;

  @override
  State<BattleLobbyPage> createState() => _BattleLobbyPageState();
}

class _BattleLobbyPageState extends State<BattleLobbyPage> {
  final BattleLink _link = BattleLink();
  StreamSubscription<BattleSignal>? _sub;

  int _mySlot = -1;
  final Map<int, String> _names = {};
  String _notice = '전투 서버에 붙는 중...';
  bool _gone = false;

  @override
  void initState() {
    super.initState();
    _sub = _link.signals.listen(_onSignal);
    _link.join(widget.room, widget.nick);
  }

  @override
  void dispose() {
    _sub?.cancel();
    // 전투 화면으로 넘어간 경우에는 연결을 그대로 넘겨준 것이라 여기서 닫지 않는다
    if (!_gone) _link.dispose();
    super.dispose();
  }

  void _onSignal(BattleSignal signal) {
    switch (signal) {
      case BattleJoined(:final slot, :final players):
        setState(() {
          _mySlot = slot;
          _names.clear();
          for (final one in players) {
            _names[one.slot] = one.nick;
          }
          _names[slot] = widget.nick;
          _notice = '';
        });
      case BattlePeerJoined(:final slot, :final nick):
        setState(() => _names[slot] = nick);
      case BattlePeerLeft(:final slot):
        setState(() => _names.remove(slot));
      case BattleStarted():
        _enterBattle();
      case BattleRefused(:final why):
        setState(() => _notice = why);
      case BattleFailed(:final why):
        setState(() => _notice = why);
      default:
        break;
    }
  }

  void _enterBattle() {
    if (_gone || _mySlot < 0 || !mounted) return;
    _gone = true;
    Navigator.pushReplacement(
      context,
      MaterialPageRoute<void>(
        builder: (_) => BattlePage(
          link: _link,
          mySlot: _mySlot,
          slots: _names.keys.toList()..sort(),
          names: Map<int, String>.of(_names),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final people = _names.keys.toList()..sort();
    final enough = people.length >= 2;
    return Scaffold(
      appBar: AppBar(title: const Text('배틀크루저 전투')),
      body: SafeArea(
        child: Column(
          children: [
            if (_notice.isNotEmpty)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(_notice,
                    style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('들어온 사람 ${people.length}명',
                    style: Theme.of(context).textTheme.labelLarge),
              ),
            ),
            Expanded(
              child: ListView(
                children: [
                  for (final slot in people)
                    ListTile(
                      leading: CircleAvatar(child: Text('${slot + 1}')),
                      title: Text(_names[slot] ?? ''),
                      trailing: slot == _mySlot ? const Text('나') : null,
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  if (widget.isHost)
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        // 둘은 돼야 전투가 된다. 혼자 시작하면 아무 일도 안 일어난다
                        onPressed: enough ? _link.startBattle : null,
                        child: Text(enough ? '시작하기' : '사람을 기다리는 중...'),
                      ),
                    )
                  else
                    Text('방을 연 사람이 시작하기를 누르면 시작됩니다.',
                        style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 8),
                  // 방 번호는 보여준다 - 채팅으로 알림이 안 간 사람에게 불러줄 수 있게
                  SelectableText('방 번호 ${widget.room}',
                      style: Theme.of(context).textTheme.labelSmall),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
