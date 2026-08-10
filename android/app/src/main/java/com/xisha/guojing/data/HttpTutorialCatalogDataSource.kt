package com.xisha.guojing.data

import com.xisha.guojing.model.TutorialSummary

class HttpTutorialCatalogDataSource internal constructor(
    private val client: HttpJsonClient,
    private val parser: TutorialCatalogJsonParser,
) : TutorialCatalogDataSource {
    constructor(baseUrl: String) : this(
        client = HttpJsonClient(baseUrl),
        parser = TutorialCatalogJsonParser(),
    )

    override suspend fun fetchPublishedTutorials(): List<TutorialSummary> =
        parser.parse(client.get("api/v1/tutorials"))
}
