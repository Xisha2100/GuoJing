package com.xisha.guojing.ui

import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.xisha.guojing.data.TutorialCatalogRepository
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.ui.catalog.TutorialCatalogScreen
import com.xisha.guojing.ui.catalog.TutorialCatalogViewModel
import com.xisha.guojing.ui.detail.TutorialDetailMode
import com.xisha.guojing.ui.detail.TutorialDetailScreen
import com.xisha.guojing.ui.detail.TutorialDetailUiState
import com.xisha.guojing.ui.detail.TutorialDetailViewModel

@Composable
fun GuoJingApp(
    catalogRepository: TutorialCatalogRepository,
    detailRepository: TutorialDetailRepository,
) {
    val navController = rememberNavController()
    NavHost(
        navController = navController,
        startDestination = CATALOG_ROUTE,
    ) {
        composable(CATALOG_ROUTE) {
            val catalogViewModel: TutorialCatalogViewModel = viewModel(
                factory = TutorialCatalogViewModel.factory(catalogRepository),
            )
            val uiState by catalogViewModel.uiState.collectAsStateWithLifecycle()
            TutorialCatalogScreen(
                uiState = uiState,
                onRetry = catalogViewModel::retry,
                onTutorialSelected = { graphId ->
                    navController.navigate("tutorial/${Uri.encode(graphId)}")
                },
            )
        }

        composable(
            route = DETAIL_ROUTE,
            arguments = listOf(
                navArgument(GRAPH_ID_ARGUMENT) {
                    type = NavType.StringType
                },
            ),
        ) { backStackEntry ->
            val graphId = requireNotNull(
                backStackEntry.arguments?.getString(GRAPH_ID_ARGUMENT),
            )
            val detailViewModel: TutorialDetailViewModel = viewModel(
                key = "tutorial-detail-$graphId",
                factory = TutorialDetailViewModel.factory(graphId, detailRepository),
            )
            val uiState by detailViewModel.uiState.collectAsStateWithLifecycle()
            val isExecuting = (
                (uiState as? TutorialDetailUiState.Content)?.mode
                    is TutorialDetailMode.Execution
                )
            BackHandler(enabled = isExecuting) {
                detailViewModel.exitExecution()
            }
            TutorialDetailScreen(
                uiState = uiState,
                onBack = {
                    if (isExecuting) {
                        detailViewModel.exitExecution()
                    } else {
                        navController.popBackStack()
                    }
                },
                onRetry = detailViewModel::retry,
                onStartTutorial = detailViewModel::startTutorial,
                onConfirmStepCompleted = detailViewModel::confirmStepCompleted,
                onExitExecution = detailViewModel::exitExecution,
            )
        }
    }
}

private const val CATALOG_ROUTE = "catalog"
private const val GRAPH_ID_ARGUMENT = "graphId"
private const val DETAIL_ROUTE = "tutorial/{$GRAPH_ID_ARGUMENT}"
