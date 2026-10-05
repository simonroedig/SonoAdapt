/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

// NonStreamScreen - DAT Device Selection and Setup
//
// This screen demonstrates DAT device management and pre-streaming setup. It handles device
// registration status, camera permissions, and stream readiness.

package com.meta.wearable.dat.externalsampleapps.cameraaccess.ui

import android.widget.Toast
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LinkOff
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.meta.wearable.dat.core.types.Permission
import com.meta.wearable.dat.core.types.PermissionStatus
import com.meta.wearable.dat.core.types.RegistrationState
import com.meta.wearable.dat.externalsampleapps.cameraaccess.R
import com.meta.wearable.dat.externalsampleapps.cameraaccess.audio.AudioViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.audio.PlaybackViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.logging.StudyLogger
import com.meta.wearable.dat.externalsampleapps.cameraaccess.stream.StreamViewModel
import com.meta.wearable.dat.externalsampleapps.cameraaccess.wearables.WearablesViewModel
import kotlinx.coroutines.launch

private val UpdateRequiredBackground = Color(0xFFFFF4D6)
private val UpdateRequiredForeground = Color(0xFF8A4B00)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NonStreamScreen(
    viewModel: WearablesViewModel,
    streamViewModel: StreamViewModel,
    audioViewModel: AudioViewModel,
    playbackViewModel: PlaybackViewModel,
    onRequestWearablesPermission: suspend (Permission) -> PermissionStatus,
    modifier: Modifier = Modifier,
) {
  val uiState by viewModel.uiState.collectAsStateWithLifecycle()
  val streamUiState by streamViewModel.uiState.collectAsStateWithLifecycle()
  val audioUiState by audioViewModel.uiState.collectAsStateWithLifecycle()
  val isPlaying by playbackViewModel.isPlaying.collectAsStateWithLifecycle()
  val gettingStartedSheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
  val scope = rememberCoroutineScope()
  var dropdownExpanded by remember { mutableStateOf(false) }
  val isDisconnectEnabled = uiState.registrationState == RegistrationState.REGISTERED
  val isUpdateRequired = uiState.isFirmwareUpdateRequired || uiState.isDatAppUpdateRequired
  val activity = LocalActivity.current
  val context = LocalContext.current

  MaterialTheme(colorScheme = darkColorScheme()) {
    Box(
        modifier = modifier.fillMaxSize().background(Color.Black).padding(all = 24.dp),
        contentAlignment = Alignment.Center,
    ) {
      Box(modifier = Modifier.align(Alignment.TopEnd).systemBarsPadding()) {
        IconButton(onClick = { dropdownExpanded = true }) {
          Icon(
              imageVector = Icons.Default.LinkOff,
              contentDescription = "DisconnectIcon",
              tint = Color.White,
              modifier = Modifier.size(28.dp),
          )
        }

        DropdownMenu(
            expanded = dropdownExpanded,
            onDismissRequest = { dropdownExpanded = false },
        ) {
          DropdownMenuItem(
              text = {
                Text(
                    stringResource(R.string.unregister_button_title),
                    color = if (isDisconnectEnabled) AppColor.Red else Color.Gray,
                )
              },
              enabled = isDisconnectEnabled,
              onClick = {
                activity?.let { viewModel.startUnregistration(it) }
                    ?: Toast.makeText(context, "Activity not available", Toast.LENGTH_SHORT).show()
                dropdownExpanded = false
              },
              modifier = Modifier.height(30.dp),
          )
        }
      }

      streamUiState.environmentName?.let { name ->
        Surface(
            modifier = Modifier.align(Alignment.TopCenter).padding(top = 80.dp),
            color = Color.White.copy(alpha = 0.2f),
            shape = RoundedCornerShape(12.dp),
        ) {
          Text(
              text = name,
              color = Color.White,
              fontSize = 24.sp,
              fontWeight = FontWeight.Bold,
              modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
          )
        }
      }

      if (audioUiState.isClassifying && !StreamViewModel.USE_RAW_AUDIO_FOR_VLM) {
        Surface(
            modifier = Modifier.align(Alignment.TopCenter).padding(top = 140.dp),
            color = Color.White.copy(alpha = 0.2f),
            shape = RoundedCornerShape(12.dp),
        ) {
          Column(
              modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
              horizontalAlignment = Alignment.CenterHorizontally
          ) {
            Text(
                text = "Noise: ${audioUiState.noiseLevel.replace("_", " ").uppercase()}",
                color = Color.White,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Source: ${audioUiState.dominantSource.replace("_", " ").uppercase()}",
                color = Color.White,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
            )
          }
        }
      }

      Column(
          modifier = Modifier.align(Alignment.BottomCenter).navigationBarsPadding(),
          horizontalAlignment = Alignment.CenterHorizontally,
          verticalArrangement = Arrangement.spacedBy(12.dp),
      ) {
        if (!uiState.hasActiveDevice) {
          Row(
              horizontalArrangement = Arrangement.spacedBy(8.dp),
              verticalAlignment = Alignment.CenterVertically,
          ) {
            Icon(
                painter = painterResource(id = R.drawable.hourglass_icon),
                contentDescription = "Waiting for device",
                tint = Color.White.copy(alpha = 0.7f),
                modifier = Modifier.size(16.dp),
            )
            Text(
                text = stringResource(R.string.waiting_for_active_device),
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.7f),
            )
          }
        }

        if (isUpdateRequired) {
          UpdateRequiredMessage(
              showFirmwareUpdate = uiState.isFirmwareUpdateRequired,
              showDatAppUpdate = uiState.isDatAppUpdateRequired,
          )
        }

        if (uiState.isFirmwareUpdateRequired) {
          SwitchButton(
              label = stringResource(R.string.update_firmware_button_title),
              onClick = {
                activity?.let { viewModel.openFirmwareUpdate(it) }
                    ?: Toast.makeText(context, "Activity not available", Toast.LENGTH_SHORT).show()
              },
          )
        }

        if (uiState.isDatAppUpdateRequired) {
          SwitchButton(
              label = stringResource(R.string.update_dat_app_button_title),
              onClick = {
                activity?.let { viewModel.openDATGlassesAppUpdate(it) }
                    ?: Toast.makeText(context, "Activity not available", Toast.LENGTH_SHORT).show()
              },
          )
        }

        // ── Hidden legacy buttons (functional, visually suppressed) ──────
        // Play Sound — kept for dev use, invisible to user
        Box(modifier = Modifier.size(0.dp)) {
          SwitchButton(
              label = if (isPlaying) "Stop Sound" else "Play Sound",
              onClick = { playbackViewModel.togglePlayback() },
              enabled = uiState.hasActiveDevice && !isUpdateRequired,
              backgroundColor = if (isPlaying) AppColor.Green else AppColor.DeepBlue
          )
        }
        // Classify Audio — hidden
        Box(modifier = Modifier.size(0.dp)) {
          SwitchButton(
              label = if (audioUiState.isClassifying) "Stop Audio Classification" else "Classify Audio",
              onClick = { audioViewModel.toggleClassification(onRequestWearablesPermission) },
              enabled = uiState.hasActiveDevice && !isUpdateRequired,
              backgroundColor = if (audioUiState.isClassifying) AppColor.Green else AppColor.DeepBlue
          )
        }
        // Visual Environment — hidden
        Box(modifier = Modifier.size(0.dp)) {
          SwitchButton(
              label = stringResource(R.string.visual_environment_button_title),
              onClick = { streamViewModel.classifyEnvironment() },
              enabled = uiState.hasActiveDevice && !isUpdateRequired && !streamUiState.isCapturing,
              backgroundColor = AppColor.DeepBlue,
              contentColor = Color.White
          )
        }

        // ── Primary CTA: Start SonoAdapt ─────────────────────────────────
        Spacer(Modifier.height(8.dp))

        // ── Log to Supabase toggle ────────────────────────────────────────
        var logToSupabase by remember { mutableStateOf(true) }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(bottom = 4.dp)
        ) {
          Checkbox(
              checked = logToSupabase,
              onCheckedChange = { logToSupabase = it },
              colors = CheckboxDefaults.colors(
                  checkedColor = Color(0xFFE09F3E),
                  uncheckedColor = Color(0xFF8A6060),
                  checkmarkColor = Color(0xFF540B0E)
              )
          )
          Text(
              text = "Log to Supabase",
              color = if (logToSupabase) Color(0xFFE09F3E) else Color(0xFF8A6060),
              fontSize = 13.sp,
              fontWeight = FontWeight.SemiBold
          )
        }

        Button(
            onClick = {
              // Set logger state before starting SonoAdapt
              StudyLogger.enabled = logToSupabase
              if (logToSupabase) {
                StudyLogger.startSession()
              }

              streamViewModel.startSonoAdapt(
                  onRequestWearablesPermission = onRequestWearablesPermission,
                  onStreamStarted = {
                      audioViewModel.startClassification(onRequestWearablesPermission)
                  },
                  getAudioHistory = {
                      val history = audioViewModel.uiState.value.audioHistory.takeLast(5)
                      history.joinToString(",\n") { """{"ts": ${it.timestamp}, "source": "${it.dominantSoundSource}", "loudness": "${it.overallLoudness}"}""" }
                  },
                  getRecentAudioWav = {
                      audioViewModel.getRecentAudioWavBase64()
                  },
                  getAudioSnapshot = {
                      val audioState = audioViewModel.uiState.value
                      if (audioState.isClassifying) {
                          com.meta.wearable.dat.externalsampleapps.cameraaccess.api.AudioChangeDetector.AudioSnapshot(
                              dominantSource = audioState.dominantSource,
                              noiseLevel = audioState.noiseLevel,
                              speechPresence = audioState.speechPresence
                          )
                      } else null
                  }
              )
            },
            enabled = uiState.hasActiveDevice && !isUpdateRequired && !streamUiState.isVisualContextActive,
            modifier = Modifier.fillMaxWidth().height(68.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFF9E2A2B),
                contentColor = Color(0xFFFFF3B0),
                disabledContainerColor = Color(0xFF4A1516),
                disabledContentColor = Color(0xFF8A6060)
            )
        ) {
            Text(
                text = stringResource(R.string.start_sonoadapt_button_title),
                fontSize = 16.sp,
                fontWeight = FontWeight.ExtraBold,
                letterSpacing = 1.sp
            )
        }

        // ── Secondary: Start Streaming ────────────────────────────────────
        Spacer(Modifier.height(6.dp))
        Button(
            onClick = {
              streamViewModel.clearEnvironmentName()
              viewModel.navigateToStreaming(onRequestWearablesPermission)
            },
            enabled = uiState.hasActiveDevice && !isUpdateRequired,
            modifier = Modifier.fillMaxWidth().height(48.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color(0xFF335C67),
                contentColor = Color(0xFFFFF3B0),
                disabledContainerColor = Color(0xFF1A2E33),
                disabledContentColor = Color(0xFF5A7A80)
            )
        ) {
            Text(
                text = stringResource(R.string.stream_button_title),
                fontSize = 13.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 0.5.sp
            )
        }
      }

      // Getting Started Sheet
      if (uiState.isGettingStartedSheetVisible) {
        ModalBottomSheet(
            onDismissRequest = { viewModel.hideGettingStartedSheet() },
            sheetState = gettingStartedSheetState,
        ) {
          GettingStartedSheetContent(
              onContinue = {
                scope.launch {
                  gettingStartedSheetState.hide()
                  viewModel.hideGettingStartedSheet()
                }
              }
          )
        }
      }
    }
  }
}

