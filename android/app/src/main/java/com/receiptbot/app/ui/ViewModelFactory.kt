package com.receiptbot.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.receiptbot.app.data.ReceiptRepository
import com.receiptbot.app.data.TokenManager
import com.receiptbot.app.ui.auth.AuthViewModel
import com.receiptbot.app.ui.home.HomeViewModel

// repository/tokenManager를 생성자에 주입하기 위한 최소한의 수동 팩토리.
class AppViewModelFactory(
    private val repository: ReceiptRepository,
    private val tokenManager: TokenManager
) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return when (modelClass) {
            AuthViewModel::class.java -> AuthViewModel(repository, tokenManager) as T
            HomeViewModel::class.java -> HomeViewModel(repository, tokenManager) as T
            else -> throw IllegalArgumentException("Unknown ViewModel class: $modelClass")
        }
    }
}
