package kr.pdlab.chupchat

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * 받아온 APK로 **설치 화면을 열어주는** 일만 한다.
 *
 * 안드로이드는 앱이 몰래 다른 앱을 설치하는 것을 허용하지 않는다. 우리가 할 수 있는 건
 * 시스템 설치 화면을 띄우는 것까지이고 마지막 '설치' 버튼은 사람이 누른다.
 *
 * 두 가지를 꼭 지켜야 한다:
 *  - 안드로이드 7부터 `file://` 주소를 다른 앱에 넘기면 예외가 난다. FileProvider 로
 *    `content://` 주소를 만들어 넘기고 읽기 권한을 같이 준다
 *  - 안드로이드 8부터는 "이 앱의 설치 허용"이 앱마다 따로 꺼져 있다. 꺼져 있으면
 *    설치 화면 대신 그 설정 화면으로 보낸다(안 그러면 눌러도 아무 일이 안 일어난다)
 */
class MainActivity : FlutterActivity() {
    private val channelName = "chupchat/installer"
    private val serviceChannelName = "chupchat/service"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                if (call.method != "install") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val path = call.arguments as? String
                if (path.isNullOrEmpty()) {
                    result.success("받은 파일을 찾지 못했습니다.")
                    return@setMethodCallHandler
                }
                result.success(openInstaller(File(path)))
            }

        // 홈으로 나가도 접속이 끊기지 않게 붙잡는 서비스. 왜 필요한지는 ChatService.kt
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, serviceChannelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "start" -> result.success(holdConnection())
                    "stop" -> {
                        stopService(Intent(this, ChatService::class.java))
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    /** 서비스를 띄운다. 안드로이드가 거절하면 false - 그러면 접속 유지는 포기한다. */
    private fun holdConnection(): Boolean {
        val intent = Intent(this, ChatService::class.java)
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            true
        } catch (error: Exception) {
            // 안드로이드 12부터 배경에서 포그라운드 서비스를 띄우면 거절당한다.
            // 우리는 앱이 보이는 동안 띄우므로 정상 경로에서는 안 걸리지만,
            // 거절당해도 앱이 죽으면 안 된다
            false
        }
    }

    /** 문제가 있으면 사람에게 보여줄 말을, 잘 열렸으면 빈 글자를 돌려준다. */
    private fun openInstaller(apk: File): String {
        if (!apk.exists()) return "받은 파일이 사라졌습니다. 다시 받아주세요."

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            // 허용 화면으로 보낸다. 켜고 돌아와서 다시 누르면 설치가 뜬다
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:$packageName")
                ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
            return "'이 앱의 설치 허용'을 켜고 다시 눌러주세요."
        }

        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apk)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return try {
            startActivity(intent)
            ""
        } catch (error: Exception) {
            "설치 화면을 열지 못했습니다: ${error.message}"
        }
    }
}

/** 쓰지 않지만 Activity 결과 코드가 필요할 때를 위해 남겨둔다. */
private const val INSTALL_REQUEST = Activity.RESULT_FIRST_USER + 1
