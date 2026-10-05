/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

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
import com.meta.wearable.dat.externalsampleapps.cameraaccess.BuildConfig
import java.io.ByteArrayOutputStream
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

enum class VlmProvider {
    GROK,
    GEMINI
}

class VlmClient(private val context: Context) {
    companion object {
        private const val TAG = "CameraAccess:VlmClient"
        private const val API_KEY = BuildConfig.GROK_API_KEY
        private const val GEMINI_API_KEY = BuildConfig.GEMINI_API_KEY
        private const val BASE_URL = "https://api.x.ai/"
        private const val GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/"
        
        val CURRENT_PROVIDER = VlmProvider.GEMINI
    }

    private val json = Json { 
        ignoreUnknownKeys = true 
        coerceInputValues = true
        classDiscriminator = "type"
    }

    private val apiService: GrokApiService by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .build()

        val contentType = "application/json".toMediaType()
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()
            .create(GrokApiService::class.java)
    }

    private val geminiApiService: GeminiApiService by lazy {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
            .build()

        val contentType = "application/json".toMediaType()
        Retrofit.Builder()
            .baseUrl(GEMINI_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory(contentType))
            .build()
            .create(GeminiApiService::class.java)
    }

    suspend fun executeGeminiRequest(request: GeminiRequest): String {
        return try {
            val response = geminiApiService.generateContent(
                model = "gemini-3.5-flash-lite",
                apiKey = GEMINI_API_KEY,
                request = request
            )
            response.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text?.trim() ?: "Unknown"
        } catch (e: Exception) {
            Log.e(TAG, "Gemini request failed", e)
            "Error: ${e.message}"
        }
    }

    suspend fun executeGrokRequest(request: ChatCompletionRequest): String {
        return try {
            val response = apiService.getChatCompletion("Bearer $API_KEY", request)
            response.choices.firstOrNull()?.message?.content?.trim() ?: "Unknown"
        } catch (e: Exception) {
            Log.e(TAG, "Grok request failed", e)
            "Error: ${e.message}"
        }
    }
}
