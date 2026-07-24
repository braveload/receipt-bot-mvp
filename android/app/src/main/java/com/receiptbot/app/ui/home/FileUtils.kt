package com.receiptbot.app.ui.home

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File
import java.util.UUID

// 카메라 촬영 결과를 담을 임시 캐시 파일과 FileProvider Uri를 만든다.
fun createCameraCaptureUri(context: Context): Pair<File, Uri> {
    val dir = File(context.cacheDir, "images").apply { mkdirs() }
    val file = File(dir, "capture_${UUID.randomUUID()}.jpg")
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    return file to uri
}

// 갤러리에서 선택한 content Uri를 업로드 가능한 로컬 파일로 복사한다.
fun copyUriToCacheFile(context: Context, uri: Uri): File? {
    return try {
        val dir = File(context.cacheDir, "images").apply { mkdirs() }
        val file = File(dir, "picked_${UUID.randomUUID()}.jpg")
        context.contentResolver.openInputStream(uri)?.use { input ->
            file.outputStream().use { output -> input.copyTo(output) }
        }
        if (file.exists() && file.length() > 0) file else null
    } catch (e: Exception) {
        null
    }
}
