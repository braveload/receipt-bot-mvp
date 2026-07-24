package com.receiptbot.app.ui.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.receiptbot.app.data.ApiException
import com.receiptbot.app.data.ReceiptRepository
import com.receiptbot.app.data.TokenManager
import kotlinx.coroutines.launch

enum class AuthMode { LOGIN, REGISTER }

class AuthViewModel(
    private val repository: ReceiptRepository,
    private val tokenManager: TokenManager
) : ViewModel() {

    var mode by mutableStateOf(AuthMode.LOGIN)
        private set
    var email by mutableStateOf("")
    var password by mutableStateOf("")
    var isLoading by mutableStateOf(false)
        private set
    var errorMessage by mutableStateOf<String?>(null)
        private set

    fun switchMode(newMode: AuthMode) {
        mode = newMode
        errorMessage = null
    }

    fun submit() {
        if (email.isBlank() || password.length < 8) {
            errorMessage = "이메일과 8자 이상의 비밀번호를 입력해주세요."
            return
        }
        viewModelScope.launch {
            isLoading = true
            errorMessage = null
            try {
                val response = if (mode == AuthMode.LOGIN) {
                    repository.login(email.trim(), password)
                } else {
                    repository.register(email.trim(), password)
                }
                tokenManager.save(response.token, response.user.email)
            } catch (e: ApiException) {
                errorMessage = e.message
            } catch (e: Exception) {
                errorMessage = "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            } finally {
                isLoading = false
            }
        }
    }
}
