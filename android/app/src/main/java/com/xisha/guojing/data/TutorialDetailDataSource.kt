package com.xisha.guojing.data

import com.xisha.guojing.model.PublishedTutorialDetail

fun interface TutorialDetailDataSource {
    suspend fun fetchPublishedTutorial(graphId: String): PublishedTutorialDetail
}
