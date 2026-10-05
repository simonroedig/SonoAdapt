package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import android.util.Log

/**
 * Audio context change detector based on YAMNet classification output.
 *
 * Instead of comparing raw audio embeddings (like CLAP), this compares the
 * SEMANTIC OUTPUT of YAMNet — the classified sound category, noise level,
 * and speech presence. This detects meaningful audio context changes
 * (e.g., silence→speech, low→high noise) without needing CLAP/ONNX.
 *
 * Design rationale (for supervisor):
 *   CLAP compares acoustic embeddings via cosine similarity, which catches
 *   low-level waveform changes. But for the notification system, what matters
 *   is whether the SOUND CLASS changed (because that's what drives unmasking
 *   cost). YAMNet's category output maps directly to the cost model dimensions.
 *
 *   This could replace or complement CLAP in the Python version too:
 *     - Compare top-K YAMNet class labels between time windows
 *     - Simpler, more interpretable, directly aligned with cost model
 *     - No embedding dimension mismatch issues
 *
 * Pattern: mirrors ChangeDetector.kt's CLIP approach:
 *   - Rolling history of last N=3 snapshots
 *   - Smoothed reference = majority vote of stored snapshots
 *   - On change: clear history, start fresh (new context baseline)
 *   - On no change: append to history (refine the reference)
 */
class AudioChangeDetector {
    companion object {
        private const val TAG = "CameraAccess:AudioChangeDetector"

        // Rolling history size (matches CLIP's EMBED_HISTORY_N = 3)
        private const val HISTORY_N = 3

        // Noise level ordinal scale for distance comparison
        private val NOISE_ORDINAL = mapOf(
            "very_low" to 0,
            "low" to 1,
            "medium" to 2,
            "high" to 3,
            "very_high" to 4
        )

        // Minimum ordinal distance to count as a noise level change
        private const val NOISE_JUMP_THRESHOLD = 2
    }

    /**
     * Snapshot of the current audio context from YAMNet.
     * Built from AudioViewModel's already-computed classification output.
     */
    data class AudioSnapshot(
        val dominantSource: String,    // "speech" | "music" | "silence" | "ambient_noise"
        val noiseLevel: String,        // "very_low" | "low" | "medium" | "high" | "very_high"
        val speechPresence: String,    // "speech_present" | "no_speech"
        val timestamp: Long = System.currentTimeMillis()
    )

    // Rolling history of recent snapshots
    private val history = ArrayDeque<AudioSnapshot>(HISTORY_N)

    // Last change reason (for UI display)
    var lastChangeReason: String = ""
        private set

    /**
     * Check if the audio context has changed significantly.
     *
     * Returns true if:
     *   - First observation (no reference yet)
     *   - Dominant sound source category changed vs majority reference
     *   - Noise level jumped by ≥ 2 ordinal steps
     *   - Speech presence toggled
     *
     * Mirrors ChangeDetector.hasContextChanged() pattern:
     *   on change → clear history, append new (fresh baseline)
     *   on no change → append to rolling window
     */
    fun hasAudioContextChanged(snapshot: AudioSnapshot): Boolean {
        val ref = smoothedReference()

        var changed = false
        val reasons = mutableListOf<String>()

        if (ref == null) {
            // First observation — always fires
            changed = true
            reasons.add("init")
        } else {
            // 1. Dominant source category changed
            if (snapshot.dominantSource != ref.dominantSource) {
                changed = true
                reasons.add("source: ${ref.dominantSource}→${snapshot.dominantSource}")
            }

            // 2. Noise level jump ≥ threshold
            val refOrd = NOISE_ORDINAL[ref.noiseLevel] ?: 0
            val curOrd = NOISE_ORDINAL[snapshot.noiseLevel] ?: 0
            val noiseDelta = kotlin.math.abs(curOrd - refOrd)
            if (noiseDelta >= NOISE_JUMP_THRESHOLD) {
                changed = true
                reasons.add("noise: ${ref.noiseLevel}→${snapshot.noiseLevel} (Δ$noiseDelta)")
            }

            // 3. Speech presence toggled
            if (snapshot.speechPresence != ref.speechPresence) {
                changed = true
                reasons.add("speech: ${ref.speechPresence}→${snapshot.speechPresence}")
            }
        }

        // Update history (same reset pattern as CLIP ChangeDetector)
        if (changed) {
            history.clear()
        }
        if (history.size >= HISTORY_N) {
            history.removeFirst()
        }
        history.addLast(snapshot)

        // Record reason for UI
        lastChangeReason = if (reasons.isNotEmpty()) {
            reasons.joinToString(", ")
            .also { Log.d(TAG, "Audio change detected: $it") }
        } else {
            Log.d(TAG, "No audio change (source=${snapshot.dominantSource}, " +
                    "noise=${snapshot.noiseLevel}, speech=${snapshot.speechPresence})")
            ""
        }

        return changed
    }

    /**
     * Smoothed reference: majority vote across the stored snapshots.
     * Returns null if history is empty (first observation).
     */
    private fun smoothedReference(): AudioSnapshot? {
        if (history.isEmpty()) return null

        // Majority vote for dominant source
        val sourceVotes = history.groupingBy { it.dominantSource }.eachCount()
        val refSource = sourceVotes.maxByOrNull { it.value }?.key ?: "silence"

        // Majority vote for noise level
        val noiseVotes = history.groupingBy { it.noiseLevel }.eachCount()
        val refNoise = noiseVotes.maxByOrNull { it.value }?.key ?: "very_low"

        // Majority vote for speech presence
        val speechVotes = history.groupingBy { it.speechPresence }.eachCount()
        val refSpeech = speechVotes.maxByOrNull { it.value }?.key ?: "no_speech"

        return AudioSnapshot(
            dominantSource = refSource,
            noiseLevel = refNoise,
            speechPresence = refSpeech
        )
    }

    /**
     * Reset history (e.g., when SonoAdapt restarts).
     */
    fun reset() {
        history.clear()
        lastChangeReason = ""
    }
}
