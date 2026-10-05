package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.util.Base64
import android.util.Log
import androidx.core.graphics.applyCanvas
import androidx.core.graphics.createBitmap
import androidx.core.graphics.scale
import kotlinx.coroutines.delay
import java.io.ByteArrayOutputStream
import kotlin.math.ln
import kotlin.math.sqrt

class ImageCaptioning(private val context: Context, private val vlmClient: VlmClient) {
    companion object {
        private const val TAG = "CameraAccess:ImageCaptioning"

        // ── Configuration (mirrors Python CONFIG block) ───────────────────────
        private const val MAX_DIMENSION = 768          // TARGET_LONG_SIDE
        private const val JPEG_QUALITY = 85            // JPEG_QUALITY
        private const val GRAYSCALE = false

        // Retry behaviour on API errors (mirrors Python MAX_RETRIES / RETRY_DELAY_S)
        private const val MAX_RETRIES = 3
        private const val RETRY_DELAY_MS = 2000L

        // Temperature + max tokens (mirrors Python TEMPERATURE / MAX_OUTPUT_TOKENS)
        private const val TEMPERATURE = 0.2f
        private const val MAX_OUTPUT_TOKENS = 8192

        // Audio window description
        private const val AUDIO_WINDOW_S = 5.0f
    }

    // ── Response schema (mirrors Python RESPONSE_SCHEMA, lines 379–472) ───────
    // Built once, reused for every request.
    private val responseSchema: GeminiSchema by lazy { buildResponseSchema() }

    /**
     * Analyze a scene from the device camera, matching the Python
     * `analyze_image()` function (lines 884–984 of image_captioning.py).
     *
     * Part ordering follows Python exactly:
     *   1. Image (inline bytes)
     *   2. "Analyze this scene." (text)
     *   3. Memory context (text, if present)
     *   4. Audio clip (inline bytes, if present)
     *   5. Audio context text (text, if present)
     */
    suspend fun analyzeEnvironment(
        bitmap: Bitmap,
        audioHistory: String = "",
        memoryContextText: String? = null,
        audioWavBase64: String? = null
    ): String {
        val systemPrompt = context.assets.open("vlm_prompt.txt")
            .bufferedReader().use { it.readText() }.trim()
        val compressedBase64 = compressBitmapToBase64(bitmap)

        Log.d(TAG, "Sending request to ${VlmClient.CURRENT_PROVIDER.name}... " +
                "Base64 length: ${compressedBase64.length}")

        if (VlmClient.CURRENT_PROVIDER == VlmProvider.GEMINI) {
            return executeGeminiWithRetry(systemPrompt, compressedBase64,
                memoryContextText, audioWavBase64)
        } else {
            return executeGrokRequest(systemPrompt, compressedBase64,
                memoryContextText, audioHistory)
        }
    }

    // ── Gemini request with retry (mirrors Python analyze_image retry loop) ───
    private suspend fun executeGeminiWithRetry(
        systemPrompt: String,
        imageBase64: String,
        memoryContextText: String?,
        audioWavBase64: String?
    ): String {
        var lastError: String? = null

        for (attempt in 1..MAX_RETRIES) {
            try {
                // Build parts in Python order:
                //   1. image, 2. "Analyze this scene.", 3. memory, 4. audio clip, 5. audio text
                val parts = mutableListOf<GeminiPart>()

                // 1. Image (inline bytes)
                parts.add(GeminiPart(
                    inlineData = GeminiInlineData(
                        mimeType = "image/jpeg",
                        data = imageBase64
                    )
                ))

                // 2. Instruction text (matches Python: "Analyze this scene.")
                parts.add(GeminiPart(text = "Analyze this scene."))

                // 3. Memory context (matches Python format_memory_context())
                val formattedMemory = formatMemoryContext(memoryContextText)
                if (formattedMemory != null) {
                    parts.add(GeminiPart(text = formattedMemory))
                }

                // 4. Audio clip (inline bytes, if present)
                if (audioWavBase64 != null) {
                    parts.add(GeminiPart(
                        inlineData = GeminiInlineData(
                            mimeType = "audio/wav",
                            data = audioWavBase64
                        )
                    ))
                }

                // 5. Audio context text (matches Python format_audio_context())
                val audioText = formatAudioContext(audioWavBase64 != null)
                if (audioText != null) {
                    parts.add(GeminiPart(text = audioText))
                }

                val request = GeminiRequest(
                    systemInstruction = GeminiSystemInstruction(
                        parts = listOf(GeminiPart(text = systemPrompt))
                    ),
                    generationConfig = GeminiGenerationConfig(
                        temperature = TEMPERATURE,
                        maxOutputTokens = MAX_OUTPUT_TOKENS,
                        responseMimeType = "application/json",
                        responseSchema = responseSchema
                    ),
                    contents = listOf(
                        GeminiContent(role = "user", parts = parts)
                    )
                )

                val result = vlmClient.executeGeminiRequest(request)
                Log.d(TAG, "Gemini response (attempt $attempt): $result")
                return result

            } catch (e: Exception) {
                lastError = e.message ?: "Unknown error"
                Log.e(TAG, "[attempt $attempt/$MAX_RETRIES] API error: $lastError", e)

                if (attempt < MAX_RETRIES) {
                    Log.d(TAG, "Retrying in ${RETRY_DELAY_MS}ms…")
                    delay(RETRY_DELAY_MS)
                }
            }
        }

        return "Error: All $MAX_RETRIES attempts failed — last error: $lastError"
    }

