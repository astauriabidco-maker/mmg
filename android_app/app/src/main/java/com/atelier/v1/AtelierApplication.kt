package com.atelier.v1

import android.app.Application
import androidx.work.Configuration
import android.util.Log

class AtelierApplication : Application(), Configuration.Provider {

    override fun getWorkManagerConfiguration(): Configuration {
        return Configuration.Builder()
            .setMinimumLoggingLevel(Log.INFO)
            .build()
    }
}
