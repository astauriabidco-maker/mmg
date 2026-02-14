# Compilation Application Mobile

## Prérequis
- Flutter SDK installé (https://flutter.dev/docs/get-started/install)
- Android Studio ou VS Code configuré

## Installation
1.  Créer un nouveau projet Flutter :
    ```bash
    flutter create atelier_mobile
    ```

2.  Remplacer le contenu de `atelier_mobile/pubspec.yaml` par le fichier `mobile/pubspec.yaml`.

3.  Remplacer le contenu de `atelier_mobile/lib/main.dart` par le fichier `mobile/lib/main.dart`.

4.  Lancer les dépendances :
    ```bash
    cd atelier_mobile
    flutter pub get
    ```

## Lancement (Test)
1.  Ouvrir un émulateur Android.
2.  Lancer l'application :
    ```bash
    flutter run
    ```

## Build APK (Production)
```bash
flutter build apk --release
```
L'APK sera dans `build/app/outputs/flutter-apk/app-release.apk`.
