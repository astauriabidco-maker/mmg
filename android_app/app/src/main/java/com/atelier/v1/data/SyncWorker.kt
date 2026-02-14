package com.atelier.v1.data

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class SyncWorker(appContext: Context, workerParams: WorkerParameters) :
    CoroutineWorker(appContext, workerParams) {

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val db = AppDatabase.getDatabase(applicationContext)
        val dao = db.pendingActionDao()
        val actions = dao.getAll()
        
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        val startAdapter = moshi.adapter(StartRequest::class.java)
        val stopAdapter = moshi.adapter(StopRequest::class.java)

        if (actions.isEmpty()) return@withContext Result.success()

        for (action in actions) {
            try {
                when (action.type) {
                    "START" -> {
                        val req = startAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.startProduction(req)
                        if (res.isSuccessful) dao.delete(action)
                    }
                    "STOP" -> {
                        val req = stopAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.stopProduction(req)
                        if (res.isSuccessful) dao.delete(action)
                    }
                    "PAUSE" -> {
                        val req = stopAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.pauseProduction(req)
                        if (res.isSuccessful) dao.delete(action)
                    }
                }
            } catch (e: Exception) {
                // Keep for next retry
                e.printStackTrace()
                return@withContext Result.retry()
            }
        }

        Result.success()
    }
}
