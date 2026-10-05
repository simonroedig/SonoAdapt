package com.meta.wearable.dat.externalsampleapps.cameraaccess.api

import android.util.Log
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.round

/**
 * Utility optimizer — pick the most opportune moment and auditory display type
 * for delivering a notification.
 *
 * Direct port of Python utility.py (sections 1–4).
 *
 * Utility formulation (updated: importance × urgency as geometric mean):
 *     (t*, d*) = argmax_{t∈[t0,t0+H], d∈{earcon,speech}}  U(t, d)
 *
 *     U(t, d) =  B(t, d)  −  C(t, d)
 *       B(t,d) =  α·√(I_n · Ũ_n(t)) + β·G_d               (benefit)
 *       C(t,d) =  λ_I·C_I(t, d) + λ_M·C_M(t, d)           (cost)
 *       I_n    =  w_s·I_sender + w_c·I_content              (importance)
 *       Ũ_n(t) =  U_n·e^{−(t−t_a)/τ_u}                    (effective urgency, decays)
 *       C_I    =  w_A·A_social(t, d) + w_D·D_task(t, d)    (interruption cost)
 *       C_M    =  M(Ŝ(t), d)                                (unmasking cost)
 *
 * With α+β=1, λ_I+λ_M=1 and each w-pair summing to 1,
 * B, C ∈ [0,1] and U ∈ [−1, 1].
 *
 * The importance/urgency pair enters as a GEOMETRIC mean, not arithmetic.
 * An arithmetic mean lets one strong dimension carry a weak one (e.g. urgent
 * but completely unimportant → 0.5 benefit). The geometric mean is 0 whenever
 * EITHER factor is 0, so both must be jointly present for a notification to
 * score well — this is what lets importance actually gate urgency (and vice
 * versa) rather than being a bystander next to it.
 *
 * Where each cost term comes from:
 *     ForecastStep.costs.socialCost[d]      → A_social(t, d)
 *     ForecastStep.costs.disruptionCost[d]  → D_task(t, d)
 *     ForecastStep.costs.unmaskingCost[d]   → C_M(t, d)
 *     ForecastStep.tOffsetS                 → t (midpoint of step's start window)
 *     ForecastStep.deliverable              → lead-time filter
 *     NotificationInfo(...)                 → I_sender, I_content, U_n, t_a
 *
 * `e_task` (type-independent task engagement) is carried through for inspection
 * but does NOT enter U: the formulation uses the per-type disruption cost
 * D_task(t,d) instead.
 */
object UtilityOptimizer {
    private const val TAG = "CameraAccess:UtilityOptimizer"

    val DISPLAY_TYPES = listOf("earcon", "speech")

    // Utilities closer than this count as tied → tie-break rules decide
    private const val TIE_TOL = 1e-6

    // ═════════════════════════════════════════════════════════════════════════
    //  1 · Inputs: the notification, and the tunable weights
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * The incoming notification whose delivery is being scheduled.
     * Mirrors Python Notification (lines 124–134).
     */
    data class NotificationInfo(
        val importanceSender: Double = 0.5,   // I_sender ∈ [0,1]
        val importanceContent: Double = 0.5,  // I_content ∈ [0,1]
        val urgency: Double = 0.5,            // U_n ∈ [0,1], as assigned at arrival t_a
        val elapsedS: Double = 0.0,           // t_0 − t_a: how long it has already waited
        val label: String = "notification"
    )

