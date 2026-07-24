package com.receiptbot.app

import android.app.Application
import com.receiptbot.app.data.ReceiptRepository
import com.receiptbot.app.data.TokenManager
import com.receiptbot.app.data.network.RetrofitClient

// 앱 전역에서 하나만 존재하는 TokenManager/Repository를 보관한다 (간단한 수동 DI).
class ReceiptBotApp : Application() {
    lateinit var tokenManager: TokenManager
        private set
    lateinit var repository: ReceiptRepository
        private set

    override fun onCreate() {
        super.onCreate()
        tokenManager = TokenManager(this)
        val api = RetrofitClient.create(tokenManager)
        repository = ReceiptRepository(api)
    }
}
