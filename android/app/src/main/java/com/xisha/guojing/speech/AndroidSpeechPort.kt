package com.xisha.guojing.speech

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import java.util.Locale
import java.util.UUID

interface SpeechPort {
    fun speak(text: String)

    fun stop()

    fun close()
}

class AndroidSpeechPort(context: Context) : SpeechPort, TextToSpeech.OnInitListener {
    private val engine = TextToSpeech(context.applicationContext, this)
    private var initialized = false
    private var pending: String? = null

    override fun onInit(status: Int) {
        initialized = status == TextToSpeech.SUCCESS
        if (!initialized) return
        engine.language = Locale.SIMPLIFIED_CHINESE
        engine.setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
        )
        pending?.let {
            pending = null
            speak(it)
        }
    }

    override fun speak(text: String) {
        if (!initialized) {
            pending = text
            return
        }
        engine.speak(text, TextToSpeech.QUEUE_FLUSH, null, UUID.randomUUID().toString())
    }

    override fun stop() {
        pending = null
        engine.stop()
    }

    override fun close() {
        stop()
        engine.shutdown()
    }
}
