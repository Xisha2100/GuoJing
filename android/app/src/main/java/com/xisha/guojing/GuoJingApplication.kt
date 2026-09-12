package com.xisha.guojing

import android.app.Application
import com.xisha.guojing.data.HttpAgentRepository
import com.xisha.guojing.observation.AccessibilityRuntimeBridge
import com.xisha.guojing.platform.AndroidTargetApps
import com.xisha.guojing.session.AgentSessionController
import com.xisha.guojing.session.EncryptedActiveSessionStore
import com.xisha.guojing.speech.AndroidSpeechPort
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

class GuoJingApplication : Application() {
    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var speech: AndroidSpeechPort

    lateinit var agentSessionController: AgentSessionController
        private set

    override fun onCreate() {
        super.onCreate()
        check(BuildConfig.DEBUG || BuildConfig.API_BASE_URL.startsWith("https://")) {
            "Release API_BASE_URL must use HTTPS"
        }
        val targetApps = AndroidTargetApps(this)
        speech = AndroidSpeechPort(this)
        agentSessionController = AgentSessionController(
            repository = HttpAgentRepository(BuildConfig.API_BASE_URL),
            capture = AccessibilityRuntimeBridge,
            overlay = AccessibilityRuntimeBridge,
            speech = speech,
            store = EncryptedActiveSessionStore(this),
            appCatalog = targetApps,
            appLauncher = targetApps,
            scope = applicationScope,
        )
        AccessibilityRuntimeBridge.setActions(agentSessionController)
    }

    override fun onTerminate() {
        speech.close()
        applicationScope.cancel()
        super.onTerminate()
    }
}
