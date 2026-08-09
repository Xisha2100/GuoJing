package com.xisha.guojing.data

import java.io.ByteArrayInputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class HttpTutorialCatalogDataSourceTest {
    @Test
    fun requests_public_catalog_and_disconnects() = runTest {
        val connection = FakeHttpURLConnection(
            responseStatus = 200,
            responseBody = VALID_CATALOG,
        )
        var requestedUrl: URL? = null
        val dataSource = HttpTutorialCatalogDataSource(
            baseUrl = "http://10.0.2.2:8000/",
            parser = TutorialCatalogJsonParser(),
            connectionFactory = { url ->
                requestedUrl = url
                connection
            },
        )

        val tutorials = dataSource.fetchPublishedTutorials()

        assertEquals("http://10.0.2.2:8000/api/v1/tutorials", requestedUrl.toString())
        assertEquals("微信打电话", tutorials.single().title)
        assertEquals("GET", connection.requestMethod)
        assertTrue(connection.disconnected)
    }

    @Test
    fun reports_http_status_and_disconnects() = runTest {
        val connection = FakeHttpURLConnection(
            responseStatus = 503,
            responseBody = "temporarily unavailable",
        )
        val dataSource = HttpTutorialCatalogDataSource(
            baseUrl = "http://localhost:8000",
            parser = TutorialCatalogJsonParser(),
            connectionFactory = { connection },
        )

        val error = assertThrows(TutorialCatalogHttpException::class.java) {
            kotlinx.coroutines.test.runTest {
                dataSource.fetchPublishedTutorials()
            }
        }

        assertEquals(503, error.statusCode)
        assertTrue(connection.disconnected)
    }

    private class FakeHttpURLConnection(
        private val responseStatus: Int,
        responseBody: String,
    ) : HttpURLConnection(URL("http://localhost")) {
        private val body = responseBody.toByteArray(Charsets.UTF_8)
        var disconnected = false

        override fun getResponseCode(): Int = responseStatus

        override fun getInputStream(): InputStream = ByteArrayInputStream(body)

        override fun getErrorStream(): InputStream = ByteArrayInputStream(body)

        override fun disconnect() {
            disconnected = true
        }

        override fun usingProxy(): Boolean = false

        override fun connect() = Unit
    }

    private companion object {
        val VALID_CATALOG =
            """
            [{
              "graph_id": "wechat-call",
              "title": "微信打电话",
              "package_name": "com.tencent.mm",
              "recorded_version_name": "8.0.60",
              "recorded_version_code": 2800,
              "revision_number": 3,
              "published_at": "2026-08-09T07:00:00Z"
            }]
            """.trimIndent()
    }
}