@Composable
private fun UpdateRequiredMessage(
    showFirmwareUpdate: Boolean,
    showDatAppUpdate: Boolean,
    modifier: Modifier = Modifier,
) {
  val message =
      when {
        showFirmwareUpdate && showDatAppUpdate ->
            stringResource(R.string.update_required_both_message)
        showFirmwareUpdate -> stringResource(R.string.update_required_firmware_message)
        else -> stringResource(R.string.update_required_dat_app_message)
      }

  Row(
      modifier =
          modifier
              .fillMaxWidth()
              .clip(RoundedCornerShape(20.dp))
              .background(UpdateRequiredBackground)
              .padding(16.dp),
      horizontalArrangement = Arrangement.spacedBy(12.dp),
      verticalAlignment = Alignment.Top,
  ) {
    Icon(
        imageVector = Icons.Default.Warning,
        contentDescription = null,
        tint = UpdateRequiredForeground,
        modifier = Modifier.size(24.dp),
    )
    Column(
        modifier = Modifier.weight(1f),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
      Text(
          text = stringResource(R.string.update_required_title),
          style = MaterialTheme.typography.titleMedium,
          fontWeight = FontWeight.SemiBold,
          color = UpdateRequiredForeground,
      )
      Text(
          text = message,
          style = MaterialTheme.typography.bodyMedium,
          color = UpdateRequiredForeground,
      )
    }
  }
}

