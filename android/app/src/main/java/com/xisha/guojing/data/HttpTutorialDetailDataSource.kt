package com.xisha.guojing.data

import com.xisha.guojing.model.PublishedTutorialDetail
import java.net.URLEncoder

class HttpTutorialDetailDataSource internal constructor(
    private val client: HttpJsonClient,
    private val parser: TutorialDetailJsonParser,
) : TutorialDetailDataSource {
    constructor(baseUrl: String) : this(
        client = HttpJsonClient(baseUrl),
        parser = TutorialDetailJsonParser(),
    )

    override suspend fun fetchPublishedTutorial(graphId: String): PublishedTutorialDetail {
        require(graphId.isNotBlank()) { "graphId must not be blank" }
        val encodedGraphId = URLEncoder.encode(graphId, Charsets.UTF_8.name())
            .replace("+", "%20")
        val detail = parser.parse(client.get("api/v1/tutorials/$encodedGraphId"))
        if (detail.graph.graphId != graphId) {
            throw TutorialDetailFormatException(
                "Tutorial response id '${detail.graph.graphId}' does not match request '$graphId'",
            )
        }
        return detail
    }
}
