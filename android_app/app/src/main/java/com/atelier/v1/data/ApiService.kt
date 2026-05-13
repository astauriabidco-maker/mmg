package com.atelier.v1.data

import retrofit2.http.Body
import retrofit2.http.Field
import retrofit2.http.FormUrlEncoded
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.Response

data class LoginResponse(
    val access_token: String,
    val token_type: String? = null,
    val role: String,
    val stations: List<String> = emptyList()
)

data class PlanningActionRequest(val planningId: Int)
data class PlanningIssueRequest(val notes: String)
data class PlanningIssueActionRequest(val planningId: Int, val notes: String)

interface ApiService {
    @FormUrlEncoded
    @POST("/token")
    suspend fun login(
        @Field("username") username: String,
        @Field("password") password: String
    ): Response<LoginResponse>

    @POST("/v2/planning/{planning_id}/start")
    suspend fun startProduction(@Path("planning_id") planningId: Int): Response<Any>

    @POST("/v2/planning/{planning_id}/pause")
    suspend fun pauseProduction(@Path("planning_id") planningId: Int): Response<Any>

    @POST("/v2/planning/{planning_id}/stop")
    suspend fun stopProduction(@Path("planning_id") planningId: Int): Response<Any>

    @POST("/v2/planning/{planning_id}/issue")
    suspend fun reportIssue(
        @Path("planning_id") planningId: Int,
        @Body request: PlanningIssueRequest
    ): Response<Any>

    @POST("/v2/printer/reprint/{order_ref}")
    suspend fun reprintLabel(@Path("order_ref") orderRef: String): Response<Any>

    @retrofit2.http.GET("/v2/analytics/daily")
    suspend fun getDailyProduction(): Response<Map<String, Int>>
}
