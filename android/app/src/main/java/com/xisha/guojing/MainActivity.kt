package com.xisha.guojing

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.xisha.guojing.data.DefaultTutorialCatalogRepository
import com.xisha.guojing.data.DefaultTutorialDetailRepository
import com.xisha.guojing.data.HttpTutorialCatalogDataSource
import com.xisha.guojing.data.HttpTutorialDetailDataSource
import com.xisha.guojing.ui.GuoJingApp
import com.xisha.guojing.ui.theme.GuoJingTheme

class MainActivity : ComponentActivity() {
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
        enableEdgeToEdge()
        setContent {
            GuoJingTheme {
                GuoJingApp(
                    catalogRepository = catalogRepository,
                    detailRepository = detailRepository,
                )
            }
        }
    }
}
