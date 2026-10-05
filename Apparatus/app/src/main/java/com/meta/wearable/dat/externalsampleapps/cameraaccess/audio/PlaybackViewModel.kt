/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

package com.meta.wearable.dat.externalsampleapps.cameraaccess.audio

import android.app.Application
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

class PlaybackViewModel(application: Application) : AndroidViewModel(application) {

    companion object {
        private const val TAG = "CameraAccess:PlaybackViewModel"
        private const val AUDIO_FILE = "richspeech_normalized_english.mp3"
        private const val EARCON_FILE = "notifications/earcon_normalized.mp3"
        private const val SPEECH_LOW_FILE = "notifications/speech_low_normalized.mp3"
        private const val SPEECH_MEDIUM_FILE = "notifications/speech_medium_normalized.mp3"
        private const val SPEECH_HIGH_FILE = "notifications/speech_high_normalized.mp3"
        /** Time to wait after suspending SCO for the A2DP switch to complete (ms). */
        private const val SCO_SWITCH_DELAY_MS = 1500L
        /** Time to wait after playback ends before re-establishing SCO (ms). */
        private const val SCO_RESUME_DELAY_MS = 500L
    }

    private val _isPlaying = MutableStateFlow(false)
    val isPlaying: StateFlow<Boolean> = _isPlaying.asStateFlow()

    private var mediaPlayer: MediaPlayer? = null

    /**
     * Optional link to the AudioViewModel for SCO suspend/resume.
     * Set this after both ViewModels are created (in the scaffold).
     * When set, notification playback temporarily suspends Bluetooth SCO
     * so audio plays in high-quality A2DP instead of phone-call HFP.
     */
    var audioViewModel: AudioViewModel? = null

    private val mainHandler = Handler(Looper.getMainLooper())

    fun togglePlayback() {
        if (_isPlaying.value) {
            stopPlayback()
        } else {
            startPlayback()
        }
    }

    private fun startPlayback() {
        try {
            stopPlayback() // Clean up any existing instance

            val context = getApplication<Application>()
            val descriptor = context.assets.openFd(AUDIO_FILE)
            
            mediaPlayer = MediaPlayer().apply {
                setDataSource(descriptor.fileDescriptor, descriptor.startOffset, descriptor.length)
                descriptor.close()
                prepare()
                setOnCompletionListener {
                    _isPlaying.update { false }
                    stopPlayback()
                }
                start()
            }
            _isPlaying.update { true }
            Log.d(TAG, "Started playback of $AUDIO_FILE")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start playback", e)
        }
    }

    fun stopPlayback() {
        try {
            mediaPlayer?.let {
                if (it.isPlaying) {
                    it.stop()
                }
                it.release()
            }
            mediaPlayer = null
            _isPlaying.update { false }
            Log.d(TAG, "Stopped playback")
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping playback", e)
        }
    }

    // ── Instant notification sound playback (earcon + speech) ──────────────

    private var notifPlayer: MediaPlayer? = null

    /**
     * Play state for UI button feedback.
     *  "idle"           → default button state
     *  "earcon_playing" / "speech_playing" → currently playing (show "...")
     *  "earcon_done"    / "speech_done"    → just finished (show "✓ Played")
     */
    private val _notifPlayState = MutableStateFlow("idle")
    val notifPlayState: StateFlow<String> = _notifPlayState.asStateFlow()

    /** Play earcon instantly on the smart glasses (with A2DP quality). */
    fun playEarcon() = playNotificationSound(EARCON_FILE, "earcon")

    /** Play a specific speech notification file on the smart glasses (with A2DP quality).
     *  Tag is derived from the full filename so each file has its own independent play-state
     *  (e.g. "notifications/speech_low_01.mp3" → tag "speech_low_01").
     */
    fun playSpeech(assetPath: String = SPEECH_MEDIUM_FILE) {
        val tag = assetPath
            .substringAfterLast("/")  // "speech_low_01.mp3"
            .removeSuffix(".mp3")     // "speech_low_01"
        playNotificationSound(assetPath, tag)
    }

    /** Play the low-urgency speech notification. */
    fun playSpeechLow() = playNotificationSound(SPEECH_LOW_FILE, "speech")

    /** Play the medium-urgency speech notification. */
    fun playSpeechMedium() = playNotificationSound(SPEECH_MEDIUM_FILE, "speech")

    /** Play the high-urgency speech notification. */
    fun playSpeechHigh() = playNotificationSound(SPEECH_HIGH_FILE, "speech")

    private fun playNotificationSound(assetPath: String, tag: String) {
        try {
            // Stop any currently playing notification sound
            notifPlayer?.let {
                if (it.isPlaying) it.stop()
                it.release()
                notifPlayer = null
            }

            _notifPlayState.update { "${tag}_playing" }

            // Suspend SCO to switch from HFP → A2DP for high-quality audio
            val avm = audioViewModel
            if (avm != null) {
                Log.d(TAG, "Suspending SCO for A2DP playback...")
                avm.suspendSco()
                // Wait for the Bluetooth profile switch, then play
                mainHandler.postDelayed({
                    doPlay(assetPath, tag)
                }, SCO_SWITCH_DELAY_MS)
            } else {
                // No SCO active, play immediately
                doPlay(assetPath, tag)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to play $tag", e)
            _notifPlayState.update { "idle" }
        }
    }

    private fun doPlay(assetPath: String, tag: String) {
        try {
            val context = getApplication<Application>()
            val descriptor = context.assets.openFd(assetPath)

            notifPlayer = MediaPlayer().apply {
                setDataSource(descriptor.fileDescriptor, descriptor.startOffset, descriptor.length)
                descriptor.close()
                prepare()
                setOnCompletionListener { mp ->
                    mp.release()
                    notifPlayer = null
                    _notifPlayState.update { "${tag}_done" }
                    // Resume SCO after a brief pause
                    val avm = audioViewModel
                    if (avm != null) {
                        mainHandler.postDelayed({
                            Log.d(TAG, "Resuming SCO after $tag playback")
                            avm.resumeSco()
                        }, SCO_RESUME_DELAY_MS)
                    }
                }
                start()
            }
            Log.d(TAG, "Playing $tag: $assetPath (A2DP mode)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to play $tag in doPlay", e)
            _notifPlayState.update { "idle" }
            // Try to resume SCO even on error
            audioViewModel?.resumeSco()
        }
    }

    /** Reset the play state back to idle (called from UI after showing feedback). */
    fun resetNotifState() {
        _notifPlayState.update { "idle" }
    }

    override fun onCleared() {
        super.onCleared()
        stopPlayback()
        notifPlayer?.release()
        notifPlayer = null
        mainHandler.removeCallbacksAndMessages(null)
    }

    class Factory(private val application: Application) : ViewModelProvider.Factory {
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            if (modelClass.isAssignableFrom(PlaybackViewModel::class.java)) {
                @Suppress("UNCHECKED_CAST")
                return PlaybackViewModel(application) as T
            }
            throw IllegalArgumentException("Unknown ViewModel class")
        }
    }
}
