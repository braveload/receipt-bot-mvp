package com.receiptbot.app.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.receiptbot.app.ui.AppViewModelFactory

@Composable
fun LoginScreen(factory: AppViewModelFactory) {
    val vm: AuthViewModel = viewModel(factory = factory)

    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("영수증 정리", style = MaterialTheme.typography.headlineSmall)
            Text(
                "카카오톡과 별개인 독립 앱입니다.",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 4.dp, bottom = 24.dp)
            )

            OutlinedTextField(
                value = vm.email,
                onValueChange = { vm.email = it },
                label = { Text("이메일") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = vm.password,
                onValueChange = { vm.password = it },
                label = { Text("비밀번호 (8자 이상)") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 16.dp)
            )

            vm.errorMessage?.let {
                Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(bottom = 12.dp))
            }

            if (vm.isLoading) {
                CircularProgressIndicator()
            } else {
                Button(onClick = { vm.submit() }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (vm.mode == AuthMode.LOGIN) "로그인" else "회원가입")
                }
                Row1Spacer()
                OutlinedButton(
                    onClick = {
                        vm.switchMode(if (vm.mode == AuthMode.LOGIN) AuthMode.REGISTER else AuthMode.LOGIN)
                    },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (vm.mode == AuthMode.LOGIN) "회원가입 하기" else "로그인으로 돌아가기")
                }
            }
        }
    }
}

@Composable
private fun Row1Spacer() {
    Box(modifier = Modifier.size(8.dp))
}