    // ── Grok fallback (unchanged) ─────────────────────────────────────────────
    private suspend fun executeGrokRequest(
        systemPrompt: String,
        imageBase64: String,
        memoryContextText: String?,
        audioHistory: String
    ): String {
        return try {
            val request = ChatCompletionRequest(
                model = "grok-4.20-0309-non-reasoning",
                messages = listOf(
                    Message(
                        role = "user",
                        content = listOf(
                            Content.TextContent(systemPrompt),
                            if (!memoryContextText.isNullOrBlank())
                                Content.TextContent(formatMemoryContext(memoryContextText) ?: "")
                            else Content.TextContent(""),
                            if (audioHistory.isNotBlank())
                                Content.TextContent("audioHistory.json:\n$audioHistory")
                            else Content.TextContent(""),
                            Content.TextContent("Analyze this scene."),
                            Content.ImageContent(
                                ImageUrl(url = "data:image/jpeg;base64,$imageBase64")
                            )
                        ).filter { it !is Content.TextContent || it.text.isNotEmpty() }
                    )
                )
            )
            val result = vlmClient.executeGrokRequest(request)
            Log.d(TAG, "Grok response: $result")
            result
        } catch (e: Exception) {
            Log.e(TAG, "Grok request failed", e)
            "Error: ${e.message}"
        }
    }

    // ── format_memory_context() — mirrors Python lines 723–733 ────────────────
    /**
     * Wrap the previous frame's scene_memory as a labeled prompt block.
     * Returns null when there is no prior memory (first captioned frame).
     */
    private fun formatMemoryContext(prevMemory: String?): String? {
        if (prevMemory.isNullOrBlank()) return null
        return "RECENT MEMORY (your own 2–3 sentence summary from the previous frame, " +
                "reliable recent history — maintain continuity with it):\n" +
                prevMemory
    }

    // ── format_audio_context() — mirrors Python lines 736–753 ─────────────────
    /**
     * Text block describing the audio context sent alongside the clip.
     * When we send a raw audio clip (USE_RAW_AUDIO_FOR_VLM), Python also sends
     * measured loudness + a text preamble. Since we don't compute RMS loudness
     * on Android yet, we send the preamble without loudness for now.
     */
    private fun formatAudioContext(clipAttached: Boolean): String? {
        if (!clipAttached) return null
        val lines = mutableListOf<String>()
        lines.add("MEASURED AUDIO (ground truth from the device microphone) for the " +
                "${AUDIO_WINDOW_S}s window ending at this frame:")
        lines.add("- The actual audio clip for this window is attached — listen to it " +
                "and identify the sound sources yourself.")
        lines.add("Use this measured audio to ground scene_context.estimated_overall_loudness " +
                "and the sound_sources you report.")
        return lines.joinToString("\n")
    }

