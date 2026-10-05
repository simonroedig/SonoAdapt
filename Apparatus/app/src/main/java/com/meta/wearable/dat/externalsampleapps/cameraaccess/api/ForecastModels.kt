package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

// ══════════════════════════════════════════════════════════════════════════════
//  Configuration — mirrors Python anticipation.py CONFIG block (lines 107–130)
// ══════════════════════════════════════════════════════════════════════════════
object ForecastConfig {
    const val N_HISTORY_FRAMES = 18       // last N observed frames loaded (window cap)
    const val N_FULL_DETAIL = 5           // most-recent go in FULL detail
    const val MEMORY_LINES_MAX = 30       // cap on one-line summaries of older frames
    const val MIN_LEAD_TIME_S = 8.0       // earliest deliverable offset
    const val DT_FALLBACK_S = 5.0         // history Δt assumed when timestamps absent
    const val FORECAST_HORIZON_S = 240.0  // soft target: cover roughly next H seconds
    const val N_FORECAST_STEPS = 5        // always emit exactly this many steps
    const val UNC_BASE = 0.15             // uncertainty floor at nearest step
    const val UNC_AT_HORIZON = 0.85       // uncertainty floor at farthest step

    const val TEMPERATURE = 0.4f
    const val MAX_RETRIES = 2
}

