/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

// StreamUiState - DAT Camera Streaming UI State
//
// This data class manages UI state for camera streaming operations using the DAT API.

package com.meta.wearable.dat.externalsampleapps.cameraaccess.stream

import android.graphics.Bitmap
import com.meta.wearable.dat.camera.types.StreamState

data class SceneLogEntry(
    val timestamp: Long,
    val socialGrouping: String,
    val activityCategory: String,
    val eventSummary: String,
    val sceneMemory: String,
    val estimatedOverallLoudness: Double,
    val rawJson: String
)

/**
 * Holds the details of a pipeline-committed delivery that is waiting for the
 * researcher's manual confirmation before the audio is actually played.
 *
 * Set by StreamViewModel when a notification commit fires. Cleared either by
 * [StreamViewModel.confirmDelivery] (play it) or [StreamViewModel.dismissDelivery]
 * (skip it — the system's internal state stays as "delivered").
 */
data class DeliveryConfirmation(
    val displayType: String,      // "earcon" or "speech"
    val assetPath: String,        // the file that would be played
    val utilityStar: Double,      // U* for this decision
    val reason: String,           // e.g. "argmax is imminent"
    val cycleCount: Int
)

data class StreamUiState(
    val streamState: StreamState = StreamState.STOPPED,
    val videoFrame: Bitmap? = null,
    val videoFrameCount: Int = 0,
    val capturedPhoto: Bitmap? = null,
    val isShareDialogVisible: Boolean = false,
    val isCapturing: Boolean = false,
    val environmentName: String? = null,
    val isVisualContextActive: Boolean = false,
    val countdownSeconds: Int = 0,
    val sceneHistory: List<SceneLogEntry> = emptyList(),
    val currentMemory: String? = null,
    val fullSessionJson: String? = null,
    val fullMemorySidecutJson: String? = null,
    val isForecasting: Boolean = false,
    val forecastResultText: String? = null,
    val vlmStatus: String = "Waiting for first frame...",
    val isAiPipelineEnabled: Boolean = true,  // when false: stream-only mode (no AI queries)
    // ── Re-planning loop state ───────────────────────────────────
    val pendingNotificationMsg: String? = null,    // null = no pending notification
    val replanCycleCount: Int = 0,                 // how many re-evaluation cycles so far
    val replanStatus: String? = null,              // latest re-plan decision summary
    val replanBestUtility: Double? = null,          // current best U*
    val replanBestDisplay: String? = null,          // current best display type
    val replanDelivered: Boolean = false,           // true once committed & delivered
    // ── Delivery confirmation gate ───────────────────────────────
    val deliveryConfirmation: DeliveryConfirmation? = null  // non-null = show confirm dialog
)
