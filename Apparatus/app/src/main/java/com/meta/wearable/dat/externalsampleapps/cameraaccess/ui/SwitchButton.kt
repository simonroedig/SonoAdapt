/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the license found in the
 * LICENSE file in the root directory of this source tree.
 */

package com.meta.wearable.dat.externalsampleapps.cameraaccess.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun SwitchButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    isDestructive: Boolean = false,
    enabled: Boolean = true,
    backgroundColor: Color? = null,
    contentColor: Color? = null,
) {
  // Destructive (Stop Streaming) uses Dark Sunset BrownRed + VanillaCustard
  val containerColor = backgroundColor
      ?: if (isDestructive) AppColor.BrownRed else AppColor.DeepBlue
  val effectiveContentColor = contentColor
      ?: if (isDestructive) AppColor.VanillaCustard else Color.White

  Button(
      modifier = modifier.height(48.dp).fillMaxWidth(),
      onClick = onClick,
      shape = RoundedCornerShape(12.dp),
      colors = ButtonDefaults.buttonColors(
          containerColor = containerColor,
          disabledContainerColor = Color.Gray,
          disabledContentColor = Color.DarkGray,
          contentColor = effectiveContentColor,
      ),
      enabled = enabled,
  ) {
    Text(
        text = label,
        fontSize = 13.sp,
        fontWeight = if (isDestructive) FontWeight.SemiBold else FontWeight.Medium
    )
  }
}
