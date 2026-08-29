package com.xisha.guojing

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import com.xisha.guojing.data.DefaultTutorialCatalogRepository
import com.xisha.guojing.data.DefaultTutorialDetailRepository
import com.xisha.guojing.data.HttpHelpRequestSender
import com.xisha.guojing.data.HttpHelpRequestStatusReader
import com.xisha.guojing.data.HttpTutorialCatalogDataSource
import com.xisha.guojing.data.HttpTutorialDetailDataSource
import com.xisha.guojing.guidance.AccessibilityGuidanceCoordinator
import com.xisha.guojing.observation.AccessibilityObservationCoordinator
import com.xisha.guojing.observation.MlKitScreenshotOcrProvider
import com.xisha.guojing.observation.isPageObservationServiceEnabled
import com.xisha.guojing.privacy.AndroidScreenshotPrivacyProcessor
import com.xisha.guojing.ui.GuoJingApp
import com.xisha.guojing.ui.theme.GuoJingTheme

class MainActivity : ComponentActivity() {
    private var pageObservationServiceEnabled by androidx.compose.runtime.mutableStateOf(false)

    private val catalogRepository by lazy {
        DefaultTutorialCatalogRepository(
            HttpTutorialCatalogDataSource(BuildConfig.API_BASE_URL),
        )
    }
    private val detailRepository by lazy {
        DefaultTutorialDetailRepository(
            HttpTutorialDetailDataSource(BuildConfig.API_BASE_URL),
        )
    }
    private val screenshotPrivacyProcessor by lazy {
        AndroidScreenshotPrivacyProcessor(contentResolver)
    }
    private val helpRequestSender by lazy {
        HttpHelpRequestSender(BuildConfig.API_BASE_URL)
    }
    private val helpRequestStatusReader by lazy {
        HttpHelpRequestStatusReader(BuildConfig.API_BASE_URL)
    }
    private val screenshotOcrProvider by lazy {
        MlKitScreenshotOcrProvider()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshPageObservationStatus()
        enableEdgeToEdge()
        setContent {
            GuoJingTheme {
                GuoJingApp(
                    catalogRepository = catalogRepository,
                    detailRepository = detailRepository,
                    observationPort = AccessibilityObservationCoordinator,
                    overlayPort = AccessibilityGuidanceCoordinator,
                    screenshotPrivacyProcessor = screenshotPrivacyProcessor,
                    helpRequestSender = helpRequestSender,
                    helpRequestStatusReader = helpRequestStatusReader,
                    screenshotOcrProvider = screenshotOcrProvider,
                    pageObservationServiceEnabled = pageObservationServiceEnabled,
                    onOpenAccessibilitySettings = {
                        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshPageObservationStatus()
    }

    override fun onDestroy() {
        screenshotOcrProvider.close()
        super.onDestroy()
    }

    private fun refreshPageObservationStatus() {
        pageObservationServiceEnabled = isPageObservationServiceEnabled(this)
    }
}
