package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import android.content.Context
import android.util.Log
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject

/**
 * Anticipation module — Kotlin port of Python anticipation.py's SoundscapeForecaster.
 *
 * Triggered on notification arrival. Predicts the user's near-future context
 * (scene, social, task) AND estimates per-step delivery costs (social, disruption,
 * unmasking) for earcon vs speech display types — all in a single Gemini call.
 *
 * Pipeline position:
 *   ImageCaptioning (scene analysis) → session log (observed frames)
 *                                    → memory sidecar (compact narrative)
 *                                          │
 *                                    Anticipation  ◄── notification arrival
 *                                          │
 *                        forecast steps with per-step costs
 *                                          │
 *                                          ▼
 *                                    utility.py → U(t,d) → argmax(t*, d*)
 */
class Anticipation(private val context: Context, private val vlmClient: VlmClient) {
    companion object {
        private const val TAG = "CameraAccess:Anticipation"
    }

    // ── System instruction loaded once from assets ────────────────────────────
    private val systemInstruction: String by lazy {
        context.assets.open("anticipation_prompt.txt")
            .bufferedReader().use { it.readText() }.trim()
    }

    // ── Gemini response schema (built once, reused) ──────────────────────────
    // Mirrors Python _build_response_schema() (lines 587–688)
    private val responseSchema: GeminiSchema by lazy { buildForecastResponseSchema() }

