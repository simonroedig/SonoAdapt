/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

// StreamScreen - DAT Camera Streaming UI
//
// This composable demonstrates the main streaming UI for DAT camera functionality. It shows how to
// display live video from wearable devices and handle photo capture.

package com.meta.wearable.dat.externalsampleapps.cameraaccess.ui

import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.meta.wearable.dat.camera.types.StreamState
import com.meta.wearable.dat.externalsampleapps.cameraaccess.R
import com.meta.wearable.dat.externalsampleapps.cameraaccess.audio.AudioViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.audio.PlaybackViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.logging.StudyLogger
import com.meta.wearable.dat.externalsampleapps.cameraaccess.stream.DeliveryConfirmation
import com.meta.wearable.dat.externalsampleapps.cameraaccess.stream.StreamViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.wearables.WearablesViewModel

// ── Dark Sunset palette ───────────────────────────────────────────────────────
private val DarkSlateGrey   = Color(0xFF335c67)   // panels, teal accent
private val VanillaCustard  = Color(0xFFFFF3B0)   // primary labels / headers
private val HoneyBronze     = Color(0xFFE09F3E)   // earcon, key accents
private val BrownRed        = Color(0xFF9E2A2B)   // cancel / danger
private val BlackCherry     = Color(0xFF540B0E)   // deep panel background
// Derived shades
private val PanelBg         = Color(0xFF0D0203)   // main overlay background
private val PanelSurface    = Color(0x99100304)   // semi-transparent surface
private val SlateLight      = Color(0xFF4A7F8F)   // lighter teal (Sim MED, etc.)
private val CustardDim      = Color(0xFFBFB07A)   // dimmed custard for secondary text
private val BronzeDim       = Color(0xFF8C6226)   // dimmer bronze
private val Success         = Color(0xFF4A7B4F)   // confirmed / played
private val BtnRadius       = 8.dp               // unified corner radius
// ─────────────────────────────────────────────────────────────────────────────

// ── Study notifications (mirrors all_notifications.json) ──────────────────────
private data class StudyNotif(
    val label: String,      // e.g. "LOW-3", "HIGH-1"
    val text: String,       // full message text
    val mp3: String,        // asset path e.g. "notifications/speech_low_03.mp3"
    val urgency: Double,    // 0.1 for low, 0.9 for high
    val isHigh: Boolean
)

