package com.atelier.v1.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

@Composable
fun ManagerDashboard(onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var dailyCount by remember { mutableStateOf(0) }
    var isLoading by remember { mutableStateOf(true) }

    LaunchedEffect(true) {
        try {
            val response = com.atelier.v1.data.NetworkModule.api.getDailyProduction()
            if (response.isSuccessful) {
                dailyCount = response.body()?.get("total") ?: 0
            }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            isLoading = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp)
    ) {
        Text("Tableau de Bord", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("Vue Manager", style = MaterialTheme.typography.titleSmall, color = Color.Gray)
        
        Spacer(modifier = Modifier.height(32.dp))

        // KPI Card
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            shape = RoundedCornerShape(16.dp),
            modifier = Modifier.fillMaxWidth().height(150.dp)
        ) {
            Column(
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text("Production du Jour", style = MaterialTheme.typography.labelLarge)
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(24.dp))
                } else {
                    Text(
                        text = "$dailyCount",
                        style = MaterialTheme.typography.displayLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
                Text("Commandes terminées", style = MaterialTheme.typography.bodySmall)
            }
        }
        
        Spacer(modifier = Modifier.height(16.dp))
        
        // Placeholder for more charts
        Card(
             colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
             modifier = Modifier.fillMaxWidth().height(200.dp)
        ) {
             Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                 Text("Graphique Retards (À venir)")
             }
        }
        
        Spacer(modifier = Modifier.weight(1f))
        
        Button(
            onClick = onBack,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Retour Accueil")
        }
    }
}
