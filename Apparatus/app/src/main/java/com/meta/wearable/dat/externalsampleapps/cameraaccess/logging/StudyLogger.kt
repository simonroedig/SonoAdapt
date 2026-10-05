package com.meta.wearable.dat.externalsampleapps.cameraaccess.logging

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Lightweight Supabase logger for the SonoAdapt user study.
 *
 * Every user interaction (button press, system decision, playback) is recorded
 * as a row in the `study_events` table. All network I/O runs on [Dispatchers.IO]
 * in fire-and-forget coroutines so the UI thread is never blocked.
 *
 * Usage:
 * ```
 *   StudyLogger.startSession()          // on "Start SonoAdapt"
 *   StudyLogger.logEarconInstant(...)   // on Earcon button
 *   StudyLogger.stopSession()           // on "Stop SonoAdapt"
 * ```
 */
object StudyLogger {

    private const val TAG = "SonoAdapt:StudyLogger"

    // ── Supabase credentials ────────────────────────────────────────────────
    private const val SUPABASE_URL =
        "https://sisoeduyorcvogutcmvw.supabase.co/rest/v1/study_events"
    private const val SUPABASE_KEY =
        "sb_publishable_KFc6p-u9-sfqzLIb_UETRQ_uP6frjYW"

    // ── HTTP client (reused across all requests) ────────────────────────────
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

    // ── Coroutine scope — survives across Activity recreations ──────────────
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // ── Session state ───────────────────────────────────────────────────────
    private var sessionId: String? = null
    private var sessionStartMs: Long = 0L

    /** Whether logging is enabled. Toggled from the UI checkbox. */
    @Volatile
    var enabled: Boolean = true

    /** True while a session is active (between start and stop). */
    val isSessionActive: Boolean get() = sessionId != null

    // ── Track simulate flow for "instant after skip" detection ──────────────
    /** Set to true after the user presses Skip on a delivery dialog. */
    @Volatile
    var lastActionWasSkip: Boolean = false

    // ── Public API ──────────────────────────────────────────────────────────

    /** Call on "Start SonoAdapt". Generates a fresh session UUID and logs the event. */
    fun startSession() {
        if (!enabled) return
        sessionId = UUID.randomUUID().toString()
        sessionStartMs = System.currentTimeMillis()
        lastActionWasSkip = false
        Log.d(TAG, "Session started: $sessionId")
        insertEvent(
            eventType = "session_start",
            elapsedS = 0.0
        )
    }

    /** Call on "Stop SonoAdapt" or stream abort. */
    fun stopSession() {
        if (!enabled || sessionId == null) return
        val elapsed = elapsedSeconds()
        Log.d(TAG, "Session stopped: $sessionId (${elapsed}s)")
        insertEvent(
            eventType = "session_stop",
            elapsedS = elapsed
        )
        sessionId = null
        sessionStartMs = 0L
        lastActionWasSkip = false
    }

    /** Earcon button pressed (instant play, no simulate flow). */
    fun logEarconInstant(
        notifLabel: String,
        notifText: String,
        aiPipelineOn: Boolean,
        imageBase64: String? = null,
        wavBase64: String? = null
    ) {
        if (!enabled || sessionId == null) return
        val eventType = if (lastActionWasSkip) "instant_after_skip_earcon" else "earcon_instant"
        lastActionWasSkip = false
        insertEvent(
            eventType = eventType,
            elapsedS = elapsedSeconds(),
            notifLabel = notifLabel,
            notifText = notifText,
            aiPipeline = if (aiPipelineOn) "ON" else "OFF",
            assetPath = "notifications/earcon_normalized.mp3",
            imageBase64 = imageBase64,
            wavBase64 = wavBase64
        )
    }

    /** Speech Instant button pressed (instant play, no simulate flow). */
    fun logSpeechInstant(
        notifLabel: String,
        notifText: String,
        aiPipelineOn: Boolean,
        assetPath: String,
        imageBase64: String? = null,
        wavBase64: String? = null
    ) {
        if (!enabled || sessionId == null) return
        val eventType = if (lastActionWasSkip) "instant_after_skip_speech" else "speech_instant"
        lastActionWasSkip = false
        insertEvent(
            eventType = eventType,
            elapsedS = elapsedSeconds(),
            notifLabel = notifLabel,
            notifText = notifText,
            aiPipeline = if (aiPipelineOn) "ON" else "OFF",
            assetPath = assetPath,
            imageBase64 = imageBase64,
            wavBase64 = wavBase64
        )
    }

    /** Simulate button clicked — notification sent into the pipeline. */
    fun logSimulateTriggered(
        notifLabel: String,
        notifText: String,
        aiPipelineOn: Boolean,
        imageBase64: String? = null,
        wavBase64: String? = null
    ) {
        if (!enabled || sessionId == null) return
        lastActionWasSkip = false
        insertEvent(
            eventType = "simulate_triggered",
            elapsedS = elapsedSeconds(),
            notifLabel = notifLabel,
            notifText = notifText,
            aiPipeline = if (aiPipelineOn) "ON" else "OFF",
            imageBase64 = imageBase64,
            wavBase64 = wavBase64
        )
    }