private val STUDY_NOTIFICATIONS = listOf(
    StudyNotif("LOW-1",  "New WhatsApp from Lilly: I went for a short walk after work yesterday.",        "notifications/speech_low_01.mp3",  0.1, false),
    StudyNotif("LOW-2",  "New WhatsApp from Max: I had pasta for dinner yesterday.",                      "notifications/speech_low_02.mp3",  0.1, false),
    StudyNotif("LOW-3",  "New WhatsApp from Anna: I watched a documentary yesterday.",                    "notifications/speech_low_03.mp3",  0.1, false),
    StudyNotif("LOW-4",  "New WhatsApp from Ben: I took the bus to work yesterday.",                      "notifications/speech_low_04.mp3",  0.1, false),
    StudyNotif("LOW-5",  "New WhatsApp from Emma: I stopped by a bakery after work yesterday.",           "notifications/speech_low_05.mp3",  0.1, false),
    StudyNotif("LOW-6",  "New WhatsApp from Tom: I finished a book I was reading yesterday.",             "notifications/speech_low_06.mp3",  0.1, false),
    StudyNotif("HIGH-1", "New WhatsApp from Sarah: I was in a bike accident. Can you call me right now?","notifications/speech_high_01.mp3", 0.9, true),
    StudyNotif("HIGH-2", "New WhatsApp from Leo: The fire alarm is going off in your apartment. Can you check?","notifications/speech_high_02.mp3", 0.9, true),
    StudyNotif("HIGH-3", "New WhatsApp from Laura: I think I forgot to turn the stove off. Can you check?",    "notifications/speech_high_03.mp3", 0.9, true),
    StudyNotif("HIGH-4", "New WhatsApp from Paul: I forgot my keys. Can you come downstairs and open the door?","notifications/speech_high_04.mp3", 0.9, true),
    StudyNotif("HIGH-5", "New WhatsApp from Sophie: I'm outside your building now. Can you come down?",          "notifications/speech_high_05.mp3", 0.9, true),
    StudyNotif("HIGH-6", "New WhatsApp from David: I think I left my wallet on the train. Can you call me right away?","notifications/speech_high_06.mp3", 0.9, true),
)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun StreamScreen(
    wearablesViewModel: WearablesViewModel,
    streamViewModel: StreamViewModel,
    audioViewModel: AudioViewModel,
    playbackViewModel: PlaybackViewModel,
    modifier: Modifier = Modifier,
) {
  val streamUiState by streamViewModel.uiState.collectAsStateWithLifecycle()
  val audioUiState by audioViewModel.uiState.collectAsStateWithLifecycle()
  val notifState by playbackViewModel.notifPlayState.collectAsStateWithLifecycle()

  // Auto-reset notification button feedback after 1.5 seconds
  LaunchedEffect(notifState) {
    if (notifState.endsWith("_done")) {
      kotlinx.coroutines.delay(1500)
      playbackViewModel.resetNotifState()
    }
  }

  LaunchedEffect(Unit) { streamViewModel.startStream() }

  Box(modifier = modifier.fillMaxSize()) {
    streamUiState.videoFrame?.let { videoFrame ->
      key(streamUiState.videoFrameCount) {
        Image(
            bitmap = videoFrame.asImageBitmap(),
            contentDescription = stringResource(R.string.live_stream),
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop,
        )
      }
    }

    if (streamUiState.streamState == StreamState.STARTING) {
      CircularProgressIndicator(
          modifier = Modifier.align(Alignment.Center),
          color = HoneyBronze,
      )
    }

    if (streamUiState.environmentName != null || streamUiState.isVisualContextActive) {
      Surface(
          modifier = Modifier
              .align(Alignment.TopCenter)
              .padding(top = 80.dp, bottom = 108.dp, start = 16.dp, end = 16.dp)
              .fillMaxSize(),
          color = PanelSurface,
          shape = RoundedCornerShape(12.dp),
      ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
          if (streamUiState.isVisualContextActive) {

            // ── Top status bar: Pipeline toggle + app title ───────────────
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 6.dp)
            ) {
              Checkbox(
                  checked = streamUiState.isAiPipelineEnabled,
                  onCheckedChange = { streamViewModel.toggleAiPipeline(it) },
                  colors = CheckboxDefaults.colors(
                      checkedColor = HoneyBronze,
                      uncheckedColor = CustardDim,
                      checkmarkColor = BlackCherry
                  )
              )
              Text(
                  text = if (streamUiState.isAiPipelineEnabled) "AI Pipeline ON"
                         else "AI Pipeline OFF",
                  color = if (streamUiState.isAiPipelineEnabled) HoneyBronze else CustardDim,
                  fontSize = 11.sp,
                  fontWeight = FontWeight.SemiBold,
              )
              Spacer(Modifier.weight(1f))
              Text(
                  text = "SONOADAPT",
                  color = VanillaCustard,
                  fontSize = 11.sp,
                  fontWeight = FontWeight.ExtraBold,
                  letterSpacing = 2.sp,
              )
            }

            // ── Provider / mode chip row ──────────────────────────────────
            val vlmProvider = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.VlmClient.CURRENT_PROVIDER.name
            val audioMode   = if (StreamViewModel.USE_RAW_AUDIO_FOR_VLM) "WAV" else "YAMNet"
            val clipGate    = if (StreamViewModel.USE_CHANGE_DETECTOR) "CLIP ✓" else "CLIP ✗"
            val yamGate     = if (StreamViewModel.USE_AUDIO_CHANGE_DETECTOR) "Audio ✓" else "Audio ✗"
            Text(
                text = "$vlmProvider · $audioMode · $clipGate · $yamGate",
                color = if (streamUiState.isAiPipelineEnabled) CustardDim else Color(0xFF665544),
                fontSize = 9.sp,
                fontWeight = FontWeight.Medium,
                letterSpacing = 0.5.sp,
                modifier = Modifier.padding(bottom = 6.dp)
            )
          }

          // ── Scene / environment name ──────────────────────────────────
          val name = streamUiState.environmentName
          if (name != null) {
            Text(
                text = name,
                color = VanillaCustard,
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
            )
          } else if (streamUiState.isVisualContextActive) {
            Text(
                text = "Analyzing…",
                color = VanillaCustard.copy(alpha = 0.45f),
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium,
            )
          }

          if (streamUiState.isVisualContextActive) {
            if (streamUiState.isAiPipelineEnabled) {
              Text(
                  text = "Next update in ${streamUiState.countdownSeconds}s",
                  color = VanillaCustard.copy(alpha = 0.6f),
                  fontSize = 11.sp,
              )
            }

            // VLM status — HoneyBronze so it's clearly visible on dark panel
            val vlmSkipped = streamUiState.vlmStatus.contains("Skipped") ||
                             streamUiState.vlmStatus.contains("stream-only", ignoreCase = true)
            Text(
                text = streamUiState.vlmStatus,
                color = if (vlmSkipped) CustardDim else HoneyBronze,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 6.dp)
            )

            // ── Notification picker: scroll + Simulate / Instant / Earcon ─────
            NotificationPickerRow(
                notifState       = notifState,
                isPipelineEnabled = streamUiState.isAiPipelineEnabled,
                isPending        = streamUiState.pendingNotificationMsg != null,
                isDelivered      = streamUiState.replanDelivered,
                pendingMsg       = streamUiState.pendingNotificationMsg,
                replanStatus     = streamUiState.replanStatus,
                replanBestUtility = streamUiState.replanBestUtility,
                replanBestDisplay = streamUiState.replanBestDisplay,
                onSimulate       = { n ->
                    StudyLogger.logSimulateTriggered(
                        notifLabel = n.label,
                        notifText = n.text,
                        aiPipelineOn = streamUiState.isAiPipelineEnabled,
                        imageBase64 = streamViewModel.getLatestFrameBase64(),
                        wavBase64 = audioViewModel.getRecentAudioWavBase64()
                    )
                    streamViewModel.triggerSimulatedNotification(
                        message          = n.text,
                        urgency          = n.urgency,
                        importanceSender = n.urgency,
                        importanceContent = n.urgency,
                        speechAssetPath  = n.mp3
                    )
                },
                onInstant = { n ->
                    StudyLogger.logSpeechInstant(
                        notifLabel = n.label,
                        notifText = n.text,
                        aiPipelineOn = streamUiState.isAiPipelineEnabled,
                        assetPath = n.mp3,
                        imageBase64 = streamViewModel.getLatestFrameBase64(),
                        wavBase64 = audioViewModel.getRecentAudioWavBase64()
                    )
                    playbackViewModel.playSpeech(n.mp3)
                },
                onEarcon  = { n ->
                    StudyLogger.logEarconInstant(
                        notifLabel = n.label,
                        notifText = n.text,
                        aiPipelineOn = streamUiState.isAiPipelineEnabled,
                        imageBase64 = streamViewModel.getLatestFrameBase64(),
                        wavBase64 = audioViewModel.getRecentAudioWavBase64()
                    )
                    playbackViewModel.playEarcon()
                },
                onCancel  = { streamViewModel.cancelPendingNotification() },
            )

          } // end isVisualContextActive

          Spacer(modifier = Modifier.height(12.dp))

          // ── Data panels (Forecast / Audio / Memory / Session) ─────────
          Column(modifier = Modifier.fillMaxWidth().weight(1f)) {

            if (streamUiState.isForecasting) {
              Column(
                  modifier = Modifier.fillMaxWidth().weight(1f),
                  horizontalAlignment = Alignment.CenterHorizontally,
                  verticalArrangement = Arrangement.Center
              ) {
                CircularProgressIndicator(color = HoneyBronze)
                Text(
                    "Generating Forecast…",
                    color = HoneyBronze,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(top = 8.dp)
                )
              }
            } else if (streamUiState.forecastResultText != null) {
              val forecastText = streamUiState.forecastResultText!!
              Column(modifier = Modifier.fillMaxWidth().weight(1.5f).padding(bottom = 6.dp)) {
                SectionLabel("ANTICIPATION FORECAST")
                Column(modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                  Text(
                      text = forecastText,
                      color = VanillaCustard.copy(alpha = 0.85f),
                      fontSize = 10.sp,
                      fontFamily = FontFamily.Monospace,
                      lineHeight = 13.sp
                  )
                }
              }
            }

            if (audioUiState.isClassifying &&
                audioUiState.audioHistory.isNotEmpty() &&
                !StreamViewModel.USE_RAW_AUDIO_FOR_VLM) {
              Column(modifier = Modifier.fillMaxWidth().weight(1f)) {
                SectionLabel("AUDIO HISTORY")
                Column(modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                  val historyText = audioUiState.audioHistory.joinToString(",\n") { e ->
                    """{"ts": ${e.timestamp}, "source": "${e.dominantSoundSource}", "loudness": "${e.overallLoudness}"}"""
                  }
                  Text(
                      text = "[\n$historyText\n]",
                      color = DarkSlateGrey.copy(alpha = 0.9f),
                      fontSize = 9.sp,
                      fontFamily = FontFamily.Monospace,
                      lineHeight = 11.sp
                  )
                }
              }
            }

            if (streamUiState.isVisualContextActive && streamUiState.sceneHistory.isNotEmpty()) {
              if (audioUiState.isClassifying &&
                  audioUiState.audioHistory.isNotEmpty() &&
                  !StreamViewModel.USE_RAW_AUDIO_FOR_VLM) {
                Spacer(modifier = Modifier.height(10.dp))
              }

              if (!streamUiState.fullMemorySidecutJson.isNullOrBlank()) {
                Column(modifier = Modifier.fillMaxWidth().weight(1f)) {
                  SectionLabel("MEMORY SIDECAR")
                  Column(modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                    Text(
                        text = streamUiState.fullMemorySidecutJson ?: "",
                        color = VanillaCustard.copy(alpha = 0.75f),
                        fontSize = 10.sp,
                        fontFamily = FontFamily.Monospace,
                        lineHeight = 13.sp
                    )
                  }
                }
                Spacer(modifier = Modifier.height(6.dp))
              }

              if (!streamUiState.fullSessionJson.isNullOrBlank()) {
                Column(modifier = Modifier.fillMaxWidth().weight(2f)) {
                  SectionLabel("FULL SESSION")
                  Column(modifier = Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                    Text(
                        text = streamUiState.fullSessionJson ?: "",
                        color = CustardDim,
                        fontSize = 9.sp,
                        fontFamily = FontFamily.Monospace,
                        lineHeight = 11.sp
                    )
                  }
                }
              }
            }
          }
        }
      }
    }

    // ── Bottom action bar ─────────────────────────────────────────────
    // horizontal padding matches panel (16.dp) so button aligns with panel edges
    Box(modifier = Modifier.fillMaxSize().padding(start = 16.dp, end = 16.dp, bottom = 16.dp)) {
      Row(
          modifier = Modifier
              .align(Alignment.BottomCenter)
              .navigationBarsPadding()
              .fillMaxWidth()
              .height(48.dp),
          horizontalArrangement = Arrangement.spacedBy(8.dp),
          verticalAlignment = Alignment.CenterVertically,
      ) {
        SwitchButton(
            label = stringResource(R.string.stop_stream_button_title),
            onClick = {
              StudyLogger.stopSession()
              streamViewModel.stopStream()
              audioViewModel.stopClassification()
              wearablesViewModel.navigateToDeviceSelection()
            },
            isDestructive = true,
            modifier = Modifier.weight(1f),
        )

        if (!streamUiState.isVisualContextActive) {
          CaptureButton(
              onClick = { streamViewModel.capturePhoto() },
          )
        }
      }
    }
  }

  // ── Share photo dialog ──────────────────────────────────────────────
  streamUiState.capturedPhoto?.let { photo ->
    if (streamUiState.isShareDialogVisible) {
      SharePhotoDialog(
          photo = photo,
          onDismiss = { streamViewModel.hideShareDialog() },
          onShare = { bitmap ->
            streamViewModel.sharePhoto(bitmap)
            streamViewModel.hideShareDialog()
          },
      )
    }
  }

  // ── Delivery confirmation overlay ───────────────────────────────────
  streamUiState.deliveryConfirmation?.let { conf ->
    DeliveryConfirmationDialog(
        confirmation = conf,
        onConfirm  = {
          StudyLogger.logSimulatePlayIt(
              systemDecision = conf.displayType,
              assetPath = conf.assetPath,
              imageBase64 = streamViewModel.getLatestFrameBase64(),
              wavBase64 = audioViewModel.getRecentAudioWavBase64()
          )
          streamViewModel.confirmDelivery()
        },
        onDismiss  = {
          StudyLogger.logSimulateSkip(
              systemDecision = conf.displayType,
              utilityStar = conf.utilityStar
          )
          streamViewModel.dismissDelivery()
        }
    )
  }
}