    /**
     * All tunable weights and model constants of the utility formulation.
     * Mirrors Python UtilityWeights (lines 137–214).
     *
     * Group constraints (checked by validate()):
     *   α + β = 1          (geometric-mean formulation)
     *   λ_I + λ_M = 1
     *   w_sender + w_content = 1
     *   w_A + w_D = 1
     *
     * These keep B, C ∈ [0,1] and therefore U ∈ [−1,1].
     */
    data class UtilityWeights(
        // Benefit weights (updated to geometric mean formulation, α+β=1).
        // α weights the geometric mean of importance and effective urgency:
        //   √(I_n · Ũ_n(t)) — both factors must be jointly present to score well.
        // β weights the urgency-scaled semantic benefit G_d·Ũ_n(t) — sets the
        //   earcon/speech threshold at β·(G_speech−G_earcon)·Ũ_n(t), i.e.
        //   0.225 at peak urgency, decaying with it; speech is only worth
        //   the extra cost when there is still something to act on.
        val alpha: Double = 0.75,      // weight on √(I_n · Ũ_n(t))
        val beta: Double = 0.25,       // weight on semantic benefit G_d·Ũ_n(t)
        // Importance split
        val wSender: Double = 0.5,
        val wContent: Double = 0.5,
        // Cost split
        val lambdaI: Double = 0.6,     // weight on interruption cost C_I
        val lambdaM: Double = 0.4,     // weight on acoustic unmasking cost C_M
        // Interruption split
        val wA: Double = 0.5,          // weight on A_social
        val wD: Double = 0.5,          // weight on D_task
        // ── Model constants ──────────────────────────────────────────────
        // G_d: semantic benefit per display type (content conveyed without device).
        //   G_earcon ≈ 0.1 (occurrence + category only)
        //   G_speech = 1.0 (sender + content)
        val G: Map<String, Double> = mapOf("earcon" to 0.1, "speech" to 1.0),
        // τ_u anchors: τ_u(U_n) = tau_min_s^U_n · tau_max_s^(1−U_n)
        val tauMinS: Double = 30.0,    // most urgent   → forced within ≈1.5 min
        val tauMaxS: Double = 3600.0,  // least urgent  → forced within ≈3 h
        // SUPPRESSION — delivering nothing is always an option, worth exactly 0:
        // no benefit gained, no interruption cost paid. When the best available
        // (t, d) still scores below this, the message should not be delivered.
        // Set to null to force a delivery in every case.
        val suppressBelow: Double? = 0.0
    ) {
        /**
         * Validate that weight groups sum to 1.
         * Mirrors Python UtilityWeights.validate() (lines 179–196).
         */
        fun validate(): UtilityWeights {
            val tol = 1e-6
            val sums = mapOf(
                "alpha+beta" to (alpha + beta),   // geometric-mean formulation: α+β=1
                "lambda_I+lambda_M" to (lambdaI + lambdaM),
                "w_sender+w_content" to (wSender + wContent),
                "w_A+w_D" to (wA + wD)
            )
            val bad = sums.filter { abs(it.value - 1.0) > tol }
            if (bad.isNotEmpty()) {
                throw IllegalArgumentException(
                    "Weight groups must each sum to 1.0; offending: $bad"
                )
            }
            val missingTypes = DISPLAY_TYPES.filter { it !in G }
            if (missingTypes.isNotEmpty()) {
                throw IllegalArgumentException("G is missing display types: $missingTypes")
            }
            if (G.values.any { it < 0.0 || it > 1.0 }) {
                throw IllegalArgumentException("All G_d must lie in [0,1]; got $G")
            }
            if (!(tauMinS > 0.0 && tauMinS <= tauMaxS)) {
                throw IllegalArgumentException("Require 0 < tau_min_s <= tau_max_s.")
            }
            return this
        }

        /** The extra-cost threshold below which speech wins over earcon.
         *  = β · (G_speech − G_earcon)
         */
        val speechThreshold: Double
            get() = beta * ((G["speech"] ?: 1.0) - (G["earcon"] ?: 0.1))
    }

    // ═════════════════════════════════════════════════════════════════════════
    //  2 · One scored row in the utility table
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * One fully-scored (step, display_type) pair.
     * Contains all intermediate terms for inspection / display.
     */
    data class UtilityRow(
        val step: Int,
        val tOffsetS: Double,
        val display: String,
        val delayS: Double,
        // Benefit terms
        val iN: Double,          // I_n (importance)
        val uEff: Double,        // Ũ_n (effective urgency after decay)
        val gD: Double,          // G_d (semantic benefit)
        val B: Double,           // total benefit
        // Cost terms
        val aSocial: Double,     // A_social(t, d)
        val dTask: Double,       // D_task(t, d)
        val cI: Double,          // C_I (interruption cost)
        val cM: Double,          // C_M (unmasking cost)
        val C: Double,           // total cost
        // Result
        val U: Double,           // U(t,d) = B − C
        // Metadata
        val candidate: Boolean,
        val deliverable: Boolean?,
        val scorable: Boolean,
        val forecastUncertainty: Double?
    )

