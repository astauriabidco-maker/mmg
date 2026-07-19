import api from './api';

/**
 * Télécharge un PDF backend via l'instance axios authentifiée (header
 * Authorization ajouté par l'intercepteur) puis l'ouvre dans un nouvel
 * onglet — comportement équivalent aux anciens liens target="_blank".
 * L'object URL est révoquée après ouverture pour éviter les fuites mémoire.
 *
 * @param {string} path Chemin relatif de l'API, ex. `/v2/pdf/quote/12`.
 */
export async function openPdf(path) {
    const response = await api.get(path, { responseType: 'blob' });
    const blob = new Blob([response.data], {
        type: response.headers['content-type'] || 'application/pdf',
    });
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, '_blank', 'noopener,noreferrer');
    // Laisse le temps au nouvel onglet de charger le blob avant révocation.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
}

/**
 * Variante avec retour utilisateur : en cas de 401, l'intercepteur d'api.js
 * purge déjà l'authentification ; toute autre erreur affiche un message,
 * cohérent avec le pattern `alert(...)` utilisé dans les pages.
 */
export async function openPdfWithFeedback(path) {
    try {
        await openPdf(path);
    } catch (error) {
        if (error?.response?.status === 401) return;
        alert("Impossible d'ouvrir le document PDF. Veuillez réessayer.");
    }
}

function filenameFromContentDisposition(header) {
    if (!header) return null;
    const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
    return match ? match[1] : null;
}

/**
 * Télécharge un export backend (CSV, FEC, XLSX…) via l'instance axios
 * authentifiée et l'enregistre comme un fichier, avec le nom fourni par
 * le header Content-Disposition s'il est présent, sinon `defaultFilename`.
 * L'object URL est révoquée après le téléchargement.
 *
 * @param {string} path Chemin relatif de l'API, ex. `/v2/stock/export/inventory`.
 * @param {string} defaultFilename Nom de secours si le backend n'en fournit pas.
 */
export async function downloadFile(path, defaultFilename = 'export.bin') {
    const response = await api.get(path, { responseType: 'blob' });
    const filename =
        filenameFromContentDisposition(response.headers['content-disposition']) || defaultFilename;
    const blob = new Blob([response.data], {
        type: response.headers['content-type'] || 'application/octet-stream',
    });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

/**
 * Variante avec retour utilisateur, même convention que openPdfWithFeedback.
 */
export async function downloadFileWithFeedback(path, defaultFilename) {
    try {
        await downloadFile(path, defaultFilename);
    } catch (error) {
        if (error?.response?.status === 401) return;
        alert("Impossible de télécharger le fichier. Veuillez réessayer.");
    }
}
