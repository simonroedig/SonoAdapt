/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

// StreamViewModel - DAT Camera Streaming API Demo
//
// This ViewModel demonstrates the DAT Camera Streaming APIs for:
// - Creating and managing stream sessions with wearable devices
// - Receiving video frames from device cameras
// - Capturing photos during streaming sessions
// - Handling different video qualities and formats
// - Processing raw video data (I420 -> ARGB conversion)

package com.meta.wearable.dat.externalsampleapps.cameraaccess.stream

import android.annotation.SuppressLint
import android.app.Application
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.util.Log
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.meta.wearable.dat.camera.Stream
import com.meta.wearable.dat.camera.addStream
import com.meta.wearable.dat.camera.types.PhotoData
import com.meta.wearable.dat.camera.types.StreamConfiguration
import com.meta.wearable.dat.camera.types.StreamError
import com.meta.wearable.dat.camera.types.StreamState
import com.meta.wearable.dat.camera.types.VideoFrame
import com.meta.wearable.dat.camera.types.VideoQuality
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.DeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.DeviceSessionError
import com.meta.wearable.dat.core.types.Permission
import com.meta.wearable.dat.core.types.PermissionStatus
import com.meta.wearable.dat.externalsampleapps.cameraaccess.R
import com.meta.wearable.dat.externalsampleapps.cameraaccess.api.VlmClient
import com.meta.wearable.dat.externalsampleapps.cameraaccess.wearables.WearablesViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.ByteArrayInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import kotlin.time.Duration.Companion.milliseconds

