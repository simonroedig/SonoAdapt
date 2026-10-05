/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

package com.meta.wearable.dat.externalsampleapps.cameraaccess.audio

data class AudioLogEntry(
    val timestamp: Long,
    val dominantSoundSource: String,
    val overallLoudness: String
)

data class AudioUiState(
    val isClassifying: Boolean = false,
    val noiseLevel: String = "very_low",
    val dominantSource: String = "silence",
    val speechPresence: String = "no_speech",
    val audioHistory: List<AudioLogEntry> = emptyList()
)