    // ══════════════════════════════════════════════════════════════════════════
    //  Public API: generateForecast()
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Generate a forecast from the observed scene history.
     *
     * @param sessionLogJson   Full session log JSON array string (all observed frames
     *                         with frame_timestamp_s, scene_context, sound_sources, etc.)
     * @param memorySidecarJson Memory sidecar JSON string ({session, narrative:[...]})
     * @param currentTimeS     Current absolute time in seconds (wall clock / 1000)
     * @return ForecastResult with forecast steps + expected timeline
     */
    suspend fun generateForecast(
        sessionLogJson: String,
        memorySidecarJson: String?,
        currentTimeS: Double
    ): ForecastResult {
        try {
            // 1. Parse the session log into frames
            val allFrames = try {
                JSONArray(sessionLogJson)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to parse session log JSON", e)
                return persistenceFallbackFromJson(sessionLogJson, currentTimeS)
            }

            if (allFrames.length() == 0) {
                Log.w(TAG, "No frames in session log, returning empty forecast")
                return ForecastResult(emptyList(), "")
            }

            // 2. Determine cursor timestamp (now = most recent frame)
            val cursorTs = currentTimeS

            // 3. Select recent history frames (last N_HISTORY_FRAMES)
            val recentFrames = selectRecentFrames(allFrames, cursorTs, ForecastConfig.N_HISTORY_FRAMES)
            if (recentFrames.length() == 0) {
                return persistenceFallbackFromJson(sessionLogJson, currentTimeS)
            }

            // 4. Split into full-detail (last N_FULL_DETAIL) and older summary
            val fullDetailFrames: JSONArray
            val oldestFullTs: Double

            if (recentFrames.length() <= ForecastConfig.N_FULL_DETAIL) {
                fullDetailFrames = recentFrames
                oldestFullTs = recentFrames.optJSONObject(0)
                    ?.optDouble("frame_timestamp_s", 0.0) ?: 0.0
            } else {
                // Take only last N_FULL_DETAIL frames for full detail
                fullDetailFrames = JSONArray()
                val startIdx = recentFrames.length() - ForecastConfig.N_FULL_DETAIL
                for (i in startIdx until recentFrames.length()) {
                    fullDetailFrames.put(recentFrames.optJSONObject(i))
                }
                oldestFullTs = fullDetailFrames.optJSONObject(0)
                    ?.optDouble("frame_timestamp_s", 0.0) ?: 0.0
            }

            // 5. Build earlier context from memory sidecar / older frames
            val earlierContext = buildEarlierContext(
                narrativeJson = memorySidecarJson,
                sessionLogJson = sessionLogJson,
                oldestFullDetailTs = oldestFullTs,
                cursorTs = cursorTs
            )

            // 6. Build the prompt (mirrors Python _build_prompt, lines 975–994)
            val recentHistoryPrompt = buildRecentHistoryForPrompt(fullDetailFrames, cursorTs)
            val nowTs = cursorTs
            val prompt = buildPromptPayload(
                nowTimestampS = nowTs,
                earlierContext = earlierContext,
                recentHistory = recentHistoryPrompt,
                horizonS = ForecastConfig.FORECAST_HORIZON_S,
                nMin = ForecastConfig.N_FORECAST_STEPS,
                nMax = ForecastConfig.N_FORECAST_STEPS
            )

            Log.d(TAG, "Sending forecast request to ${VlmClient.CURRENT_PROVIDER.name}... " +
                    "Prompt length: ${prompt.length} chars, " +
                    "Recent frames: ${fullDetailFrames.length()}, " +
                    "Earlier context: ${earlierContext.length()} lines")

            // 7. Call Gemini with retry
            return callGeminiWithRetry(prompt, nowTs)

        } catch (e: Exception) {
            Log.e(TAG, "Forecasting failed", e)
            return persistenceFallbackFromJson(sessionLogJson, currentTimeS)
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  Prompt construction
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Build the user-side prompt payload. Mirrors Python _build_prompt() (lines 975–994).
     */
    private fun buildPromptPayload(
        nowTimestampS: Double,
        earlierContext: JSONArray,
        recentHistory: JSONArray,
        horizonS: Double,
        nMin: Int,
        nMax: Int
    ): String {
        val payload = JSONObject().apply {
            put("now_timestamp_s", nowTimestampS)
            put("earlier_context", earlierContext)
            put("recent_history", recentHistory)
            put("forecast_horizon_s", horizonS)
            put("min_steps", nMin)
            put("max_steps", nMax)
        }
        return "Forecast the next steps of the scene, each with a duration range.\n" +
                payload.toString(2)
    }

    /**
     * Build the recent history array for the prompt with t_offset_s relative to cursor.
     * Mirrors Python frames_up_to() (lines 194–210) + to_prompt_dict() (lines 178–191).
     *
     * Each entry includes `held_for_s` from the session log's `persistance_s` field,
     * which tells the LLM how long this context has already lasted — a critical cue
     * for timing the first forecast step's duration.
     */
    private fun buildRecentHistoryForPrompt(frames: JSONArray, cursorTs: Double): JSONArray {
        val result = JSONArray()
        for (i in 0 until frames.length()) {
            val frame = frames.optJSONObject(i) ?: continue
            val frameTs = frame.optDouble("frame_timestamp_s", 0.0)
            val tOffset = frameTs - cursorTs

            val promptEntry = JSONObject().apply {
                put("t_offset_s", round3(tOffset))
                put("frame_timestamp_s", frameTs)
                put("observed", true)

                // held_for_s: how long this context has persisted (from session log's persistance_s)
                // Mirrors Python _build_prompt() which injects held_for_s from the segment's dwell time
                val persistanceS = frame.optDouble("persistance_s", Double.NaN)
                if (!persistanceS.isNaN()) {
                    put("held_for_s", round3(persistanceS))
                }

                // scene_context
                val sc = frame.optJSONObject("scene_context")
                if (sc != null) put("scene_context", sc)

                // sound_sources
                val ss = frame.optJSONArray("sound_sources")
                if (ss != null) put("sound_sources", ss)

                // social_context
                val soc = frame.optJSONObject("social_context")
                if (soc != null) put("social_context", soc)

                // task_context
                val tc = frame.optJSONObject("task_context")
                if (tc != null) put("task_context", tc)
            }
            result.put(promptEntry)
        }
        return result
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  Gemini call with retry — mirrors Python _forecast_llm() (lines 996–1026)
    // ══════════════════════════════════════════════════════════════════════════

    private suspend fun callGeminiWithRetry(prompt: String, t0Ts: Double): ForecastResult {
        var lastError: Exception? = null

        for (attempt in 0..ForecastConfig.MAX_RETRIES) {
            try {
                val request = GeminiRequest(
                    systemInstruction = GeminiSystemInstruction(
                        parts = listOf(GeminiPart(text = systemInstruction))
                    ),
                    generationConfig = GeminiGenerationConfig(
                        temperature = ForecastConfig.TEMPERATURE,
                        responseMimeType = "application/json",
                        responseSchema = responseSchema
                    ),
                    contents = listOf(
                        GeminiContent(
                            role = "user",
                            parts = listOf(GeminiPart(text = prompt))
                        )
                    )
                )

                val rawResponse = vlmClient.executeGeminiRequest(request)
                Log.d(TAG, "Gemini forecast response (attempt ${attempt + 1}): " +
                        "${rawResponse.take(500)}...")

                // Check for error responses
                if (rawResponse.startsWith("Error:")) {
                    throw Exception(rawResponse)
                }

                return parseForecastResponse(rawResponse, t0Ts)

            } catch (e: Exception) {
                lastError = e
                Log.e(TAG, "[attempt ${attempt + 1}/${ForecastConfig.MAX_RETRIES + 1}] " +
                        "Forecast call failed: ${e.message}", e)
                if (attempt < ForecastConfig.MAX_RETRIES) {
                    delay(1000L * (attempt + 1))
                }
            }
        }

        Log.e(TAG, "All forecast attempts failed, using persistence fallback")
        throw lastError ?: Exception("Unknown forecast error")
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  Response parsing — mirrors Python SoundscapeForecaster._parse() (1028–1048)
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Parse the Gemini JSON response into a ForecastResult.
     */
    private fun parseForecastResponse(rawJson: String, t0Ts: Double): ForecastResult {
        // Clean up any markdown wrappers
        val cleanJson = rawJson
            .replace("```json", "").replace("```", "")
            .trim()

        val data = JSONObject(cleanJson)
        val items = data.optJSONArray("forecast_frames") ?: JSONArray()
        val expectedTimeline = data.optString("expected_timeline", "")

        val steps = mutableListOf<ForecastStep>()
        for (i in 0 until items.length()) {
            val d = items.optJSONObject(i) ?: continue

            val step = ForecastStep(
                sceneContext = d.optJSONObject("scene_context") ?: JSONObject(),
                soundSources = d.optJSONArray("sound_sources") ?: JSONArray(),
                socialContext = d.optJSONObject("social_context"),
                taskContext = d.optJSONObject("task_context"),
                changeSummary = d.optString("change_summary", ""),
                durationMinS = d.optDouble("duration_min_s", ForecastConfig.DT_FALLBACK_S),
                durationMaxS = d.optDouble("duration_max_s", ForecastConfig.DT_FALLBACK_S),
                forecastUncertainty = d.optDouble("forecast_uncertainty", 0.5)
            )

            // Parse per-step delivery costs (merged interruption + unmasking)
            step.costs = StepCosts.fromLlmMap(d.optJSONObject("costs"))

            steps.add(step)
        }

        // Derive start windows, representative offset, timestamps, deliverable,
        // and floor forecast_uncertainty by the horizon curve
        applyStepTiming(steps, t0Ts, ForecastConfig.MIN_LEAD_TIME_S)

        Log.d(TAG, "Parsed ${steps.size} forecast steps, timeline: $expectedTimeline")

        return ForecastResult(steps = steps, expectedTimeline = expectedTimeline)
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  History helpers
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Select the most recent frames from the session log up to the cursor,
     * capped at `limit`. Mirrors Python frames_up_to() (lines 194–210).
     */
    private fun selectRecentFrames(allFrames: JSONArray, cursorTs: Double, limit: Int): JSONArray {
        val eligible = mutableListOf<JSONObject>()
        for (i in 0 until allFrames.length()) {
            val frame = allFrames.optJSONObject(i) ?: continue
            val ts = frame.optDouble("frame_timestamp_s", Double.NaN)
            if (!ts.isNaN() && ts <= cursorTs + 1e-6) {
                eligible.add(frame)
            }
        }

        // Sort by timestamp
        eligible.sortBy { it.optDouble("frame_timestamp_s", 0.0) }

        // Take last `limit` frames
        val selected = if (eligible.size > limit) eligible.takeLast(limit) else eligible

        return JSONArray().apply { selected.forEach { put(it) } }
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  Persistence fallback
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Persistence fallback when LLM is unavailable. Uses the last observed frame
     * to build a simple repeat-forward forecast with heuristic costs.
     */
    private fun persistenceFallbackFromJson(
        sessionLogJson: String,
        currentTimeS: Double
    ): ForecastResult {
        return try {
            val arr = JSONArray(sessionLogJson)
            if (arr.length() == 0) {
                ForecastResult(emptyList(), "No history available for forecast.")
            } else {
                val lastFrame = arr.getJSONObject(arr.length() - 1)
                persistenceForecast(lastFrame, currentTimeS)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Persistence fallback also failed", e)
            ForecastResult(emptyList(), "Forecast failed: ${e.message}")
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    //  Response schema — mirrors Python _build_response_schema() (lines 587–688)
    // ══════════════════════════════════════════════════════════════════════════

    /**
     * Build the Gemini structured output schema for the forecast response.
     * Ensures the model returns well-typed JSON with all required fields.
     */
    private fun buildForecastResponseSchema(): GeminiSchema {
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

        // Scene context schema
        val sceneContextSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "environment" to GeminiSchema(type = "STRING"),
                "estimated_overall_loudness" to GeminiSchema(type = "NUMBER")
            ),
            required = listOf("environment", "estimated_overall_loudness")
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

        // Per-step costs schema (merged interruption + masking)
        // Flat keys for reliable structured output
        val costsSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "social_cost_earcon" to GeminiSchema(type = "NUMBER"),
                "social_cost_speech" to GeminiSchema(type = "NUMBER"),
                "disruption_cost_earcon" to GeminiSchema(type = "NUMBER"),
                "disruption_cost_speech" to GeminiSchema(type = "NUMBER"),
                "unmasking_cost_earcon" to GeminiSchema(type = "NUMBER"),
                "unmasking_cost_speech" to GeminiSchema(type = "NUMBER"),
                "e_task" to GeminiSchema(type = "NUMBER"),
                "cost_rationale" to GeminiSchema(type = "STRING")
            ),
            required = listOf(
                "social_cost_earcon", "social_cost_speech",
                "disruption_cost_earcon", "disruption_cost_speech",
                "unmasking_cost_earcon", "unmasking_cost_speech",
                "e_task", "cost_rationale"
            )
        )

        // Forecast frame schema (scene content + costs)
        val forecastFrameSchema = GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "duration_min_s" to GeminiSchema(type = "NUMBER"),
                "duration_max_s" to GeminiSchema(type = "NUMBER"),
                "scene_context" to sceneContextSchema,
                "sound_sources" to GeminiSchema(type = "ARRAY", items = soundSourceSchema),
                "social_context" to socialContextSchema,
                "task_context" to taskContextSchema,
                "forecast_uncertainty" to GeminiSchema(type = "NUMBER"),
                "change_summary" to GeminiSchema(type = "STRING"),
                "costs" to costsSchema
            ),
            required = listOf(
                "duration_min_s", "duration_max_s", "scene_context",
                "sound_sources", "social_context", "task_context",
                "forecast_uncertainty", "change_summary", "costs"
            )
        )

        // Top-level response schema
        return GeminiSchema(
            type = "OBJECT",
            properties = mapOf(
                "forecast_frames" to GeminiSchema(type = "ARRAY", items = forecastFrameSchema),
                "expected_timeline" to GeminiSchema(type = "STRING")
            ),
            required = listOf("forecast_frames", "expected_timeline")
        )
    }
}
