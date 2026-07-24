package com.receiptbot.app.data.network

import com.receiptbot.app.data.model.AuthRequest
import com.receiptbot.app.data.model.AuthResponse
import com.receiptbot.app.data.model.CorrectionRequest
import com.receiptbot.app.data.model.DeleteResponse
import com.receiptbot.app.data.model.DiscardResponse
import com.receiptbot.app.data.model.MonthlySummary
import com.receiptbot.app.data.model.Receipt
import com.receiptbot.app.data.model.UploadResponse
import com.receiptbot.app.data.model.UserDto
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Query

// 웹앱(app/web_api.py)과 동일한 /api 엔드포인트를 그대로 사용한다.
interface ApiService {

    @POST("auth/register")
    suspend fun register(@Body body: AuthRequest): AuthResponse

    @POST("auth/login")
    suspend fun login(@Body body: AuthRequest): AuthResponse

    @GET("me")
    suspend fun me(): UserDto

    @Multipart
    @POST("receipts/upload")
    suspend fun uploadReceipt(@Part file: MultipartBody.Part): UploadResponse

    @GET("receipts/pending")
    suspend fun getPending(): Receipt?

    @PATCH("receipts/pending")
    suspend fun correctPending(@Body body: CorrectionRequest): Receipt

    @DELETE("receipts/pending")
    suspend fun discardPending(): DiscardResponse

    @POST("receipts/confirm")
    suspend fun confirmReceipt(): Receipt

    @GET("receipts")
    suspend fun listReceipts(@Query("month") month: String?): List<Receipt>

    @GET("receipts/summary")
    suspend fun getSummary(@Query("month") month: String?): MonthlySummary

    @GET("receipts/export")
    suspend fun exportExcel(@Query("month") month: String?): Response<ResponseBody>

    @DELETE("receipts/latest")
    suspend fun deleteLatest(): DeleteResponse
}
