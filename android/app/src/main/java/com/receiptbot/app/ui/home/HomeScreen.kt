@file:OptIn(ExperimentalMaterial3Api::class)

package com.receiptbot.app.ui.home

import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.receiptbot.app.data.model.FieldType
import com.receiptbot.app.data.model.RECEIPT_FIELDS
import com.receiptbot.app.data.model.Receipt
import com.receiptbot.app.ui.AppViewModelFactory
import java.io.File

@Composable
fun HomeScreen(factory: AppViewModelFactory) {
    val vm: HomeViewModel = viewModel(factory = factory)
    val context = LocalContext.current

    var pendingCaptureFile by remember { mutableStateOf<File?>(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) pendingCaptureFile?.let { vm.uploadFile(it) }
    }
    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            copyUriToCacheFile(context, it)?.let { file -> vm.uploadFile(file) }
        }
    }

    LaunchedEffect(vm.toastMessage) {
        vm.toastMessage?.let {
            Toast.makeText(context, it, Toast.LENGTH_SHORT).show()
            vm.consumeToast()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("영수증 정리") },
                actions = {
                    Text(vm.userEmail, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(end = 8.dp))
                    TextButton(onClick = { vm.logout() }) {
                        Text("로그아웃")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            UploadCard(
                isUploading = vm.isUploading,
                onCamera = {
                    val (file, uri) = createCameraCaptureUri(context)
                    pendingCaptureFile = file
                    cameraLauncher.launch(uri)
                },
                onGallery = { galleryLauncher.launch("image/*") }
            )

            vm.pendingReceipt?.let { receipt ->
                Card(modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("확인 중인 영수증", style = MaterialTheme.typography.titleMedium)
                        if ((receipt.confidence ?: 1.0) < 0.6) {
                            Text(
                                "※ OCR 신뢰도 낮음, 꼭 확인하세요",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error,
                                modifier = Modifier.padding(top = 4.dp)
                            )
                        }
                        RECEIPT_FIELDS.forEach { def ->
                            FieldEditor(
                                label = def.label,
                                value = vm.editedFields.value[def.key] ?: "",
                                type = def.type,
                                options = def.options,
                                onChange = { vm.updateField(def.key, it) }
                            )
                        }
                        vm.pendingError?.let {
                            Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp))
                        }
                        Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                            Button(onClick = { vm.saveCorrection() }, enabled = !vm.isSaving, modifier = Modifier.weight(1f)) {
                                if (vm.isSaving) CircularProgressIndicator(modifier = Modifier.size(18.dp)) else Text("저장")
                            }
                            Row1Spacer()
                            OutlinedButton(onClick = { vm.discardPending() }, modifier = Modifier.weight(1f)) {
                                Text("취소")
                            }
                        }
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth().padding(top = 16.dp)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("월간 요약", style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(
                            value = vm.selectedMonth,
                            onValueChange = { vm.onMonthChanged(it) },
                            modifier = Modifier.width(140.dp),
                            singleLine = true,
                            label = { Text("YYYY-MM") }
                        )
                    }
                    val summary = vm.summary
                    if (summary == null || summary.count == 0) {
                        Text(
                            "${vm.selectedMonth}에는 아직 등록된 영수증이 없어요.",
                            color = MaterialTheme.colorScheme.outline,
                            modifier = Modifier.padding(top = 8.dp)
                        )
                    } else {
                        Column(modifier = Modifier.padding(top = 8.dp)) {
                            Text("총 ${summary.count}건")
                            Text("사업 경비(인정 가능): ${"%,d".format(summary.biz_total)}원")
                            Text("개인 지출: ${"%,d".format(summary.personal_total)}원")
                            summary.categories.take(3).forEach {
                                Text("· ${it.category}: ${"%,d".format(it.amount)}원", style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                    Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                        Button(
                            onClick = {
                                vm.exportExcel(context) { _, msg ->
                                    Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
                                }
                            },
                            modifier = Modifier.weight(1f)
                        ) { Text("엑셀로 다운로드") }
                        Row1Spacer()
                        OutlinedButton(onClick = { vm.deleteLatestReceipt() }, modifier = Modifier.weight(1f)) {
                            Text("최근 항목 삭제")
                        }
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 24.dp)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("이번 달 내역", style = MaterialTheme.typography.titleMedium)
                    if (vm.receipts.isEmpty()) {
                        Text("내역이 없습니다.", color = MaterialTheme.colorScheme.outline, modifier = Modifier.padding(top = 8.dp))
                    } else {
                        Column {
                            vm.receipts.forEach { r ->
                                ReceiptRow(r)
                                Divider()
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun UploadCard(isUploading: Boolean, onCamera: () -> Unit, onGallery: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text("영수증 등록", style = MaterialTheme.typography.titleMedium)
            if (isUploading) {
                Row(modifier = Modifier.padding(top = 12.dp)) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    Text("영수증 읽는 중...", modifier = Modifier.padding(start = 8.dp))
                }
            } else {
                Row(modifier = Modifier.fillMaxWidth().padding(top = 12.dp)) {
                    Button(onClick = onCamera, modifier = Modifier.weight(1f)) { Text("사진 촬영") }
                    Row1Spacer()
                    OutlinedButton(onClick = onGallery, modifier = Modifier.weight(1f)) { Text("갤러리에서 선택") }
                }
            }
        }
    }
}

@Composable
private fun FieldEditor(
    label: String,
    value: String,
    type: FieldType,
    options: List<String>,
    onChange: (String) -> Unit
) {
    if (type == FieldType.SELECT) {
        var expanded by remember { mutableStateOf(false) }
        ExposedDropdownMenuBox(
            expanded = expanded,
            onExpandedChange = { expanded = it },
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
        ) {
            OutlinedTextField(
                value = value,
                onValueChange = {},
                readOnly = true,
                label = { Text(label) },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                modifier = Modifier.fillMaxWidth()
            )
            ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                options.forEach { option ->
                    DropdownMenuItem(text = { Text(option) }, onClick = {
                        onChange(option)
                        expanded = false
                    })
                }
            }
        }
    } else {
        OutlinedTextField(
            value = value,
            onValueChange = onChange,
            label = { Text(label) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
        )
    }
}

@Composable
private fun ReceiptRow(r: Receipt) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Column {
            Text(r.merchant, style = MaterialTheme.typography.bodyLarge)
            Text(
                "${r.date} · ${r.category} · ${r.biz_or_personal}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.outline
            )
        }
        Text("${"%,d".format(r.amount)}원", style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun Row1Spacer() {
    Spacer(modifier = Modifier.width(8.dp))
}
