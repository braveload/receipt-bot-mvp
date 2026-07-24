package com.receiptbot.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.receiptbot.app.ui.AppViewModelFactory
import com.receiptbot.app.ui.auth.LoginScreen
import com.receiptbot.app.ui.home.HomeScreen
import com.receiptbot.app.ui.theme.ReceiptBotTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as ReceiptBotApp
        val factory = AppViewModelFactory(app.repository, app.tokenManager)

        setContent {
            ReceiptBotTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    ReceiptBotRoot(factory)
                }
            }
        }
    }
}

@Composable
private fun ReceiptBotRoot(factory: AppViewModelFactory) {
    val app = androidx.compose.ui.platform.LocalContext.current.applicationContext as ReceiptBotApp
    val token by app.tokenManager.tokenFlow.collectAsState(initial = "")

    // token == "" 은 "아직 DataStore 로딩 전"이라 판단하지 않고 그대로 로그인 화면을 보여준다.
    // (null 이면 로그아웃 상태, 비어있지 않은 문자열이면 로그인 상태)
    if (token.isNullOrEmpty()) {
        LoginScreen(factory)
    } else {
        HomeScreen(factory)
    }
}
