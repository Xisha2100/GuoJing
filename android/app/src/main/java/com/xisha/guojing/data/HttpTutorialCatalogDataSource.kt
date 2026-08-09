package com.xisha.guojing.data

import com.xisha.guojing.model.TutorialSummary
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class TutorialCatalogHttpException(
    val statusCode: Int,
    responseBody: String,
) : IllegalStateException("Tutorial catalog request failed with HTTP $statusCode: $responseBody")

class HttpTutorialCatalogDataSource internal constructor(
    baseUrl: String,
    private val parser: TutorialCatalogJsonParser,
    private val connectionFactory: (URL) -> HttpURLConnection,
) : TutorialCatalogDataSource {
    constructor(baseUrl: String) : this(
        baseUrl = baseUrl,
        parser = TutorialCatalogJsonParser(),
        connectionFactory = { url -> url.openConnection() as HttpURLConnection },
    )

    private val endpoint = URL("${baseUrl.trimEnd('/')}/api/v1/tutorials")

    override suspend fun fetchPublishedTutorials(): List<TutorialSummary> =
        withContext(Dispatchers.IO) {
            val connection = connectionFactory(endpoint)
            try {
                connection.requestMethod = "GET"
                connection.connectTimeout = CONNECT_TIMEOUT_MILLIS
                connection.readTimeout = READ_TIMEOUT_MILLIS
                connection.setRequestProperty("Accept", "application/json")

                val statusCode = connection.responseCode
                if (statusCode !in 200..299) {
                    val responseBody = connection.errorStream
                        ?.bufferedReader(Charsets.UTF_8)
                        ?.use { it.readText() }
                        .orEmpty()
                        .take(MAX_ERROR_BODY_LENGTH)
                    throw TutorialCatalogHttpException(statusCode, responseBody)
                }

                val payload = connection.inputStream
                    .bufferedReader(Charsets.UTF_8)
                    .use { it.readText() }
                parser.parse(payload)
            } finally {
                connection.disconnect()
            }
        }

    private companion object {
        const val CONNECT_TIMEOUT_MILLIS = 5_000
        const val READ_TIMEOUT_MILLIS = 10_000
        const val MAX_ERROR_BODY_LENGTH = 200
    }
}
