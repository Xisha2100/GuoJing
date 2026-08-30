package com.xisha.guojing.data

import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class TutorialHttpException(
    val statusCode: Int,
    responseBody: String,
) : IllegalStateException("Tutorial request failed with HTTP $statusCode: $responseBody")

internal class HttpJsonClient(
    baseUrl: String,
    private val connectionFactory: (URL) -> HttpURLConnection = { url ->
        url.openConnection() as HttpURLConnection
    },
) {
    private val normalizedBaseUrl = baseUrl.trimEnd('/')

    suspend fun get(path: String, headers: Map<String, String> = emptyMap()): String = withContext(Dispatchers.IO) {
        execute(path, method = "GET", headers = headers)
    }

    suspend fun postJson(
        path: String,
        body: String,
        headers: Map<String, String> = emptyMap(),
    ): String = withContext(Dispatchers.IO) {
        execute(path, method = "POST", requestBody = body, headers = headers)
    }

    private fun execute(
        path: String,
        method: String,
        requestBody: String? = null,
        headers: Map<String, String> = emptyMap(),
    ): String {
        val endpoint = URL("$normalizedBaseUrl/${path.trimStart('/')}")
        val connection = connectionFactory(endpoint)
        return try {
            connection.requestMethod = method
            connection.connectTimeout = CONNECT_TIMEOUT_MILLIS
            connection.readTimeout = READ_TIMEOUT_MILLIS
            connection.setRequestProperty("Accept", "application/json")
            headers.forEach { (name, value) -> connection.setRequestProperty(name, value) }
            if (requestBody != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { writer ->
                    writer.write(requestBody)
                }
            }

            val statusCode = connection.responseCode
            if (statusCode !in 200..299) {
                val responseBody = connection.errorStream
                    ?.bufferedReader(Charsets.UTF_8)
                    ?.use { it.readText() }
                    .orEmpty()
                    .take(MAX_ERROR_BODY_LENGTH)
                throw TutorialHttpException(statusCode, responseBody)
            }

            connection.inputStream
                .bufferedReader(Charsets.UTF_8)
                .use { it.readText() }
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
