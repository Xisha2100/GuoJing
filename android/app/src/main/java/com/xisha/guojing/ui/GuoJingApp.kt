package com.xisha.guojing.ui

import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.xisha.guojing.data.DisabledHelpRequestSender
import com.xisha.guojing.data.DisabledHelpRequestStatusReader
import com.xisha.guojing.data.HelpRequestSender
import com.xisha.guojing.data.HelpRequestStatusReader
import com.xisha.guojing.data.TutorialCatalogRepository
import com.xisha.guojing.data.TutorialDetailRepository
import com.xisha.guojing.guidance.DisabledGuidanceOverlayPort
import com.xisha.guojing.guidance.GuidanceOverlayPort
import com.xisha.guojing.observation.DisabledScreenObservationPort
import com.xisha.guojing.observation.DisabledScreenshotOcrProvider
import com.xisha.guojing.observation.ScreenObservationPort
import com.xisha.guojing.observation.ScreenshotOcrProvider
import com.xisha.guojing.privacy.DisabledScreenshotPrivacyProcessor
import com.xisha.guojing.privacy.ScreenshotPrivacyProcessor
import com.xisha.guojing.ui.catalog.TutorialCatalogScreen
import com.xisha.guojing.ui.catalog.TutorialCatalogViewModel
import com.xisha.guojing.ui.detail.TutorialDetailMode
import com.xisha.guojing.ui.detail.TutorialDetailScreen
import com.xisha.guojing.ui.detail.TutorialDetailUiState
import com.xisha.guojing.ui.detail.TutorialDetailViewModel
import com.xisha.guojing.ui.help.ScreenshotHelpScreen
import com.xisha.guojing.ui.help.ScreenshotHelpViewModel

@Composable
fun GuoJingApp(
    catalogRepository: TutorialCatalogRepository,
    detailRepository: TutorialDetailRepository,
    observationPort: ScreenObservationPort = DisabledScreenObservationPort,
    overlayPort: GuidanceOverlayPort = DisabledGuidanceOverlayPort,
    screenshotPrivacyProcessor: ScreenshotPrivacyProcessor =
        DisabledScreenshotPrivacyProcessor,
    helpRequestSender: HelpRequestSender = DisabledHelpRequestSender,
    helpRequestStatusReader: HelpRequestStatusReader = DisabledHelpRequestStatusReader,
    screenshotOcrProvider: ScreenshotOcrProvider = DisabledScreenshotOcrProvider,
    pageObservationServiceEnabled: Boolean = false,
    onOpenAccessibilitySettings: () -> Unit = {},
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
                onScreenshotHelp = {
                    navController.navigate(SCREENSHOT_HELP_ROUTE)
                },
            )
        }

        composable(SCREENSHOT_HELP_ROUTE) {
            val screenshotHelpViewModel: ScreenshotHelpViewModel = viewModel(
                factory = ScreenshotHelpViewModel.factory(
                    screenshotPrivacyProcessor,
                    helpRequestSender,
                    screenshotOcrProvider,
                    helpRequestStatusReader,
                ),
            )
            val uiState by screenshotHelpViewModel.uiState.collectAsStateWithLifecycle()
            val picker = rememberLauncherForActivityResult(PickVisualMedia()) { uri ->
                uri?.let { screenshotHelpViewModel.importScreenshot(it.toString()) }
            }
            val leaveHelp = {
                screenshotHelpViewModel.discard()
                navController.popBackStack()
                Unit
            }
            BackHandler(onBack = leaveHelp)
            ScreenshotHelpScreen(
                uiState = uiState,
                onBack = leaveHelp,
                onPickScreenshot = {
                    picker.launch(PickVisualMediaRequest(PickVisualMedia.ImageOnly))
                },
                onQuestionChanged = screenshotHelpViewModel::updateQuestion,
                onAddRedaction = screenshotHelpViewModel::addRedaction,
                onUndoRedaction = screenshotHelpViewModel::undoLastRedaction,
                onNoSensitiveContentChanged =
                    screenshotHelpViewModel::setNoSensitiveContentConfirmed,
                onSanitize = screenshotHelpViewModel::sanitize,
                onIntentSelected = screenshotHelpViewModel::selectIntent,
                onSendConsentChanged = screenshotHelpViewModel::setSendConsent,
                onSend = screenshotHelpViewModel::send,
                onRefreshStatus = screenshotHelpViewModel::refreshStatus,
                onAcceptPrivacySuggestion = screenshotHelpViewModel::acceptPrivacySuggestion,
                onRejectPrivacySuggestion = screenshotHelpViewModel::rejectPrivacySuggestion,
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
                factory = TutorialDetailViewModel.factory(
                    graphId,
                    detailRepository,
                    observationPort,
                    overlayPort,
                ),
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
                onConfirmStepCompleted = {
                    detailViewModel.confirmStepCompleted(
                        requirePageVerification = pageObservationServiceEnabled,
                    )
                },
                onExitExecution = detailViewModel::exitExecution,
                pageObservationServiceEnabled = pageObservationServiceEnabled,
                onOpenAccessibilitySettings = onOpenAccessibilitySettings,
            )
        }
    }
}

private const val CATALOG_ROUTE = "catalog"
private const val SCREENSHOT_HELP_ROUTE = "screenshot-help"
private const val GRAPH_ID_ARGUMENT = "graphId"
private const val DETAIL_ROUTE = "tutorial/{$GRAPH_ID_ARGUMENT}"
