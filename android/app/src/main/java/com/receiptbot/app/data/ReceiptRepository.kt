package com.receiptbot.app.data

import com.google.gson.Gson
import com.receiptbot.app.data.model.AuthRequest
import com.receiptbot.app.data.model.AuthResponse
import com.receiptbot.app.data.model.CorrectionRequest
import com.receiptbot.app.data.model.MonthlySummary
import com.receiptbot.app.data.model.Receipt
import com.receiptbot.app.data.model.UploadResponse
import com.receiptbot.app.data.network.ApiService
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.ResponseBody
import retrofit2.HttpException
import java.io.File

// FastAPI가 내려주는 {"detail": "..."} 형태의 에러 메시지를 그대로 사용자에게 보여주기 위한 파서.
private fun HttpException.detailMessage(): String {
    return try {
        val body = response()?.errorBody()?.string()
        if (body.isNullOrBlank()) return message()
        Gson().fromJson(body, Map::class.java)["detail"] as? String ?: message()
    } catch (e: Exception) {
        message()
    }
}

class ApiException(message: String) : Exception(message)

class ReceiptRepository(private val api: ApiService) {

    private suspend fun <T> safeCall(block: suspend () -> T): T {
        return try {
            block()
        } catch (e: HttpException) {
            throw ApiException(e.detailMessage())
        }
    }

    suspend fun register(email: String, password: String): AuthResponse =
        safeCall { api.register(AuthRequest(email, password)) }

    suspend fun login(email: String, password: String): AuthResponse =
        safeCall { api.login(AuthRequest(email, password)) }

    suspend fun uploadReceipt(file: File): UploadResponse = safeCall {
        val requestFile = file.asRequestBody("image/jpeg".toMediaTypeOrNull())
        val part = MultipartBody.Part.createFormData("file", file.name, requestFile)
        api.uploadReceipt(part)
    }

    suspend fun getPending(): Receipt? = safeCall { api.getPending() }

    suspend fun correctPending(changes: Map<String, Any>): Receipt =
        safeCall { api.correctPending(CorrectionRequest(changes)) }

    suspend fun discardPending() = safeCall { api.discardPending() }

    suspend fun confirmReceipt(): Receipt = safeCall { api.confirmReceipt() }

    suspend fun listReceipts(month: String?): List<Receipt> = safeCall { api.listReceipts(month) }

    suspend fun getSummary(month: String?): MonthlySummary = safeCall { api.getSummary(month) }

    suspend fun exportExcel(month: String?): ResponseBody {
        val response = api.exportExcel(month)
        if (!response.isSuccessful) {
            val detail = try {
                val body = response.errorBody()?.string()
                if (body.isNullOrBlank()) null
                else Gson().fromJson(body, Map::class.java)["detail"] as? String
            } catch (e: Exception) {
                null
            }
            throw ApiException(detail ?: "내보내기에 실패했습니다.")
        }
        return response.body() ?: throw ApiException("내보내기 파일을 받지 못했습니다.")
    }

    suspend fun deleteLatest() = safeCall { api.deleteLatest() }
}
