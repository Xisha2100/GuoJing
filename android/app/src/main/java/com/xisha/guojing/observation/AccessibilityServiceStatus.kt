package com.xisha.guojing.observation

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.Context
import android.view.accessibility.AccessibilityManager

fun isPageObservationServiceEnabled(context: Context): Boolean {
    val manager = context.getSystemService(AccessibilityManager::class.java)
    val expected = ComponentName(context, GuoJingAccessibilityService::class.java)
    return manager
        .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        .any { info -> ComponentName.unflattenFromString(info.id) == expected }
}
