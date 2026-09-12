package com.xisha.guojing.platform

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import com.xisha.guojing.model.TargetApp
import java.text.Collator
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

fun interface TargetAppCatalog {
    suspend fun listLaunchableApps(): List<TargetApp>
}

fun interface TargetAppLauncher {
    fun launch(packageName: String): Boolean
}

class AndroidTargetApps(private val context: Context) : TargetAppCatalog, TargetAppLauncher {
    override suspend fun listLaunchableApps(): List<TargetApp> = withContext(Dispatchers.IO) {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val activities = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.packageManager.queryIntentActivities(
                intent,
                PackageManager.ResolveInfoFlags.of(0),
            )
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.queryIntentActivities(intent, 0)
        }
        val collator = Collator.getInstance(Locale.SIMPLIFIED_CHINESE)
        activities
            .asSequence()
            .map { info ->
                TargetApp(
                    packageName = info.activityInfo.packageName,
                    label = info.loadLabel(context.packageManager).toString(),
                )
            }
            .filter { it.packageName != context.packageName }
            .distinctBy(TargetApp::packageName)
            .sortedWith { first, second -> collator.compare(first.label, second.label) }
            .toList()
    }

    override fun launch(packageName: String): Boolean {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }
}
