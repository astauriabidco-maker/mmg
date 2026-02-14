package com.atelier.v1.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AtelierV1Theme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    AppNavigation()
                }
            }
        }
    }
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()

    NavHost(navController = navController, startDestination = "login") {
        composable("login") {
            LoginScreen(
                onLoginSuccess = { isAdmin ->
                    if (isAdmin) {
                        navController.navigate("manager") { popUpTo("login") { inclusive = true } }
                    } else {
                        navController.navigate("home") { popUpTo("login") { inclusive = true } }
                    }
                }
            )
        }
        composable("manager") {
            ManagerDashboard(onBack = { navController.navigate("home") })
        }
        composable("home") {
            ScanScreen(
                onQrScanned = { qrValue ->
                    // Navigate to Action Screen
                    navController.navigate("action/${qrValue}")
                }
            )
        }
        composable("action/{qrValue}") { backStackEntry ->
            val qrValue = backStackEntry.arguments?.getString("qrValue") ?: ""
            ControlScreen(
                qrRef = qrValue,
                onBack = { navController.popBackStack() }
            )
        }
    }
}
