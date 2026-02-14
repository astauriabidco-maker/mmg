package com.atelier.v1.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Backspace
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(onLoginSuccess: (Boolean) -> Unit) {
    var pin by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()
    var isLoading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun handleNum(num: Int) {
        if (pin.length < 4) pin += num.toString()
        error = null
    }

    fun handleDelete() {
        if (pin.isNotEmpty()) pin = pin.dropLast(1)
    }

    fun handleSubmit() {
        if (pin.isNotEmpty()) {
            isLoading = true
            scope.launch {
                try {
                    val response = com.atelier.v1.data.NetworkModule.api.login(
                        com.atelier.v1.data.LoginRequest(username = "admin", pin = pin)
                    )
                    
                    if (response.isSuccessful && response.body() != null) {
                        val body = response.body()!!
                        // Save Token & Station
                        com.atelier.v1.data.NetworkModule.authToken = body.access_token
                        com.atelier.v1.data.NetworkModule.userStation = body.station
                        
                        // Check Role
                        if (body.role == "ADMIN") {
                            onLoginSuccess(true) // Start Manager Flow
                        } else {
                            onLoginSuccess(false) // Start Operator Flow
                        }
                    } else {
                        error = "PIN Incorrect (Err ${response.code()})"
                        pin = ""
                    }
                } catch (e: Exception) {
                    error = "Erreur Réseau: ${e.message}"
                } finally {
                    isLoading = false
                }
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "Atelier V2",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            text = "Connexion Opérateur",
            style = MaterialTheme.typography.bodyLarge,
            color = Color.Gray
        )

        Spacer(modifier = Modifier.height(48.dp))

        // PIN Dots
        Row(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            modifier = Modifier.padding(bottom = 32.dp)
        ) {
            repeat(4) { index ->
                Box(
                    modifier = Modifier
                        .size(24.dp)
                        .clip(CircleShape)
                        .background(
                            if (index < pin.length) MaterialTheme.colorScheme.primary else Color.LightGray
                        )
                )
            }
        }

        if (error != null) {
            Text(text = error!!, color = Color.Red, modifier = Modifier.padding(bottom = 16.dp))
        }

        // Numpad
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            val rows = listOf(
                listOf(1, 2, 3),
                listOf(4, 5, 6),
                listOf(7, 8, 9)
            )

            for (row in rows) {
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    for (num in row) {
                        NumButton(number = num, onClick = { handleNum(num) })
                    }
                }
            }
            
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                Spacer(modifier = Modifier.size(80.dp)) // Empty slot
                NumButton(number = 0, onClick = { handleNum(0) })
                IconButton(
                    onClick = { handleDelete() },
                    modifier = Modifier
                        .size(80.dp)
                        .clip(CircleShape)
                        .background(Color.Transparent)
                ) {
                    Icon(Icons.Default.Backspace, contentDescription = "Delete", tint = Color.Gray)
                }
            }
        }
        
        Spacer(modifier = Modifier.height(32.dp))
        
        Button(
            onClick = { handleSubmit() },
            enabled = pin.length == 4 && !isLoading,
            modifier = Modifier.fillMaxWidth().height(56.dp)
        ) {
             Text("CONNEXION", fontSize = 18.sp)
        }
    }
}

@Composable
fun NumButton(number: Int, onClick: () -> Unit) {
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(80.dp)
            .clip(CircleShape)
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .clickable { onClick() }
    ) {
        Text(
            text = number.toString(),
            fontSize = 32.sp,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