    /**
     * The full result of evaluating a forecast: all rows + the optimal solution.
     */
    data class UtilityResult(
        val notification: NotificationInfo,
        val weights: UtilityWeights,
        val tauUS: Double,              // τ_u for this notification's urgency
        val speechThreshold: Double,    // Δcost below which speech wins
        val horizonS: Double,
        val nSteps: Int,
        val nCandidates: Int,
        val rows: List<UtilityRow>,
        val optimalSolution: UtilityRow?, // null if no deliverable candidate
        val suppressed: Boolean,         // best U < suppress_below → don't deliver
        val deliver: Boolean             // = optimalSolution != null && !suppressed
    ) {
        /**
         * Human-readable summary for the UI.
         * Mirrors Python print_utility_summary() (lines 613–658).
         */
        fun toDisplayString(): String {
            val sb = StringBuilder()
            sb.append("┌─ UTILITY  U(t,d) = B(t,d) − C(t,d) ${"─".repeat(20)}\n")
            sb.append("│  I_n=${r2(rows.firstOrNull()?.iN ?: 0.0)}  ")
            sb.append("U_n=${r2(notification.urgency)} → τ_u=${tauUS.toLong()}s   ")
            sb.append("withheld ${notification.elapsedS.toLong()}s\n")
            sb.append("│  H=${horizonS.toLong()}s   ")
            sb.append("$nCandidates/$nSteps deliverable   ")
            sb.append("speech wins below Δcost ${r2(speechThreshold)}\n")
            sb.append("│\n")

            // Group rows by step index
            val byStep = rows.groupBy { it.step }
            for (stepIdx in byStep.keys.sorted()) {
                val stepRows = byStep[stepIdx] ?: continue
                val first = stepRows.first()
                val mark = if (first.candidate) "✓"
                           else if (first.scorable) "·"
                           else "!"
                sb.append("│  $mark step $stepIdx  t+${first.tOffsetS.toLong()}s  ")
                sb.append("unc=${first.forecastUncertainty?.let { r2(it) } ?: "?"}\n")
                for (r in stepRows) {
                    val star = if (optimalSolution != null &&
                                   r.step == optimalSolution.step &&
                                   r.display == optimalSolution.display) " ←" else ""
                    sb.append("│    ${r.display.padStart(7)}  ")
                    sb.append("A=${r2(r.aSocial)} D=${r2(r.dTask)} ")
                    sb.append("C_M=${r2(r.cM)} │ ")
                    sb.append("B=${r3(r.B)} C=${r3(r.C)} ")
                    sb.append("U=${signed3(r.U)}$star\n")
                }
            }
            sb.append("│\n")

            if (optimalSolution != null) {
                val best = optimalSolution
                if (suppressed) {
                    sb.append("│  ✗ SUPPRESSED: best U*=${signed3(best.U)} < ${r2(weights.suppressBelow ?: 0.0)}\n")
                    sb.append("│    Would have been ${best.display.uppercase()} at ")
                    sb.append("t+${best.tOffsetS.toLong()}s — but delivering nothing is better.\n")
                } else {
                    sb.append("│  ► OPTIMAL: deliver ${best.display.uppercase()} at ")
                    sb.append("t+${best.tOffsetS.toLong()}s (step ${best.step})   ")
                    sb.append("U*=${signed3(best.U)}\n")
                }
                sb.append("│    Ũ_n=${r2(best.uEff)} G_d=${r2(best.gD)} │ ")
                sb.append("A_social=${r2(best.aSocial)} D_task=${r2(best.dTask)} ")
                sb.append("C_M=${r2(best.cM)}\n")
            } else {
                sb.append("│  ► No deliverable candidate — keep waiting and re-plan.\n")
            }
            sb.append("└${"─".repeat(56)}")

            return sb.toString()
        }
    }

    // ═════════════════════════════════════════════════════════════════════════
    //  3 · Core terms of U(t, d)
    //      Mirrors Python utility.py lines 361–435
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * I_n = w_s·I_sender + w_c·I_content.
     * Mirrors Python importance() (line 364–366).
     */
    fun importance(n: NotificationInfo, w: UtilityWeights): Double {
        return w.wSender * n.importanceSender + w.wContent * n.importanceContent
    }

    /**
     * τ_u(U_n) = τ_min^U_n · τ_max^(1−U_n) — geometric interpolation, in seconds.
     * Mirrors Python tau_u() (lines 369–372).
     *
     * At urgency 1.0: τ_u = τ_min (30s default → message loses value fast)
     * At urgency 0.0: τ_u = τ_max (3600s default → can wait a long time)
     */
    fun tauU(urgency: Double, w: UtilityWeights): Double {
        val u = min(1.0, max(0.0, urgency))
        return exp(u * ln(w.tauMinS) + (1.0 - u) * ln(w.tauMaxS))
    }

