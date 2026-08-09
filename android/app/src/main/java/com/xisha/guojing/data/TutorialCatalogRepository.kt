package com.xisha.guojing.data

import com.xisha.guojing.model.TutorialSummary

fun interface TutorialCatalogRepository {
    suspend fun getPublishedTutorials(): List<TutorialSummary>
}

class DefaultTutorialCatalogRepository(
    private val dataSource: TutorialCatalogDataSource,
) : TutorialCatalogRepository {
    override suspend fun getPublishedTutorials(): List<TutorialSummary> =
        dataSource.fetchPublishedTutorials().toList()
}
