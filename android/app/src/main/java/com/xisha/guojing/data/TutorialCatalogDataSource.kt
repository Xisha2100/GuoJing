package com.xisha.guojing.data

import com.xisha.guojing.model.TutorialSummary

fun interface TutorialCatalogDataSource {
    suspend fun fetchPublishedTutorials(): List<TutorialSummary>
}