    /**
     * Ũ_n(t) = U_n·e^{−delay/τ_u}.
     * Mirrors Python effective_urgency() (lines 375–384).
     *
     * Starts at U_n on arrival and decays towards 0 the longer delivery is deferred.
     * The decay rate is set by the urgency itself (τ_u), so an urgent message loses
     * value in seconds while a low-urgency one can wait out a bad context.
     */
    fun effectiveUrgency(n: NotificationInfo, w: UtilityWeights, delayS: Double): Double {
        return n.urgency * exp(-max(0.0, delayS) / tauU(n.urgency, w))
    }

    /**
     * G_d — content conveyed by display type d without device interaction.
     * Mirrors Python semantic_benefit() (lines 387–389).
     */
    fun semanticBenefit(d: String, w: UtilityWeights): Double {
        return w.G[d] ?: 0.0
    }

    /**
     * B(t,d) = α·√(I_n · Ũ_n(t)) + β·G_d·Ũ_n(t).
     *
     * The semantic benefit of a display type is scaled by effective urgency:
     * what speech buys over an earcon is that you can act without reaching
     * for the device, and that is only worth paying for while there is still
     * something to act on. High urgency → strong speech preference;
     * low urgency → earcon suffices.
     * Mirrors Python benefit() (utility.py).
     */
    fun benefit(n: NotificationInfo, w: UtilityWeights, d: String, delayS: Double): Double {
        val iN = max(0.0, importance(n, w))
        val uEff = max(0.0, effectiveUrgency(n, w, delayS))
        return w.alpha * Math.sqrt(iN * uEff) + w.beta * semanticBenefit(d, w) * uEff
    }

    /**
     * C_I(t,d) = w_A·A_social(t,d) + w_D·D_task(t,d).
     * Mirrors Python interrupt_cost() (lines 399–401).
     */
    fun interruptCost(step: ForecastStep, d: String, w: UtilityWeights): Double {
        val aSocial = step.costs?.socialCost?.get(d) ?: 0.0
        val dTask = step.costs?.disruptionCost?.get(d) ?: 0.0
        return w.wA * aSocial + w.wD * dTask
    }

    /**
     * C_M(t,d) = M(Ŝ(t), d) — estimated by anticipation from the forecast soundscape.
     * Mirrors Python masking_cost() (lines 404–406).
     */
    fun maskingCost(step: ForecastStep, d: String): Double {
        return step.costs?.unmaskingCost?.get(d) ?: 0.0
    }

    /**
     * Full U(t, d) with all intermediate terms, for one forecast step and display type.
     * Mirrors Python utility() (lines 409–435).
     *
     * step.tOffsetS is relative to planning origin t_0; the delay that drives Ũ_n
     * is n.elapsedS + t_offset_s, i.e. measured from the arrival time t_a.
     */
    fun utilityScore(
        n: NotificationInfo,
        step: ForecastStep,
        d: String,
        w: UtilityWeights,
        stepIndex: Int
    ): UtilityRow {
        val delay = max(0.0, n.elapsedS + step.tOffsetS)
        val B = benefit(n, w, d, delay)
        val cI = interruptCost(step, d, w)
        val cM = maskingCost(step, d)
        val C = w.lambdaI * cI + w.lambdaM * cM
        return UtilityRow(
            step = stepIndex,
            tOffsetS = step.tOffsetS,
            display = d,
            delayS = r4(delay),
            iN = r4(importance(n, w)),
            uEff = r4(effectiveUrgency(n, w, delay)),
            gD = r4(semanticBenefit(d, w)),
            B = r4(B),
            aSocial = step.costs?.socialCost?.get(d) ?: 0.0,
            dTask = step.costs?.disruptionCost?.get(d) ?: 0.0,
            cI = r4(cI),
            cM = step.costs?.unmaskingCost?.get(d) ?: 0.0,
            C = r4(C),
            U = r4(B - C),
            candidate = false,  // set later by evaluate()
            deliverable = step.deliverable,
            scorable = step.costs != null,
            forecastUncertainty = step.forecastUncertainty
        )
    }

    // ═════════════════════════════════════════════════════════════════════════
    //  4 · Evaluation: build the full U(t, d) table and pick the argmax
    //      Mirrors Python evaluate() (lines 466–506)
    // ═════════════════════════════════════════════════════════════════════════

    /**
     * Whether a step is a valid candidate for delivery.
     * Mirrors Python _is_candidate() (lines 441–451).
     */
    private fun isCandidate(
        step: ForecastStep,
        horizonS: Double,
        respectDeliverable: Boolean
    ): Boolean {
        if (step.costs == null) return false         // no costs → can't score
        if (step.tOffsetS < 0.0) return false        // observed frames are context only
        if (step.tOffsetS > horizonS + 1e-9) return false
        if (respectDeliverable && !step.deliverable) return false  // too soon (lead-time)
        return true
    }

