import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, FileText, AlertTriangle, Fingerprint, Lock, Check } from 'lucide-react';
import WindowVisualizer from '../components/WindowVisualizer';
import api, { API_BASE_URL } from '../services/api';

export default function ClientPortal() {
    const { token } = useParams();
    const [quote, setQuote] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isSigning, setIsSigning] = useState(false);
    const [signSuccess, setSignSuccess] = useState(false);
    const [consent, setConsent] = useState(false);

    useEffect(() => {
        const fetchQuote = async () => {
            try {
                const res = await api.get(`/v2/sales/portal/${token}`);
                setQuote(res.data);
                if (res.data.status === 'VALIDATED') {
                    setSignSuccess(true);
                }
            } catch (err) {
                setError("Ce lien est invalide, expiré ou n'existe pas.");
            } finally {
                setLoading(false);
            }
        };
        fetchQuote();
    }, [token]);

    const handleSign = async () => {
        if (!consent) return;
        setIsSigning(true);
        try {
            await api.post(`/v2/sales/portal/${token}/sign`);
            setSignSuccess(true);
        } catch (err) {
            alert("Une erreur est survenue lors de la signature.");
        } finally {
            setIsSigning(false);
        }
    };

    if (loading) return <div className="h-screen flex items-center justify-center font-bold text-slate-500 animate-pulse">Chargement sécurisé...</div>;
    
    if (error) return (
        <div className="h-screen flex items-center justify-center bg-slate-50">
            <div className="max-w-md p-8 bg-white rounded-[2rem] shadow-xl text-center border border-red-100">
                <AlertTriangle className="w-16 h-16 text-red-500 mx-auto mb-4" />
                <h2 className="text-xl font-black text-slate-900 mb-2">Accès Refusé</h2>
                <p className="text-slate-500 font-medium">{error}</p>
            </div>
        </div>
    );

    const currency = quote.currency || 'EUR';
    const taxRate = Number(quote.tax_rate ?? 20);
    const totalHT = quote.lines.reduce((sum, l) => sum + (l.quantity * l.unit_price * (1 - (l.discount_pct || 0) / 100)), 0);
    const tva = totalHT * (taxRate / 100);
    const totalTTC = totalHT + tva;
    const formatMoney = (value) => value.toLocaleString('fr-FR', {style: 'currency', currency});
    const statusLabels = {
        DRAFT: 'Brouillon',
        SENT: 'Envoyé',
        VALIDATED: 'Signé',
        ACCEPTED: 'Accepté',
        CANCELLED: 'Annulé',
        IN_DESIGN: "Bureau d'études",
        READY_FOR_PROD: 'Prêt pour production',
        IN_PRODUCTION: 'En production'
    };
    const validUntil = quote.created_at
        ? new Date(new Date(quote.created_at).getTime() + Number(quote.validity_days || 30) * 24 * 60 * 60 * 1000)
        : null;

    return (
        <div className="min-h-screen bg-slate-50 font-sans py-12 px-4">
            <div className="max-w-3xl mx-auto">
                
                {/* BRAND HEADER */}
                <div className="text-center mb-8">
                    <h1 className="text-2xl font-black text-slate-900 tracking-tighter">MMG MENUISERIES</h1>
                    <p className="text-slate-500 font-bold uppercase tracking-widest text-xs mt-1 flex items-center justify-center gap-2">
                        <Lock className="w-3 h-3"/> Portail de Signature Sécurisé
                    </p>
                </div>

                <div className="bg-white rounded-[2rem] shadow-2xl border border-slate-200 overflow-hidden">
                    
                    {/* QUOTE HEADER */}
                    <div className="bg-slate-900 p-8 text-white relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
                        <div className="relative z-10 flex justify-between items-start">
                            <div>
                                <h2 className="text-2xl font-black mb-1">Devis {quote.reference}</h2>
                                <p className="text-blue-200 font-medium">{quote.client_name}</p>
                                <p className="text-slate-300 font-bold text-xs uppercase tracking-widest mt-3">
                                    Statut : {statusLabels[quote.status] || quote.status} · Validité : {quote.validity_days || 30} jours
                                    {validUntil ? ` · Jusqu'au ${validUntil.toLocaleDateString('fr-FR')}` : ''}
                                </p>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">Montant TTC</p>
                                <p className="text-4xl font-black">{formatMoney(totalTTC)}</p>
                                <p className="text-xs font-bold text-slate-300 mt-2">HT {formatMoney(totalHT)} · TVA {taxRate}%</p>
                            </div>
                        </div>
                    </div>

                    {/* PDF DOWNLOAD */}
                    <div className="p-8 border-b border-slate-100 bg-blue-50/50 flex justify-between items-center">
                        <div>
                            <h3 className="font-bold text-slate-900 flex items-center gap-2">
                                <FileText className="w-5 h-5 text-blue-600"/>
                                Document Officiel
                            </h3>
                            <p className="text-sm text-slate-500 font-medium mt-1">Veuillez consulter le devis détaillé avant de signer.</p>
                        </div>
                        <a 
                            href={`${API_BASE_URL}/v2/pdf/quote/${quote.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="bg-white text-blue-700 border border-blue-200 px-6 py-3 rounded-xl font-bold shadow-sm hover:shadow-md transition-all flex items-center gap-2"
                        >
                            Voir le PDF
                        </a>
                    </div>
                    
                    {/* QUOTE LINES PREVIEW */}
                    <div className="p-8 border-b border-slate-100 bg-white">
                        <h3 className="font-bold text-slate-900 mb-6 text-lg">Détail de votre projet</h3>
                        <div className="space-y-4">
                            {quote.lines.map((line, idx) => {
                                const visualConfig = line.visual_config ? JSON.parse(line.visual_config) : null;
                                return (
                                    <div key={idx} className="flex gap-6 items-center p-4 border border-slate-100 rounded-2xl bg-slate-50/50">
                                        {visualConfig && (
                                            <div className="shrink-0 bg-white p-3 rounded-xl shadow-sm border border-slate-200">
                                                <WindowVisualizer 
                                                    type={visualConfig.type} 
                                                    width={visualConfig.width} 
                                                    height={visualConfig.height} 
                                                    color={visualConfig.color}
                                                    hasRollerShutter={visualConfig.hasRollerShutter}
                                                    openingDirection={visualConfig.openingDirection}
                                                    glassType={visualConfig.glassType}
                                                    hasMuntins={visualConfig.hasMuntins}
                                                    bottomPanelHeight={visualConfig.bottomPanelHeight}
                                                    scale={0.08} 
                                                />
                                            </div>
                                        )}
                                        <div className="flex-1">
                                            <h4 className="font-black text-slate-800 text-lg">{line.description}</h4>
                                            <p className="text-slate-500 font-medium text-sm mt-1">
                                                <span className="text-slate-700 font-bold">{line.line_type === 'STOCK_ITEM' ? 'Article stock' : 'Prestation'}</span>
                                                {' · '}Quantité : <span className="text-slate-700 font-bold">{line.quantity}</span>
                                                {line.discount_pct ? <> · Remise : <span className="text-slate-700 font-bold">{line.discount_pct}%</span></> : null}
                                            </p>
                                        </div>
                                        <div className="text-right shrink-0">
                                            <p className="font-mono text-slate-400 text-sm">{formatMoney(line.unit_price)} / u</p>
                                            <p className="font-black text-slate-900 text-xl">{formatMoney(line.quantity * line.unit_price * (1 - (line.discount_pct || 0)/100))}</p>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* CONDITIONS GENERALES DE VENTE */}
                    <div className="p-8 border-b border-slate-100 bg-slate-50">
                        <h3 className="font-bold text-slate-900 mb-4 text-sm uppercase tracking-widest flex items-center gap-2">
                            <FileText className="w-4 h-4 text-slate-400"/>
                            Conditions Générales de Vente (CGV)
                        </h3>
                        <div className="h-40 overflow-y-auto bg-white border border-slate-200 rounded-xl p-6 text-xs text-slate-600 space-y-4 font-medium leading-relaxed shadow-inner">
                            <p className="font-bold text-slate-800">Article 1 - Objet</p>
                            <p>Les présentes conditions générales de vente régissent les droits et obligations des parties dans le cadre de la vente des menuiseries métalliques fabriquées par MMG. Toute commande implique l'adhésion sans réserve de l'acheteur aux présentes CGV.</p>
                            
                            <p className="font-bold text-slate-800">Article 2 - Commandes et Validité des devis</p>
                            <p>Le devis est valable pour une durée de {quote.validity_days || 30} jours à compter de sa date d'émission. La commande ne devient définitive qu'après signature électronique du devis et versement d'un acompte de 50%, sauf dérogation expresse.</p>
                            
                            <p className="font-bold text-slate-800">Article 3 - Délais et Livraison</p>
                            <p>Les délais de fabrication (indiqués à titre indicatif) courent à partir de la réception de l'acompte et de la prise de côtes définitive sur chantier. MMG ne saurait être tenue responsable des retards liés à des cas de force majeure ou des ruptures d'approvisionnement fournisseurs.</p>

                            <p className="font-bold text-slate-800">Article 4 - Garanties</p>
                            <p>Nos profilés aluminium et vitrages sont garantis selon les normes fabricants. La garantie ne couvre pas les dommages résultant d'un mauvais entretien, de chocs ou de l'intervention d'un tiers non agréé par MMG.</p>
                        </div>
                    </div>

                    {/* SIGNATURE AREA */}
                    <div className="p-8">
                        {signSuccess ? (
                            <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-8 text-center animate-fade-in">
                                <div className="w-16 h-16 bg-emerald-500 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-500/30">
                                    <Check className="w-8 h-8 text-white" />
                                </div>
                                <h3 className="text-2xl font-black text-emerald-900 mb-2">Devis Signé avec Succès !</h3>
                                <p className="text-emerald-700 font-medium">
                                    Merci pour votre confiance. Ce devis a été validé électroniquement.
                                    <br/><span className="text-xs opacity-75 mt-2 inline-block">Validé le {new Date(quote.signed_at).toLocaleString('fr-FR')}</span>
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-6">
                                <div className="bg-slate-50 rounded-2xl p-6 border border-slate-200">
                                    <h4 className="font-black text-slate-900 mb-4 flex items-center gap-2">
                                        <Fingerprint className="w-5 h-5 text-indigo-500"/>
                                        Validation Électronique
                                    </h4>
                                    
                                    <label className="flex items-start gap-3 cursor-pointer p-4 bg-white rounded-xl border border-slate-200 hover:border-indigo-300 transition-colors">
                                        <input 
                                            type="checkbox" 
                                            className="w-5 h-5 mt-0.5 accent-indigo-600"
                                            checked={consent}
                                            onChange={(e) => setConsent(e.target.checked)}
                                        />
                                        <span className="text-sm font-medium text-slate-700">
                                            Je soussigné(e) <b>{quote.client_name}</b>, déclare avoir pris connaissance du devis {quote.reference} et de ses conditions générales de vente. Je donne mon accord pour l'exécution des travaux et la commande des matériaux. Mon adresse IP et l'horodatage feront office de signature légale.
                                        </span>
                                    </label>
                                </div>

                                <button
                                    onClick={handleSign}
                                    disabled={!consent || isSigning}
                                    className={`w-full py-5 rounded-2xl font-black text-lg flex items-center justify-center gap-3 transition-all ${
                                        consent && !isSigning 
                                        ? 'bg-slate-900 text-white hover:bg-slate-800 hover:scale-[1.01] shadow-xl shadow-slate-900/20' 
                                        : 'bg-slate-200 text-slate-400 cursor-not-allowed'
                                    }`}
                                >
                                    {isSigning ? "Signature en cours..." : "Approuver et Signer"} 
                                    {!isSigning && <CheckCircle2 className="w-6 h-6"/>}
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                <p className="text-center text-xs font-bold text-slate-400 mt-8">
                    Transaction sécurisée et auditée. Propulsé par l'ERP MMG Menuiseries.
                </p>

            </div>
        </div>
    );
}
