package ru.slqa.sltracker

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import java.util.concurrent.atomic.AtomicBoolean

class TrackerService : Service() {

    companion object {
        const val CHANNEL_ID = "sltracker_channel"
        const val NOTIFICATION_ID = 1
        const val ACTION_START = "ru.slqa.sltracker.START"
        const val ACTION_STOP = "ru.slqa.sltracker.STOP"
        private const val APP_POLL_MS = 3000L
        private const val APP_LOOKBACK_MS = 60_000L   // окно, за которое смотрим события
    }

    private var receiver: BroadcastReceiver? = null
    private val isWorking = AtomicBoolean(false)
    private var lastChangeMs = 0L

    private var appThread: Thread? = null
    private val appPolling = AtomicBoolean(false)
    @Volatile private var lastAppPackage: String? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }

        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            buildNotification("Мониторинг запущен"),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE)
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            else 0
        )

        if (isWorking.compareAndSet(false, true)) {
            registerScreenReceiver()
            lastChangeMs = System.currentTimeMillis()
            LogWriter.append(this, "=== Мониторинг запущен ===")
            LogWriter.append(this, "НАЧАЛО РАБОТА")
            lastAppPackage = null
            startAppPolling()
        }

        return START_STICKY
    }

    override fun onDestroy() {
        unregisterScreenReceiver()
        stopAppPolling()

        if (isWorking.get()) {
            val now = System.currentTimeMillis()
            val duration = (now - lastChangeMs) / 1000
            LogWriter.append(this, "КОНЕЦ РАБОТА ($duration сек)")
            LogWriter.append(this, "=== Мониторинг остановлен ===")
            isWorking.set(false)
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ---------- состояние экрана ----------

    private fun registerScreenReceiver() {
        if (receiver != null) return
        receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                when (intent.action) {
                    Intent.ACTION_SCREEN_OFF -> onScreenOff()
                    Intent.ACTION_USER_PRESENT -> onUserPresent()
                }
            }
        }
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_USER_PRESENT)
        }
        registerReceiver(receiver, filter)
    }

    private fun unregisterScreenReceiver() {
        receiver?.let {
            try { unregisterReceiver(it) } catch (_: Exception) {}
            receiver = null
        }
    }

    private fun onScreenOff() {
        if (!isWorking.compareAndSet(true, false)) return
        val now = System.currentTimeMillis()
        val duration = (now - lastChangeMs) / 1000
        LogWriter.append(this, "КОНЕЦ РАБОТА ($duration сек)")
        LogWriter.append(this, "НАЧАЛО ПРОСТОЙ")
        lastChangeMs = now
        lastAppPackage = null
    }

    private fun onUserPresent() {
        if (!isWorking.compareAndSet(false, true)) return
        val now = System.currentTimeMillis()
        val duration = (now - lastChangeMs) / 1000
        LogWriter.append(this, "КОНЕЦ ПРОСТОЙ ($duration сек)")
        LogWriter.append(this, "НАЧАЛО РАБОТА")
        lastChangeMs = now
        lastAppPackage = null
    }

    // ---------- трекинг приложений ----------

    private fun startAppPolling() {
        if (!appPolling.compareAndSet(false, true)) return
        appThread = Thread {
            while (appPolling.get()) {
                try {
                    if (isWorking.get() && UsageStatsCollector.hasPermission(this)) {
                        val pkg = UsageStatsCollector.getForegroundPackage(this, APP_LOOKBACK_MS)
                        if (pkg != null && pkg != lastAppPackage) {
                            val label = UsageStatsCollector.appLabel(this, pkg)
                            LogWriter.append(this, "  окно: $pkg | $label")
                            lastAppPackage = pkg
                        }
                    }
                } catch (_: Exception) {
                }
                try { Thread.sleep(APP_POLL_MS) } catch (_: InterruptedException) { break }
            }
        }.also { it.isDaemon = true; it.start() }
    }

    private fun stopAppPolling() {
        appPolling.set(false)
        appThread?.interrupt()
        appThread = null
    }

    // ---------- уведомление ----------

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Activity Tracker",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Мониторинг активности"
                setShowBadge(false)
            }
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("sltracker")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_recent_history)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }
}