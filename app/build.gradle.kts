plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val defaultBackendUrl = providers.gradleProperty("SMARTCLASS_API_URL")
    .orElse("https://ais-smartclass-api.onrender.com")
    .get()

android {
    namespace = "com.aismartclass"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.aismartclass"
        minSdk = 26
        targetSdk = 34
        versionCode = 10
        versionName = "0.9"
        buildConfigField("String", "DEFAULT_BACKEND_URL", "\"$defaultBackendUrl\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation(platform("androidx.compose:compose-bom:2024.02.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
}

tasks.configureEach {
    if (name == "assembleDebug") {
        doLast {
            val debugApk = layout.buildDirectory.file("outputs/apk/debug/app-debug.apk").get().asFile
            val releaseApk = rootProject.file("AIClassroom_v${android.defaultConfig.versionName}.apk")
            debugApk.copyTo(releaseApk, overwrite = true)
        }
    }
}