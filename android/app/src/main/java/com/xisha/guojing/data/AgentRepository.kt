package com.xisha.guojing.data

import android.util.Base64
import android.util.Base64OutputStream
import com.xisha.guojing.model.AgentRunAccepted
import com.xisha.guojing.model.AgentRunSnapshot
import com.xisha.guojing.model.AgentSessionHandle
import com.xisha.guojing.model.CapturedScreen
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import okio.BufferedSink

interface AgentRepository {
    suspend fun createSession(
        clientSessionId: UUID,
        goal: String,
        targetPackage: String,
    ): AgentSessionHandle

    suspend fun createRun(
        session: AgentSessionHandle,
        clientTurnId: UUID,
        screenshot: CapturedScreen,
    ): AgentRunAccepted

    suspend fun getRun(runId: UUID, accessToken: String): AgentRunSnapshot

    fun observeRun(
        eventsEndpoint: String,
        accessToken: String,
    ): Flow<AgentRunSnapshot>

    suspend fun cancelRun(runId: UUID, accessToken: String)

    suspend fun closeSession(sessionId: UUID, accessToken: String)
}

class AgentHttpException(val statusCode: Int) : IOException("Agent request failed")

class HttpAgentRepository(
    baseUrl: String,
    client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(java.time.Duration.ofSeconds(10))
        .readTimeout(java.time.Duration.ofSeconds(100))
        .build(),
) : AgentRepository {
    // Custom session headers must never follow a redirect to another origin.
    private val client = client.newBuilder()
        .followRedirects(false)
        .followSslRedirects(false)
        .callTimeout(java.time.Duration.ofSeconds(100))
        .build()
    private val baseUrl = (baseUrl.trimEnd('/') + "/").toHttpUrl()
    private val eventSourceFactory = EventSources.createFactory(this.client)

    override suspend fun createSession(
        clientSessionId: UUID,
        goal: String,
        targetPackage: String,
    ): AgentSessionHandle {
        val body = AgentProtocol.createSessionBody(clientSessionId, goal, targetPackage)
        val request = Request.Builder()
            .url(resolve("api/v1/agent/sessions"))
            .post(body.toRequestBody(JSON_MEDIA_TYPE))
            .header("Accept", "application/json")
            .build()
        return AgentProtocol.parseSession(executeText(request))
    }

    override suspend fun createRun(
        session: AgentSessionHandle,
        clientTurnId: UUID,
        screenshot: CapturedScreen,
    ): AgentRunAccepted {
        val request = Request.Builder()
            .url(resolve("api/v1/agent/sessions/${session.sessionId}/runs"))
            .post(ScreenshotRunRequestBody(clientTurnId, screenshot))
            .agentToken(session.accessToken)
            .header("Accept", "application/json")
            .build()
        return AgentProtocol.parseRunAccepted(executeText(request))
    }

    override suspend fun getRun(runId: UUID, accessToken: String): AgentRunSnapshot {
        val request = Request.Builder()
            .url(resolve("api/v1/agent/runs/$runId"))
            .get()
            .agentToken(accessToken)
            .header("Accept", "application/json")
            .build()
        return AgentProtocol.parseRun(executeText(request))
    }

    override fun observeRun(
        eventsEndpoint: String,
        accessToken: String,
    ): Flow<AgentRunSnapshot> = callbackFlow {
        val request = Request.Builder()
            .url(resolve(eventsEndpoint))
            .get()
            .agentToken(accessToken)
            .header("Accept", "text/event-stream")
            .build()
        val source = eventSourceFactory.newEventSource(
            request,
            object : EventSourceListener() {
                override fun onEvent(
                    eventSource: EventSource,
                    id: String?,
                    type: String?,
                    data: String,
                ) {
                    try {
                        val snapshot = AgentProtocol.parseRun(data)
                        trySend(snapshot)
                        if (snapshot.status.isTerminal) close()
                    } catch (error: Exception) {
                        close(error)
                        eventSource.cancel()
                    }
                }

                override fun onClosed(eventSource: EventSource) {
                    close()
                }

                override fun onFailure(
                    eventSource: EventSource,
                    throwable: Throwable?,
                    response: Response?,
                ) {
                    close(
                        response?.let { AgentHttpException(it.code) }
                            ?: throwable
                            ?: IOException("Agent event stream failed"),
                    )
                }
            },
        )
        awaitClose { source.cancel() }
    }

    override suspend fun cancelRun(runId: UUID, accessToken: String) {
        executeEmpty(
            Request.Builder()
                .url(resolve("api/v1/agent/runs/$runId"))
                .delete()
                .agentToken(accessToken)
                .build(),
        )
    }

    override suspend fun closeSession(sessionId: UUID, accessToken: String) {
        executeEmpty(
            Request.Builder()
                .url(resolve("api/v1/agent/sessions/$sessionId"))
                .delete()
                .agentToken(accessToken)
                .build(),
        )
    }

    private suspend fun executeText(request: Request): String = withContext(Dispatchers.IO) {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw AgentHttpException(response.code)
            val source = response.body.source()
            if (source.request(MAX_RESPONSE_CHARS.toLong() + 1)) {
                throw IOException("Agent response exceeds size limit")
            }
            source.readUtf8()
        }
    }

    private suspend fun executeEmpty(request: Request) {
        withContext(Dispatchers.IO) {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw AgentHttpException(response.code)
            }
        }
    }

    private fun resolve(path: String): HttpUrl {
        val resolved = baseUrl.resolve(path) ?: throw IllegalArgumentException("Invalid API path")
        require(
            resolved.scheme == baseUrl.scheme &&
                resolved.host == baseUrl.host &&
                resolved.port == baseUrl.port,
        ) { "Agent endpoint must remain on the configured origin" }
        return resolved
    }

    private fun Request.Builder.agentToken(value: String): Request.Builder =
        header("X-Agent-Session-Token", value)

    private companion object {
        val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        const val MAX_RESPONSE_CHARS = 16 * 1024
    }
}

private class ScreenshotRunRequestBody(
    private val clientTurnId: UUID,
    private val screenshot: CapturedScreen,
) : RequestBody() {
    override fun contentType() = "application/json; charset=utf-8".toMediaType()

    override fun writeTo(sink: BufferedSink) {
        sink.writeUtf8(
            "{\"schema_version\":\"1.0\"," +
                "\"client_turn_id\":\"$clientTurnId\"," +
                "\"image_media_type\":\"image/jpeg\"," +
                "\"screen_width\":${screenshot.width}," +
                "\"screen_height\":${screenshot.height}," +
                "\"screenshot_base64\":\"",
        )
        Base64OutputStream(
            sink.outputStream(),
            Base64.NO_WRAP or Base64.NO_CLOSE,
        ).use { encoded -> encoded.write(screenshot.jpegBytes) }
        sink.writeUtf8("\"}")
    }
}