    /**
     * Pipeline committed a decision — delivery confirmation dialog shown.
     * Called from StreamViewModel when replan loop commits.
     *
     * Stores the full AI context in [metadata] JSONB so you can later
     * reconstruct *why* the system chose earcon vs speech at that moment.
     */
    fun logSimulateSystemDecision(
        systemDecision: String,
        utilityStar: Double,
        cycleCount: Int,
        assetPath: String,
        reason: String? = null,
        // ── Notification inputs ────────────────────────────────────────
        notifUrgency: Double? = null,
        notifImportanceSender: Double? = null,
        notifImportanceContent: Double? = null,
        elapsedHeldS: Double? = null,    // seconds the notification was withheld
        forceDelivered: Boolean = false,
        suppressed: Boolean = false,
        // ── Best step info ─────────────────────────────────────────────
        bestStepIndex: Int? = null,
        bestTOffsetS: Double? = null,
        bestForecastUncertainty: Double? = null,
        // ── Benefit / cost breakdown ───────────────────────────────────
        benefitTotal: Double? = null,
        costTotal: Double? = null,
        benefitIN: Double? = null,       // I_n importance
        benefitUEff: Double? = null,     // Ũ_n effective urgency after decay
        benefitGD: Double? = null,       // G_d semantic benefit
        costASocial: Double? = null,     // A_social
        costDTask: Double? = null,       // D_task
        costCI: Double? = null,          // C_I interruption cost
        costCM: Double? = null,          // C_M unmasking cost
        speechThreshold: Double? = null, // Δcost below which speech wins
        tauUS: Double? = null,           // τ_u urgency decay time constant
        nCandidates: Int? = null,        // how many steps were deliverable
        nSteps: Int? = null,
        // ── Forecast steps (all of them, for full reconstruction) ───────
        forecastStepsJson: org.json.JSONArray? = null,
        // ── LLM-generated timeline narrative ──────────────────────────
        expectedTimeline: String? = null,
        // ── Scene at best step (quick-access fields) ──────────────────
        bestEnvironment: String? = null,
        bestLoudness: Double? = null,
        bestActivity: String? = null,
        bestActivityCategory: String? = null,
        bestSocialGrouping: String? = null,
        bestInteractionMode: String? = null,
        bestEnforcedSilence: Boolean? = null,
        bestSettingFormality: String? = null,
        bestSubjectInMotion: Boolean? = null,
        // ── Cost rationale from LLM for best step ─────────────────────
        bestCostRationale: String? = null
    ) {
        if (!enabled || sessionId == null) return

        val meta = JSONObject().apply {
            // ── Decision context ──────────────────────────────────────
            reason?.let { put("reason", it) }
            put("force_delivered", forceDelivered)
            put("suppressed", suppressed)

            // ── Notification inputs that the optimizer received ────────
            val notifInputs = JSONObject()
            notifUrgency?.let { notifInputs.put("urgency", it) }
            notifImportanceSender?.let { notifInputs.put("importance_sender", it) }
            notifImportanceContent?.let { notifInputs.put("importance_content", it) }
            elapsedHeldS?.let { notifInputs.put("elapsed_held_s", it) }
            if (notifInputs.length() > 0) put("notification_inputs", notifInputs)

            // ── Optimizer summary ──────────────────────────────────────
            val optimizer = JSONObject()
            nCandidates?.let { optimizer.put("n_candidates", it) }
            nSteps?.let { optimizer.put("n_steps", it) }
            speechThreshold?.let { optimizer.put("speech_threshold_delta_cost", it) }
            tauUS?.let { optimizer.put("tau_u_s", it) }
            if (optimizer.length() > 0) put("optimizer_summary", optimizer)

            // ── Best step detail ───────────────────────────────────────
            val bestStep = JSONObject()
            bestStepIndex?.let { bestStep.put("step_index", it) }
            bestTOffsetS?.let { bestStep.put("t_offset_s", it) }
            bestForecastUncertainty?.let { bestStep.put("forecast_uncertainty", it) }
            // Benefit / cost breakdown
            val benefit = JSONObject()
            benefitIN?.let { benefit.put("I_n_importance", it) }
            benefitUEff?.let { benefit.put("U_eff_urgency_decayed", it) }
            benefitGD?.let { benefit.put("G_d_semantic", it) }
            benefitTotal?.let { benefit.put("B_total", it) }
            if (benefit.length() > 0) bestStep.put("benefit", benefit)
            val cost = JSONObject()
            costASocial?.let { cost.put("A_social", it) }
            costDTask?.let { cost.put("D_task", it) }
            costCI?.let { cost.put("C_I_interruption", it) }
            costCM?.let { cost.put("C_M_unmasking", it) }
            costTotal?.let { cost.put("C_total", it) }
            if (cost.length() > 0) bestStep.put("cost", cost)
            // Scene at best step
            val scene = JSONObject()
            bestEnvironment?.let { scene.put("environment", it) }
            bestLoudness?.let { scene.put("loudness", it) }
            bestActivity?.let { scene.put("activity", it) }
            bestActivityCategory?.let { scene.put("activity_category", it) }
            bestSocialGrouping?.let { scene.put("social_grouping", it) }
            bestInteractionMode?.let { scene.put("interaction_mode", it) }
            bestEnforcedSilence?.let { scene.put("enforced_silence_venue", it) }
            bestSettingFormality?.let { scene.put("setting_formality", it) }
            bestSubjectInMotion?.let { scene.put("subject_in_motion", it) }
            if (scene.length() > 0) bestStep.put("scene", scene)
            bestCostRationale?.let { bestStep.put("cost_rationale", it) }
            if (bestStep.length() > 0) put("best_step", bestStep)

            // ── LLM timeline narrative ─────────────────────────────────
            expectedTimeline?.let { put("expected_timeline", it) }

            // ── All forecast steps (full reconstruction) ───────────────
            forecastStepsJson?.let { put("forecast_steps", it) }
        }

        insertEvent(
            eventType = "simulate_system_decision",
            elapsedS = elapsedSeconds(),
            systemDecision = systemDecision,
            utilityStar = utilityStar,
            cycleCount = cycleCount,
            assetPath = assetPath,
            metadata = meta
        )
    }