// ══════════════════════════════════════════════════════════════════════════════
//  StepCosts — mirrors Python StepCosts dataclass (lines 397–446)
//  Delivery costs for one forecast step, per display type d ∈ {earcon, speech}
// ══════════════════════════════════════════════════════════════════════════════
data class StepCosts(
    val socialCost: Map<String, Double>,      // {"earcon": 0–1, "speech": 0–1}
    val disruptionCost: Map<String, Double>,   // {"earcon": 0–1, "speech": 0–1}
    val unmaskingCost: Map<String, Double>,     // {"earcon": 0–1, "speech": 0–1}
    val eTask: Double,                         // task engagement, type-independent
    val rationale: String = ""                 // one-sentence explanation
) {
    fun toDisplayString(): String {
        val sb = StringBuilder()
        sb.append("    Social:     earcon=${f2(socialCost["earcon"])}  speech=${f2(socialCost["speech"])}\n")
        sb.append("    Disruption: earcon=${f2(disruptionCost["earcon"])}  speech=${f2(disruptionCost["speech"])}\n")
        sb.append("    Unmasking:  earcon=${f2(unmaskingCost["earcon"])}  speech=${f2(unmaskingCost["speech"])}\n")
        sb.append("    E_task:     ${f2(eTask)}\n")
        if (rationale.isNotBlank()) {
            sb.append("    Rationale:  $rationale")
        }
        return sb.toString()
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put("social_cost", JSONObject().apply {
            put("earcon", socialCost["earcon"])
            put("speech", socialCost["speech"])
        })
        put("disruption_cost", JSONObject().apply {
            put("earcon", disruptionCost["earcon"])
            put("speech", disruptionCost["speech"])
        })
        put("unmasking_cost", JSONObject().apply {
            put("earcon", unmaskingCost["earcon"])
            put("speech", unmaskingCost["speech"])
        })
        put("e_task", eTask)
        put("cost_rationale", rationale)
    }

    companion object {
        /**
         * Parse from the flat-key LLM response dict.
         * Mirrors Python StepCosts.from_llm_dict() (lines 428–446).
         */
        fun fromLlmMap(d: JSONObject?): StepCosts {
            val obj = d ?: JSONObject()
            return StepCosts(
                socialCost = mapOf(
                    "earcon" to clip01(obj.optDouble("social_cost_earcon", 0.25)),
                    "speech" to clip01(obj.optDouble("social_cost_speech", 0.40))
                ),
                disruptionCost = mapOf(
                    "earcon" to clip01(obj.optDouble("disruption_cost_earcon", 0.35)),
                    "speech" to clip01(obj.optDouble("disruption_cost_speech", 0.55))
                ),
                unmaskingCost = mapOf(
                    "earcon" to clip01(obj.optDouble("unmasking_cost_earcon", 0.20)),
                    "speech" to clip01(obj.optDouble("unmasking_cost_speech", 0.18))
                ),
                eTask = clip01(obj.optDouble("e_task", 0.5)),
                rationale = obj.optString("cost_rationale", "")
            )
        }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
//  ForecastStep — one forecast step with scene content + timing + costs
// ══════════════════════════════════════════════════════════════════════════════
data class ForecastStep(
    // Scene content (from LLM)
    val sceneContext: JSONObject,         // {environment, estimated_overall_loudness}
    val soundSources: JSONArray,          // [{object, motion_state, ...}]
    val socialContext: JSONObject?,       // social context fields
    val taskContext: JSONObject?,         // task context fields
    val changeSummary: String = "",

    // Timing (derived by applyStepTiming)
    var durationMinS: Double = 0.0,
    var durationMaxS: Double = 0.0,
    var startEarliestS: Double = 0.0,
    var startLatestS: Double = 0.0,
    var tOffsetS: Double = 0.0,          // midpoint of start window
    var frameTimestampS: Double? = null,

    // Uncertainty + deliverability
    var forecastUncertainty: Double = 0.5,
    var deliverable: Boolean = false,

    // Costs (from LLM or heuristic)
    var costs: StepCosts? = null
) {
    val environment: String
        get() = sceneContext.optString("environment", "unknown")

    val estimatedOverallLoudness: Double
        get() = sceneContext.optDouble("estimated_overall_loudness", 0.0)

    val activityDescription: String
        get() = taskContext?.optString("activity_description", "unknown") ?: "unknown"

    val activityCategory: String
        get() = taskContext?.optString("activity_category", "unknown") ?: "unknown"

    val socialGrouping: String
        get() = socialContext?.optString("social_grouping", "unknown") ?: "unknown"

    val enforcedSilenceVenue: Boolean
        get() = socialContext?.optBoolean("enforced_silence_venue", false) ?: false

    val settingFormality: String
        get() = socialContext?.optString("setting_formality", "unknown") ?: "unknown"

    val interactionMode: String
        get() = socialContext?.optString("interaction_mode", "unknown") ?: "unknown"

    val subjectInMotion: Boolean
        get() = taskContext?.optBoolean("subject_in_motion", false) ?: false

    /**
     * Human-readable summary for one forecast step, mirroring Python
     * print_forecast_summary() (lines 1178–1245).
     */
    fun toDisplayString(index: Int): String {
        val sb = StringBuilder()
        val deliv = if (deliverable) "✓ deliverable" else "✗ too soon"
        val unc = f2(forecastUncertainty)

        // Timing window
        val se = startEarliestS
        val sl = startLatestS
        val win = if (abs(sl - se) < 0.5) "t+${se.toInt()}s"
                  else "t+${se.toInt()}–${sl.toInt()}s"
        val dur = if (durationMinS > 0 && durationMaxS > 0) {
            if (abs(durationMaxS - durationMinS) < 0.5) "~${durationMinS.toInt()}s"
            else "${durationMinS.toInt()}–${durationMaxS.toInt()}s"
        } else ""

        sb.append("┌─ Step ${index + 1}  starts $win  lasts $dur  [$deliv]  unc=$unc\n")
        sb.append("│  Env: $environment  Loudness: ${f2(estimatedOverallLoudness)}\n")
        sb.append("│  Activity: $activityDescription\n")
        sb.append("│  Social: $socialGrouping\n")
        if (changeSummary.isNotBlank()) {
            sb.append("│  Δ $changeSummary\n")
        }

        // Costs
        val c = costs
        if (c != null) {
            sb.append("│  ── Costs ──\n")
            sb.append("│  ${c.toDisplayString().replace("\n", "\n│  ").trimEnd()}\n")
        }
        sb.append("└${"─".repeat(50)}")

        return sb.toString()
    }

    /**
     * Serialize this step back to a JSON dict matching the captioning format,
     * mirroring Python _frame_out_dict() (lines 1164–1172).
     */
    fun toJson(): JSONObject = JSONObject().apply {
        put("t_offset_s", tOffsetS)
        put("observed", false)
        put("scene_context", sceneContext)
        put("sound_sources", soundSources)
        socialContext?.let { put("social_context", it) }
        taskContext?.let { put("task_context", it) }
        put("forecast_uncertainty", forecastUncertainty)
        put("deliverable", deliverable)
        put("duration_min_s", durationMinS)
        put("duration_max_s", durationMaxS)
        put("start_earliest_s", startEarliestS)
        put("start_latest_s", startLatestS)
        frameTimestampS?.let { put("frame_timestamp_s", it) }
        if (changeSummary.isNotBlank()) put("change_summary", changeSummary)
        costs?.let { put("costs", it.toJson()) }
    }
}

// ══════════════════════════════════════════════════════════════════════════════
//  ForecastResult — top-level container for a forecast call
// ══════════════════════════════════════════════════════════════════════════════
data class ForecastResult(
    val steps: List<ForecastStep>,
    val expectedTimeline: String
) {
    /**
     * Full human-readable summary mirroring Python print_forecast_summary().
     */
    fun toDisplayString(): String {
        val sb = StringBuilder()
        sb.append("┌─ FORECAST ${"─".repeat(45)}\n")
        if (expectedTimeline.isNotBlank()) {
            sb.append("│  Timeline: $expectedTimeline\n")
            sb.append("│${"─".repeat(55)}\n")
        }
        for ((i, step) in steps.withIndex()) {
            sb.append("│\n")
            sb.append(step.toDisplayString(i)).append("\n")
        }
        sb.append("└${"─".repeat(56)}")
        return sb.toString()
    }
}

// ══════════════════════════════════════════════════════════════════════════════
//  Step-timing derivation — mirrors Python _apply_step_timing() (lines 319–372)
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Monotonic uncertainty floor, linear from UNC_BASE to UNC_AT_HORIZON.
 * Mirrors Python horizon_uncertainty() (lines 311–316).
 */
fun horizonUncertainty(tOffsetS: Double, maxOffset: Double): Double {
    if (maxOffset <= 0) return ForecastConfig.UNC_AT_HORIZON
    val frac = max(0.0, min(1.0, tOffsetS / maxOffset))
    return round3(ForecastConfig.UNC_BASE + (ForecastConfig.UNC_AT_HORIZON - ForecastConfig.UNC_BASE) * frac)
}

/**
 * Turn a sequence of forecast steps (each with duration_min/max) into a timeline.
 * Steps are consecutive; step 0 begins now (start = 0).
 * Mirrors Python _apply_step_timing() (lines 319–372).
 */
fun applyStepTiming(
    steps: List<ForecastStep>,
    t0Ts: Double?,
    minLead: Double = ForecastConfig.MIN_LEAD_TIME_S
) {
    if (steps.isEmpty()) return

    var cumMin = 0.0
    var cumMax = 0.0
    for (step in steps) {
        var dmin = max(0.0, step.durationMinS)
        var dmax = max(0.0, step.durationMaxS)
        if (dmax < dmin) {
            val tmp = dmin; dmin = dmax; dmax = tmp
        }
        step.durationMinS = round3(dmin)
        step.durationMaxS = round3(dmax)
        step.startEarliestS = round3(cumMin)
        step.startLatestS = round3(cumMax)
        cumMin += dmin
        cumMax += dmax
    }

    // Representative offset + deliverability (UPDATED to match Python lines 422-436)
    //
    // CRITICAL FIX: Python changed the deliverable rule from:
    //   OLD: deliverable = start_earliest >= min_lead  (step 0 NEVER deliverable)
    //   NEW: deliverable = end_earliest > min_lead     (step 0 IS deliverable if
    //        its duration reaches past min_lead)
    //
    // The old rule caused "the commit window to recede exactly as fast as the cursor
    // advanced" — the system deferred forever. (See Python comments lines 390-401.)
    var maxMid = 0.0
    for (step in steps) {
        val mid = 0.5 * (step.startEarliestS + step.startLatestS)
        val endEarliest = step.startEarliestS + step.durationMinS
        step.deliverable = endEarliest > minLead - 1e-6

        // When the step begins before the lead time but IS deliverable, clamp
        // t_offset_s UP to min_lead (deliver as early as legally possible).
        // Python lines 433-436.
        if (step.deliverable && mid < minLead) {
            step.tOffsetS = round3(minLead)
        } else {
            step.tOffsetS = round3(mid)
        }
        maxMid = max(maxMid, step.tOffsetS)
    }

    for (step in steps) {
        step.frameTimestampS = if (t0Ts != null) round3(t0Ts + step.tOffsetS) else null
        val floor = horizonUncertainty(step.tOffsetS, maxMid)
        step.forecastUncertainty = round3(max(step.forecastUncertainty, floor))
    }
}

// ══════════════════════════════════════════════════════════════════════════════
//  Heuristic cost estimation — mirrors Python heuristic_costs() (lines 475–534)
//  LLM-free cost estimate for offline fallback
// ══════════════════════════════════════════════════════════════════════════════

private val SPEECH_WORDS = listOf("speech", "voice", "talking", "conversation", "podcast",
    "announcement", "chatter", "radio")
private val MUSIC_WORDS = listOf("music", "song", "melody", "instrument", "singing")

/**
 * Coarse background class: 'speech' | 'music' | 'quiet' | 'other'.
 * Mirrors Python _soundscape_class() (lines 455–472).
 */
fun soundscapeClass(soundSources: JSONArray, overallLoudness: Double): String {
    var hasSpeech = false
    var hasMusic = false
    for (i in 0 until soundSources.length()) {
        val s = soundSources.optJSONObject(i) ?: continue
        if (s.optDouble("sound_probability", 0.0) < 0.4) continue
        val types = s.optJSONArray("sound_type")
        val blob = buildString {
            if (types != null) {
                for (j in 0 until types.length()) {
                    append(types.optString(j, "").lowercase())
                    append(" ")
                }
            }
            append(s.optString("object", "").lowercase())
        }
        if (SPEECH_WORDS.any { it in blob }) hasSpeech = true
        if (MUSIC_WORDS.any { it in blob }) hasMusic = true
    }
    if (hasSpeech) return "speech"
    if (hasMusic) return "music"
    if (overallLoudness < 0.3) return "quiet"
    return "other"
}

/**
 * LLM-free cost estimate. Mirrors Python heuristic_costs() (lines 475–534).
 */
fun heuristicCosts(step: ForecastStep): StepCosts {
    val L = max(0.0, min(1.0, step.estimatedOverallLoudness))
    val cls = soundscapeClass(step.soundSources, L)

    // Unmasking: loudness floor + same-class penalty
    val umE = 0.06 + 0.20 * L + if (cls == "music") 0.12 else 0.0
    val umS = 0.04 + 0.16 * L + if (cls == "speech") 0.20 else 0.0

    // Task engagement from task context
    var eTask = 0.4
    val cat = step.activityCategory.lowercase()
    if (listOf("work", "focus", "read", "study", "mental").any { it in cat }) {
        eTask = 0.75
    } else if (listOf("transit", "physical", "sport", "cook").any { it in cat }) {
        eTask = 0.55
    } else if (listOf("idle", "wait", "rest", "leisure").any { it in cat }) {
        eTask = 0.25
    }
    if (step.subjectInMotion) {
        eTask = min(1.0, eTask + 0.05)
    }

    // Social: grouping + formality + enforced silence
    var baseSocial = 0.18
    val grouping = step.socialGrouping.lowercase()
    if (listOf("group", "crowd", "colleague", "friend", "people").any { it in grouping }) {
        baseSocial = 0.30
    }
    if (listOf("convers", "meeting", "talk", "interact").any { it in step.interactionMode.lowercase() }) {
        baseSocial += 0.18
    }
    if (step.settingFormality.lowercase().startsWith("formal")) {
        baseSocial += 0.08
    }
    if (step.enforcedSilenceVenue) {
        baseSocial += 0.22
    }
    val socE = baseSocial
    val socS = baseSocial * 1.5 + 0.05

    // Disruption: driven by task engagement
    val disE = 0.15 + 0.50 * eTask
    val disS = disE * 1.4 + 0.08

    return StepCosts(
        socialCost = mapOf("earcon" to clip01(socE), "speech" to clip01(socS)),
        disruptionCost = mapOf("earcon" to clip01(disE), "speech" to clip01(disS)),
        unmaskingCost = mapOf("earcon" to clip01(umE), "speech" to clip01(umS)),
        eTask = clip01(eTask),
        rationale = "heuristic: background=$cls, loudness=${f2(L)}, engagement=${f2(eTask)}"
    )
}

/**
 * Build a persistence forecast from the last observed frame.
 * Mirrors Python _persistence_forecast() (lines 540–571).
 */
fun persistenceForecast(
    lastFrame: JSONObject,
    t0Ts: Double?,
    horizonS: Double = ForecastConfig.FORECAST_HORIZON_S,
    nSteps: Int = ForecastConfig.N_FORECAST_STEPS,
    minLead: Double = ForecastConfig.MIN_LEAD_TIME_S
): ForecastResult {
    val n = max(1, nSteps)
    val stepDur = max(ForecastConfig.DT_FALLBACK_S, horizonS / n)
    val steps = mutableListOf<ForecastStep>()

    for (i in 0 until n) {
        val step = ForecastStep(
            sceneContext = JSONObject(lastFrame.optJSONObject("scene_context")?.toString() ?: "{}"),
            soundSources = JSONArray(lastFrame.optJSONArray("sound_sources")?.toString() ?: "[]"),
            socialContext = lastFrame.optJSONObject("social_context")?.let { JSONObject(it.toString()) },
            taskContext = lastFrame.optJSONObject("task_context")?.let { JSONObject(it.toString()) },
            changeSummary = "no notable change (persistence)",
            durationMinS = stepDur * 0.7,
            durationMaxS = stepDur * 1.3,
            forecastUncertainty = 0.5
        )
        step.costs = heuristicCosts(step)
        steps.add(step)
    }

    applyStepTiming(steps, t0Ts, minLead)

    val last = steps.lastOrNull()
    val endS = if (last != null) last.startLatestS + (last.durationMaxS) else 0.0
    val env = steps.firstOrNull()?.environment ?: "unknown"
    val timeline = "(persistence) scene assumed to hold through ~t+${endS.toInt()}s: $env, no modelled transitions."

    return ForecastResult(steps = steps, expectedTimeline = timeline)
}

// ══════════════════════════════════════════════════════════════════════════════
//  Earlier context builder — mirrors Python build_earlier_context() (lines 275–305)
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Build compact earlier_context from the memory sidecar narrative for frames
 * older than the recent-history window. Returns a JSONArray of summary objects.
 */
fun buildEarlierContext(
    narrativeJson: String?,
    sessionLogJson: String?,
    oldestFullDetailTs: Double,
    cursorTs: Double,
    maxLines: Int = ForecastConfig.MEMORY_LINES_MAX
): JSONArray {
    val lines = mutableListOf<JSONObject>()

    // Prefer the memory sidecar's narrative lines
    if (!narrativeJson.isNullOrBlank()) {
        try {
            val memoryObj = JSONObject(narrativeJson)
            val narrative = memoryObj.optJSONArray("narrative")
            if (narrative != null) {
                for (i in 0 until narrative.length()) {
                    val e = narrative.optJSONObject(i) ?: continue
                    val ts = e.optDouble("t_start", Double.NaN)
                    if (ts.isNaN()) continue
                    if (ts < oldestFullDetailTs - 1e-6 && ts <= cursorTs + 1e-6) {
                        lines.add(JSONObject().apply {
                            put("t_start", ts)
                            put("t_end", e.optDouble("t_end", ts))
                            put("summary", e.optString("event_summary", ""))
                        })
                    }
                }
            }
        } catch (_: Exception) { }
    }

    // Fallback: synthesise from session log frames
    if (lines.isEmpty() && !sessionLogJson.isNullOrBlank()) {
        try {
            val sessionArr = JSONArray(sessionLogJson)
            for (i in 0 until sessionArr.length()) {
                val d = sessionArr.optJSONObject(i) ?: continue
                val ts = d.optDouble("frame_timestamp_s", Double.NaN)
                if (ts.isNaN()) continue
                if (ts < oldestFullDetailTs - 1e-6 && ts <= cursorTs + 1e-6) {
                    lines.add(JSONObject().apply {
                        put("t_start", ts)
                        put("t_end", ts)
                        put("summary", frameOneLiner(d))
                    })
                }
            }
        } catch (_: Exception) { }
    }

    // Cap to most recent maxLines
    val capped = if (lines.size > maxLines) lines.takeLast(maxLines) else lines
    return JSONArray().apply { capped.forEach { put(it) } }
}

/**
 * Fallback one-line summary of a frame when no memory sidecar exists.
 * Mirrors Python _frame_oneliner() (lines 259–272).
 */
private fun frameOneLiner(d: JSONObject): String {
    val ctx = d.optJSONObject("scene_context") ?: JSONObject()
    val env = ctx.optString("environment", "?")
    val loud = ctx.optDouble("estimated_overall_loudness", Double.NaN)
    val summ = d.optString("event_summary", "").ifBlank {
        d.optJSONObject("task_context")?.optString("activity_description", "") ?: ""
    }
    val base = summ.ifBlank { "in $env" }
    return if (!loud.isNaN()) "$base (env=$env, loudness≈${f2(loud)})" else "$base (env=$env)"
}

// ══════════════════════════════════════════════════════════════════════════════
//  Utility helpers
// ══════════════════════════════════════════════════════════════════════════════

/** Clamp to [0, 1], default on NaN. Mirrors Python _clip01(). */
fun clip01(x: Double, default: Double = 0.5): Double {
    if (x.isNaN() || x.isInfinite()) return default
    return round3(max(0.0, min(1.0, x)))
}

/** Format a Double to 2 decimal places. */
fun f2(v: Double?): String = String.format(java.util.Locale.US, "%.2f", v ?: 0.0)

/** Round to 3 decimal places. */
fun round3(v: Double): Double = Math.round(v * 1000.0) / 1000.0
