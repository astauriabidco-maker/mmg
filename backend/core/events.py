from fastapi import BackgroundTasks
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --- INTERNAL AUTOMATION ENGINE (Zero UI / Zero External Tools) ---
# Ce module remplace Zapier/n8n en gérant les événements en arrière-plan.

_PRODUCTION_FILES_DIR = Path("uploads") / "production_files"
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9 \-]")
_MAX_CLIENT_NAME_LENGTH = 50

# --- SMTP (emails transactionnels, best-effort) ---
# Source de configuration unique : variables d'environnement. L'endpoint
# /v2/config/test-smtp reçoit sa config dans le corps de requête (test ad hoc
# depuis l'UI) : il n'existe pas de config SMTP persistée en base à réutiliser.
_SMTP_TIMEOUT_SECONDS = 15
_FALSE_VALUES = {"0", "false", "no", "non", "off"}


def _smtp_settings() -> Optional[dict]:
    """Retourne la config SMTP depuis l'environnement, ou None si incomplète.

    Variables : SMTP_HOST, SMTP_PORT (défaut 587), SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM (repli sur SMTP_USER), SMTP_USE_TLS (défaut true).
    """
    host = (os.environ.get("SMTP_HOST") or "").strip()
    sender = (os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "").strip()
    if not host or not sender:
        return None
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError:
        port = 587
    use_tls = (os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in _FALSE_VALUES)
    return {
        "host": host,
        "port": port,
        "user": (os.environ.get("SMTP_USER") or "").strip(),
        "password": os.environ.get("SMTP_PASSWORD") or "",
        "sender": sender,
        "use_tls": use_tls,
    }


def _send_smtp_email(recipient: str, subject: str, text_body: str, html_body: str) -> bool:
    """Envoie un email texte+HTML. False (sans lever) si SMTP non configuré.

    Toute erreur de transport (connexion, auth, refus) est propagée : c'est
    l'appelant (tâche de fond) qui décide de la politique — ici, logger et
    ne jamais casser le flux métier.
    """
    settings = _smtp_settings()
    if settings is None:
        logger.warning(
            "[EventBus] SMTP non configuré (SMTP_HOST / SMTP_FROM absents) : "
            "email « %s » vers %s ignoré.",
            subject, recipient,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings["sender"]
    msg["To"] = recipient
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(settings["host"], settings["port"], timeout=_SMTP_TIMEOUT_SECONDS) as server:
        if settings["use_tls"]:
            server.starttls()
        if settings["user"]:
            server.login(settings["user"], settings["password"])
        server.send_message(msg)
    return True


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
    def on_quote_accepted(
        quote_id: int,
        client_name: str,
        amount_ttc: float,
        background_tasks: BackgroundTasks,
        client_email: Optional[str] = None,
        reference: Optional[str] = None,
        portal_link: Optional[str] = None,
    ):
        """
        Déclenché quand un devis passe en statut 'Accepté'.
        """
        background_tasks.add_task(
            EventBus._task_send_quote_confirmation_email,
            client_email, client_name, reference or f"#{quote_id}", amount_ttc, portal_link,
        )
        background_tasks.add_task(EventBus._task_notify_manager_whatsapp, f"🎉 Nouveau devis signé ! Client: {client_name} - Montant: {amount_ttc} €")
        background_tasks.add_task(EventBus._task_create_production_folder, quote_id, client_name)

    @staticmethod
    def on_quote_signed(
        client_email: Optional[str],
        client_name: str,
        reference: str,
        amount_ttc: float,
        background_tasks: BackgroundTasks,
    ):
        """
        Déclenché quand le client signe son devis depuis le portail public.
        Email de confirmation best-effort : jamais d'exception vers le flux.
        """
        background_tasks.add_task(
            EventBus._task_send_quote_confirmation_email,
            client_email, client_name, reference, amount_ttc, None,
        )

    @staticmethod
    def on_stock_alert(material_name: str, current_qty: float, background_tasks: BackgroundTasks):
        """
        Déclenché quand un stock passe sous le seuil d'alerte.
        """
        background_tasks.add_task(EventBus._task_notify_manager_whatsapp, f"⚠️ ALERTE STOCK : Le matériel {material_name} est critique ({current_qty} restants).")

    # --- TASKS IMPLEMENTATIONS ---

    @staticmethod
    def _task_send_quote_confirmation_email(
        client_email: Optional[str],
        client_name: str,
        reference: str,
        amount_ttc: float,
        portal_link: Optional[str] = None,
    ):
        """Email de confirmation de devis signé (best-effort, jamais d'exception).

        Tourne dans une tâche de fond FastAPI (threadpool pour les fonctions
        sync) : le smtplib bloquant ne gêne donc pas la boucle asyncio.
        """
        if not client_email:
            logger.warning(
                "[EventBus] Pas d'adresse email pour %s : confirmation du devis %s non envoyée.",
                client_name, reference,
            )
            return

        amount_label = f"{amount_ttc:,.2f}".replace(",", " ").replace(".", ",")
        subject = f"Confirmation de votre devis {reference} — MMG"
        portal_line = (
            f"\nVous pouvez consulter votre devis à tout moment ici :\n{portal_link}\n"
            if portal_link else ""
        )
        text_body = (
            f"Bonjour {client_name},\n\n"
            f"Nous vous confirmons la bonne réception de votre accord sur le devis {reference}, "
            f"d'un montant de {amount_label} € TTC.\n"
            f"{portal_line}\n"
            f"L'équipe MMG lance dès à présent la préparation de votre commande. "
            f"Nous revenons vers vous pour la planification de la fabrication et de la pose.\n\n"
            f"Cordialement,\n"
            f"L'équipe MMG"
        )
        portal_html = (
            f'<p>Vous pouvez consulter votre devis à tout moment : '
            f'<a href="{portal_link}">suivre ma commande</a>.</p>'
            if portal_link else ""
        )
        html_body = (
            f"<html><body style=\"font-family: Arial, sans-serif; color: #1e293b;\">"
            f"<p>Bonjour {client_name},</p>"
            f"<p>Nous vous confirmons la bonne réception de votre accord sur le devis "
            f"<b>{reference}</b>, d'un montant de <b>{amount_label} &euro; TTC</b>.</p>"
            f"{portal_html}"
            f"<p>L'équipe MMG lance dès à présent la préparation de votre commande. "
            f"Nous revenons vers vous pour la planification de la fabrication et de la pose.</p>"
            f"<p>Cordialement,<br/>L'équipe MMG</p>"
            f"</body></html>"
        )

        try:
            sent = _send_smtp_email(client_email, subject, text_body, html_body)
            if sent:
                logger.info("[EventBus] ✉️ Email de confirmation envoyé à %s (devis %s).", client_email, reference)
        except Exception as exc:  # best-effort : l'email ne casse jamais le flux métier
            logger.error(
                "[EventBus] Échec d'envoi de l'email de confirmation du devis %s à %s : %s",
                reference, client_email, exc,
            )

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