// ── Small reusable composables ────────────────────────────────────────────────

/** Consistent section-label style used above data panels. */
@Composable
private fun SectionLabel(text: String) {
  Text(
      text = text,
      color = HoneyBronze,
      fontSize = 9.sp,
      fontWeight = FontWeight.ExtraBold,
      letterSpacing = 1.5.sp,
      modifier = Modifier.padding(bottom = 3.dp)
  )
}

/**
 * Scrollable notification picker + Simulate / Instant / Earcon buttons.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────┐
 *   │ [Scrollable list │ Simulate  │  Instant     ] │
 *   │ [status text if pending / delivered        ] │
 *   │ [         Earcon   (full width)            ] │
 *   └──────────────────────────────────────────────┘
 */
@Composable
private fun NotificationPickerRow(
    notifState: String,
    isPipelineEnabled: Boolean,
    isPending: Boolean,
    isDelivered: Boolean,
    pendingMsg: String?,
    replanStatus: String?,
    replanBestUtility: Double?,
    replanBestDisplay: String?,
    onSimulate: (StudyNotif) -> Unit,
    onInstant: (StudyNotif) -> Unit,
    onEarcon: (StudyNotif) -> Unit,
    onCancel: () -> Unit,
) {
    var selectedIdx by remember { mutableStateOf(0) }
    val selected = STUDY_NOTIFICATIONS[selectedIdx]
    val listState = rememberLazyListState()

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 6.dp)
    ) {
        // ── Main picker row ───────────────────────────────────────────────
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(90.dp),
            horizontalArrangement = Arrangement.spacedBy(5.dp)
        ) {
            // ── Scrollable notification list ──────────────────────────────
            Box(
                modifier = Modifier
                    .weight(1.4f)
                    .fillMaxHeight()
                    .background(Color(0x33000000), RoundedCornerShape(BtnRadius))
            ) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(vertical = 2.dp)
                ) {
                    items(STUDY_NOTIFICATIONS.size) { idx ->
                        val n = STUDY_NOTIFICATIONS[idx]
                        val isSelected = idx == selectedIdx
                        val accentBg = if (n.isHigh) BrownRed else DarkSlateGrey
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(24.dp)
                                .clickable { selectedIdx = idx }
                                .background(
                                    if (isSelected) accentBg else Color.Transparent,
                                    if (isSelected) RoundedCornerShape(4.dp)
                                    else RoundedCornerShape(0.dp)
                                )
                                .padding(horizontal = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = n.label,
                                color = if (isSelected) VanillaCustard
                                        else CustardDim.copy(alpha = 0.55f),
                                fontSize = 10.sp,
                                fontWeight = if (isSelected) FontWeight.ExtraBold
                                            else FontWeight.Normal,
                                maxLines = 1
                            )
                        }
                    }
                }
            }

            // ── Simulate button (with border; merges Cancel when pending) ────
            val accentColor = if (selected.isHigh) BrownRed else DarkSlateGrey
            val simBg = when {
                isPending    -> accentColor.copy(alpha = 0.55f)  // dimmed while evaluating
                isDelivered  -> Success
                !isPipelineEnabled -> Color(0xFF2A2020)
                else         -> accentColor
            }
            val simText = when {
                isPending   -> "…"
                isDelivered -> "✓"
                else        -> "Simulate"
            }
            Button(
                onClick = { if (isPending) onCancel() else if (isPipelineEnabled) onSimulate(selected) },
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .border(1.dp, VanillaCustard.copy(alpha = 0.40f), RoundedCornerShape(BtnRadius)),
                shape = RoundedCornerShape(BtnRadius),
                colors = ButtonDefaults.buttonColors(
                    containerColor = simBg,
                    disabledContainerColor = Color(0xFF2A2020)
                )
            ) {
                Text(simText, fontSize = 9.sp,
                     color = VanillaCustard, fontWeight = FontWeight.Bold)
            }

            // ── Instant button ────────────────────────────────────────────
            val mp3Tag = selected.mp3
                .removePrefix("notifications/")
                .removeSuffix(".mp3")   // e.g. "speech_low_01"
            val instantPlaying = notifState == "${mp3Tag}_playing"
            val instantDone    = notifState == "${mp3Tag}_done"
            // Instant is always available regardless of AI pipeline state
            val instantBg = if (instantDone) Success else accentColor
            Button(
                onClick = { onInstant(selected) },
                modifier = Modifier.weight(1f).fillMaxHeight(),
                shape = RoundedCornerShape(BtnRadius),
                colors = ButtonDefaults.buttonColors(containerColor = instantBg)
            ) {
                Text(
                    text = when {
                        instantPlaying -> "…"
                        instantDone    -> "✓"
                        else           -> "Speech"
                    },
                    fontSize = 9.sp,
                    color = VanillaCustard,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        // ── Pipeline status (pending / delivered) ─────────────────────────
        if (isPending && pendingMsg != null) {
            Text(
                text = "⏳ \"$pendingMsg\"",
                color = VanillaCustard,
                fontSize = 9.sp,
                maxLines = 2,
                modifier = Modifier.padding(top = 3.dp)
            )
            replanStatus?.let {
                Text(text = it, color = CustardDim, fontSize = 9.sp)
            }
            replanBestUtility?.let {
                Text(
                    text = "Best U*: ${String.format(java.util.Locale.US, "%+.3f", it)}" +
                           " (${replanBestDisplay?.uppercase() ?: "?"})",
                    color = HoneyBronze, fontSize = 9.sp
                )
            }
        } else if (isDelivered && replanStatus != null) {
            Text(
                text = replanStatus,
                color = HoneyBronze,
                fontSize = 9.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 3.dp)
            )
        }

        // ── Earcon button (full width, tall for confident tap) ──────────────
        Spacer(Modifier.height(4.dp))
        val earconDone = notifState == "earcon_done"
        Button(
            onClick = { onEarcon(selected) },
            modifier = Modifier.fillMaxWidth().height(44.dp),
            contentPadding = PaddingValues(0.dp),
            shape = RoundedCornerShape(BtnRadius),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (earconDone) Success else HoneyBronze
            )
        ) {
            Text(
                text = when (notifState) {
                    "earcon_playing" -> "…"
                    "earcon_done"    -> "✓ Earcon"
                    else             -> "Earcon"
                },
                fontSize = 9.sp, color = BlackCherry, fontWeight = FontWeight.Bold
            )
        }
    }
}

