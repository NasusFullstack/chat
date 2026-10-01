/// 채팅 화면 - 좁으면 한 칸, 넓으면 두 칸.
///
/// 레이아웃만 갈리고 **상태는 하나**다(`AppState`). 그래서 폴드를 접었다 펴도 보던
/// 내용과 쓰던 글이 그대로 남는다 - 레이아웃이 바뀌는 순간이 위험한 자리라, 그때
/// 다시 만들어지는 것을 최대한 줄였다.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import 'layout.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key, required this.state});

  final AppState state;

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  // 입력 중인 글과 스크롤 위치는 **화면 바깥**에 둔다. 폴드를 펴면서 레이아웃이
  // 1칸 <-> 2칸으로 갈아끼워질 때 쓰던 글이 날아가지 않게
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onChanged);
  }

  @override
  void dispose() {
    widget.state.removeListener(_onChanged);
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onChanged() {
    if (!mounted) return;
    setState(() {});
    // 새 줄이 오면 맨 아래로. 위를 보고 있을 때는 끌어내리지 않는다
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final pos = _scroll.position;
      if (pos.pixels > pos.maxScrollExtent - 160) {
        _scroll.jumpTo(pos.maxScrollExtent);
      }
    });
  }

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty) return;
    widget.state.sendChat(text);
    _input.clear();
  }

  Future<void> _askChannel() async {
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
    if (name != null && name.trim().isNotEmpty) {
      widget.state.joinChannel(name.trim());
    }
  }

  void _showMembers() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => _MemberList(state: widget.state),
    );
  }

  @override
  Widget build(BuildContext context) {
    final wide = isWide(context);
    final state = widget.state;
    final body = Column(
      children: [
        Expanded(child: _Messages(state: state, scroll: _scroll)),
        _InputRow(controller: _input, onSend: _send, enabled: state.current.isNotEmpty),
      ],
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(state.current.isEmpty ? '춥채팅' : state.current),
        actions: [
          IconButton(
            onPressed: state.current.isEmpty ? null : _showMembers,
            icon: const Icon(Icons.people_outline),
            tooltip: '참여자',
          ),
        ],
      ),
      // 좁은 화면에서는 채널 목록을 서랍으로 숨긴다. 넓으면 왼쪽에 펼쳐 둔다
      drawer: wide
          ? null
          : Drawer(child: _ChannelList(state: state, onAdd: _askChannel)),
      body: SafeArea(
        child: wide
            ? Row(
                children: [
                  SizedBox(
                    width: sidePaneWidth,
                    child: _ChannelList(state: state, onAdd: _askChannel),
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(child: body),
                ],
              )
            : body,
      ),
    );
  }
}

class _ChannelList extends StatelessWidget {
  const _ChannelList({required this.state, required this.onAdd});

  final AppState state;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          ListTile(
            title: const Text('채널'),
            trailing: IconButton(
              onPressed: onAdd,
              icon: const Icon(Icons.add),
              tooltip: '채널 들어가기',
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: state.channels.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: Text('아직 들어간 채널이 없습니다.\n+ 를 눌러 들어가세요.',
                          textAlign: TextAlign.center),
                    ),
                  )
                : ListView.builder(
                    itemCount: state.channels.length,
                    itemBuilder: (_, i) {
                      final channel = state.channels[i];
                      final count = state.unread[channel] ?? 0;
                      return ListTile(
                        selected: channel == state.current,
                        title: Text(channel),
                        trailing: count > 0
                            ? Badge(label: Text('$count'))
                            : null,
                        onTap: () {
                          state.showChannel(channel);
                          // 서랍으로 열려 있던 경우에만 닫는다
                          final nav = Navigator.of(context);
                          if (nav.canPop()) nav.pop();
                        },
                        onLongPress: () => state.leaveChannel(channel),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _MemberList extends StatelessWidget {
  const _MemberList({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final people = state.members[state.current] ?? const <String>[];
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(title: Text('참여자 ${people.length}명')),
          const Divider(height: 1),
          Flexible(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: people.length,
              itemBuilder: (_, i) => ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(people[i]),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Messages extends StatelessWidget {
  const _Messages({required this.state, required this.scroll});

  final AppState state;
  final ScrollController scroll;

  @override
  Widget build(BuildContext context) {
    final lines = state.lines[state.current] ?? const <ChatLine>[];
    if (lines.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            state.current.isEmpty
                ? '채널에 들어가면 여기에 이야기가 쌓입니다.'
                : '아직 아무 말도 없습니다.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        ),
      );
    }
    return ListView.builder(
      controller: scroll,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: lines.length,
      itemBuilder: (_, i) => _Line(line: lines[i]),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.line});

  final ChatLine line;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (line.isSystem) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Text(
          line.text,
          textAlign: TextAlign.center,
          style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${line.sender}: ',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              color: line.mine ? scheme.primary : scheme.tertiary,
            ),
          ),
          // 긴 글이 화면 밖으로 나가지 않게 남은 폭을 전부 준다
          Expanded(
            child: Text(
              line.text,
              style: line.isMention
                  ? TextStyle(
                      backgroundColor: scheme.primaryContainer,
                      color: scheme.onPrimaryContainer,
                    )
                  : null,
            ),
          ),
        ],
      ),
    );
  }
}

class _InputRow extends StatelessWidget {
  const _InputRow({
    required this.controller,
    required this.onSend,
    required this.enabled,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 8, 10),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              enabled: enabled,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => onSend(),
              decoration: InputDecoration(
                isDense: true,
                hintText: enabled ? '메시지 입력' : '채널에 먼저 들어가세요',
                border: const OutlineInputBorder(),
              ),
            ),
          ),
          IconButton(
            onPressed: enabled ? onSend : null,
            icon: const Icon(Icons.send),
            tooltip: '보내기',
          ),
        ],
      ),
    );
  }
}
