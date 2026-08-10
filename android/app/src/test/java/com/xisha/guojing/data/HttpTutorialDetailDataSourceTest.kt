package com.xisha.guojing.data

import java.io.ByteArrayInputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class HttpTutorialDetailDataSourceTest {
    @Test
    fun encodes_graph_id_as_one_path_segment() = runTest {
        var requestedUrl: URL? = null
        val connection = FakeHttpURLConnection(VALID_TUTORIAL_DETAIL_JSON)
        val dataSource = HttpTutorialDetailDataSource(
            client = HttpJsonClient("http://10.0.2.2:8000") { url ->
                requestedUrl = url
                connection
            },
            parser = TutorialDetailJsonParser(),
        )

        dataSource.fetchPublishedTutorial("wechat_open_family_chat")

        assertEquals(
            "http://10.0.2.2:8000/api/v1/tutorials/wechat_open_family_chat",
            requestedUrl.toString(),
        )
    }

    @Test
    fun rejects_response_for_a_different_graph_id() {
        val connection = FakeHttpURLConnection(VALID_TUTORIAL_DETAIL_JSON)
        val dataSource = HttpTutorialDetailDataSource(
            client = HttpJsonClient("http://localhost:8000") { connection },
            parser = TutorialDetailJsonParser(),
        )

        val error = assertThrows(TutorialDetailFormatException::class.java) {
            runTest {
                dataSource.fetchPublishedTutorial("another_graph")
            }
        }

        assertEquals(
            "Tutorial response id 'wechat_open_family_chat' does not match request 'another_graph'",
            error.message,
        )
    }

    private class FakeHttpURLConnection(
        responseBody: String,
    ) : HttpURLConnection(URL("http://localhost")) {
        private val body = responseBody.toByteArray(Charsets.UTF_8)

        override fun getResponseCode(): Int = 200

        override fun getInputStream(): InputStream = ByteArrayInputStream(body)

        override fun disconnect() = Unit

        override fun usingProxy(): Boolean = false

        override fun connect() = Unit
    }
}