@SuppressLint("AutoCloseableUse")
class StreamViewModel(
    application: Application,
    private val wearablesViewModel: WearablesViewModel,
) : AndroidViewModel(application) {

  /**
   * Interval in milliseconds for periodic VLM analysis in Visual Context mode.
   * Swiftly change this to adjust the frequency of analysis.
   */
  var visualContextIntervalMs = 5_000L

  /**
   * Initial delay in milliseconds before the first VLM analysis starts.
   */
  var visualContextInitialDelayMs = 5_000L

  companion object {
    private const val TAG = "CameraAccess:StreamViewModel"
    private val INITIAL_STATE = StreamUiState()
    private val SESSION_TERMINAL_STATES = setOf(StreamState.CLOSED)
    /**
     * Flag to toggle between Real Grok API calls and Mock data.
     * true = Use Real VLM API
     * false = Use Mock "Home Office" result
     */
    const val USE_REAL_VLM = true
    const val USE_RAW_AUDIO_FOR_VLM = true
    const val USE_CHANGE_DETECTOR = true
    const val USE_AUDIO_CHANGE_DETECTOR = true

    // ── Re-planning loop constants (matching Python simulate.py) ─────────
    const val REPLAN_S = 5.0            // re-evaluate every 5s (Python: --replan 5, one per capture tick)
    const val MIN_LEAD_S = 8.0          // minimum lead time (Python: MIN_LEAD_TIME_S)
    const val FORECAST_HORIZON_S = 240.0 // forecast horizon (Python: FORECAST_HORIZON_S)
    const val SUPPRESS_BELOW = 0.0      // U* below this → suppress (hold, don't deliver)
    const val MAX_HOLD_S = 120.0        // force-deliver after this many seconds (end_of_replay equivalent)
  }

  private val deviceSelector: DeviceSelector = wearablesViewModel.deviceSelector
  private var session: DeviceSession? = null
  private val vlmClient = VlmClient(application)
  private val imageCaptioning = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.ImageCaptioning(application, vlmClient)
  private val anticipation = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.Anticipation(application, vlmClient)
  private val changeDetector = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.ChangeDetector(application)
  private val audioChangeDetector = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.AudioChangeDetector()

  private var _uiState = MutableStateFlow(INITIAL_STATE)
  val uiState = _uiState.asStateFlow()

  private var streamStartTimeMs: Long = 0L
  private var frameIndexCount = 0

  private var videoJob: Job? = null
  private var stateJob: Job? = null
  private var errorJob: Job? = null
  @SuppressLint("MissingGuardedByAnnotation") private var sessionErrorJob: Job? = null
  private var sessionStateJob: Job? = null
  private var visualContextJob: Job? = null
  private var stream: Stream? = null
  private var previousDeviceSessionState: DeviceSessionState? = null
  private var isBackgroundClassificationStream = false

  // Latest bitmap from the stream for periodic VLM analysis
  private var latestStreamBitmap: Bitmap? = null

  /**
   * Encode the latest stream frame as a JPEG base64 string for study logging.
   * Returns null if no frame is available. Quality 70 keeps size ~80-150 KB.
   */
  fun getLatestFrameBase64(): String? {
    val bmp = latestStreamBitmap ?: return null
    return try {
      val stream = java.io.ByteArrayOutputStream()
      bmp.compress(Bitmap.CompressFormat.JPEG, 70, stream)
      android.util.Base64.encodeToString(stream.toByteArray(), android.util.Base64.NO_WRAP)
    } catch (e: Exception) {
      Log.e(TAG, "Failed to encode frame as base64", e)
      null
    }
  }

  // ── Re-planning loop state ───────────────────────────────────────────

  /**
   * A notification waiting to be delivered. Created by triggerSimulatedNotification(),
   * re-evaluated on every scene analysis cycle, and cleared on commit or cancel.
   */
  data class PendingNotification(
      val message: String,
      val arrivalTimeMs: Long,           // System.currentTimeMillis() at button press
      val arrivalStreamTimeS: Double,    // seconds since stream start
      val importanceSender: Double = 1.0,   // high importance for user study
      val importanceContent: Double = 1.0,  // high importance for user study
      val urgency: Double = 1.0,            // high urgency → τ_u=30s, commits fast
      val speechAssetPath: String = "notifications/speech_medium_normalized.mp3",
      var bestUtility: Double = Double.NEGATIVE_INFINITY,
      var bestDisplay: String = "earcon",
      var bestTOffsetS: Double = 0.0,
      var cycleCount: Int = 0
  )

  private var pendingNotification: PendingNotification? = null
  private var replanTimerJob: Job? = null   // fixed 10s re-evaluation timer (matches Python --replan)

  /**
   * Optional reference to PlaybackViewModel for auto-delivery of notifications.
   * Set from the scaffold after both ViewModels are created.
   */
  var playbackViewModel: com.meta.wearable.dat.externalsampleapps.cameraaccess.audio.PlaybackViewModel? = null

  // Presentation queue for buffering frames after color conversion
  private var presentationQueue: PresentationQueue? = null

  fun startStream() {
    videoJob?.cancel()
    stateJob?.cancel()
    errorJob?.cancel()
    sessionErrorJob?.cancel()
    sessionStateJob?.cancel()
    presentationQueue?.stop()
    presentationQueue = null
    previousDeviceSessionState = null

    // Initialize presentation queue - frames are presented based on timestamp, not arrival time
    // Uses IntArray pooling for efficiency - cheaper than Bitmap.copy()
    val queue =
        PresentationQueue(
            bufferDelayMs = 100L,
            maxQueueSize = 15,
            onFrameReady = { frame ->
              // This is called from the presentation thread at regular intervals
              // when a frame's presentation time has arrived
              viewModelScope.launch(kotlinx.coroutines.Dispatchers.Main) {
                _uiState.update {
                  it.copy(videoFrame = frame.bitmap, videoFrameCount = it.videoFrameCount + 1)
                }
              }
            },
        )
    presentationQueue = queue
    queue.start()
    if (session == null) {
      previousDeviceSessionState = null
      Wearables.createSession(deviceSelector)
          .onSuccess { createdSession ->
            session = createdSession
            sessionErrorJob = viewModelScope.launch {
              createdSession.errors.collect { error -> handleSessionError(error) }
            }
            session?.start()
          }
          .onFailure { error, _ ->
            Log.e(TAG, "Failed to create session: ${error.description}")
            handleSessionError(error)
          }
      if (session == null) return
    }
    startStreamInternal()
  }

  private fun startStreamInternal() {
    Log.d(TAG, "startStreamInternal() - collecting session state")
    sessionStateJob = viewModelScope.launch {
      session?.state?.collect { currentState ->
        val prevState = previousDeviceSessionState
        previousDeviceSessionState = currentState

        if (currentState == DeviceSessionState.STARTED) {
          wearablesViewModel.setDatAppUpdateRequired(false)
          if (prevState == DeviceSessionState.PAUSED && stream != null) {
            // PAUSED → STARTED: device-initiated resume (tap gesture).
            // The SDK handles resume internally via requestCameraOn() → resumeStreaming().
            // Do NOT recreate the stream — just let the SDK resume it.
            Log.d(TAG, "Session resumed from PAUSED — stream stays alive")
            return@collect
          }

          videoJob?.cancel()
          stateJob?.cancel()
          errorJob?.cancel()
          stream?.stop()
          stream = null
          session
              ?.addStream(StreamConfiguration(videoQuality = VideoQuality.MEDIUM, frameRate = 24))
              ?.onSuccess { addedStream ->
                stream = addedStream
                videoJob = viewModelScope.launch {
                  Log.d(TAG, "Collecting video frames from stream")
                  stream?.videoStream?.collect { handleVideoFrame(it) }
                  Log.d(TAG, "Video stream collection ended")
                }
                stateJob = viewModelScope.launch {
                  stream?.state?.collect { streamState ->
                    val prevStreamState = _uiState.value.streamState
                    Log.d(TAG, "Stream state changed: $prevStreamState -> $streamState")
                    _uiState.update { it.copy(streamState = streamState) }

                    val wasActive = prevStreamState !in SESSION_TERMINAL_STATES
                    val isTerminated = streamState in SESSION_TERMINAL_STATES
                    if (wasActive && isTerminated) {
                      Log.d(TAG, "Terminal state reached, navigating back")
                      stopStream()
                      wearablesViewModel.navigateToDeviceSelection()
                    }
                  }
                }
                errorJob = viewModelScope.launch {
                  stream?.errorStream?.collect { error ->
                    Log.d(TAG, "Stream error received: $error (description: ${error.description})")
                    if (error == StreamError.STREAM_ERROR) {
                      Log.d(TAG, "Non-critical error, stream continues")
                      return@collect
                    }
                    stopStream()
                    wearablesViewModel.navigateToDeviceSelection()
                    wearablesViewModel.setRecentError(error.description)
                  }
                }
                stream?.start()
              }
              ?.onFailure { error, _ ->
                Log.e(TAG, "Failed to add stream to session: ${error.description}")
              }
        } else if (currentState == DeviceSessionState.PAUSED) {
          // Tap gesture paused the session — keep the stream alive.
          // The SDK transitions StreamState to PAUSED internally.
          Log.d(TAG, "Session paused (tap gesture) — keeping stream alive for resume")
        }
      }
    }
  }

  fun stopStream() {
    stopVisualContext()
    videoJob?.cancel()
    videoJob = null
    stateJob?.cancel()
    stateJob = null
    errorJob?.cancel()
    errorJob = null
    sessionErrorJob?.cancel()
    sessionErrorJob = null
    sessionStateJob?.cancel()
    sessionStateJob = null
    presentationQueue?.stop()
    presentationQueue = null
    _uiState.update { INITIAL_STATE }
    stream?.stop()
    stream = null
    session?.stop()
    session = null
    changeDetector.close()
  }

  fun stopVisualContext() {
    visualContextJob?.cancel()
    visualContextJob = null
    _uiState.update { it.copy(isVisualContextActive = false) }
  }

  /**
   * Toggle the AI pipeline on/off. When off, the stream continues but no AI
   * queries (CLIP, YAMNet, Gemini) are made — stream-only mode for user study
   * baseline condition.
   */
  fun toggleAiPipeline(enabled: Boolean) {
    _uiState.update { it.copy(isAiPipelineEnabled = enabled) }
    Log.d(TAG, "AI pipeline ${if (enabled) "ENABLED" else "DISABLED (stream-only mode)"}")
  }

  fun startSonoAdapt(
      onRequestWearablesPermission: suspend (Permission) -> PermissionStatus,
      onStreamStarted: (suspend () -> Unit)? = null,
      getAudioHistory: (() -> String)? = null,
      getRecentAudioWav: (() -> String?)? = null,
      getAudioSnapshot: (() -> com.meta.wearable.dat.externalsampleapps.cameraaccess.api.AudioChangeDetector.AudioSnapshot?)? = null
  ) {
    if (uiState.value.isVisualContextActive) {
      Log.d(TAG, "SonoAdapt already active")
      return
    }

    Log.d(TAG, "Starting SonoAdapt")
    _uiState.update {
      it.copy(
          isVisualContextActive = true,
          environmentName = null,
          countdownSeconds = (visualContextInitialDelayMs / 1000).toInt(),
          sceneHistory = emptyList(),
          currentMemory = null,
          fullSessionJson = null,
          fullMemorySidecutJson = null
      )
    }

    try {
      java.io.File(getApplication<Application>().filesDir, "sceneHistory.json").delete()
      java.io.File(getApplication<Application>().filesDir, "session_log.json").delete()
      streamStartTimeMs = 0L
      frameIndexCount = 0
    } catch (e: Exception) {
      Log.e(TAG, "Failed to delete scene history files", e)
    }

    // ── Reset change-detector state so the first frame of the new session
    //    always triggers a VLM call, regardless of what the previous session saw.
    changeDetector.reset()
    audioChangeDetector.reset()
    Log.d(TAG, "Change detector histories cleared for new SonoAdapt session.")

    viewModelScope.launch {
      // Start the stream if it's not active
      if (uiState.value.streamState != StreamState.STREAMING) {
        wearablesViewModel.navigateToStreaming(onRequestWearablesPermission)

        // Wait for streaming state
        var waitCount = 0
        while (uiState.value.streamState != StreamState.STREAMING && waitCount < 100) {
          kotlinx.coroutines.delay(100.milliseconds)
          waitCount++
        }
      }

      if (uiState.value.streamState == StreamState.STREAMING) {
        onStreamStarted?.invoke()
        streamStartTimeMs = System.currentTimeMillis()
        
        visualContextJob = viewModelScope.launch {
          // Initial countdown before the first analysis
          for (i in (visualContextInitialDelayMs / 1000).toInt() downTo 1) {
            _uiState.update { it.copy(countdownSeconds = i) }
            kotlinx.coroutines.delay(1000.milliseconds)
          }

          while (isActive && uiState.value.isVisualContextActive) {
            // ── Stream-only mode: skip all AI queries ──────────────────────
            if (!uiState.value.isAiPipelineEnabled) {
              _uiState.update { it.copy(vlmStatus = "Stream-only mode (AI pipeline off)", countdownSeconds = 0) }
              kotlinx.coroutines.delay(1000.milliseconds)
              continue
            }

            val bitmap = latestStreamBitmap
            if (bitmap != null) {
              Log.d(TAG, "Analyzing stream frame for Visual Context")
              
              // ── Change detection gate: CLIP (visual) OR YAMNet (audio) ─────────
              val visualChanged = if (USE_CHANGE_DETECTOR) {
                  changeDetector.hasContextChanged(bitmap, null)
              } else true // continuous mode: always fires

              val audioSnapshot = if (USE_AUDIO_CHANGE_DETECTOR) getAudioSnapshot?.invoke() else null
              val audioChanged = if (USE_AUDIO_CHANGE_DETECTOR && audioSnapshot != null) {
                  audioChangeDetector.hasAudioContextChanged(audioSnapshot)
              } else false

              val shouldQueryVlm = visualChanged || audioChanged

              if (shouldQueryVlm) {
                // Build descriptive status message showing which detector(s) triggered
                val triggerReasons = mutableListOf<String>()
                if (!USE_CHANGE_DETECTOR) triggerReasons.add("Continuous Mode")
                else if (visualChanged) triggerReasons.add("CLIP")
                if (audioChanged) {
                    val reason = audioChangeDetector.lastChangeReason
                    triggerReasons.add("YAMNet Audio" + if (reason.isNotBlank()) ": $reason" else "")
                }
                val statusMsg = "Change detected (${triggerReasons.joinToString(" + ")})! Querying VLM..."
                _uiState.update { it.copy(vlmStatus = statusMsg) }
                Log.d(TAG, statusMsg)

                val result = if (USE_REAL_VLM) {
                  val audioHist = if (!USE_RAW_AUDIO_FOR_VLM) getAudioHistory?.invoke() ?: "" else ""
                  val audioWav = if (USE_RAW_AUDIO_FOR_VLM) getRecentAudioWav?.invoke() else null
                  imageCaptioning.analyzeEnvironment(bitmap, audioHist, uiState.value.currentMemory, audioWav)
                } else {
                  kotlinx.coroutines.delay(1000.milliseconds)
                  """{"scene_context":{"environment":"Mock Environment","estimated_overall_loudness":0.5},"sound_sources":[],"social_context":{"social_grouping":"alone","setting_privacy":"private","setting_formality":"casual","venue_type":"home","interaction_mode":"none","subject_role":"isolated","enforced_silence_venue":false,"observed_social_cues":"none"},"task_context":{"activity_description":"Testing","activity_category":"cognitive_high","gaze_target":"environment","subject_in_motion":false,"content_mode":"consuming","observable_task_artifacts":"computer"},"scene_memory":"Mock memory state","event_summary":"Mock event occurred"}"""
                }
                parseAndSaveScene(result)
                _uiState.update { it.copy(vlmStatus = "VLM query complete. Waiting for next interval...") }
              } else {
                // ── No change: extend the current segment (mirrors Python _gate_and_process
                //    lines 1556–1566 — no VLM call, just extend persistance_s) ──────────
                Log.d(TAG, "ChangeDetector: No significant change detected (visual or audio). Skipping VLM call.")
                val tNowSec = if (streamStartTimeMs > 0) (System.currentTimeMillis() - streamStartTimeMs) / 1000.0 else 0.0
                val intervalSec = visualContextIntervalMs / 1000.0
                viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
                    try {
                        val sessionLogFile = java.io.File(getApplication<Application>().filesDir, "session_log.json")
                        if (sessionLogFile.exists()) {
                            val content = sessionLogFile.readText()
                            if (content.isNotBlank()) {
                                val arr = org.json.JSONArray(content)
                                if (arr.length() > 0) {
                                    val lastEntry = arr.getJSONObject(arr.length() - 1)
                                    lastEntry.put("persistance_s",
                                        lastEntry.optDouble("persistance_s", intervalSec) + intervalSec)
                                    lastEntry.put("last_seen_t", tNowSec)
                                    lastEntry.put("observation_count",
                                        lastEntry.optInt("observation_count", 1) + 1)
                                    sessionLogFile.writeText(arr.toString(2))
                                    _uiState.update { it.copy(fullSessionJson = arr.toString(2)) }
                                }
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to extend persistance_s in session log", e)
                    }
                }
                _uiState.update { it.copy(vlmStatus = "No change detected. Skipped VLM.") }
              }
            } else {
              Log.w(TAG, "No frame available for Visual Context analysis")
            }

            // Periodic countdown logic
            for (i in (visualContextIntervalMs / 1000).toInt() downTo 1) {
              _uiState.update { it.copy(countdownSeconds = i) }
              kotlinx.coroutines.delay(1000.milliseconds)
            }
          }
        }
      } else {
        Log.e(TAG, "Failed to start stream for Visual Context")
        _uiState.update { it.copy(isVisualContextActive = false) }
      }
    }
  }

  private fun parseAndSaveScene(jsonString: String) {
    try {
      // Strip markdown code block if present
      val cleanJson = jsonString.replace("```json", "").replace("```", "").trim()
      val jsonObject = org.json.JSONObject(cleanJson)
      
      val timestampMs = System.currentTimeMillis()
      val tStartSec = if (streamStartTimeMs > 0) (timestampMs - streamStartTimeMs) / 1000.0 else 0.0
      
      val intervalSec = visualContextIntervalMs / 1000.0

      // 1. Build the full session log object (mirrors Python process_frame + seg_meta)
      val augmentedSessionObj = org.json.JSONObject(cleanJson).apply {
          put("frame_index", frameIndexCount++)
          put("frame_timestamp_s", tStartSec)
          put("wall_time", java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSSSS", java.util.Locale.US).format(java.util.Date(timestampMs)))
          put("latency_s", 0.0) // Not easily tracked from here, defaulting to 0.0
          put("model", "gemini-3.5-flash-lite")
          put("image_bytes_sent", 0)
          // seg_meta fields (mirrors Python _gate_and_process seg_meta, lines 1532–1542)
          put("persistance_s", intervalSec)
          put("first_seen_t", tStartSec)
          put("last_seen_t", tStartSec)
          put("observation_count", 1)
          // Strip event_summary from session log (mirrors Python line 1428:
          // log.append({k: v for k, v in result.items() if k != "event_summary"}))
          remove("event_summary")
      }

      // Build both files inside a single coroutine to avoid race conditions
      viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
          var fullSessionJsonString = ""
          try {
              val sessionLogFile = java.io.File(getApplication<Application>().filesDir, "session_log.json")
              val sessionLogArray = if (sessionLogFile.exists()) {
                  val content = sessionLogFile.readText()
                  if (content.isNotBlank()) org.json.JSONArray(content) else org.json.JSONArray()
              } else {
                  org.json.JSONArray()
              }
              sessionLogArray.put(augmentedSessionObj)
              sessionLogFile.writeText(sessionLogArray.toString(2))
              fullSessionJsonString = sessionLogArray.toString(2)
          } catch (e: Exception) {
              Log.e(TAG, "Failed to write session log", e)
          }

          val socialContext = jsonObject.optJSONObject("social_context")
          val taskContext = jsonObject.optJSONObject("task_context")
          val sceneContext = jsonObject.optJSONObject("scene_context")
          val eventSummary = jsonObject.optString("event_summary", taskContext?.optString("activity_description", "Scene Analyzed") ?: "Scene Analyzed")
          val sceneMemory = jsonObject.optString("scene_memory", "")

          var fullMemorySidecutJsonString = ""
          try {
              val memoryFile = java.io.File(getApplication<Application>().filesDir, "sceneHistory.json")
              val memoryObj = if (memoryFile.exists()) {
                  val content = memoryFile.readText()
                  if (content.isNotBlank()) org.json.JSONObject(content) else org.json.JSONObject().apply {
                      put("session", "session_live")
                      put("narrative", org.json.JSONArray())
                  }
              } else {
                  org.json.JSONObject().apply {
                      put("session", "session_live")
                      put("narrative", org.json.JSONArray())
                  }
              }
              
              val narrativeArray = memoryObj.getJSONArray("narrative")
              if (narrativeArray.length() > 0) {
                  val prevObj = narrativeArray.getJSONObject(narrativeArray.length() - 1)
                  if (prevObj.has("t_end")) {
                      prevObj.put("t_end", tStartSec)
                  }
              }
              
              val newNarrativeObj = org.json.JSONObject().apply {
                  put("t_start", tStartSec)
                  put("t_end", tStartSec)
                  put("event_summary", eventSummary)
              }
              narrativeArray.put(newNarrativeObj)
              memoryFile.writeText(memoryObj.toString(2))
              fullMemorySidecutJsonString = memoryObj.toString(2)

              val entry = SceneLogEntry(
                  timestamp = timestampMs,
                  socialGrouping = socialContext?.optString("social_grouping", "unknown") ?: "unknown",
                  activityCategory = taskContext?.optString("activity_category", "unknown") ?: "unknown",
                  eventSummary = eventSummary,
                  sceneMemory = sceneMemory,
                  estimatedOverallLoudness = sceneContext?.optDouble("estimated_overall_loudness", 0.0) ?: 0.0,
                  rawJson = jsonObject.toString(2)
              )

              val currentState = _uiState.value
              val newHistory = (currentState.sceneHistory + entry).takeLast(5)
              
              _uiState.update { it.copy(
                  sceneHistory = newHistory,
                  currentMemory = sceneMemory,
                  fullSessionJson = fullSessionJsonString,
                  fullMemorySidecutJson = fullMemorySidecutJsonString,
                  environmentName = "Scene Memory: $sceneMemory"
              ) }
          } catch (e: Exception) {
              Log.e(TAG, "Failed to write scene history sidecar", e)
          }
      }

    } catch (e: Exception) {
      Log.e(TAG, "Failed to parse VLM response: $jsonString", e)
    }
  }

  /**
   * Trigger the anticipation pipeline on a simulated notification arrival.
   *
   * This creates a PendingNotification and runs the FIRST evaluation cycle.
   * Subsequent re-evaluations happen automatically in the scene analysis loop
   * (every ~10s when a VLM call fires), matching Python simulate.py's
   * replanning loop with the FullSystem condition.
   *
   * Pipeline per cycle:
   *   1. Load session log + memory sidecar
   *   2. Anticipation.generateForecast() → ForecastResult with costs
   *   3. UtilityOptimizer.evaluate() with elapsed_s → U(t,d) table
   *   4. Commit rule: deliver when best moment is imminent
   */
  fun triggerSimulatedNotification(
      message: String,
      urgency: Double = 1.0,
      importanceSender: Double = 1.0,
      importanceContent: Double = 1.0,
      speechAssetPath: String = "notifications/speech_medium_normalized.mp3"
  ) {
    if (pendingNotification != null) {
      Log.d(TAG, "Notification already pending — ignoring new trigger")
      return
    }

    val nowMs = System.currentTimeMillis()
    val arrivalS = if (streamStartTimeMs > 0) {
      (nowMs - streamStartTimeMs) / 1000.0
    } else 0.0

    pendingNotification = PendingNotification(
        message = message,
        arrivalTimeMs = nowMs,
        arrivalStreamTimeS = arrivalS,
        importanceSender = importanceSender,
        importanceContent = importanceContent,
        urgency = urgency,
        speechAssetPath = speechAssetPath
    )

    _uiState.update { it.copy(
        pendingNotificationMsg = message,
        replanCycleCount = 0,
        replanStatus = "Notification arrived (u=${String.format("%.1f", urgency)}, i=${String.format("%.1f", importanceSender)}). Running first evaluation...",
        replanBestUtility = null,
        replanBestDisplay = null,
        replanDelivered = false,
        isForecasting = true,
        forecastResultText = "Notification pending — evaluating..."
    ) }

    Log.d(TAG, "═══ NEW NOTIFICATION ═══ \"$message\" urgency=$urgency importance=$importanceSender at t=$arrivalS s")

    // Start a dedicated re-planning timer loop (fixed 10s, matching Python --replan)
    // This runs INDEPENDENTLY of the VLM change detection loop.
    // First cycle runs immediately, then every REPLAN_S seconds.
    replanTimerJob?.cancel()
    replanTimerJob = viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) {
      while (isActive && pendingNotification != null) {
        reEvaluatePendingNotification()
        if (pendingNotification == null) break  // committed or cancelled
        kotlinx.coroutines.delay((REPLAN_S * 1000).toLong())
      }
    }
  }

  /**
   * Cancel a pending notification without delivering it.
   */
  fun cancelPendingNotification() {
    replanTimerJob?.cancel()
    replanTimerJob = null
    pendingNotification = null
    _uiState.update { it.copy(
        pendingNotificationMsg = null,
        replanCycleCount = 0,
        replanStatus = null,
        replanBestUtility = null,
        replanBestDisplay = null,
        replanDelivered = false,
        isForecasting = false
    ) }
    Log.d(TAG, "Pending notification cancelled")
  }

  /**
   * Re-evaluate the pending notification against the current scene context.
   *
   * Mirrors Python simulate.py's replanning loop (lines 201–242):
   *   1. elapsed_s = now - t_a (urgency decays across cycles)
   *   2. Fresh forecast from the current session log
   *   3. Utility evaluation with elapsed_s
   *   4. Commit rule (Python conditions.py line 195):
   *      commit when best.t_offset_s <= MIN_LEAD_S + REPLAN_S
   *   5. On commit → auto-play earcon or speech, clear pending
   */
  private suspend fun reEvaluatePendingNotification() {
    val pending = pendingNotification ?: return
    val cycleNum = pending.cycleCount + 1
    pending.cycleCount = cycleNum

    val nowMs = System.currentTimeMillis()
    val elapsedS = (nowMs - pending.arrivalTimeMs) / 1000.0
    val currentTimeS = if (streamStartTimeMs > 0) {
      (nowMs - streamStartTimeMs) / 1000.0
    } else nowMs / 1000.0

    Log.d(TAG, "── Re-plan cycle #$cycleNum ── elapsed=${String.format("%.1f", elapsedS)}s")
    _uiState.update { it.copy(
        replanCycleCount = cycleNum,
        replanStatus = "Cycle #$cycleNum: evaluating (elapsed ${elapsedS.toLong()}s)...",
        isForecasting = true
    ) }

    try {
      // 1. Load session log + memory sidecar
      val sessionLogFile = java.io.File(getApplication<Application>().filesDir, "session_log.json")
      val sessionLogJson = if (sessionLogFile.exists()) {
        sessionLogFile.readText().ifBlank { "[]" }
      } else "[]"

      val memoryFile = java.io.File(getApplication<Application>().filesDir, "sceneHistory.json")
      val memorySidecarJson = if (memoryFile.exists()) {
        memoryFile.readText().ifBlank { null }
      } else null

      // 2. Forecast
      val forecastResult = anticipation.generateForecast(
          sessionLogJson = sessionLogJson,
          memorySidecarJson = memorySidecarJson,
          currentTimeS = currentTimeS
      )

      if (forecastResult.steps.isEmpty()) {
        Log.w(TAG, "Re-plan cycle #$cycleNum: no forecast steps — will retry next cycle")
        _uiState.update { it.copy(
            replanStatus = "Cycle #$cycleNum: no forecast steps, waiting for next scene update...",
            isForecasting = false
        ) }
        return
      }

      // 3. Utility evaluation with elapsed_s
      val notification = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.UtilityOptimizer.NotificationInfo(
          importanceSender = pending.importanceSender,
          importanceContent = pending.importanceContent,
          urgency = pending.urgency,
          elapsedS = elapsedS,
          label = pending.message
      )
      val weights = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.UtilityOptimizer.UtilityWeights()

      val utilityResult = com.meta.wearable.dat.externalsampleapps.cameraaccess.api.UtilityOptimizer.evaluate(
          steps = forecastResult.steps,
          notification = notification,
          weights = weights
      )

      val best = utilityResult.optimalSolution

      // Build display text for the UI
      val sb = StringBuilder()
      sb.append("━━━ RE-PLAN CYCLE #$cycleNum ━━━\n")
      sb.append("  \"${pending.message}\"\n")
      sb.append("  elapsed: ${String.format(java.util.Locale.US, "%.1f", elapsedS)}s\n\n")
      sb.append(forecastResult.toDisplayString())
      sb.append("\n\n")
      sb.append(utilityResult.toDisplayString())

      if (best == null) {
        // No deliverable candidate — keep waiting
        sb.append("\n\n━━━ DECISION: WAIT ━━━\n")
        sb.append("  No deliverable candidate — re-evaluating next cycle.\n")
        _uiState.update { it.copy(
            forecastResultText = sb.toString().trim(),
            replanStatus = "Cycle #$cycleNum: no candidate, waiting...",
            isForecasting = false
        ) }
        Log.d(TAG, "Re-plan cycle #$cycleNum: no deliverable candidate, will re-evaluate")
        return
      }

      // Track best utility seen so far
      if (best.U > pending.bestUtility) {
        pending.bestUtility = best.U
        pending.bestDisplay = best.display
        pending.bestTOffsetS = best.tOffsetS
      }

      // 4. Commit rule (mirrors Python conditions.py line 195):
      //    commit = best["t_offset_s"] <= min_lead_s + replan_s
      //    PLUS forced delivery when held too long (mirrors Python end_of_replay fallback)
      val forceDeliver = elapsedS >= MAX_HOLD_S
      val commit = best.tOffsetS <= MIN_LEAD_S + REPLAN_S || forceDeliver

      // 5. Check suppression (mirrors Python conditions.py lines 183-193)
      //    But if force-delivering, override suppression — we MUST act now.
      val suppressed = utilityResult.suppressed && !forceDeliver

      sb.append("\n\n━━━ DECISION ━━━\n")

      if (commit && !suppressed && (best.U > SUPPRESS_BELOW || forceDeliver)) {
        // ══════════════ COMMIT: request researcher confirmation ══════════════
        val reason = if (forceDeliver) "FORCED (max hold ${MAX_HOLD_S.toLong()}s exceeded)" else "best moment is imminent"
        sb.append("  ✓ COMMIT — awaiting confirmation for ${best.display.uppercase()}\n")
        sb.append("  Reason: $reason\n")
        sb.append("  U*: ${String.format(java.util.Locale.US, "%+.3f", best.U)}\n")
        sb.append("  Cycles: $cycleNum  |  Withheld: ${elapsedS.toLong()}s\n")

        Log.d(TAG, "═══ COMMIT ═══ ${best.display.uppercase()} U*=${best.U} after $cycleNum cycles — waiting for researcher confirmation")

        // Stop the replan timer so we don't keep firing while dialog is open
        replanTimerJob?.cancel()
        replanTimerJob = null

        // Clear the pending notification and show the confirmation dialog
        val assetPath = if (best.display == "speech") pending.speechAssetPath
                        else "notifications/earcon_normalized.mp3"

        // ── Log system decision to Supabase (rich context) ───────────────
        val forecastStepsJson = org.json.JSONArray().apply {
          for (step in forecastResult.steps) { put(step.toJson()) }
        }
        com.meta.wearable.dat.externalsampleapps.cameraaccess.logging.StudyLogger.logSimulateSystemDecision(
            systemDecision      = best.display,
            utilityStar         = best.U,
            cycleCount          = cycleNum,
            assetPath           = assetPath,
            reason              = reason,
            // Notification inputs
            notifUrgency             = pending.urgency,
            notifImportanceSender    = pending.importanceSender,
            notifImportanceContent   = pending.importanceContent,
            elapsedHeldS             = elapsedS,
            forceDelivered           = forceDeliver,
            suppressed               = suppressed,
            // Best step
            bestStepIndex            = best.step,
            bestTOffsetS             = best.tOffsetS,
            bestForecastUncertainty  = best.forecastUncertainty,
            // Benefit / cost breakdown from UtilityRow
            benefitIN                = best.iN,
            benefitUEff              = best.uEff,
            benefitGD                = best.gD,
            benefitTotal             = best.B,
            costASocial              = best.aSocial,
            costDTask                = best.dTask,
            costCI                   = best.cI,
            costCM                   = best.cM,
            costTotal                = best.C,
            // Optimizer summary
            speechThreshold          = utilityResult.speechThreshold,
            tauUS                    = utilityResult.tauUS,
            nCandidates              = utilityResult.nCandidates,
            nSteps                   = utilityResult.nSteps,
            // Forecast
            forecastStepsJson        = forecastStepsJson,
            expectedTimeline         = forecastResult.expectedTimeline.ifBlank { null },
            // Scene at best step (from the matching ForecastStep)
            bestEnvironment          = forecastResult.steps.getOrNull(best.step)?.environment,
            bestLoudness             = forecastResult.steps.getOrNull(best.step)?.estimatedOverallLoudness,
            bestActivity             = forecastResult.steps.getOrNull(best.step)?.activityDescription,
            bestActivityCategory     = forecastResult.steps.getOrNull(best.step)?.activityCategory,
            bestSocialGrouping       = forecastResult.steps.getOrNull(best.step)?.socialGrouping,
            bestInteractionMode      = forecastResult.steps.getOrNull(best.step)?.interactionMode,
            bestEnforcedSilence      = forecastResult.steps.getOrNull(best.step)?.enforcedSilenceVenue,
            bestSettingFormality     = forecastResult.steps.getOrNull(best.step)?.settingFormality,
            bestSubjectInMotion      = forecastResult.steps.getOrNull(best.step)?.subjectInMotion,
            bestCostRationale        = forecastResult.steps.getOrNull(best.step)?.costs?.rationale?.ifBlank { null }
        )

        pendingNotification = null
        _uiState.update { it.copy(
            forecastResultText = sb.toString().trim(),
            replanStatus = "⏸ Awaiting confirmation: ${best.display.uppercase()}",
            replanBestUtility = best.U,
            replanBestDisplay = best.display,
            replanDelivered = true,
            pendingNotificationMsg = null,
            isForecasting = false,
            deliveryConfirmation = DeliveryConfirmation(
                displayType = best.display,
                assetPath   = assetPath,
                utilityStar = best.U,
                reason      = reason,
                cycleCount  = cycleNum
            )
        ) }

      } else if (suppressed) {
        // ══════════════ SUPPRESSED: hold, scene may improve ══════════════
        sb.append("  ⊘ SUPPRESSED — no audio is better than any audio here\n")
        sb.append("  Best would be: ${best.display.uppercase()} at t+${best.tOffsetS.toLong()}s\n")
        sb.append("  U*: ${String.format(java.util.Locale.US, "%+.3f", best.U)} (below threshold)\n")
        sb.append("  Holding — scene may improve. Re-evaluating next cycle...\n")

        Log.d(TAG, "Re-plan cycle #$cycleNum: SUPPRESSED U*=${best.U} — holding")
        _uiState.update { it.copy(
            forecastResultText = sb.toString().trim(),
            replanStatus = "Cycle #$cycleNum: suppressed (U*=${String.format(java.util.Locale.US, "%+.3f", best.U)}), waiting...",
            replanBestUtility = pending.bestUtility,
            replanBestDisplay = pending.bestDisplay,
            isForecasting = false
        ) }

      } else {
        // ══════════════ WAIT: better moment further out ══════════════
        sb.append("  ► WAIT — better moment forecast at t+${best.tOffsetS.toLong()}s\n")
        sb.append("  ${best.display.uppercase()} U*: ${String.format(java.util.Locale.US, "%+.3f", best.U)}\n")
        sb.append("  Re-evaluating in ${REPLAN_S.toLong()}s...\n")

        Log.d(TAG, "Re-plan cycle #$cycleNum: WAIT — best at +${best.tOffsetS.toLong()}s, U*=${best.U}")
        _uiState.update { it.copy(
            forecastResultText = sb.toString().trim(),
            replanStatus = "Cycle #$cycleNum: waiting (best at +${best.tOffsetS.toLong()}s, U*=${String.format(java.util.Locale.US, "%+.3f", best.U)})",
            replanBestUtility = pending.bestUtility,
            replanBestDisplay = pending.bestDisplay,
            isForecasting = false
        ) }
      }

    } catch (e: Exception) {
      Log.e(TAG, "Re-plan cycle #$cycleNum failed", e)
      _uiState.update { it.copy(
          replanStatus = "Cycle #$cycleNum failed: ${e.message}",
          isForecasting = false
      ) }
    }
  }

  /**
   * Called when the researcher taps ✓ on the delivery confirmation dialog.
   * Plays the audio that the system selected and clears the dialog.
   */
  fun confirmDelivery() {
    val conf = _uiState.value.deliveryConfirmation ?: return
    val pbvm = playbackViewModel
    if (pbvm != null) {
      viewModelScope.launch(kotlinx.coroutines.Dispatchers.Main) {
        if (conf.displayType == "speech") {
          pbvm.playSpeech(conf.assetPath)
        } else {
          pbvm.playEarcon()
        }
      }
    } else {
      Log.w(TAG, "confirmDelivery: PlaybackViewModel not linked")
    }
    _uiState.update { it.copy(
        deliveryConfirmation = null,
        replanStatus = "✓ Confirmed & played: ${conf.displayType.uppercase()} (U*=${String.format(java.util.Locale.US, "%+.3f", conf.utilityStar)})"
    ) }
    // Auto-reset the delivered checkmark after 2 s so Simulate returns to its normal state
    viewModelScope.launch {
      kotlinx.coroutines.delay(2_000)
      _uiState.update { it.copy(replanDelivered = false, replanStatus = null) }
    }
    Log.d(TAG, "Delivery confirmed: ${conf.displayType.uppercase()} ${conf.assetPath}")
  }

  /**
   * Called when the researcher taps ✗ on the delivery confirmation dialog.
   * Discards the audio — the system's internal state stays as "delivered".
   * replanDelivered is reset immediately so the Simulate button does NOT show ✓.
   */
  fun dismissDelivery() {
    val conf = _uiState.value.deliveryConfirmation ?: return
    _uiState.update { it.copy(
        deliveryConfirmation = null,
        replanDelivered = false,   // researcher skipped — no checkmark
        replanStatus = "✗ Skipped by researcher: ${conf.displayType.uppercase()} (U*=${String.format(java.util.Locale.US, "%+.3f", conf.utilityStar)})"
    ) }
    // Clear the skip status after 2 s
    viewModelScope.launch {
      kotlinx.coroutines.delay(2_000)
      _uiState.update { it.copy(replanStatus = null) }
    }
    Log.d(TAG, "Delivery dismissed by researcher: ${conf.displayType.uppercase()}")
  }


  private fun handleSessionError(error: DeviceSessionError) {
    Log.e(TAG, "Session error: ${error.description}")
    val alreadyShowingUpdateRequired =
        wearablesViewModel.uiState.value.isFirmwareUpdateRequired ||
            wearablesViewModel.uiState.value.isDatAppUpdateRequired

    if (
        error == DeviceSessionError.SESSION_ENDED_BY_DEVICE &&
            shouldTreatSessionEndedAsDatAppUpdateRequired()
    ) {
      wearablesViewModel.setDatAppUpdateRequired(true)
      wearablesViewModel.setRecentError(
          getApplication<Application>().getString(R.string.update_required_dat_app_message)
      )
      stopStream()
      wearablesViewModel.navigateToDeviceSelection()
      return
    }

    if (alreadyShowingUpdateRequired && error == DeviceSessionError.SESSION_ENDED_BY_DEVICE) {
      stopStream()
      wearablesViewModel.navigateToDeviceSelection()
      return
    }

    if (error == DeviceSessionError.DAT_APP_ON_THE_GLASSES_UPDATE_REQUIRED) {
      wearablesViewModel.setDatAppUpdateRequired(true)
    }
    wearablesViewModel.setRecentError(error.description)
    stopStream()
    wearablesViewModel.navigateToDeviceSelection()
  }

  private fun shouldTreatSessionEndedAsDatAppUpdateRequired(): Boolean {
    val sessionNeverStarted =
        previousDeviceSessionState != DeviceSessionState.STARTED &&
            previousDeviceSessionState != DeviceSessionState.PAUSED
    return sessionNeverStarted
  }

  fun capturePhoto() {
    if (uiState.value.isCapturing) {
      Log.d(TAG, "Photo capture already in progress, ignoring request")
      return
    }

    if (uiState.value.streamState == StreamState.STREAMING) {
      Log.d(TAG, "Starting photo capture")
      _uiState.update { it.copy(isCapturing = true) }

      viewModelScope.launch {
        stream
            ?.capturePhoto()
            ?.onSuccess { photoData ->
              Log.d(TAG, "Photo capture successful")
              handlePhotoData(photoData)
              _uiState.update { it.copy(isCapturing = false) }
            }
            ?.onFailure { error, _ ->
              Log.e(TAG, "Photo capture failed: ${error.description}")
              _uiState.update { it.copy(isCapturing = false) }
            }
      }
    } else {
      Log.w(
          TAG,
          "Cannot capture photo: stream not active (state=${uiState.value.streamState})",
      )
    }
  }

  /**
   * Captures a photo and classifies the environment.
   * For now, this is a mock implementation that always returns "Home Office".
   * This is where a real VLM API call should be implemented in the future.
   */
  fun classifyEnvironment() {
    if (uiState.value.isCapturing) {
      Log.d(TAG, "Classification already in progress, ignoring request")
      return
    }

    Log.d(TAG, "Starting environment classification")
    _uiState.update { it.copy(isCapturing = true, environmentName = null) }

    viewModelScope.launch {
      // If we aren't streaming yet, start the stream first
      if (uiState.value.streamState != StreamState.STREAMING) {
        Log.d(TAG, "Stream not active, starting it for classification")
        isBackgroundClassificationStream = true
        startStream()
        
        // Wait for the stream to reach STREAMING state (max 10 seconds)
        var waitCount = 0
        while (uiState.value.streamState != StreamState.STREAMING && waitCount < 100) {
          kotlinx.coroutines.delay(100.milliseconds)
          waitCount++
        }
      }

      if (uiState.value.streamState == StreamState.STREAMING) {
        stream
            ?.capturePhoto()
            ?.onSuccess { photoData ->
              Log.d(TAG, "Classification capture successful")
              
              // IMMEDIATELY stop the stream if it was a background capture to turn off the LED
              if (isBackgroundClassificationStream) {
                Log.d(TAG, "Shutting down background stream to turn off LED")
                stopStream()
                isBackgroundClassificationStream = false
              }

              viewModelScope.launch {
                val result = if (USE_REAL_VLM) {
                  // Real VLM Logic
                  when (photoData) {
                    is PhotoData.Bitmap -> imageCaptioning.analyzeEnvironment(photoData.bitmap)
                    is PhotoData.HEIC -> {
                      val byteArray = ByteArray(photoData.data.remaining())
                      photoData.data.get(byteArray)
                      val bitmap = BitmapFactory.decodeByteArray(byteArray, 0, byteArray.size)
                      imageCaptioning.analyzeEnvironment(bitmap)
                    }
                  }
                } else {
                  // Mock Logic
                  kotlinx.coroutines.delay(1000.milliseconds)
                  "Test: Home Office"
                }
                
                _uiState.update {
                  it.copy(isCapturing = false, environmentName = result)
                }
              }
            }
            ?.onFailure { error, _ ->
              Log.e(TAG, "Classification capture failed: ${error.description}")
              _uiState.update { it.copy(isCapturing = false) }
            }
      } else {
        Log.e(TAG, "Failed to start stream for classification (state=${uiState.value.streamState})")
        _uiState.update { it.copy(isCapturing = false) }
      }
    }
  }

  fun clearEnvironmentName() {
    _uiState.update { it.copy(environmentName = null) }
  }

  fun showShareDialog() {
    _uiState.update { it.copy(isShareDialogVisible = true) }
  }

  fun hideShareDialog() {
    _uiState.update { it.copy(isShareDialogVisible = false) }
  }

  fun sharePhoto(bitmap: Bitmap) {
    val context = getApplication<Application>()
    val imagesFolder = File(context.cacheDir, "images")
    try {
      imagesFolder.mkdirs()
      val file = File(imagesFolder, "shared_image.png")
      FileOutputStream(file).use { stream ->
        bitmap.compress(Bitmap.CompressFormat.PNG, 90, stream)
      }

      val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
      val intent = Intent(Intent.ACTION_SEND)
      intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK
      intent.putExtra(Intent.EXTRA_STREAM, uri)
      intent.type = "image/png"
      intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)

      val chooser = Intent.createChooser(intent, "Share Image")
      chooser.flags = Intent.FLAG_ACTIVITY_NEW_TASK
      context.startActivity(chooser)
    } catch (e: IOException) {
      Log.e("StreamViewModel", "Failed to share photo", e)
    }
  }

  private fun handleVideoFrame(videoFrame: VideoFrame) {
    // VideoFrame contains raw I420 video data in a ByteBuffer
    // Use optimized YuvToBitmapConverter for direct I420 to ARGB conversion
    val bitmap =
        YuvToBitmapConverter.convert(
            videoFrame.buffer,
            videoFrame.width,
            videoFrame.height,
        )
    if (bitmap != null) {
      latestStreamBitmap = bitmap
      presentationQueue?.enqueue(
          bitmap,
          videoFrame.presentationTimeUs,
      )
    } else {
      Log.e(TAG, "Failed to convert YUV to bitmap")
    }
  }

  private fun handlePhotoData(photo: PhotoData) {
    val capturedPhoto =
        when (photo) {
          is PhotoData.Bitmap -> photo.bitmap
          is PhotoData.HEIC -> {
            val byteArray = ByteArray(photo.data.remaining())
            photo.data.get(byteArray)

            // Extract EXIF transformation matrix and apply to bitmap
            val exifInfo = getExifInfo(byteArray)
            val transform = getTransform(exifInfo)
            decodeHeic(byteArray, transform)
          }
        }
    _uiState.update { it.copy(capturedPhoto = capturedPhoto, isShareDialogVisible = true) }
  }

  // HEIC Decoding with EXIF transformation
  private fun decodeHeic(heicBytes: ByteArray, transform: Matrix): Bitmap {
    val bitmap = BitmapFactory.decodeByteArray(heicBytes, 0, heicBytes.size)
    return applyTransform(bitmap, transform)
  }

  private fun getExifInfo(heicBytes: ByteArray): ExifInterface? {
    return try {
      ByteArrayInputStream(heicBytes).use { inputStream -> ExifInterface(inputStream) }
    } catch (e: IOException) {
      Log.w(TAG, "Failed to read EXIF from HEIC", e)
      null
    }
  }

  private fun getTransform(exifInfo: ExifInterface?): Matrix {
    val matrix = Matrix()

    if (exifInfo == null) {
      return matrix // Identity matrix (no transformation)
    }

    when (
        exifInfo.getAttributeInt(
            ExifInterface.TAG_ORIENTATION,
            ExifInterface.ORIENTATION_NORMAL,
        )
    ) {
      ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> {
        matrix.postScale(-1f, 1f)
      }
      ExifInterface.ORIENTATION_ROTATE_180 -> {
        matrix.postRotate(180f)
      }
      ExifInterface.ORIENTATION_FLIP_VERTICAL -> {
        matrix.postScale(1f, -1f)
      }
      ExifInterface.ORIENTATION_TRANSPOSE -> {
        matrix.postRotate(90f)
        matrix.postScale(-1f, 1f)
      }
      ExifInterface.ORIENTATION_ROTATE_90 -> {
        matrix.postRotate(90f)
      }
      ExifInterface.ORIENTATION_TRANSVERSE -> {
        matrix.postRotate(270f)
        matrix.postScale(-1f, 1f)
      }
      ExifInterface.ORIENTATION_ROTATE_270 -> {
        matrix.postRotate(270f)
      }
      ExifInterface.ORIENTATION_NORMAL,
      ExifInterface.ORIENTATION_UNDEFINED -> {
        // No transformation needed
      }
    }

    return matrix
  }

  private fun applyTransform(bitmap: Bitmap, matrix: Matrix): Bitmap {
    if (matrix.isIdentity) {
      return bitmap
    }

    return try {
      val transformed = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
      if (transformed != bitmap) {
        bitmap.recycle()
      }
      transformed
    } catch (e: OutOfMemoryError) {
      Log.e(TAG, "Failed to apply transformation due to memory", e)
      bitmap
    }
  }

  override fun onCleared() {
    super.onCleared()
    stopStream()
    session?.stop()
    session = null
  }

  class Factory(
      private val application: Application,
      private val wearablesViewModel: WearablesViewModel,
  ) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
      if (modelClass.isAssignableFrom(StreamViewModel::class.java)) {
        @Suppress("UNCHECKED_CAST", "KotlinGenericsCast")
        return StreamViewModel(
            application = application,
            wearablesViewModel = wearablesViewModel,
        )
            as T
      }
      throw IllegalArgumentException("Unknown ViewModel class")
    }
  }
}
