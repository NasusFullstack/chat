/// 새 버전 안내 - 무엇이 바뀌었는지 보여주고, 받는 동안 진행률을 보여준다.
///
/// 받는 데 한참 걸린다(50MB쯤). 아무 표시가 없으면 멈춘 줄 알고 앱을 꺼버린다 -
/// 그러면 받던 게 다 날아간다. 그래서 몇 %인지, 몇 MB 중 몇 MB인지 같이 보여준다.
library;

import 'dart:io';

import 'package:flutter/material.dart';

import '../net/relay_api.dart' show readable;
import '../net/updater.dart';

/// 새 버전이 있으면 안내를 띄운다. 없으면 아무 일도 안 한다.
Future<void> showUpdate(BuildContext context, Available found) {
  return showModalBottomSheet<void>(
    context: context,
    isDismissible: false,
    enableDrag: false,
    showDragHandle: true,
    builder: (_) => _UpdateSheet(found: found),
  );
}

class _UpdateSheet extends StatefulWidget {
  const _UpdateSheet({required this.found});

  final Available found;

  @override
  State<_UpdateSheet> createState() => _UpdateSheetState();
}

class _UpdateSheetState extends State<_UpdateSheet> {
  final Updater _updater = Updater();
  bool _busy = false;
  bool _cancelled = false;
  int _got = 0;
  int _total = 0;
  String _problem = '';

  Future<void> _start() async {
    setState(() {
      _busy = true;
      _cancelled = false;
      _problem = '';
      _got = 0;
      _total = 0;
    });

    final file = await _updater.download(
      widget.found.url,
      (got, total) {
        if (!mounted) return;
        setState(() {
          _got = got;
          _total = total;
        });
      },
      cancelled: () => _cancelled,
    );
    if (!mounted) return;

    if (_cancelled) {
      setState(() => _busy = false);
      return;
    }
    if (file == null) {
      setState(() {
        _busy = false;
        _problem = '받지 못했습니다. 인터넷을 확인하고 다시 시도해 주세요.';
      });
      return;
    }

    final problem = await _updater.install(file);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _problem = problem;
    });
  }

  @override
  Widget build(BuildContext context) {
    final percent = _total > 0 ? (_got * 100 ~/ _total) : 0;
    final notes = widget.found.notes.trim();
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('새 버전 ${widget.found.version}',
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 10),
            if (notes.isNotEmpty)
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: SingleChildScrollView(
                  child: Text(notes,
                      style: Theme.of(context).textTheme.bodySmall),
                ),
              ),
            const SizedBox(height: 16),
            if (_busy) ...[
              // 받는 중 - 몇 %인지와 몇 MB인지 둘 다 보여준다. %만 있으면 큰 파일에서
              // 1%가 한참 안 움직여 멈춘 것처럼 보인다
              LinearProgressIndicator(
                  value: _total > 0 ? _got / _total : null),
              const SizedBox(height: 6),
              Text(
                _total > 0
                    ? '$percent%  (${readable(_got)} / ${readable(_total)})'
                    : '받는 중...',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => setState(() => _cancelled = true),
                  child: const Text('취소'),
                ),
              ),
            ] else ...[
              if (_problem.isNotEmpty) ...[
                Text(_problem,
                    style: TextStyle(color: Theme.of(context).colorScheme.error)),
                const SizedBox(height: 10),
              ],
              Row(
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('나중에'),
                  ),
                  const Spacer(),
                  FilledButton(
                    onPressed: _start,
                    child: Text(_problem.isEmpty ? '받아서 설치' : '다시 시도'),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                // 처음 받는 사람은 "설치 화면이 왜 또 뜨지?" 하게 된다. 미리 말해준다
                '마지막 설치 버튼은 직접 눌러야 합니다(안드로이드 규칙). '
                '처음에는 "이 앱의 설치 허용"도 한 번 켜야 합니다.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// 받은 파일을 치운다 - 설치가 끝나면 50MB를 들고 있을 이유가 없다.
Future<void> cleanDownloaded(File? file) async {
  try {
    if (file != null && await file.exists()) await file.delete();
  } on Object {
    // 못 지워도 임시 폴더라 언젠가 정리된다
  }
}
