from fastapi import BackgroundTasks
import smtplib
from email.mime.text import MIMEText
import os
import re
from datetime import datetime
from pathlib import Path

# --- INTERNAL AUTOMATION ENGINE (Zero UI / Zero External Tools) ---
# Ce module remplace Zapier/n8n en gérant les événements en arrière-plan.

_PRODUCTION_FILES_DIR = Path("uploads") / "production_files"
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9 \-]")
_MAX_CLIENT_NAME_LENGTH = 50


def sanitize_client_name(client_name: str) -> str:
    """Rend un nom client sûr pour un usage dans un chemin de dossier.

    Anti path traversal : whitelist stricte (alphanumérique, espaces, tirets),
    tout le reste — dont ``.`` et ``/`` — devient ``_``, ce qui élimine les
    séquences ``..`` et tout séparateur de chemin. Longueur bornée.
    """
    sanitized = _SAFE_CHARS.sub("_", client_name or "")
    sanitized = sanitized.strip(" _-")[:_MAX_CLIENT_NAME_LENGTH].strip(" _-")
    return sanitized or "client-inconnu"

class EventBus:
    @staticmethod
    def on_quote_accepted(quote_id: int, client_name: str, amount: float, background_tasks: BackgroundTasks):
        """
        Déclenché quand un devis passe en statut 'Accepté'.
        """
        background_tasks.add_task(EventBus._task_send_welcome_email, client_name)
        background_tasks.add_task(EventBus._task_notify_manager_whatsapp, f"🎉 Nouveau devis signé ! Client: {client_name} - Montant: {amount} €")
        background_tasks.add_task(EventBus._task_create_production_folder, quote_id, client_name)

    @staticmethod
    def on_stock_alert(material_name: str, current_qty: float, background_tasks: BackgroundTasks):
        """
        Déclenché quand un stock passe sous le seuil d'alerte.
        """
        background_tasks.add_task(EventBus._task_notify_manager_whatsapp, f"⚠️ ALERTE STOCK : Le matériel {material_name} est critique ({current_qty} restants).")

    # --- TASKS IMPLEMENTATIONS ---

    @staticmethod
    def _task_send_welcome_email(client_name: str):
        """ Envoi d'un email de confirmation natif en Python sans Zapier. """
        # Exemple d'implémentation SMTP native
        print(f"[EventBus] ✉️ Simulation Envoi Email de confirmation à {client_name}...")
        # from email.message import EmailMessage
        # msg = EmailMessage()
        # msg.set_content(f"Bonjour {client_name},\nNous avons bien reçu la validation de votre devis. L'équipe MMG lance la production !")
        # msg['Subject'] = 'Confirmation de votre commande MMG'
        # msg['From'] = 'contact@mmg-france.fr'
        # msg['To'] = 'client@example.com'
        # server = smtplib.SMTP('smtp.votre-serveur.com', 587)
        # server.send_message(msg)
        # server.quit()

    @staticmethod
    def _task_notify_manager_whatsapp(message: str):
        """ Notifie le Gérant par WhatsApp en interne. """
        from ..routers.v2_webhook import send_whatsapp_message
        print(f"[EventBus] 📱 Notification interne WhatsApp: {message}")
        # ID du numéro de téléphone du gérant (Solopreneur)
        manager_phone = os.environ.get("MANAGER_PHONE", "+33600000000")
        send_whatsapp_message(manager_phone, message)

    @staticmethod
    def _task_create_production_folder(quote_id: int, client_name: str):
        """ Automatise la création des dossiers locaux ou cloud. """
        safe_name = sanitize_client_name(client_name)
        folder_name = f"{datetime.now().strftime('%Y%m%d')}_{safe_name.replace(' ', '_')}_CMD{quote_id}"
        base = _PRODUCTION_FILES_DIR.resolve()
        path = (base / folder_name).resolve()
        # Dernier filet de sécurité : le chemin final résolu doit rester dans
        # le dossier de production prévu (défense en profondeur, la whitelist
        # de sanitize_client_name rend déjà toute traversée impossible).
        if not path.is_relative_to(base):
            raise ValueError(f"Chemin de dossier de production invalide : {folder_name!r}")
        os.makedirs(path, exist_ok=True)
        print(f"[EventBus] 📁 Dossier de production généré automatiquement : {path}")

