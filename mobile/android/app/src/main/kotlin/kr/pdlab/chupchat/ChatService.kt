package kr.pdlab.chupchat

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat

/**
 * 홈으로 나가도 **접속이 끊기지 않게** 프로세스를 붙잡아 두는 서비스.
 *
 * 안드로이드 11부터는 화면에서 사라진 앱의 프로세스를 얼린다(cached app freezer).
 * 소켓은 열려 있는데 우리가 움직일 수 없으니 서버가 보내는 PING 에 PONG 을 못 하고,
 * 서버는 응답 없는 손님으로 보고 연결을 끊는다. 그래서 "홈 버튼을 누르면 접속이
 * 끊긴다"가 된다.
 *
 * 포그라운드 서비스가 돌고 있으면 그 프로세스는 얼지 않는다. 대가로 **"실행 중"
 * 알림을 하나 띄워야 한다** - 안드로이드 규칙이고 앱이 숨길 수 없다. 그게 싫은
 * 사람은 설정에서 끌 수 있게 해뒀다(끄면 홈으로 나갈 때 접속이 끊긴다).
 *
 * 이 서비스는 **아무 일도 하지 않는다.** 채팅은 그대로 Flutter 쪽이 하고, 여기는
 * 프로세스가 살아 있게 하는 역할만 한다. 소켓을 여기로 옮기면 같은 코드를 코틀린에
 * 또 짜야 하고 PC 앱과 답이 갈라진다.
 */
class ChatService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ServiceCompat.startForeground(
            this,
            ONGOING_ID,
            ongoingNotification(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            } else {
                0
            },
        )
        // 앱이 죽은 뒤에 시스템이 알아서 되살리면 안 된다 - 끈 줄 알았는데 접속되어
        // 있는 상태가 된다. 다시 붙는 것은 사람이 앱을 켤 때다
        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // 최근 앱 목록에서 밀어서 **끈** 것이다. 홈으로 나간 것과 다르게 봐야 한다 -
        // 끄면 접속도 끊겨야 한다. 매니페스트의 stopWithTask 와 겹치지만, 기기마다
        // 어느 쪽이 먼저 오는지가 달라서 둘 다 둔다
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    /** 안드로이드가 요구하는 "실행 중" 알림. 소리도 진동도 없게 한다. */
    private fun ongoingNotification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            // 낮은 중요도 - 상태줄에만 조용히 있는다. 사람이 이것만 따로 숨길 수도 있다
            val channel = NotificationChannel(
                ONGOING_CHANNEL,
                "접속 유지",
                NotificationManager.IMPORTANCE_LOW,
            )
            channel.description = "홈으로 나가도 채팅 접속이 끊기지 않게 합니다."
            channel.setShowBadge(false)
            manager.createNotificationChannel(channel)
        }

        // 눌렀을 때 앱으로 돌아오게 한다. 안 그러면 눌러도 아무 일이 안 일어나서
        // 고장난 것처럼 보인다
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, ONGOING_CHANNEL)
            .setContentTitle("춥채팅 접속 중")
            .setContentText("새 말이 오면 알려드립니다.")
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentIntent(open)
            .setOngoing(true)
            .setSilent(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        private const val ONGOING_ID = 42
        private const val ONGOING_CHANNEL = "chupchat_keepalive"
    }
}
