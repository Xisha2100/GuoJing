package com.xisha.guojing.speech

import android.content.Context
import android.media.AudioAttributes
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.util.Locale

interface SpeechPort {
    fun setRangeListener(listener: (Int, Int) -> Unit) {}
    fun speak(text: String)
    fun stop()
    fun close()
}

data class SpeechSegment(val start: Int, val end: Int)

/** Small natural phrases keep the active phrase visible even without range callbacks. */
fun speechSegments(text: String): List<SpeechSegment> {
    val result = mutableListOf<SpeechSegment>()
    var start = 0
    var cursor = 0
    var count = 0
    while (cursor < text.length) {
        val codePoint = text.codePointAt(cursor)
        cursor += Character.charCount(codePoint)
        count++
        if (count >= 14 || codePoint.toChar() in "，。；！？、\n") {
            result += SpeechSegment(start, cursor)
            start = cursor
            count = 0
        }
    }
    if (start < text.length) result += SpeechSegment(start, text.length)
    return result
}

class AndroidSpeechPort(context: Context) : SpeechPort {
    private val main = Handler(Looper.getMainLooper())
    private var ready = false
    private var pending: String? = null
    private var generation = 0L
    private var ranges = emptyMap<String, SpeechSegment>()
    private var listener: (Int, Int) -> Unit = { _, _ -> }
    private val engine = TextToSpeech(context.applicationContext) { status ->
        main.post { initialize(status) }
    }

    private fun initialize(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (!ready) return
        ready = engine.setLanguage(Locale.SIMPLIFIED_CHINESE) >= TextToSpeech.LANG_AVAILABLE
        engine.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build(),
        )
        engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String) = range(id, 0, null)
            override fun onRangeStart(id: String, start: Int, end: Int, frame: Int) =
                range(id, start, end)
            override fun onDone(id: String) { main.post { ranges = ranges - id } }
            @Deprecated("Legacy callback")
            override fun onError(id: String) { main.post { ranges = ranges - id } }
            override fun onError(id: String, errorCode: Int) {
                main.post { ranges = ranges - id }
            }
        })
        pending?.let { pending = null; speak(it) }
    }

    private fun range(id: String, start: Int, end: Int?) {
        main.post {
            val segment = ranges[id] ?: return@post
            listener(
                (segment.start + start).coerceIn(segment.start, segment.end),
                end?.let { (segment.start + it).coerceIn(segment.start, segment.end) }
                    ?: segment.end,
            )
        }
    }

    override fun setRangeListener(listener: (Int, Int) -> Unit) { this.listener = listener }

    override fun speak(text: String) {
        stop()
        listener(0, 0)
        if (!ready) { pending = text; return }
        val segments = speechSegments(text)
        ranges = segments.mapIndexed { index, segment ->
            "$generation:$index" to segment
        }.toMap()
        segments.forEachIndexed { index, segment ->
            engine.speak(
                text.substring(segment.start, segment.end),
                if (index == 0) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD,
                null, "$generation:$index",
            )
        }
    }

    override fun stop() {
        generation++
        pending = null
        ranges = emptyMap()
        engine.stop()
    }

    override fun close() { stop(); engine.shutdown() }
}
