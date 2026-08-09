package com.xisha.guojing.model

/** A published tutorial entry returned by the public backend catalog. */
data class TutorialSummary(
    val graphId: String,
    val title: String,
    val packageName: String,
    val recordedVersionName: String,
    val recordedVersionCode: Int,
    val revisionNumber: Int,
    val publishedAt: String,
)