/**
 * Full-screen dimmed dialog that asks the researcher to approve or reject
 * the notification the pipeline has decided to deliver.
 */
@Composable
private fun DeliveryConfirmationDialog(
    confirmation: DeliveryConfirmation,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
  Dialog(
      onDismissRequest = { /* block back-tap — user must press a button */ },
      properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false)
  ) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = BlackCherry)
    ) {
      Column(
          modifier = Modifier.padding(20.dp),
          horizontalAlignment = Alignment.CenterHorizontally
      ) {
        // Header
        Text(
            text = "SonoAdapt wants to play now:",
            color = VanillaCustard,
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.5.sp,
            modifier = Modifier.padding(bottom = 12.dp)
        )

        // Display type badge
        val isEarcon   = confirmation.displayType == "earcon"
        val badgeColor = if (isEarcon) HoneyBronze else DarkSlateGrey
        val badgeLabel = if (isEarcon) "EARCON" else "SPEECH"
        Surface(
            color = badgeColor,
            shape = RoundedCornerShape(8.dp),
            modifier = Modifier.padding(bottom = 10.dp)
        ) {
          Text(
              text = badgeLabel,
              color = if (isEarcon) BlackCherry else VanillaCustard,
              fontSize = 20.sp,
              fontWeight = FontWeight.ExtraBold,
              letterSpacing = 2.sp,
              modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)
          )
        }

        // Details
        Text(
            text = "U* = ${String.format(java.util.Locale.US, "%+.3f", confirmation.utilityStar)}",
            color = HoneyBronze,
            fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(bottom = 2.dp)
        )
        Text(
            text = "After ${confirmation.cycleCount} cycle(s)",
            color = CustardDim,
            fontSize = 11.sp,
            modifier = Modifier.padding(bottom = 2.dp)
        )
        Text(
            text = confirmation.reason,
            color = CustardDim,
            fontSize = 10.sp,
            modifier = Modifier.padding(bottom = 4.dp)
        )
        // Show the MP3 filename for researcher verification
        if (confirmation.displayType == "speech") {
            val filename = confirmation.assetPath.substringAfterLast("/")
            Text(
                text = "▶ $filename",
                color = HoneyBronze.copy(alpha = 0.8f),
                fontSize = 10.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.padding(bottom = 12.dp)
            )
        } else {
            Spacer(Modifier.height(12.dp))
        }

        // Action buttons
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
          Button(
              onClick = onDismiss,
              modifier = Modifier.weight(1f),
              contentPadding = PaddingValues(horizontal = 8.dp, vertical = 12.dp),
              colors = ButtonDefaults.buttonColors(containerColor = BrownRed),
              shape = RoundedCornerShape(10.dp)
          ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
              Text("✗", fontSize = 18.sp, color = VanillaCustard,
                   fontWeight = FontWeight.Bold, lineHeight = 20.sp)
              Text("Skip", fontSize = 11.sp, color = VanillaCustard)
            }
          }

          Button(
              onClick = onConfirm,
              modifier = Modifier.weight(1f),
              contentPadding = PaddingValues(horizontal = 8.dp, vertical = 12.dp),
              colors = ButtonDefaults.buttonColors(containerColor = DarkSlateGrey),
              shape = RoundedCornerShape(10.dp)
          ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
              Text("✓", fontSize = 18.sp, color = VanillaCustard,
                   fontWeight = FontWeight.Bold, lineHeight = 20.sp)
              Text("Play it", fontSize = 11.sp, color = VanillaCustard)
            }
          }
        }
      }
    }
  }
}
