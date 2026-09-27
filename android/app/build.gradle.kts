import java.net.URI

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
}

val releaseApiUrl = providers.gradleProperty("GUOJING_API_BASE_URL")
val signingValues = listOf("STORE_FILE", "STORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")
    .associateWith { providers.environmentVariable("GUOJING_SIGNING_$it").orNull }

val validateReleaseConfiguration by tasks.registering {
    doLast {
        val url = runCatching { URI(releaseApiUrl.get()) }.getOrNull()
        require(url?.scheme == "https" && url.host != null && url.host.contains('.') &&
            !url.host.endsWith(".invalid") && url.host != "localhost" &&
            url.rawUserInfo == null && url.rawQuery == null && url.rawFragment == null &&
            (url.path.isNullOrEmpty() || url.path == "/")) {
            "Release requires GUOJING_API_BASE_URL with a real HTTPS origin"
        }
        require(signingValues.values.all { !it.isNullOrBlank() }) {
            "Release requires all GUOJING_SIGNING_* environment variables"
        }
        require(file(requireNotNull(signingValues["STORE_FILE"])).isFile) { "Signing keystore missing" }
    }
}
tasks.configureEach {
    if (name == "preReleaseBuild") dependsOn(validateReleaseConfiguration)
}

android {
    namespace = "com.xisha.guojing"
    compileSdk = 37
    buildToolsVersion = "37.0.0"

    defaultConfig {
        applicationId = "com.xisha.guojing"
        minSdk = 30
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (signingValues.values.all { !it.isNullOrBlank() }) {
            create("release") {
                storeFile = file(requireNotNull(signingValues["STORE_FILE"]))
                storePassword = signingValues["STORE_PASSWORD"]
                keyAlias = signingValues["KEY_ALIAS"]
                keyPassword = signingValues["KEY_PASSWORD"]
            }
        }
    }

    buildTypes {
        debug {
            val apiBaseUrl = providers.gradleProperty("GUOJING_DEBUG_API_BASE_URL")
                .getOrElse("http://10.0.2.2:8000")
            buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
        }
        release {
            signingConfig = signingConfigs.findByName("release")
            val apiBaseUrl = providers.gradleProperty("GUOJING_API_BASE_URL")
                .getOrElse("https://api.invalid")
            buildConfigField("String", "API_BASE_URL", "\"$apiBaseUrl\"")
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)

    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.okhttp.sse)

    testImplementation(libs.junit4)
    testImplementation(libs.kotlinx.coroutines.test)

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)

    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}
