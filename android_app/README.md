# Atelier V1 - Application Android Native

Application de suivi de production pour terminaux Android (Zebra, Samsung Rugged).

## Tech Stack
-   **Langage** : Kotlin
-   **UI** : Jetpack Compose
-   **Database** : Room (SQLite)
-   **Network** : Retrofit + Moshi
-   **Sync** : WorkManager
-   **Scan** : CameraX + ML Kit

## Prérequis
-   Android Studio Iguana ou plus récent.
-   JDK 17.
-   SDK Android 34 (UpsideDownCake).

## Installation
1.  Ouvrir Android Studio.
2.  "Open Project" -> Sélectionner le dossier `android_app`.
3.  Synchroniser Gradle.
4.  Configurer l'URL API dans `SyncWorker.kt` (ligne ~20) :
    -   Pour émulateur : `http://10.0.2.2:8000`
    -   Pour device réel : `http://<IP_PC>:8000`

## Fonctionnalités V1
-   **Scan QR** : Décode `CMD-XXXX|LxH|MAT`.
-   **Mode Gants** : Boutons "Giant" (Hauteur 100dp).
-   **Offline First** : Données stockées localement, synchronisées quand le réseau est disponible.
-   **Chrono** : Start/Stop avec calcul de durée.

## Structure
-   `com.atelier.v1.data` : Logique BDD et Réseau.
-   `com.atelier.v1.ui` : Écrans Compose (`ScanScreen`, `WorkScreen`).
