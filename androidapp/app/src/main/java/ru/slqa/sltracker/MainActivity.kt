package ru.slqa.sltracker

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.delay
import ru.slqa.sltracker.ui.theme.SltrackerTheme

class MainActivity : ComponentActivity() {

    private val notifPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(
                    this, Manifest.permission.POST_NOTIFICATIONS
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                notifPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        setContent {
            SltrackerTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(
                        onStart = { startTracker() },
                        onStop = { stopTracker() },
                        onOpenUsageSettings = { openUsageSettings() }
                    )
                }
            }
        }
    }

    private fun startTracker() {
        val intent = Intent(this, TrackerService::class.java).apply {
            action = TrackerService.ACTION_START
        }
        ContextCompat.startForegroundService(this, intent)
    }

    private fun stopTracker() {
        val intent = Intent(this, TrackerService::class.java).apply {
            action = TrackerService.ACTION_STOP
        }
        startService(intent)
    }

    private fun openUsageSettings() {
        startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
    }
}

@Composable
fun MainScreen(
    onStart: () -> Unit,
    onStop: () -> Unit,
    onOpenUsageSettings: () -> Unit
) {
    val context = LocalContext.current
    var logText by remember { mutableStateOf("") }
    var hasUsagePermission by remember { mutableStateOf(false) }
    val scrollState = rememberScrollState()

    LaunchedEffect(Unit) {
        while (true) {
            logText = LogWriter.readAll(context)
            hasUsagePermission = UsageStatsCollector.hasPermission(context)
            delay(1000)
        }
    }

    LaunchedEffect(logText) {
        scrollState.scrollTo(scrollState.maxValue)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Button(onClick = onStart) { Text("Старт") }
            Spacer(Modifier.width(8.dp))
            Button(onClick = onStop) { Text("Стоп") }
            Spacer(Modifier.weight(1f))
            Text("activity.log", fontWeight = FontWeight.Bold)
        }

        Spacer(Modifier.height(8.dp))

        if (!hasUsagePermission) {
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.errorContainer
                ),
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        "Нет доступа к статистике использования",
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Без него не получится писать, какое приложение активно.",
                        fontSize = 13.sp
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = onOpenUsageSettings) {
                        Text("Разрешить")
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }

        Box(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(scrollState)
        ) {
            Text(
                text = logText.ifEmpty { "(лог пуст)" },
                fontFamily = FontFamily.Monospace,
                fontSize = 12.sp,
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}