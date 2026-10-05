/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

package com.meta.wearable.dat.externalsampleapps.cameraaccess.audio

import android.annotation.SuppressLint
import android.app.Application
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.google.mediapipe.tasks.audio.audioclassifier.AudioClassifier
import com.google.mediapipe.tasks.components.containers.AudioData
import com.google.mediapipe.tasks.core.BaseOptions
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.types.Permission
import com.meta.wearable.dat.core.types.PermissionStatus
import com.meta.wearable.dat.externalsampleapps.cameraaccess.wearables.WearablesViewModel
import java.io.File
import java.util.ArrayDeque
import kotlin.math.sqrt
import kotlin.time.Duration.Companion.milliseconds
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class AudioViewModel(
    application: Application,
    private val wearablesViewModel: WearablesViewModel,
) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "CameraAccess:AudioViewModel"
        private const val MODEL_FILE = "yamnet.tflite"
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val HISTORY_SIZE = 3
        private const val BLOCK_SIZE = 15600 // ~0.975s @ 16kHz
        
        private val YAMNET_TO_DIMENSIONS = mapOf(
            "Speech" to "speech",
            "Conversation" to "speech",
            "Narration, monologue" to "speech",
            "Child speech, kid speaking" to "speech",
            "Male speech, man speaking" to "speech",
            "Female speech, woman speaking" to "speech",
            "Music" to "music",
            "Background music" to "music",
            "Musical instrument" to "music",
            "Silence" to "silence",
            "Traffic noise, roadway noise" to "ambient_noise",
            "Car" to "ambient_noise",
            "Train" to "ambient_noise",
            "Subway, metro" to "ambient_noise",
            "Bus" to "ambient_noise",
            "Aircraft" to "ambient_noise",
            "Crowd" to "ambient_noise",
            "Hubbub, speech noise" to "ambient_noise",
            "Applause" to "ambient_noise",
            "Wind" to "ambient_noise",
            "Rain" to "ambient_noise",
            "Bird" to "ambient_noise",
            "Thunder" to "ambient_noise",
            "Water" to "ambient_noise",
            "Inside, small room" to "ambient_noise",
            "Vacuum cleaner" to "ambient_noise",
            "Typing" to "ambient_noise",
            "Mouse clicking" to "ambient_noise",
            "Dishwasher" to "ambient_noise",
            "Fan" to "ambient_noise"
        )
    }

    private val _uiState = MutableStateFlow(AudioUiState())
    val uiState: StateFlow<AudioUiState> = _uiState.asStateFlow()

    private val audioManager = getApplication<Application>().getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var isScoStarted = false
    private val isScoConnected = MutableStateFlow(false)

    private val scoReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val state = intent?.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, -1)
            Log.d(TAG, "Bluetooth SCO state changed: $state")
            when (state) {
                AudioManager.SCO_AUDIO_STATE_CONNECTED -> {
                    Log.d(TAG, "Bluetooth SCO Connected - Glass mic should be active")
                    isScoConnected.value = true
                }
                AudioManager.SCO_AUDIO_STATE_DISCONNECTED -> {
                    Log.d(TAG, "Bluetooth SCO Disconnected")
                    isScoConnected.value = false
                }
            }
        }
    }

    private var classificationJob: Job? = null
    private var audioClassifier: AudioClassifier? = null
    private val history = ArrayDeque<Map<String, String>>(HISTORY_SIZE)
    private var latestRms: Float = 0f

    private val maxRawSamples = SAMPLE_RATE * 5 // 5 seconds of audio
    private val rawAudioBuffer = ShortArray(maxRawSamples)
    private var rawAudioBufferIndex = 0

    init {
        setupClassifier()
    }

    private fun setupClassifier() {
        try {
            val baseOptionsBuilder = BaseOptions.builder().setModelAssetPath(MODEL_FILE)
            val options = AudioClassifier.AudioClassifierOptions.builder()
                .setBaseOptions(baseOptionsBuilder.build())
                .setMaxResults(10)
                .setScoreThreshold(0.15f)
                .build()
            audioClassifier = AudioClassifier.createFromOptions(getApplication(), options)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize AudioClassifier", e)
        }
    }

    fun toggleClassification(onRequestWearablesPermission: suspend (Permission) -> PermissionStatus) {
        if (_uiState.value.isClassifying) {
            stopClassification()
        } else {
            startClassification(onRequestWearablesPermission)
        }
    }

    fun startClassification(onRequestWearablesPermission: suspend (Permission) -> PermissionStatus) {
        viewModelScope.launch {
            // Check glasses permission
            val permission = Permission.MICROPHONE
            val result = Wearables.checkPermissionStatus(permission)
            
            var permissionStatus = result.getOrNull()
            if (permissionStatus != PermissionStatus.Granted) {
                permissionStatus = onRequestWearablesPermission(permission)
            }

            if (permissionStatus == PermissionStatus.Granted) {
                // Clear old history
                _uiState.update { it.copy(isClassifying = true, audioHistory = emptyList()) }
                try {
                    File(getApplication<Application>().filesDir, "audioHistory.json").delete()
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to delete audio history file", e)
                }
                
                // Request Bluetooth SCO for the glasses mic
                try {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                        val devices = audioManager.availableCommunicationDevices
                        val wearableDevice = devices.find { 
                            it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO || 
                            it.type == AudioDeviceInfo.TYPE_BLE_HEADSET 
                        }
                        if (wearableDevice != null) {
                            audioManager.setCommunicationDevice(wearableDevice)
                            Log.d(TAG, "Set communication device to wearable: ${wearableDevice.productName}")
                            isScoConnected.value = true // Assume connected for modern API
                        } else {
                            Log.w(TAG, "No wearable communication device found, falling back to legacy SCO")
                            startLegacySco()
                        }
                    } else {
                        startLegacySco()
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to route audio to wearable", e)
                }

                startAudioLoop()
            } else {
                wearablesViewModel.setRecentError("Microphone permission denied")
            }
        }
    }

    private fun startLegacySco() {
        getApplication<Application>().registerReceiver(
            scoReceiver,
            IntentFilter(AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED)
        )
        audioManager.startBluetoothSco()
        audioManager.isBluetoothScoOn = true
        isScoStarted = true
        Log.d(TAG, "Requested legacy Bluetooth SCO")
    }

    @SuppressLint("MissingPermission")
    private fun startAudioLoop() {
        classificationJob?.cancel()
        classificationJob = viewModelScope.launch(Dispatchers.IO) {
            // Wait for handshake (only for legacy SCO)
            if (isScoStarted) {
                Log.d(TAG, "Waiting for SCO connection handshake...")
                var waitCount = 0
                while (!isScoConnected.value && waitCount < 50) {
                    delay(100.milliseconds)
                    waitCount++
                }
                if (!isScoConnected.value) {
                    Log.w(TAG, "SCO handshake timed out, will attempt capture anyway")
                }
            }

            val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
            val audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize.coerceAtLeast(BLOCK_SIZE * 2)
            )

            if (audioRecord.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord initialization failed")
                _uiState.update { it.copy(isClassifying = false) }
                return@launch
            }

            audioRecord.startRecording()
            val audioBuffer = ShortArray(BLOCK_SIZE)

            try {
                while (_uiState.value.isClassifying) {
                    val readResult = audioRecord.read(audioBuffer, 0, BLOCK_SIZE)
                    if (readResult > 0) {
                        synchronized(rawAudioBuffer) {
                            for (i in 0 until readResult) {
                                rawAudioBuffer[rawAudioBufferIndex] = audioBuffer[i]
                                rawAudioBufferIndex = (rawAudioBufferIndex + 1) % maxRawSamples
                            }
                        }

                        val floatBuffer = FloatArray(readResult)
                        var sumSquares = 0f
                        for (i in 0 until readResult) {
                            floatBuffer[i] = audioBuffer[i] / 32768.0f
                            sumSquares += floatBuffer[i] * floatBuffer[i]
                        }
                        latestRms = sqrt(sumSquares / readResult)
                        
                        classifyChunk(floatBuffer)
                    }
                    delay(100.milliseconds) // Small breather
                }
            } catch (e: Exception) {
                Log.e(TAG, "Audio loop error", e)
            } finally {
                audioRecord.stop()
                audioRecord.release()
            }
        }
    }

    private fun classifyChunk(audioData: FloatArray) {
        val classifier = audioClassifier ?: return
        val format = AudioData.AudioDataFormat.builder()
            .setNumOfChannels(1)
            .setSampleRate(SAMPLE_RATE.toFloat())
            .build()
        val mediaPipeAudioData = AudioData.create(format, audioData.size)
        mediaPipeAudioData.load(audioData)

        val results = classifier.classify(mediaPipeAudioData)
        
        if (results.classificationResults().isNotEmpty()) {
            val topCategories = results.classificationResults()[0].classifications()[0].categories()
            val scores = topCategories.filter { it.score() >= 0.18f }
                .associate { it.categoryName() to it.score() }

            val rawResult = processCategories(scores, latestRms)
            applySmoothing(rawResult)
        }
    }

    private fun processCategories(scores: Map<String, Float>, rms: Float): Map<String, String> {
        // 1. Dominant sound source
        var dominant = "ambient_noise"
        var maxScore = 0f
        for ((name, score) in scores) {
            val mapped = YAMNET_TO_DIMENSIONS[name]
            if (mapped != null && score > maxScore) {
                dominant = mapped
                maxScore = score
            }
        }

        // 2. Speech presence
        val speechPresent = scores.keys.any { 
            it.startsWith("Speech") || it.startsWith("Conversation") || it.contains("speech", ignoreCase = true) 
        }

        // 3. Noise level
        val noiseLevel = when {
            rms < 0.005f -> "very_low"
            rms < 0.02f -> "low"
            rms < 0.08f -> "medium"
            rms < 0.20f -> "high"
            else -> "very_high"
        }

        // Force silence if exceptionally quiet
        val finalDominant = if (noiseLevel == "very_low" && dominant != "speech") "silence" else dominant

        return mapOf(
            "overall_noise_level" to noiseLevel,
            "dominant_sound_source" to finalDominant,
            "speech_presence" to if (speechPresent) "speech_present" else "no_speech"
        )
    }

    private fun applySmoothing(rawResult: Map<String, String>) {
        synchronized(history) {
            if (history.size >= HISTORY_SIZE) {
                history.removeFirst()
            }
            history.addLast(rawResult)

            if (history.size < 2) {
                updateUi(rawResult)
                return
            }

            val smoothed = mutableMapOf<String, String>()
            for (key in rawResult.keys) {
                val counts = history.map { it[key]!! }.groupingBy { it }.eachCount()
                smoothed[key] = counts.maxBy { it.value }.key
            }
            updateUi(smoothed)
        }
    }

    private fun appendToHistoryFile(entry: AudioLogEntry) {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val file = File(getApplication<Application>().filesDir, "audioHistory.json")
                val jsonObject = org.json.JSONObject().apply {
                    put("timestamp", entry.timestamp)
                    put("dominantSoundSource", entry.dominantSoundSource)
                    put("overallLoudness", entry.overallLoudness)
                }
                
                val jsonArray = if (file.exists()) {
                    val content = file.readText()
                    if (content.isNotBlank()) org.json.JSONArray(content) else org.json.JSONArray()
                } else {
                    org.json.JSONArray()
                }
                
                jsonArray.put(jsonObject)
                file.writeText(jsonArray.toString(2))
            } catch (e: Exception) {
                Log.e(TAG, "Failed to write history", e)
            }
        }
    }

    private fun updateUi(result: Map<String, String>) {
        val newNoiseLevel = result["overall_noise_level"] ?: "very_low"
        val newDominantSource = result["dominant_sound_source"] ?: "silence"
        val newSpeechPresence = result["speech_presence"] ?: "no_speech"

        val currentState = _uiState.value
        
        val entry = AudioLogEntry(
            timestamp = System.currentTimeMillis(),
            dominantSoundSource = newDominantSource,
            overallLoudness = newNoiseLevel
        )
        
        appendToHistoryFile(entry)
        
        // Keep the last 10 entries in memory for the UI to display
        val newHistory = (currentState.audioHistory + entry).takeLast(10)
        
        _uiState.update {
            it.copy(
                noiseLevel = newNoiseLevel,
                dominantSource = newDominantSource,
                speechPresence = newSpeechPresence,
                audioHistory = newHistory
            )
        }
    }

    fun stopClassification() {
        _uiState.update { it.copy(isClassifying = false) }
        classificationJob?.cancel()
        classificationJob = null

        if (isScoStarted) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    audioManager.clearCommunicationDevice()
                }
                audioManager.stopBluetoothSco()
                audioManager.isBluetoothScoOn = false
                getApplication<Application>().unregisterReceiver(scoReceiver)
                isScoStarted = false
                isScoConnected.value = false
                Log.d(TAG, "Stopped Bluetooth SCO")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to stop Bluetooth SCO", e)
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
        }
    }

    // ── SCO suspend/resume for high-quality A2DP notification playback ────

    /**
     * Temporarily stop the SCO link so Bluetooth switches from HFP → A2DP.
     * This makes audio output high-quality (stereo, 44.1kHz) instead of
     * phone-call quality (mono, 8kHz). Call [resumeSco] after playback.
     *
     * Does NOT stop the classification job — the AudioRecord will get silence
     * or stale data during the suspend, which is fine for a brief notification.
     */
    fun suspendSco() {
        if (!isScoStarted && !isScoConnected.value) {
            Log.d(TAG, "suspendSco: SCO not active, nothing to suspend")
            return
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                audioManager.clearCommunicationDevice()
            }
            audioManager.stopBluetoothSco()
            audioManager.isBluetoothScoOn = false
            Log.d(TAG, "SCO suspended for A2DP playback")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to suspend SCO", e)
        }
    }

    /**
     * Re-establish the SCO link after a notification was played in A2DP.
     * Restores the HFP microphone connection for continued audio capture.
     */
    @SuppressLint("MissingPermission")
    fun resumeSco() {
        if (!isScoStarted) {
            Log.d(TAG, "resumeSco: SCO was not originally started, skipping")
            return
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val devices = audioManager.availableCommunicationDevices
                val wearableDevice = devices.find {
                    it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
                }
                if (wearableDevice != null) {
                    audioManager.setCommunicationDevice(wearableDevice)
                    Log.d(TAG, "SCO resumed: ${wearableDevice.productName}")
                } else {
                    audioManager.startBluetoothSco()
                    audioManager.isBluetoothScoOn = true
                    Log.d(TAG, "SCO resumed via legacy path")
                }
            } else {
                audioManager.startBluetoothSco()
                audioManager.isBluetoothScoOn = true
                Log.d(TAG, "SCO resumed via legacy path")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to resume SCO", e)
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopClassification()
        audioClassifier?.close()
    }

    fun getRecentAudioWavBase64(): String? {
        val pcmData = ShortArray(maxRawSamples)
        synchronized(rawAudioBuffer) {
            var targetIdx = 0
            for (i in rawAudioBufferIndex until maxRawSamples) {
                pcmData[targetIdx++] = rawAudioBuffer[i]
            }
            for (i in 0 until rawAudioBufferIndex) {
                pcmData[targetIdx++] = rawAudioBuffer[i]
            }
        }
        
        try {
            val byteRate = SAMPLE_RATE * 1 * 2
            val dataSize = pcmData.size * 2
            val totalDataLen = dataSize + 36

            val header = ByteArray(44)
            header[0] = 'R'.code.toByte(); header[1] = 'I'.code.toByte(); header[2] = 'F'.code.toByte(); header[3] = 'F'.code.toByte()
            header[4] = (totalDataLen and 0xff).toByte(); header[5] = ((totalDataLen shr 8) and 0xff).toByte()
            header[6] = ((totalDataLen shr 16) and 0xff).toByte(); header[7] = ((totalDataLen shr 24) and 0xff).toByte()
            header[8] = 'W'.code.toByte(); header[9] = 'A'.code.toByte(); header[10] = 'V'.code.toByte(); header[11] = 'E'.code.toByte()
            header[12] = 'f'.code.toByte(); header[13] = 'm'.code.toByte(); header[14] = 't'.code.toByte(); header[15] = ' '.code.toByte()
            header[16] = 16; header[17] = 0; header[18] = 0; header[19] = 0
            header[20] = 1; header[21] = 0
            header[22] = 1; header[23] = 0
            header[24] = (SAMPLE_RATE and 0xff).toByte(); header[25] = ((SAMPLE_RATE shr 8) and 0xff).toByte()
            header[26] = ((SAMPLE_RATE shr 16) and 0xff).toByte(); header[27] = ((SAMPLE_RATE shr 24) and 0xff).toByte()
            header[28] = (byteRate and 0xff).toByte(); header[29] = ((byteRate shr 8) and 0xff).toByte()
            header[30] = ((byteRate shr 16) and 0xff).toByte(); header[31] = ((byteRate shr 24) and 0xff).toByte()
            header[32] = 2; header[33] = 0
            header[34] = 16; header[35] = 0
            header[36] = 'd'.code.toByte(); header[37] = 'a'.code.toByte(); header[38] = 't'.code.toByte(); header[39] = 'a'.code.toByte()
            header[40] = (dataSize and 0xff).toByte(); header[41] = ((dataSize shr 8) and 0xff).toByte()
            header[42] = ((dataSize shr 16) and 0xff).toByte(); header[43] = ((dataSize shr 24) and 0xff).toByte()

            val wavBytes = ByteArray(44 + dataSize)
            System.arraycopy(header, 0, wavBytes, 0, 44)
            var byteIdx = 44
            for (sample in pcmData) {
                wavBytes[byteIdx++] = (sample.toInt() and 0xff).toByte()
                wavBytes[byteIdx++] = ((sample.toInt() shr 8) and 0xff).toByte()
            }
            return android.util.Base64.encodeToString(wavBytes, android.util.Base64.NO_WRAP)
        } catch(e: Exception) {
            Log.e(TAG, "Failed to encode WAV", e)
            return null
        }
    }

    class Factory(
        private val application: Application,
        private val wearablesViewModel: WearablesViewModel,
    ) : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(AudioViewModel::class.java)) {
                @Suppress("UNCHECKED_CAST")
                return AudioViewModel(application, wearablesViewModel) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