    /**
     * Compare two rows for the argmax. Returns true if `a` is strictly better than `b`.
     * Mirrors Python _selection_key() (lines 454–463).
     *
     * 1. Highest utility (quantized by TIE_TOL so near-equal count as tied)
     * 2. Earliest delivery time — prefer sooner
     * 3. Least intrusive display type (lowest G_d) — deterministic final tie-break
     */
    private fun isBetterThan(a: UtilityRow, b: UtilityRow, w: UtilityWeights): Boolean {
        // Negate utility so lower = better (highest U wins)
        val aU = -round(a.U / TIE_TOL).toLong()
        val bU = -round(b.U / TIE_TOL).toLong()
        if (aU != bU) return aU < bU
        // Earliest delivery time wins
        if (a.tOffsetS != b.tOffsetS) return a.tOffsetS < b.tOffsetS
        // Least intrusive display type wins
        return (w.G[a.display] ?: 0.0) < (w.G[b.display] ?: 0.0)
    }

    /**
     * Compute U(t, d) for every (step, display type); return the table and the argmax.
     * Mirrors Python evaluate() (lines 466–506).
     *
     * @param steps           Forecast steps from Anticipation.generateForecast()
     * @param notification    The notification being scheduled
     * @param weights         Tunable weights (defaults are the paper's values)
     * @param horizonS        Max horizon in seconds (null → last step's t_offset)
     * @param respectDeliverable  Whether to honor the per-step 'deliverable' flag
     */
    fun evaluate(
        steps: List<ForecastStep>,
        notification: NotificationInfo,
        weights: UtilityWeights = UtilityWeights(),
        horizonS: Double? = null,
        respectDeliverable: Boolean = true
    ): UtilityResult {
        weights.validate()

        val effectiveHorizon = horizonS
            ?: steps.filter { it.tOffsetS > 0 }.maxOfOrNull { it.tOffsetS }
            ?: 0.0

        val rows = mutableListOf<UtilityRow>()
        var best: UtilityRow? = null

        for ((i, step) in steps.withIndex()) {
            val candidate = isCandidate(step, effectiveHorizon, respectDeliverable)

            for (d in DISPLAY_TYPES) {
                val row = utilityScore(notification, step, d, weights, i)
                    .copy(candidate = candidate)  // mark candidacy
                rows.add(row)

                if (candidate) {
                    if (best == null || isBetterThan(row, best, weights)) {
                        best = row
                    }
                }
            }
        }

        val tauUS = tauU(notification.urgency, weights)

        // "Deliver nothing" is the third action, worth 0. When even the best
        // moment and type score below the suppression floor, delivering is worse
        // than staying silent. Mirrors Python evaluate() lines 517–523.
        val suppressed = weights.suppressBelow != null &&
                         best != null &&
                         best.U < weights.suppressBelow

        Log.d(TAG, "Evaluated ${rows.size} (step,display) pairs: " +
                "${rows.count { it.candidate }} candidates, " +
                "optimal=${best?.let { "${it.display}@t+${it.tOffsetS.toLong()}s U=${signed3(it.U)}" } ?: "none"}" +
                if (suppressed) " [SUPPRESSED]" else "")

        return UtilityResult(
            notification = notification,
            weights = weights,
            tauUS = r1(tauUS),
            speechThreshold = r4(weights.speechThreshold),
            horizonS = effectiveHorizon,
            nSteps = steps.size,
            nCandidates = rows.count { it.candidate } / DISPLAY_TYPES.size,
            rows = rows,
            optimalSolution = best,
            suppressed = suppressed,
            deliver = best != null && !suppressed
        )
    }

    // ═════════════════════════════════════════════════════════════════════════
    //  Formatting helpers
    // ═════════════════════════════════════════════════════════════════════════
    private fun r1(v: Double): Double = Math.round(v * 10.0) / 10.0
    private fun r4(v: Double): Double = Math.round(v * 10000.0) / 10000.0
    private fun r2(v: Double): String = String.format(java.util.Locale.US, "%.2f", v)
    private fun r3(v: Double): String = String.format(java.util.Locale.US, "%.3f", v)
    private fun signed3(v: Double): String = String.format(java.util.Locale.US, "%+.3f", v)
}
