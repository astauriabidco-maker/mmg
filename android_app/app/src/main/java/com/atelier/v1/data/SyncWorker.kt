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
        val actionAdapter = moshi.adapter(PlanningActionRequest::class.java)
        val issueAdapter = moshi.adapter(PlanningIssueActionRequest::class.java)

        if (actions.isEmpty()) return@withContext Result.success()

        for (action in actions) {
            try {
                when (action.type) {
                    "START" -> {
                        val req = actionAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.startProduction(req.planningId)
                        if (res.isSuccessful) dao.delete(action)
                    }
                    "STOP" -> {
                        val req = actionAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.stopProduction(req.planningId)
                        if (res.isSuccessful) dao.delete(action)
                    }
                    "PAUSE" -> {
                        val req = actionAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.pauseProduction(req.planningId)
                        if (res.isSuccessful) dao.delete(action)
                    }
                    "ISSUE", "DEFECT" -> {
                        val req = issueAdapter.fromJson(action.payloadJson)!!
                        val res = NetworkModule.api.reportIssue(
                            req.planningId,
                            PlanningIssueRequest(notes = req.notes)
                        )
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
