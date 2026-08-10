package com.xisha.guojing.data

import com.xisha.guojing.model.PublishedTutorialDetail

fun interface TutorialDetailRepository {
    suspend fun getPublishedTutorial(graphId: String): PublishedTutorialDetail
}

class DefaultTutorialDetailRepository(
    private val dataSource: TutorialDetailDataSource,
) : TutorialDetailRepository {
    override suspend fun getPublishedTutorial(graphId: String): PublishedTutorialDetail =
        dataSource.fetchPublishedTutorial(graphId)
}
