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
import com.xisha.guojing.data.HttpTutorialCatalogDataSource
import com.xisha.guojing.data.HttpTutorialDetailDataSource
import com.xisha.guojing.observation.AccessibilityObservationCoordinator
import com.xisha.guojing.observation.isPageObservationServiceEnabled
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

    private fun refreshPageObservationStatus() {
        pageObservationServiceEnabled = isPageObservationServiceEnabled(this)
    }
}
