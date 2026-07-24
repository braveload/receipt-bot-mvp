package com.receiptbot.app.ui.home

import android.content.ContentResolver
import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.receiptbot.app.data.ApiException
import com.receiptbot.app.data.ReceiptRepository
import com.receiptbot.app.data.TokenManager
import com.receiptbot.app.data.model.MonthlySummary
import com.receiptbot.app.data.model.Receipt
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HomeViewModel(
    private val repository: ReceiptRepository,
    private val tokenManager: TokenManager
) : ViewModel() {

    var userEmail by mutableStateOf("")
        private set

    var isUploading by mutableStateOf(false)
        private set
    var isSaving by mutableStateOf(false)
        private set

    var pendingReceipt by mutableStateOf<Receipt?>(null)
        private set
    var editedFields = mutableStateOf<Map<String, String>>(emptyMap())
        private set
    var pendingError by mutableStateOf<String?>(null)
        private set

    var selectedMonth by mutableStateOf(currentMonth())
        private set
    var summary by mutableStateOf<MonthlySummary?>(null)
        private set
    var receipts by mutableStateOf<List<Receipt>>(emptyList())
        private set

    var toastMessage by mutableStateOf<String?>(null)
        private set

    init {
        viewModelScope.launch {
            userEmail = tokenManager.emailFlow.first() ?: ""
        }
        refreshAll()
    }

    private fun showToast(msg: String) {
        toastMessage = msg
    }

    fun consumeToast() {
        toastMessage = null
    }

    fun refreshAll() {
        loadPending()
        loadSummaryAndList()
    }

    private fun loadPending() {
        viewModelScope.launch {
            try {
                val pending = repository.getPending()
                pendingReceipt = pending
                editedFields.value = pending?.let { fieldsFrom(it) } ?: emptyMap()
            } catch (e: Exception) {
                // 대기 중인 영수증 조회 실패는 조용히 무시 (화면 진입 시 흔히 발생하는 401 등은 상위에서 처리).
            }
        }
    }

    private fun fieldsFrom(r: Receipt): Map<String, String> = mapOf(
        "merchant" to r.merchant,
        "amount" to r.amount.toString(),
        "date" to r.date,
        "doc_type" to r.doc_type,
        "category" to r.category,
        "biz_or_personal" to r.biz_or_personal,
        "supply_amount" to (r.supply_amount?.toString() ?: ""),
        "vat_amount" to (r.vat_amount?.toString() ?: ""),
    )

    fun updateField(key: String, value: String) {
        editedFields.value = editedFields.value.toMutableMap().apply { put(key, value) }
    }

    fun uploadFile(file: File) {
        viewModelScope.launch {
            isUploading = true
            try {
                val result = repository.uploadReceipt(file)
                pendingReceipt = result.receipt
                editedFields.value = fieldsFrom(result.receipt)
                showToast(
                    if (result.duplicate) "이미 등록된 영수증이에요."
                    else "영수증을 읽었어요. 내용을 확인해주세요."
                )
            } catch (e: ApiException) {
                showToast(e.message ?: "업로드에 실패했습니다.")
            } catch (e: Exception) {
                showToast("업로드 중 오류가 발생했습니다.")
            } finally {
                isUploading = false
                file.delete()
            }
        }
    }

    fun saveCorrection() {
        viewModelScope.launch {
            isSaving = true
            pendingError = null
            // 빈 문자열(선택 항목 미입력)은 서버로 보내지 않는다 — 웹앱과 동일한 규칙.
            val changes: Map<String, Any> = editedFields.value.filterValues { it.isNotEmpty() }
            try {
                repository.correctPending(changes)
                repository.confirmReceipt()
                showToast("저장 완료했어요. ✅")
                pendingReceipt = null
                editedFields.value = emptyMap()
                loadSummaryAndList()
            } catch (e: ApiException) {
                pendingError = e.message
            } catch (e: Exception) {
                pendingError = "저장 중 오류가 발생했습니다."
            } finally {
                isSaving = false
            }
        }
    }

    fun discardPending() {
        viewModelScope.launch {
            try {
                repository.discardPending()
            } catch (e: Exception) {
                // 취소는 실패해도 화면 상태만 초기화한다.
            }
            pendingReceipt = null
            editedFields.value = emptyMap()
        }
    }

    fun onMonthChanged(month: String) {
        selectedMonth = month
        loadSummaryAndList()
    }

    fun loadSummaryAndList() {
        viewModelScope.launch {
            try {
                summary = repository.getSummary(selectedMonth)
                receipts = repository.listReceipts(selectedMonth)
            } catch (e: Exception) {
                // 요약 조회 실패는 조용히 무시 (로그인 직후 등).
            }
        }
    }

    fun deleteLatestReceipt() {
        viewModelScope.launch {
            try {
                val result = repository.deleteLatest()
                if (result.deleted) {
                    showToast("최근 영수증을 삭제했어요.")
                    loadSummaryAndList()
                } else {
                    showToast("삭제할 영수증이 없습니다.")
                }
            } catch (e: ApiException) {
                showToast(e.message ?: "삭제에 실패했습니다.")
            }
        }
    }

    fun exportExcel(context: Context, onDone: (Boolean, String) -> Unit) {
        viewModelScope.launch {
            try {
                val body = repository.exportExcel(selectedMonth)
                val fileName = "영수증_$selectedMonth.xlsx"
                val savedOk = saveToDownloads(context, fileName, body.bytes())
                onDone(savedOk, if (savedOk) "다운로드 폴더에 저장했어요: $fileName" else "저장에 실패했습니다.")
            } catch (e: ApiException) {
                onDone(false, e.message ?: "내보내기에 실패했습니다.")
            } catch (e: Exception) {
                onDone(false, "내보내기 중 오류가 발생했습니다.")
            }
        }
    }

    private fun saveToDownloads(context: Context, fileName: String, bytes: ByteArray): Boolean {
        return try {
            val resolver: ContentResolver = context.contentResolver
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                    put(
                        MediaStore.Downloads.MIME_TYPE,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    put(MediaStore.Downloads.IS_PENDING, 1)
                }
                val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return false
                resolver.openOutputStream(uri)?.use { it.write(bytes) }
                values.clear()
                values.put(MediaStore.Downloads.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
            } else {
                @Suppress("DEPRECATION")
                val downloadsDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
                val file = File(downloadsDir, fileName)
                file.writeBytes(bytes)
            }
            true
        } catch (e: Exception) {
            false
        }
    }

    fun logout() {
        viewModelScope.launch {
            tokenManager.clear()
        }
    }

    companion object {
        fun currentMonth(): String = SimpleDateFormat("yyyy-MM", Locale.US).format(Date())
    }
}
