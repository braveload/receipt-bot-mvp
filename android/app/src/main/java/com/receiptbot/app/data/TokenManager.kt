package com.receiptbot.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "auth")

// JWT/이메일을 기기에 저장한다 (앱 재실행 시 자동 로그인 유지).
class TokenManager(private val context: Context) {
    private val tokenKey = stringPreferencesKey("token")
    private val emailKey = stringPreferencesKey("email")

    val tokenFlow: Flow<String?> = context.dataStore.data.map { it[tokenKey] }
    val emailFlow: Flow<String?> = context.dataStore.data.map { it[emailKey] }

    suspend fun currentToken(): String? = tokenFlow.first()

    suspend fun save(token: String, email: String) {
        context.dataStore.edit { prefs ->
            prefs[tokenKey] = token
            prefs[emailKey] = email
        }
    }

    suspend fun clear() {
        context.dataStore.edit { prefs ->
            prefs.remove(tokenKey)
            prefs.remove(emailKey)
        }
    }
}
