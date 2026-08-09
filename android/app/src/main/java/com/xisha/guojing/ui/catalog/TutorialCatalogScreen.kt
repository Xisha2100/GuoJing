package com.xisha.guojing.ui.catalog

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.xisha.guojing.model.TutorialSummary

@Composable
fun TutorialCatalogScreen(
    uiState: TutorialCatalogUiState,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.safeDrawing),
        ) {
            CatalogHeader()
            when (uiState) {
                TutorialCatalogUiState.Loading -> LoadingContent()
                TutorialCatalogUiState.Empty -> EmptyContent()
                TutorialCatalogUiState.Error -> ErrorContent(onRetry)
                is TutorialCatalogUiState.Content -> TutorialList(uiState.tutorials)
            }
        }
    }
}

@Composable
private fun CatalogHeader() {
    Column(
        modifier = Modifier.padding(horizontal = 24.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MaterialTheme.colorScheme.primary,
            ) {
                Text(
                    text = "老",
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                    color = MaterialTheme.colorScheme.onPrimary,
                    style = MaterialTheme.typography.headlineSmall,
                )
            }
            Text(
                text = "老牌子",
                modifier = Modifier.semantics { heading() },
                style = MaterialTheme.typography.headlineLarge,
            )
        }
        Text(
            text = "手机不会用？我们一步一步来。",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
        )
    }
}

@Composable
private fun LoadingContent() {
    CenteredMessage {
        CircularProgressIndicator(
            modifier = Modifier.size(48.dp),
            strokeWidth = 5.dp,
        )
        Spacer(Modifier.height(20.dp))
        Text(
            text = "正在查找可以学习的教程……",
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun EmptyContent() {
    CenteredMessage {
        Text(
            text = "暂时还没有教程",
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = "教程发布后会自动显示在这里。",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun ErrorContent(onRetry: () -> Unit) {
    CenteredMessage {
        Text(
            text = "现在无法加载教程",
            modifier = Modifier.semantics { heading() },
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = "请检查网络，或者稍后再试。",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodyLarge,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))
        Button(
            onClick = onRetry,
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
        ) {
            Text("重新加载")
        }
    }
}

@Composable
private fun TutorialList(tutorials: List<TutorialSummary>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        item {
            Text(
                text = "可以学习的教程",
                modifier = Modifier
                    .padding(top = 4.dp, bottom = 4.dp)
                    .semantics { heading() },
                style = MaterialTheme.typography.headlineSmall,
            )
        }
        items(
            items = tutorials,
            key = { it.graphId },
        ) { tutorial ->
            TutorialCard(tutorial)
        }
    }
}

@Composable
private fun TutorialCard(tutorial: TutorialSummary) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 22.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = tutorial.title,
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                text = "适用于 ${tutorial.recordedVersionName} 版本",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                text = "教程版本 ${tutorial.revisionNumber}",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun CenteredMessage(content: @Composable ColumnScope.() -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 28.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            content = content,
        )
    }
}
