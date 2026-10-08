package ru.slqa.sltracker

import android.content.Context
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

object LogWriter {
    private const val FILE_NAME = "activity.log"
    private val tsFormat = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")

    private fun logFile(context: Context): File =
        File(context.filesDir, FILE_NAME)

    @Synchronized
    fun append(context: Context, message: String) {
        val line = "${LocalDateTime.now().format(tsFormat)} | $message\n"
        logFile(context).appendText(line)
    }

    @Synchronized
    fun readAll(context: Context): String {
        val f = logFile(context)
        return if (f.exists()) f.readText() else ""
    }

    @Synchronized
    fun clear(context: Context) {
        val f = logFile(context)
        if (f.exists()) f.delete()
    }

    fun filePath(context: Context): String = logFile(context).absolutePath
}