package com.xisha.guojing

import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.xisha.guojing.ui.GuoJingApp
import com.xisha.guojing.ui.theme.GuoJingTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val controller = (application as GuoJingApplication).agentSessionController
        setContent {
            GuoJingTheme {
                GuoJingApp(
                    controller = controller,
                    onOpenAccessibilitySettings = {
                        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    },
                )
            }
        }
    }

}
