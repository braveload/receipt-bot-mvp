package com.receiptbot.app.data.model

data class AuthRequest(val email: String, val password: String)

data class AuthResponse(val token: String, val user: UserDto)

data class UserDto(val id: Int, val email: String)

data class Receipt(
    val id: Int,
    val merchant: String,
    val amount: Long,
    val date: String,
    val doc_type: String,
    val category: String,
    val biz_or_personal: String,
    val biz_reg_no: String?,
    val confidence: Double?,
    val supply_amount: Long?,
    val vat_amount: Long?,
    val status: String
)

data class UploadResponse(val duplicate: Boolean, val receipt: Receipt)

data class CorrectionRequest(val changes: Map<String, Any>)

data class MonthlySummary(
    val month: String,
    val count: Int,
    val biz_total: Long,
    val personal_total: Long,
    val categories: List<CategoryAmount>
)

data class CategoryAmount(val category: String, val amount: Long)

data class DiscardResponse(val discarded: Boolean)

data class DeleteResponse(val deleted: Boolean, val receipt: Receipt?)

// 영수증 수정 폼에서 쓰는 필드 정의 (표시용 라벨 + 타입).
enum class FieldType { TEXT, NUMBER, DATE, SELECT }

data class FieldDef(
    val key: String,
    val label: String,
    val type: FieldType,
    val options: List<String> = emptyList()
)

val RECEIPT_FIELDS = listOf(
    FieldDef("merchant", "상호명", FieldType.TEXT),
    FieldDef("amount", "금액", FieldType.NUMBER),
    FieldDef("date", "날짜", FieldType.DATE),
    FieldDef("doc_type", "증빙유형", FieldType.SELECT, listOf("간이영수증", "세금계산서", "현금영수증", "카드전표")),
    FieldDef("category", "카테고리", FieldType.SELECT, listOf("광고비", "접대비", "소모품비", "통신비", "교통비", "식비", "임차료", "기타")),
    FieldDef("biz_or_personal", "구분", FieldType.SELECT, listOf("사업", "개인")),
    FieldDef("supply_amount", "공급가액", FieldType.NUMBER),
    FieldDef("vat_amount", "부가세", FieldType.NUMBER),
)
