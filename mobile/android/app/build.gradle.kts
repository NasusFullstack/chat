import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "kr.pdlab.chupchat"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // 알림 플러그인(flutter_local_notifications)이 요구한다. 없으면 빌드가
        // "Call requires API level 26" 류로 통째로 멈춘다
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "kr.pdlab.chupchat"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // 서명 정보는 저장소에 안 넣는다. 로컬에서는 key.properties(gitignore 됨),
    // CI에서는 GitHub 비밀값이 만들어 준 같은 파일을 읽는다.
    //
    // **왜 반드시 같은 키여야 하나**: 안드로이드는 앱의 신원을 '패키지 이름 + 서명 키'로
    // 본다. 키가 달라지면 덮어쓰기 설치가 거부되고 사람이 지웠다 다시 깔아야 한다
    // (그때 설정과 로그인 정보가 날아간다). 그래서 어느 컴퓨터에서 빌드하든 같은 키를 쓴다.
    val keyProps = Properties()
    val keyPropsFile = rootProject.file("key.properties")
    if (keyPropsFile.exists()) {
        keyPropsFile.inputStream().use { keyProps.load(it) }
    }

    signingConfigs {
        create("release") {
            if (keyPropsFile.exists()) {
                storeFile = rootProject.file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // 서명 정보가 없으면 디버그 키로 떨어진다. 그래야 키 없는 사람도
            // `flutter run --release` 로 돌려볼 수 있다 - 다만 그렇게 만든 APK는
            // 배포하면 안 된다(도장이 달라서 업데이트가 안 깔린다)
            signingConfig = if (keyPropsFile.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

dependencies {
    // 위 isCoreLibraryDesugaringEnabled 와 **짝**이다. 하나만 넣으면 빌드가 안 된다
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
