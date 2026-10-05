package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.util.Log
import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.FloatBuffer
import kotlin.math.sqrt

/**
 * Visual context change detection using CLIP image embeddings.
 *
 * Mirrors Python `ContextChangeDetector` (image_captioning.py lines 767–877):
 *   - Uses a rolling history of the last N=3 embeddings
 *   - Smoothed reference = arithmetic mean of stored embeddings, re-normalized to unit length
 *   - On change: clears history, appends new embedding (fresh start for new context)
 *   - On no change: appends new embedding to history (rolling window)
 *   - Change fires when cosine similarity < threshold
 *
 * Audio change detection is handled separately by AudioChangeDetector (YAMNet-based).
 */
class ChangeDetector(context: Context) {
    companion object {
        private const val TAG = "CameraAccess:ChangeDetector"

        // ── Thresholds (mirrors Python IMAGE_SIM_THRESHOLD / AUDIO_SIM_THRESHOLD) ─
        private const val IMAGE_THRESHOLD = 0.90f  // raised 0.85→0.90: more sensitive
        private const val AUDIO_THRESHOLD = 0.90f  // raised 0.85→0.90: more sensitive

        // ── Rolling history size (mirrors Python EMBED_HISTORY_N = 3) ─────────────
        private const val EMBED_HISTORY_N = 3
    }

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private var clipSession: OrtSession? = null

    // Rolling deque of recent CLIP embeddings (mirrors Python deque(maxlen=history_n))
    private val imgHist = ArrayDeque<FloatArray>(EMBED_HISTORY_N)

    init {
        try {
            val clipBytes = context.assets.open("onnx_models/clip_image_model_quantized.onnx").readBytes()
            val opts = OrtSession.SessionOptions()
            clipSession = env.createSession(clipBytes, opts)
            Log.d(TAG, "CLIP ONNX model loaded successfully.")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load CLIP ONNX model", e)
        }
    }

    /**
     * Mirrors Python `update_and_check()` (lines 840–877).
     *
     * Returns true if context has changed (or first observation).
     * image_sim / audio_sim are cosine vs the smoothed reference.
     */
    fun hasContextChanged(bitmap: Bitmap?, audioSamples: FloatArray?): Boolean {
        val imgEmb = if (bitmap != null) embedImage(bitmap) else null

        // Compute smoothed reference from rolling history
        val imgRef = smoothed(imgHist)

        // Cosine similarity against smoothed reference
        val imgSim = if (imgEmb != null && imgRef != null) dotProduct(imgEmb, imgRef) else null

        var changed = false
        val reasons = mutableListOf<String>()

        if (imgRef == null) {
            // Very first observation — always fires
            changed = true
            reasons.add("init")
        } else {
            if (imgSim != null && imgSim < IMAGE_THRESHOLD) {
                changed = true
                reasons.add("image ${String.format("%.3f", imgSim)}<$IMAGE_THRESHOLD")
            }
        }

        // On change, reset the reference so we compare against the NEW context
        if (changed) {
            imgHist.clear()
        }

        // Append current embedding to history (capped at EMBED_HISTORY_N)
        if (imgEmb != null) {
            if (imgHist.size >= EMBED_HISTORY_N) imgHist.removeFirst()
            imgHist.addLast(imgEmb)
        }

        if (reasons.isNotEmpty()) {
            Log.d(TAG, "Visual change detected: ${reasons.joinToString(", ")}")
        } else {
            Log.d(TAG, "No visual change (img_sim=$imgSim)")
        }

        return changed
    }

    // ── Smoothed reference (mirrors Python _smoothed(), lines 830–837) ────────
    /**
     * Average the stored embeddings and renormalize to unit length.
     */
    private fun smoothed(hist: ArrayDeque<FloatArray>): FloatArray? {
        if (hist.isEmpty()) return null
        val dim = hist.first().size
        val mean = FloatArray(dim)
        for (emb in hist) {
            for (i in emb.indices) {
                mean[i] += emb[i]
            }
        }
        val n = hist.size.toFloat()
        for (i in mean.indices) {
            mean[i] /= n
        }
        return normalizeL2(mean)
    }

    // ── Dot product (for unit vectors, this is cosine similarity) ──────────────
    private fun dotProduct(a: FloatArray, b: FloatArray): Float {
        var sum = 0f
        for (i in a.indices) {
            sum += a[i] * b[i]
        }
        return sum.coerceIn(-1f, 1f)
    }

    private fun embedImage(bitmap: Bitmap): FloatArray? {
        val session = clipSession ?: return null
        try {
            // CLIP expects 224x224 RGB, normalized
            val scaledBitmap = Bitmap.createScaledBitmap(bitmap, 224, 224, true)
            val floatBuffer = FloatBuffer.allocate(1 * 3 * 224 * 224)

            // Normalize per CLIP's requirements
            val mean = floatArrayOf(0.48145466f, 0.4578275f, 0.40821073f)
            val std = floatArrayOf(0.26862954f, 0.26130258f, 0.27577711f)

            for (c in 0 until 3) {
                for (y in 0 until 224) {
                    for (x in 0 until 224) {
                        val pixel = scaledBitmap.getPixel(x, y)
                        val value = when (c) {
                            0 -> Color.red(pixel) / 255.0f
                            1 -> Color.green(pixel) / 255.0f
                            else -> Color.blue(pixel) / 255.0f
                        }
                        val normalized = (value - mean[c]) / std[c]
                        floatBuffer.put(normalized)
                    }
                }
            }
            floatBuffer.rewind()

            val inputTensor = OnnxTensor.createTensor(env, floatBuffer, longArrayOf(1, 3, 224, 224))
            val result = session.run(mapOf("pixel_values" to inputTensor))

            val outputTensor = result.iterator().next().value as OnnxTensor
            val output = (outputTensor.value as Array<FloatArray>)[0]
            inputTensor.close()
            result.close()

            return normalizeL2(output)
        } catch (e: Exception) {
            Log.e(TAG, "CLIP Inference failed", e)
            return null
        }
    }

    private fun normalizeL2(vec: FloatArray): FloatArray {
        var sum = 0f
        for (v in vec) sum += v * v
        val norm = sqrt(sum)
        if (norm > 0) {
            for (i in vec.indices) vec[i] /= norm
        }
        return vec
    }

    /**
     * Reset the rolling embedding history.
     * Must be called whenever a new SonoAdapt session starts so that the
     * very first frame is always treated as a fresh observation ("init"),
     * guaranteeing the VLM fires regardless of how similar the scene looks
     * to the previous session.
     */
    fun reset() {
        imgHist.clear()
        Log.d(TAG, "ChangeDetector history reset for new session.")
    }

    fun close() {
        clipSession?.close()
    }
}
