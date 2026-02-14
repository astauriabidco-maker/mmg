package com.atelier.v1.data

import retrofit2.http.Body
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.Response

data class LoginRequest(val username: String, val pin: String)
data class LoginResponse(val access_token: String, val role: String, val station: String?)

interface ApiService {
    @POST("/token")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("/v2/planning/start")
    suspend fun startProduction(@Body request: StartRequest): Response<Any>

    @POST("/v2/planning/pause")
    suspend fun pauseProduction(@Body request: StopRequest): Response<Any>

    @POST("/v2/planning/stop")
    suspend fun stopProduction(@Body request: StopRequest): Response<Any>

    @POST("/v2/planning/defect")
    suspend fun reportDefect(@Body request: StopRequest): Response<Any>

    @POST("/v2/printer/reprint/{order_ref}")
    suspend fun reprintLabel(@Path("order_ref") orderRef: String): Response<Any>

    @retrofit2.http.GET("/v2/analytics/daily")
    suspend fun getDailyProduction(): Response<Map<String, Int>>
}
