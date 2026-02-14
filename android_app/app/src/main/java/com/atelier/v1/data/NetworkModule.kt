package com.atelier.v1.data

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory

object NetworkModule {
    // 10.0.2.2 is localhost for Android Emulator
    private const val BASE_URL = "http://10.0.2.2:8000" 

    private val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    // Token stored in memory for simplicity (use EncryptedSharedPreferences in production)
    var authToken: String? = null
    var userStation: String? = null // Stored after login

    private val client = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val original = chain.request()
            val builder = original.newBuilder()
            
            authToken?.let {
                builder.header("Authorization", "Bearer $it")
            }
            
            chain.proceed(builder.build())
        }
        .build()

    val api: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(ApiService::class.java)
    }
}
