package com.xisha.guojing

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.xisha.guojing.data.DefaultTutorialCatalogRepository
import com.xisha.guojing.data.HttpTutorialCatalogDataSource
import com.xisha.guojing.ui.catalog.TutorialCatalogScreen
import com.xisha.guojing.ui.catalog.TutorialCatalogViewModel
import com.xisha.guojing.ui.theme.GuoJingTheme

class MainActivity : ComponentActivity() {
    private val catalogRepository by lazy {
        DefaultTutorialCatalogRepository(
            HttpTutorialCatalogDataSource(BuildConfig.API_BASE_URL),
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            GuoJingTheme {
                val catalogViewModel: TutorialCatalogViewModel = viewModel(
                    factory = TutorialCatalogViewModel.factory(catalogRepository),
                )
                val uiState by catalogViewModel.uiState.collectAsStateWithLifecycle()
                TutorialCatalogScreen(
                    uiState = uiState,
                    onRetry = catalogViewModel::retry,
                )
            }
        }
    }
}
