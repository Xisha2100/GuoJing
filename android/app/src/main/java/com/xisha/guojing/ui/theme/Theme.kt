package com.xisha.guojing.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val GuoJingColors = lightColorScheme(
    primary = BrandRed,
    onPrimary = WarmSurface,
    primaryContainer = BrandRedContainer,
    onPrimaryContainer = DarkText,
    background = WarmBackground,
    onBackground = DarkText,
    surface = WarmSurface,
    onSurface = DarkText,
    onSurfaceVariant = MutedText,
    outlineVariant = Divider,
)

private val GuoJingTypography = Typography(
    headlineLarge = TextStyle(
        fontSize = 32.sp,
        lineHeight = 40.sp,
        fontWeight = FontWeight.Bold,
    ),
    headlineSmall = TextStyle(
        fontSize = 24.sp,
        lineHeight = 32.sp,
        fontWeight = FontWeight.Bold,
    ),
    titleLarge = TextStyle(
        fontSize = 22.sp,
        lineHeight = 30.sp,
        fontWeight = FontWeight.Bold,
    ),
    bodyLarge = TextStyle(
        fontSize = 20.sp,
        lineHeight = 30.sp,
        fontWeight = FontWeight.Normal,
    ),
    bodyMedium = TextStyle(
        fontSize = 17.sp,
        lineHeight = 26.sp,
        fontWeight = FontWeight.Normal,
    ),
    labelLarge = TextStyle(
        fontSize = 20.sp,
        lineHeight = 26.sp,
        fontWeight = FontWeight.Bold,
    ),
)

@Composable
fun GuoJingTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = GuoJingColors,
        typography = GuoJingTypography,
        content = content,
    )
}
