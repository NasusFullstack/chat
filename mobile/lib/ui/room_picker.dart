/// 들어갈 방 고르기 - **서버에 있는 방을 보고** 고른다.
///
/// 예전에는 방 이름을 글자로 쳐야 했다. 이름을 모르면 들어갈 수가 없고, 폰에서 글자를
/// 치는 것은 번거롭다. 서버 채팅은 서버가 방을 들고 있으므로 목록을 물어볼 수 있다.
///
/// **화면은 "지금 서버 채팅인가"를 묻지 않는다.** `state.canListRooms` 로 "목록을
/// 보여줄 수 있나"를 묻는다 - 그래야 프로토콜이 늘어도 여기는 안 바뀐다. 목록을 못
/// 주는 쪽(IRC)에서는 예전처럼 이름을 받는다.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/events.dart';

/// 방을 고르게 하고 고른 이름을 돌려준다. 그만두면 null.
Future<({String name, String key})?> pickRoom(
    BuildContext context, AppState state) async {
  if (!state.canListRooms) {
    final typed = await _askName(context);
    return typed == null ? null : (name: typed, key: '');
  }
  state.refreshRoomList();
  if (!context.mounted) return null;
  return showModalBottomSheet<({String name, String key})>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _RoomSheet(state: state),
  );
}

/// 이름을 글자로 받는다(목록을 못 주는 쪽).
Future<String?> _askName(BuildContext context) async {
  final controller = TextEditingController();
  final name = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('채널 들어가기'),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: const InputDecoration(
          hintText: '일반',
          helperText: '# 은 안 붙여도 됩니다',
        ),
        onSubmitted: (v) => Navigator.pop(ctx, v),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, controller.text),
          child: const Text('들어가기'),
        ),
      ],
    ),
  );
  final trimmed = name?.trim() ?? '';
  return trimmed.isEmpty ? null : trimmed;
}

class _RoomSheet extends StatefulWidget {
  const _RoomSheet({required this.state});

  final AppState state;

  @override
  State<_RoomSheet> createState() => _RoomSheetState();
}

class _RoomSheetState extends State<_RoomSheet> {
  final _newRoom = TextEditingController();

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onChanged);
  }

  @override
  void dispose() {
    widget.state.removeListener(_onChanged);
    _newRoom.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  /// 비밀번호가 걸린 방이면 받아서 같이 넘긴다.
  Future<void> _enter(RoomInfo room) async {
    if (!room.locked) {
      Navigator.pop(context, (name: room.name, key: ''));
      return;
    }
    final controller = TextEditingController();
    final key = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${room.name} 비밀번호'),
        content: TextField(
          controller: controller,
          autofocus: true,
          obscureText: true,
          onSubmitted: (v) => Navigator.pop(ctx, v),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('취소')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text),
            child: const Text('들어가기'),
          ),
        ],
      ),
    );
    if (key == null || !mounted) return;
    Navigator.pop(context, (name: room.name, key: key));
  }

  void _makeNew() {
    final name = _newRoom.text.trim();
    if (name.isEmpty) return;
    // **없으면 서버가 만든다** - 따로 '만들기'가 없다(IRC 처럼 들어가면 곧 생긴다)
    Navigator.pop(context, (name: name, key: ''));
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final rooms = state.roomList;
    final already = state.channels.toSet();
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text('방 고르기',
                      style: Theme.of(context).textTheme.titleLarge),
                ),
                IconButton(
                  tooltip: '다시 받아오기',
                  onPressed: state.roomListLoading ? null : state.refreshRoomList,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 4),
            if (state.roomListLoading && rooms.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 28),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (rooms.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Text('아직 만들어진 방이 없습니다. 아래에 이름을 적으면 새로 만듭니다.'),
              )
            else
              ConstrainedBox(
                // 방이 많아도 화면을 다 먹지 않게. 아래 '새 방' 칸이 늘 보여야 한다
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.of(context).size.height * 0.45,
                ),
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: rooms.length,
                  itemBuilder: (_, i) {
                    final room = rooms[i];
                    final joined = already.contains(room.name);
                    return ListTile(
                      leading: Icon(room.locked ? Icons.lock_outline : Icons.tag),
                      title: Text(room.name),
                      subtitle: Text(room.users == 0
                          ? '아무도 없음'
                          : '${room.users}명 있음'),
                      // 이미 들어가 있는 방은 그렇다고 알려준다 - 눌러도 되지만
                      // "아무 일도 안 일어난다"로 보이지 않게
                      trailing: joined
                          ? const Text('들어가 있음')
                          : const Icon(Icons.chevron_right),
                      onTap: () => _enter(room),
                    );
                  },
                ),
              ),
            const Divider(height: 24),
            TextField(
              controller: _newRoom,
              decoration: InputDecoration(
                labelText: '새 방 만들기',
                helperText: '한글 이름도 됩니다',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.arrow_forward),
                  onPressed: _makeNew,
                ),
              ),
              onSubmitted: (_) => _makeNew(),
            ),
          ],
        ),
      ),
    );
  }
}