@Composable
private fun GettingStartedSheetContent(onContinue: () -> Unit, modifier: Modifier = Modifier) {
  Column(
      modifier = modifier.fillMaxWidth().padding(horizontal = 24.dp).padding(bottom = 24.dp),
      horizontalAlignment = Alignment.CenterHorizontally,
      verticalArrangement = Arrangement.spacedBy(24.dp),
  ) {
    Text(
        text = stringResource(R.string.getting_started_title),
        style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.SemiBold,
        textAlign = TextAlign.Center,
    )

    Column(
        verticalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth().padding(8.dp).padding(bottom = 16.dp),
    ) {
      TipItem(
          iconResId = R.drawable.video_icon,
          text = stringResource(R.string.getting_started_tip_permission),
      )
      TipItem(
          iconResId = R.drawable.tap_icon,
          text = stringResource(R.string.getting_started_tip_photo),
      )
      TipItem(
          iconResId = R.drawable.smart_glasses_icon,
          text = stringResource(R.string.getting_started_tip_led),
      )
    }

    SwitchButton(
        label = stringResource(R.string.getting_started_continue),
        onClick = onContinue,
        modifier = Modifier.navigationBarsPadding(),
    )
  }
}

@Composable
private fun TipItem(iconResId: Int, text: String, modifier: Modifier = Modifier) {
  Row(modifier = modifier.fillMaxWidth()) {
    Icon(
        painter = painterResource(id = iconResId),
        contentDescription = "Getting started tip icon",
        modifier = Modifier.padding(start = 4.dp, top = 4.dp).width(24.dp),
    )
    Spacer(modifier = Modifier.width(10.dp))
    Text(text = text)
  }
}