    /** Researcher tapped "Play It" on the delivery confirmation dialog. */
    fun logSimulatePlayIt(
        systemDecision: String,
        assetPath: String,
        imageBase64: String? = null,
        wavBase64: String? = null
    ) {
        if (!enabled || sessionId == null) return
        lastActionWasSkip = false
        insertEvent(
            eventType = "simulate_play_it",
            elapsedS = elapsedSeconds(),
            systemDecision = systemDecision,
            assetPath = assetPath,
            imageBase64 = imageBase64,
            wavBase64 = wavBase64
        )
    }

    /** Researcher tapped "Skip" on the delivery confirmation dialog. */
    fun logSimulateSkip(
        systemDecision: String,
        utilityStar: Double? = null
    ) {
        if (!enabled || sessionId == null) return
        lastActionWasSkip = true
        insertEvent(
            eventType = "simulate_skip",
            elapsedS = elapsedSeconds(),
            systemDecision = systemDecision,
            utilityStar = utilityStar
        )
    }

    // ── Private helpers ─────────────────────────────────────────────────────

    private fun elapsedSeconds(): Double {
        if (sessionStartMs <= 0L) return 0.0
        return (System.currentTimeMillis() - sessionStartMs) / 1000.0
    }

    /**
     * Insert a single row into `study_events` via the Supabase REST API.
     * Runs asynchronously — failures are logged but never thrown to the caller.
     */
    private fun insertEvent(
        eventType: String,
        elapsedS: Double,
        notifLabel: String? = null,
        notifText: String? = null,
        aiPipeline: String? = null,
        systemDecision: String? = null,
        utilityStar: Double? = null,
        cycleCount: Int? = null,
        assetPath: String? = null,
        metadata: JSONObject? = null,
        imageBase64: String? = null,
        wavBase64: String? = null
    ) {
        val sid = sessionId ?: return

        val json = JSONObject().apply {
            put("session_id", sid)
            put("event_type", eventType)
            put("elapsed_s", elapsedS)
            // ── Timestamps from the phone clock in Europe/Berlin ─────────
            val nowMs = System.currentTimeMillis()
            put("timestamp_unix", nowMs)
            val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.GERMANY)
            sdf.timeZone = TimeZone.getTimeZone("Europe/Berlin")
            put("timestamp_local", sdf.format(Date(nowMs)))
            // ─────────────────────────────────────────────────────────────
            notifLabel?.let { put("notification_label", it) }
            notifText?.let { put("notification_text", it) }
            aiPipeline?.let { put("ai_pipeline", it) }
            systemDecision?.let { put("system_decision", it) }
            utilityStar?.let { put("utility_star", it) }
            cycleCount?.let { put("cycle_count", it) }
            assetPath?.let { put("asset_path", it) }
            metadata?.let { put("metadata", it) }
            imageBase64?.let { put("image_base64", it) }
            wavBase64?.let { put("wav_base64", it) }
        }

        scope.launch {
            try {
                val body = json.toString().toRequestBody(JSON_MEDIA)
                val request = Request.Builder()
                    .url(SUPABASE_URL)
                    .addHeader("apikey", SUPABASE_KEY)
                    .addHeader("Authorization", "Bearer $SUPABASE_KEY")
                    .addHeader("Content-Type", "application/json")
                    .addHeader("Prefer", "return=minimal")
                    .post(body)
                    .build()

                client.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.d(TAG, "✓ Logged [$eventType] session=$sid elapsed=${String.format("%.1f", elapsedS)}s")
                    } else {
                        Log.e(TAG, "✗ Failed [$eventType]: ${response.code} ${response.body?.string()}")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "✗ Network error logging [$eventType]", e)
            }
        }
    }
}
