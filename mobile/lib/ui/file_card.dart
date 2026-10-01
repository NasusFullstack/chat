/// 채팅에 뜬 파일을 카드로 - 이름·크기·언제까지 받을 수 있는지, 그리고 받기.
///
/// PC 앱과 같은 모양이고 같은 이유다: 주소 한 줄만 있으면 그게 무슨 파일인지, 얼마나
/// 큰지, 아직 살아 있기는 한지 알 수가 없다. 게다가 우리 주소는 이름이 부호화돼 있어
/// 눈으로 읽기도 어렵다.
///
/// **받는 것은 브라우저에 맡긴다.** 앱이 직접 받으면 끊겼을 때 이어받기·바이러스 검사·
/// "인터넷에서 받은 파일" 표시를 전부 우리가 다시 만들어야 하는데, 브라우저는 이미 다 한다.
library;

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../net/relay_api.dart';

class FileCard extends StatelessWidget {
  const FileCard({
    super.key,
    required this.url,
    required this.info,
    this.mine = false,
  });

  final String url;
  final Map<String, dynamic> info;

  /// 내가 올린 것인가(표가 있으면 내 것이다).
  final bool mine;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final name = info['name'] as String? ?? '파일';
    final size = (info['size'] as num?)?.toInt() ?? 0;
    final expires = (info['expires'] as num?)?.toDouble() ?? 0;
    final left = remainingText(expires);
    final detail = [readable(size), if (left.isNotEmpty) left].join(' · ');

    return Container(
      constraints: const BoxConstraints(maxWidth: 380),
      margin: const EdgeInsets.only(top: 4, bottom: 2),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.description_outlined, color: scheme.onSurfaceVariant),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
                Text(detail,
                    style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
              ],
            ),
          ),
          TextButton(
            onPressed: () => launchUrl(Uri.parse(url),
                mode: LaunchMode.externalApplication),
            child: const Text('받기'),
          ),
        ],
      ),
    );
  }
}