    // ── Image compression (unchanged logic) ───────────────────────────────────
    private fun compressBitmapToBase64(original: Bitmap): String {
        var bitmap = original

        // 1. Grayscale
        if (GRAYSCALE) {
            val grayscaleBitmap = createBitmap(bitmap.width, bitmap.height, Bitmap.Config.ARGB_8888)
            grayscaleBitmap.applyCanvas {
                val paint = Paint()
                val colorMatrix = ColorMatrix().apply { setSaturation(0f) }
                paint.colorFilter = ColorMatrixColorFilter(colorMatrix)
                drawBitmap(bitmap, 0f, 0f, paint)
            }
            bitmap = grayscaleBitmap
        }

        // 2. Resize (mirrors Python resize_and_encode: longest side ≤ MAX_DIMENSION)
        val width = bitmap.width
        val height = bitmap.height
        if (maxOf(width, height) > MAX_DIMENSION) {
            val scaleFactor = MAX_DIMENSION.toFloat() / maxOf(width, height)
            val newWidth = (width * scaleFactor).toInt()
            val newHeight = (height * scaleFactor).toInt()
            bitmap = bitmap.scale(newWidth, newHeight, true)
        }

        // 3. JPEG Compression
        val outputStream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, outputStream)
        val byteArray = outputStream.toByteArray()

        return Base64.encodeToString(byteArray, Base64.NO_WRAP)
    }

    // ── buildResponseSchema() — mirrors Python RESPONSE_SCHEMA (lines 379–472) ─
    private fun buildResponseSchema(): GeminiSchema {
        // Sound source object schema
        val soundSourceSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "object" to GeminiSchema(type = "STRING"),
                "motion_state" to GeminiSchema(type = "STRING"),
                "distance" to GeminiSchema(type = "STRING"),
                "direction" to GeminiSchema(type = "STRING"),
                "sound_probability" to GeminiSchema(type = "NUMBER"),
                "sound_type" to GeminiSchema(
                    type = "ARRAY",
                    items = GeminiSchema(type = "STRING")
                ),
                "estimated_loudness" to GeminiSchema(type = "NUMBER"),
                "uncertainty" to GeminiSchema(type = "NUMBER")
            ),
            required = listOf(
                "object", "motion_state", "distance", "direction",
                "sound_probability", "sound_type", "estimated_loudness", "uncertainty"
            )
        )

        // Social context schema
        val socialContextSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "social_grouping" to GeminiSchema(type = "STRING"),
                "setting_privacy" to GeminiSchema(type = "STRING"),
                "setting_formality" to GeminiSchema(type = "STRING"),
                "venue_type" to GeminiSchema(type = "STRING"),
                "interaction_mode" to GeminiSchema(type = "STRING"),
                "subject_role" to GeminiSchema(type = "STRING"),
                "enforced_silence_venue" to GeminiSchema(type = "BOOLEAN"),
                "observed_social_cues" to GeminiSchema(
                    type = "ARRAY",
                    items = GeminiSchema(type = "STRING")
                )
            ),
            required = listOf(
                "social_grouping", "setting_privacy", "setting_formality",
                "venue_type", "interaction_mode", "subject_role",
                "enforced_silence_venue", "observed_social_cues"
            )
        )

        // Task context schema
        val taskContextSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "activity_description" to GeminiSchema(type = "STRING"),
                "activity_category" to GeminiSchema(type = "STRING"),
                "gaze_target" to GeminiSchema(type = "STRING"),
                "subject_in_motion" to GeminiSchema(type = "BOOLEAN"),
                "content_mode" to GeminiSchema(type = "STRING"),
                "observable_task_artifacts" to GeminiSchema(
                    type = "ARRAY",
                    items = GeminiSchema(type = "STRING")
                )
            ),
            required = listOf(
                "activity_description", "activity_category", "gaze_target",
                "subject_in_motion", "content_mode", "observable_task_artifacts"
            )
        )

        // Scene context schema
        val sceneContextSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "environment" to GeminiSchema(type = "STRING"),
                "estimated_overall_loudness" to GeminiSchema(type = "NUMBER")
            ),
            required = listOf("environment", "estimated_overall_loudness")
        )

        // Top-level response schema
        return GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "scene_context" to sceneContextSchema,
                "sound_sources" to GeminiSchema(
                    type = "ARRAY",
                    items = soundSourceSchema
                ),
                "social_context" to socialContextSchema,
                "task_context" to taskContextSchema,
                "scene_memory" to GeminiSchema(type = "STRING"),
                "event_summary" to GeminiSchema(type = "STRING")
            ),
            required = listOf(
                "scene_context", "sound_sources", "social_context",
                "task_context", "scene_memory", "event_summary"
            )
        )
    }
}
