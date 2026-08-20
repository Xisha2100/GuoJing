package com.xisha.guojing.observation

import android.accessibilityservice.AccessibilityService
import android.content.pm.PackageManager
import android.graphics.Rect
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.content.pm.PackageInfoCompat

class GuoJingAccessibilityService : AccessibilityService() {
    private val observationBuilder = SemanticObservationBuilder()

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val request = AccessibilityObservationCoordinator.activeRequest() ?: return
        // This check happens before rootInActiveWindow: capture-paused means no tree access.
        if (request.privacyMode == com.xisha.guojing.model.PrivacyMode.CapturePaused) return
        val packageName = event.packageName?.toString() ?: return
        if (packageName != request.targetPackageName) return
        val root = rootInActiveWindow ?: return
        // Events can arrive after a fast app switch; verify the live root independently.
        if (root.packageName?.toString() != request.targetPackageName) return
        val observation = observationBuilder.build(
            request = request,
            app = readObservedApp(packageName),
            nodes = readSemanticNodes(root),
        ) ?: return
        AccessibilityObservationCoordinator.publish(observation)
    }

    override fun onInterrupt() = Unit

    override fun onServiceConnected() {
        super.onServiceConnected()
        // A prior observation may describe a stale window after the service reconnects.
        AccessibilityObservationCoordinator.activeRequest()?.let(
            AccessibilityObservationCoordinator::observe,
        )
    }

    override fun onDestroy() {
        AccessibilityObservationCoordinator.stop()
        super.onDestroy()
    }

    private fun readObservedApp(packageName: String): ObservedApp {
        val packageInfo = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                packageManager.getPackageInfo(
                    packageName,
                    PackageManager.PackageInfoFlags.of(0),
                )
            } else {
                @Suppress("DEPRECATION")
                packageManager.getPackageInfo(packageName, 0)
            }
        } catch (_: PackageManager.NameNotFoundException) {
            null
        }
        return ObservedApp(
            packageName = packageName,
            versionName = packageInfo?.versionName.orEmpty(),
            versionCode = packageInfo?.let(PackageInfoCompat::getLongVersionCode) ?: 0,
        )
    }

    private fun readSemanticNodes(root: AccessibilityNodeInfo): List<SemanticNodeSnapshot> {
        val (screenWidth, screenHeight) = screenSize()
        val pending = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        val snapshots = mutableListOf<SemanticNodeSnapshot>()
        pending.add(root to 0)
        while (pending.isNotEmpty() && snapshots.size < MAX_NODE_COUNT) {
            val (node, depth) = pending.removeFirst()
            snapshots += node.toSnapshot(screenWidth, screenHeight)
            if (depth >= MAX_TREE_DEPTH) continue
            repeat(node.childCount) { index ->
                node.getChild(index)?.let { child -> pending.add(child to depth + 1) }
            }
        }
        return snapshots
    }

    private fun AccessibilityNodeInfo.toSnapshot(
        screenWidth: Int,
        screenHeight: Int,
    ): SemanticNodeSnapshot {
        val bounds = Rect()
        getBoundsInScreen(bounds)
        val containsPassword = isPassword
        return SemanticNodeSnapshot(
            resourceId = viewIdResourceName?.limited(),
            contentDescription = if (containsPassword) null else contentDescription?.toString()?.limited(),
            text = if (containsPassword) null else text?.toString()?.limited(),
            normalizedBounds = if (screenWidth > 0 && screenHeight > 0 && !bounds.isEmpty) {
                NormalizedScreenBounds(
                    left = bounds.left.toDouble() / screenWidth,
                    top = bounds.top.toDouble() / screenHeight,
                    right = bounds.right.toDouble() / screenWidth,
                    bottom = bounds.bottom.toDouble() / screenHeight,
                )
            } else {
                null
            },
        )
    }

    private fun screenSize(): Pair<Int, Int> {
        val metrics = resources.displayMetrics
        return metrics.widthPixels to metrics.heightPixels
    }

    private fun String.limited(): String = take(MAX_SEMANTIC_VALUE_LENGTH)

    private companion object {
        const val MAX_NODE_COUNT = 500
        const val MAX_TREE_DEPTH = 30
        const val MAX_SEMANTIC_VALUE_LENGTH = 200
    }
}
