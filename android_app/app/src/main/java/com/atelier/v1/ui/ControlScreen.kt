package com.atelier.v1.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Archive
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Print
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun extractPlanningId(qrRef: String): Int? {
    qrRef.trim().toIntOrNull()?.let { return it }

    val match = Regex(
        pattern = "(?:planning_id|planningId|planning|plan|PLN)[=:/-]?(\\d+)",
        option = RegexOption.IGNORE_CASE
    ).find(qrRef)

    return match?.groupValues?.getOrNull(1)?.toIntOrNull()
}

@Composable
fun ControlScreen(qrRef: String, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var status by remember { mutableStateOf("PENDING") }
    var timer by remember { mutableStateOf(0) }
    var actionMessage by remember { mutableStateOf<String?>(null) }
    
    // Simulate Fetch Data
    val orderId = qrRef.replace("CMD-", "")
    val planningId = remember(qrRef) { extractPlanningId(qrRef) }

    // Timer Logic
    LaunchedEffect(status) {
        if (status == "IN_PROGRESS") {
            while (status == "IN_PROGRESS") {
                delay(1000)
                timer++
            }
        }
    }

    fun formatTime(seconds: Int): String {
        val min = seconds / 60
        val sec = seconds % 60
        return "%02d:%02d".format(min, sec)
    }

    // Offline / Sync Logic
    val context = androidx.compose.ui.platform.LocalContext.current
    val db = remember { com.atelier.v1.data.AppDatabase.getDatabase(context) }
    val moshi = com.squareup.moshi.Moshi.Builder().add(com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory()).build()

    fun scheduleSync() {
        val request = androidx.work.OneTimeWorkRequestBuilder<com.atelier.v1.data.SyncWorker>()
            .setConstraints(
                androidx.work.Constraints.Builder()
                    .setRequiredNetworkType(androidx.work.NetworkType.CONNECTED)
                    .build()
            )
            .build()
        androidx.work.WorkManager.getInstance(context).enqueue(request)
    }

    fun handleStart() {
        scope.launch {
            val id = planningId
            if (id == null) {
                actionMessage = "planning_id absent du QR: action non envoyée."
                return@launch
            }
            val req = com.atelier.v1.data.PlanningActionRequest(planningId = id)
            try {
                val response = com.atelier.v1.data.NetworkModule.api.startProduction(id)
                if (response.isSuccessful) status = "IN_PROGRESS"
            } catch (e: Exception) {
                // Offline Fallback
                val json = moshi.adapter(com.atelier.v1.data.PlanningActionRequest::class.java).toJson(req)
                db.pendingActionDao().insert(
                    com.atelier.v1.data.PendingAction(type = "START", payloadJson = json)
                )
                status = "IN_PROGRESS (OFFLINE)"
                scheduleSync()
            }
        }
    }

    fun handlePause() {
        scope.launch {
            val id = planningId
            if (id == null) {
                actionMessage = "planning_id absent du QR: action non envoyée."
                return@launch
            }
            val req = com.atelier.v1.data.PlanningActionRequest(planningId = id)
            try {
                val response = com.atelier.v1.data.NetworkModule.api.pauseProduction(id)
                if (response.isSuccessful) status = "PAUSED"
            } catch (e: Exception) {
                val json = moshi.adapter(com.atelier.v1.data.PlanningActionRequest::class.java).toJson(req)
                db.pendingActionDao().insert(
                    com.atelier.v1.data.PendingAction(type = "PAUSE", payloadJson = json)
                )
                status = "PAUSED (OFFLINE)"
                scheduleSync()
            }
        }
    }

    fun handleDefect() {
        scope.launch {
            val id = planningId
            if (id == null) {
                actionMessage = "planning_id absent du QR: action non envoyée."
                return@launch
            }
            val notes = "Signalé depuis l'application mobile"
            val req = com.atelier.v1.data.PlanningIssueActionRequest(planningId = id, notes = notes)
            try {
                val response = com.atelier.v1.data.NetworkModule.api.reportIssue(
                    id,
                    com.atelier.v1.data.PlanningIssueRequest(notes = notes)
                )
                if (response.isSuccessful) status = "DEFECT"
            } catch (e: Exception) {
                // Offline support
                val json = moshi.adapter(com.atelier.v1.data.PlanningIssueActionRequest::class.java).toJson(req)
                db.pendingActionDao().insert(
                    com.atelier.v1.data.PendingAction(type = "ISSUE", payloadJson = json)
                )
                status = "DEFECT (OFFLINE)"
                scheduleSync()
            }
        }
    }

    fun handleStop() {
        scope.launch {
            val id = planningId
            if (id == null) {
                actionMessage = "planning_id absent du QR: action non envoyée."
                return@launch
            }
            val req = com.atelier.v1.data.PlanningActionRequest(planningId = id)
            try {
                val response = com.atelier.v1.data.NetworkModule.api.stopProduction(id)
                if (response.isSuccessful) {
                    status = "DONE"
                    timer = 0
                }
            } catch (e: Exception) {
                val json = moshi.adapter(com.atelier.v1.data.PlanningActionRequest::class.java).toJson(req)
                db.pendingActionDao().insert(
                    com.atelier.v1.data.PendingAction(type = "STOP", payloadJson = json)
                )
                status = "DONE (OFFLINE)"
                scheduleSync()
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                // Icon Back
                Text("<", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            }
            Text("Pilotage", style = MaterialTheme.typography.titleMedium, color = Color.Gray)
            Spacer(modifier = Modifier.size(48.dp))
        }

        Spacer(modifier = Modifier.height(32.dp))

        // Order Card
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "COMMANDE",
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = "#$orderId",
                    style = MaterialTheme.typography.displayMedium,
                    fontWeight = FontWeight.Black,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                planningId?.let {
                    Text(
                        text = "Planning #$it",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color.Gray
                    )
                }
                Spacer(modifier = Modifier.height(8.dp))
                
                // Status Badge
                Surface(
                    color = if (status == "IN_PROGRESS") Color(0xFFE3F2FD) else Color(0xFFEEEEEE),
                    shape = CircleShape
                ) {
                    Text(
                        text = status,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                        color = if (status == "IN_PROGRESS") Color(0xFF1565C0) else Color.Gray,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }

        actionMessage?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(top = 12.dp)
            )
        }
        
        // Reprint Action
        TextButton(
            onClick = {
                scope.launch {
                    try {
                        com.atelier.v1.data.NetworkModule.api.reprintLabel(qrRef)
                        // Toast.makeText(context, "Impression lancée...", Toast.LENGTH_SHORT).show()
                    } catch (e: Exception) {}
                }
            },
            modifier = Modifier.padding(top = 8.dp)
        ) {
            Icon(Icons.Default.Print, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(modifier = Modifier.width(8.dp))
            Text("RÉIMPRIMER ÉTIQUETTE", color = MaterialTheme.colorScheme.primary)
        }

        Spacer(modifier = Modifier.weight(1f))

        // Timer
        if (status == "IN_PROGRESS") {
            Text(
                text = formatTime(timer),
                style = MaterialTheme.typography.displayLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary
            )
            Text(
                text = "En production...",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.secondary,
                modifier = Modifier.padding(top = 8.dp)
            )
            
            Spacer(modifier = Modifier.height(32.dp))
            
            // Defect Button
            Button(
                onClick = { handleDefect() },
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                modifier = Modifier.fillMaxWidth().height(56.dp)
            ) {
                Icon(Icons.Default.Warning, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text("SIGNALER UN DÉFAUT", fontWeight = FontWeight.Bold)
            }
        }

        Spacer(modifier = Modifier.weight(1f))

        // Actions
        if (status != "IN_PROGRESS") {
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                // Resume Button if Paused
                Button(
                    onClick = { handleStart() },
                    modifier = Modifier
                        .weight(1f)
                        .height(80.dp),
                    shape = RoundedCornerShape(20.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary)
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.PlayArrow, contentDescription = null, modifier = Modifier.size(32.dp))
                        Text(if (status == "PAUSED") "REPRENDRE" else "DÉMARRER", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        } else {
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                // Pause Button
                Button(
                    onClick = { handlePause() },
                    modifier = Modifier
                        .weight(1f)
                        .height(80.dp),
                    shape = RoundedCornerShape(20.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFFA000)) // Amber
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(androidx.compose.material.icons.filled.Pause, contentDescription = null, modifier = Modifier.size(32.dp))
                        Text("PAUSE", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                }

                // Done Button
                Button(
                    onClick = { handleStop() },
                    modifier = Modifier
                        .weight(1f)
                        .height(80.dp),
                    shape = RoundedCornerShape(20.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF43A047)) // Green
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(androidx.compose.material.icons.filled.Check, contentDescription = null, modifier = Modifier.size(32.dp))
                        Text("TERMINER", fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
        
        Spacer(modifier = Modifier.height(32.dp))
    }
}
