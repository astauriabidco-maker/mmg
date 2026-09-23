import React, { useEffect, useState } from 'react';
import {
    Settings, Users, Network, BrainCircuit, Box, Shield,
    Building2, Database, Save, CheckCircle2, MessageCircle,
    Activity, RefreshCw, AlertTriangle, Send, WifiOff
} from 'lucide-react';
import StationManager from './StationManager';
import RBACMatrix from './RBACMatrix';
import BusinessRulesManager from './BusinessRulesManager';
import ConfigDashboard from '../pages/ConfigDashboard';
import api from '../services/api';

export default function PlatformSettings() {
    const [activeTab, setActiveTab] = useState('users');
    const [isSaving, setIsSaving] = useState(false);
    
    // SMTP Test state
    const [smtpConfig, setSmtpConfig] = useState({
        host: '',
        port: '587',
        username: '',
        password: '',
        recipient: ''
    });
    const [smtpTestStatus, setSmtpTestStatus] = useState({ loading: false, message: '', type: '' });
    const [wahaStatus, setWahaStatus] = useState(null);
    const [wahaLoading, setWahaLoading] = useState(false);
    const [wahaTest, setWahaTest] = useState({
        recipient: '',
        message: 'Test MMG : connexion WAHA opérationnelle.'
    });
    const [wahaTestStatus, setWahaTestStatus] = useState({ loading: false, message: '', type: '' });

    const loadWahaStatus = async () => {
        setWahaLoading(true);
        try {
            const res = await api.get('/v2/config/waha/status');
            setWahaStatus(res.data);
        } catch (err) {
            const detail = err.response?.data?.detail || 'Statut WAHA indisponible';
            setWahaStatus({
                configured: false,
                healthy: false,
                status: 'error',
                detail,
                activity: [],
                checked_at: new Date().toISOString()
            });
        } finally {
            setWahaLoading(false);
        }
    };

    useEffect(() => {
        if (activeTab !== 'ai') return undefined;
        loadWahaStatus();
        const timer = window.setInterval(loadWahaStatus, 30000);
        return () => window.clearInterval(timer);
    }, [activeTab]);

    const handleSmtpTest = async () => {
        setSmtpTestStatus({ loading: true, message: 'Test en cours...', type: 'info' });
        try {
            const res = await api.post('/v2/config/test-smtp', {
                ...smtpConfig,
                port: parseInt(smtpConfig.port, 10) || 587
            });
            setSmtpTestStatus({ loading: false, message: 'Succès: ' + (res.data?.message || 'Email de test envoyé'), type: 'success' });
        } catch (err) {
            const detail = err.response?.data?.detail || 'Erreur réseau';
            setSmtpTestStatus({ loading: false, message: 'Erreur: ' + detail, type: 'error' });
        }
    };

    const handleWahaTest = async () => {
        setWahaTestStatus({ loading: true, message: 'Envoi du message test...', type: 'info' });
        try {
            const res = await api.post('/v2/config/waha/test-message', wahaTest);
            setWahaTestStatus({
                loading: false,
                message: `Message envoyé via la session ${res.data?.session || 'WAHA'}.`,
                type: 'success'
            });
            await loadWahaStatus();
        } catch (err) {
            const detail = err.response?.data?.detail || 'Erreur WAHA';
            setWahaTestStatus({ loading: false, message: detail, type: 'error' });
            await loadWahaStatus();
        }
    };
    
    // Simulate save
    const handleSave = () => {
        setIsSaving(true);
        setTimeout(() => {
            setIsSaving(false);
        }, 800);
    };

    const tabs = [
        { id: 'users', icon: Users, label: 'Utilisateurs & profils', helper: 'Créer les comptes, PIN, rôles et droits.' },
        { id: 'stations', icon: Box, label: 'Postes atelier', helper: 'Configurer les stations PVC/ALU.' },
        { id: 'workflow', icon: Network, label: 'Règles métier atelier', helper: 'Définir les règles et seuils métier.' },
        { id: 'pim', icon: Database, label: 'Référentiels catalogue', helper: 'Familles, gammes, données catalogue.' },
        { id: 'general', icon: Building2, label: 'Entreprise & documents', helper: 'Identité, CGV, mentions et facturation.' },
        { id: 'ai', icon: BrainCircuit, label: 'IA & intégrations', helper: 'OpenAI, SMTP, WhatsApp et connecteurs.' },
    ];

    return (
        <div className="w-full min-w-0 animate-fade-in">
            <header className="border-b border-slate-200 bg-white px-4 py-5 sm:px-6 xl:px-8">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div className="flex min-w-0 items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
                            <Settings className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                            <h1 className="text-xl font-black text-slate-900">Paramètres & accès</h1>
                            <p className="text-sm font-semibold text-slate-500">
                                Utilisateurs, atelier, référentiels et intégrations.
                            </p>
                        </div>
                    </div>
                    {['general', 'ai', 'workflow'].includes(activeTab) && (
                        <button
                            onClick={handleSave}
                            className="inline-flex h-10 items-center justify-center gap-2 self-start rounded-lg bg-indigo-600 px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-indigo-500 xl:self-auto"
                        >
                            {isSaving ? <CheckCircle2 className="h-4 w-4 animate-pulse" /> : <Save className="h-4 w-4" />}
                            {isSaving ? 'Enregistré' : 'Enregistrer'}
                        </button>
                    )}
                </div>

                <nav className="mt-5 grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-6" aria-label="Sections des paramètres">
                    {tabs.map(tab => {
                        const Icon = tab.icon;
                        const isActive = activeTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                type="button"
                                onClick={() => setActiveTab(tab.id)}
                                aria-current={isActive ? 'page' : undefined}
                                className={`flex min-w-0 items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors ${
                                    isActive
                                        ? 'border-slate-900 bg-slate-900 text-white'
                                        : 'border-slate-200 bg-white text-slate-600 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700'
                                }`}
                            >
                                <Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-indigo-300' : 'text-slate-400'}`} />
                                <span className="min-w-0">
                                    <span className="block truncate text-sm font-black">{tab.label}</span>
                                    <span className={`mt-0.5 hidden truncate text-[11px] font-semibold 2xl:block ${isActive ? 'text-white/60' : 'text-slate-400'}`}>
                                        {tab.helper}
                                    </span>
                                </span>
                            </button>
                        );
                    })}
                </nav>
            </header>

            <main className="min-w-0 px-4 py-5 sm:px-6 xl:px-8">
                        
                        {/* 1. GENERAL SETTINGS */}
                        {activeTab === 'general' && (
                            <div className="space-y-8 animate-fade-in">
                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Identité Visuelle & Informations</h3>
                                    <div className="flex gap-8 mb-6">
                                        <div className="shrink-0 flex flex-col items-center gap-3">
                                            <div className="w-32 h-32 bg-slate-50 border-2 border-dashed border-slate-200 rounded-2xl flex items-center justify-center relative overflow-hidden group cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/30 transition-all">
                                                <div className="text-center group-hover:scale-105 transition-transform">
                                                    <Box className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                                                    <span className="text-[10px] font-bold text-slate-400 uppercase">Logo MMG</span>
                                                </div>
                                                <input type="file" accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer" />
                                            </div>
                                            <span className="text-xs font-bold text-slate-500">Format: PNG, JPG</span>
                                        </div>

                                        <div className="flex-1 grid grid-cols-2 gap-6">
                                            <div className="col-span-2">
                                                <label className="block text-xs font-bold text-slate-500 mb-2">Nom de l'Entreprise</label>
                                                <input type="text" defaultValue="MMG - Menuiserie Métallique" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 mb-2">SIRET</label>
                                                <input type="text" defaultValue="123 456 789 00012" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 mb-2">TVA Intracommunautaire</label>
                                                <input type="text" defaultValue="FR 12 345678901" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 mb-2">Email de Contact</label>
                                                <input type="email" defaultValue="contact@mmg-france.fr" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 mb-2">Téléphone</label>
                                                <input type="tel" defaultValue="+33 1 23 45 67 89" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                            <div className="col-span-2">
                                                <label className="block text-xs font-bold text-slate-500 mb-2">Adresse du Siège Social / Facturation</label>
                                                <input type="text" defaultValue="Zone Industrielle Ouest, 75000 Paris, France" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                            </div>
                                        </div>
                                    </div>
                                </section>

                                <div className="h-px bg-slate-100"></div>

                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Préférences Financières</h3>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Devise par défaut</label>
                                            <select className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500">
                                                <option>Euro (€)</option>
                                                <option>USD ($)</option>
                                                <option>FCFA (XAF)</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Taux de TVA par défaut (%)</label>
                                            <input type="number" defaultValue="20.0" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                    </div>
                                </section>

                                <div className="h-px bg-slate-100"></div>

                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Documents Légaux & Facturation</h3>
                                    <div className="grid grid-cols-1 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Pied de page des Factures (Mentions Légales)</label>
                                            <textarea 
                                                defaultValue="MMG - SARL au capital de 10 000 € - SIRET: 123 456 789 00012 - TVA: FR 12 345678901. Les factures sont payables à réception. Tout retard entraînera des pénalités." 
                                                className="w-full h-20 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Conditions Générales de Vente (CGV)</label>
                                            <textarea 
                                                placeholder="Saisissez ou collez les Conditions Générales de Vente qui s'appliqueront par défaut aux devis..." 
                                                className="w-full h-32 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                                            />
                                        </div>
                                    </div>
                                </section>
                            </div>
                        )}

                        {/* 2. AI & INTEGRATIONS */}
                        {activeTab === 'ai' && (
                            <div className="space-y-8 animate-fade-in">
                                <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4 flex items-start gap-4">
                                    <BrainCircuit className="w-6 h-6 text-indigo-600 shrink-0 mt-0.5" />
                                    <div>
                                        <h4 className="text-sm font-black text-indigo-900">Moteurs d'Intelligence Artificielle</h4>
                                        <p className="text-sm text-indigo-700/80 mt-1 font-medium">Configurez les clés API et les endpoints locaux pour alimenter le Copilote Commercial et l'Insight Engine.</p>
                                    </div>
                                </div>

                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">OpenAI (GPT-4)</h3>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 mb-2">Clé API (sk-...)</label>
                                        <input type="password" placeholder="sk-proj-xxxxxxxxxxxxxxx" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                    </div>
                                </section>

                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Ollama (Modèles Locaux / RAG)</h3>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Endpoint Serveur Ollama</label>
                                            <input type="text" defaultValue="http://localhost:11434" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Modèle par défaut</label>
                                            <select className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500">
                                                <option>mistral</option>
                                                <option>llama3</option>
                                                <option>llava</option>
                                            </select>
                                        </div>
                                    </div>
                                </section>

                                <div className="h-px bg-slate-100"></div>

                                <section>
                                    <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                                        <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest">WhatsApp WAHA</h3>
                                        <button
                                            type="button"
                                            onClick={loadWahaStatus}
                                            disabled={wahaLoading}
                                            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 transition-colors hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700 disabled:opacity-50"
                                        >
                                            <RefreshCw className={`h-4 w-4 ${wahaLoading ? 'animate-spin' : ''}`} />
                                            Actualiser
                                        </button>
                                    </div>

                                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1.15fr]">
                                        <div className="rounded-lg border border-slate-200 bg-white p-4">
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="flex min-w-0 items-start gap-3">
                                                    <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                                                        wahaStatus?.healthy
                                                            ? 'bg-emerald-100 text-emerald-700'
                                                            : wahaStatus?.configured
                                                                ? 'bg-amber-100 text-amber-700'
                                                                : 'bg-slate-100 text-slate-500'
                                                    }`}>
                                                        {wahaStatus?.healthy ? <MessageCircle className="h-5 w-5" /> : <WifiOff className="h-5 w-5" />}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-black text-slate-900">
                                                            {wahaStatus?.healthy
                                                                ? 'Session connectée'
                                                                : wahaStatus?.configured
                                                                    ? 'Session à surveiller'
                                                                    : 'WAHA non configuré'}
                                                        </p>
                                                        <p className="mt-1 truncate text-xs font-semibold text-slate-500">
                                                            {wahaStatus?.base_url || 'WAHA_BASE_URL absent'} · {wahaStatus?.session || 'session inconnue'}
                                                        </p>
                                                    </div>
                                                </div>
                                                <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-black uppercase ${
                                                    wahaStatus?.healthy
                                                        ? 'bg-emerald-100 text-emerald-700'
                                                        : wahaStatus?.configured
                                                            ? 'bg-amber-100 text-amber-700'
                                                            : 'bg-slate-100 text-slate-500'
                                                }`}>
                                                    {wahaStatus?.status || 'inconnu'}
                                                </span>
                                            </div>

                                            {wahaStatus?.detail && (
                                                <div className={`mt-4 flex items-start gap-2 rounded-lg px-3 py-2 text-xs font-bold ${
                                                    wahaStatus?.healthy ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'
                                                }`}>
                                                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                                                    <span className="min-w-0 break-words">{wahaStatus.detail}</span>
                                                </div>
                                            )}

                                            <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                                                <div className="rounded-lg bg-slate-50 p-3">
                                                    <p className="font-black uppercase text-slate-400">Dernier contrôle</p>
                                                    <p className="mt-1 font-bold text-slate-700">
                                                        {wahaStatus?.checked_at ? new Date(wahaStatus.checked_at).toLocaleString('fr-FR') : 'Jamais'}
                                                    </p>
                                                </div>
                                                <div className="rounded-lg bg-slate-50 p-3">
                                                    <p className="font-black uppercase text-slate-400">Transport actif</p>
                                                    <p className="mt-1 font-bold text-slate-700">{wahaStatus?.configured ? 'WAHA' : 'Fallback / log'}</p>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                                            <h4 className="mb-4 flex items-center gap-2 text-sm font-black text-slate-800">
                                                <Send className="h-4 w-4 text-emerald-600" />
                                                Message test
                                            </h4>
                                            <div className="grid grid-cols-1 gap-3 md:grid-cols-[0.9fr_1.3fr_auto]">
                                                <input
                                                    type="tel"
                                                    placeholder="33612345678"
                                                    value={wahaTest.recipient}
                                                    onChange={e => setWahaTest({ ...wahaTest, recipient: e.target.value })}
                                                    className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                                                />
                                                <input
                                                    type="text"
                                                    value={wahaTest.message}
                                                    onChange={e => setWahaTest({ ...wahaTest, message: e.target.value })}
                                                    className="h-11 rounded-lg border border-slate-200 bg-white px-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                                                />
                                                <button
                                                    type="button"
                                                    onClick={handleWahaTest}
                                                    disabled={wahaTestStatus.loading || !wahaTest.recipient || !wahaStatus?.configured}
                                                    className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 text-sm font-black text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
                                                >
                                                    <Send className="h-4 w-4" />
                                                    Envoyer
                                                </button>
                                            </div>
                                            {wahaTestStatus.message && (
                                                <div className={`mt-3 rounded-lg px-3 py-2 text-sm font-bold ${
                                                    wahaTestStatus.type === 'success'
                                                        ? 'bg-emerald-100 text-emerald-700'
                                                        : wahaTestStatus.type === 'error'
                                                            ? 'bg-red-100 text-red-700'
                                                            : 'bg-blue-100 text-blue-700'
                                                }`}>
                                                    {wahaTestStatus.message}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    <div className="mt-4 rounded-lg border border-slate-200 bg-white">
                                        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                                            <h4 className="flex items-center gap-2 text-sm font-black text-slate-800">
                                                <Activity className="h-4 w-4 text-slate-500" />
                                                Activité des flux WAHA
                                            </h4>
                                            <span className="text-xs font-bold text-slate-400">Polling 30 s</span>
                                        </div>
                                        <div className="max-h-64 overflow-y-auto">
                                            {(wahaStatus?.activity || []).length === 0 ? (
                                                <div className="px-4 py-6 text-sm font-semibold text-slate-400">Aucun événement WAHA capturé depuis le démarrage backend.</div>
                                            ) : (
                                                <div className="divide-y divide-slate-100">
                                                    {wahaStatus.activity.map((event, index) => (
                                                        <div key={`${event.at}-${index}`} className="grid grid-cols-[120px_90px_1fr] gap-3 px-4 py-3 text-xs">
                                                            <span className="font-bold text-slate-500">{new Date(event.at).toLocaleTimeString('fr-FR')}</span>
                                                            <span className={`font-black uppercase ${event.status === 'ok' ? 'text-emerald-700' : 'text-red-700'}`}>
                                                                {event.type}
                                                            </span>
                                                            <span className="min-w-0 break-words font-semibold text-slate-700">
                                                                {event.recipient ? `${event.recipient} · ` : ''}{event.detail}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </section>

                                <div className="h-px bg-slate-100"></div>

                                <section>
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">Serveur SMTP (Envoi d'Emails)</h3>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Hôte (Host)</label>
                                            <input type="text" placeholder="ex: smtp.gmail.com" value={smtpConfig.host} onChange={e => setSmtpConfig({...smtpConfig, host: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Port</label>
                                            <input type="text" placeholder="ex: 587 ou 465" value={smtpConfig.port} onChange={e => setSmtpConfig({...smtpConfig, port: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Nom d'utilisateur (Email)</label>
                                            <input type="text" placeholder="ex: contact@mmg.com" value={smtpConfig.username} onChange={e => setSmtpConfig({...smtpConfig, username: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Mot de passe / Clé d'application</label>
                                            <input type="password" placeholder="••••••••" value={smtpConfig.password} onChange={e => setSmtpConfig({...smtpConfig, password: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div className="md:col-span-2 mt-4 p-4 bg-slate-50 rounded-xl border border-slate-200">
                                            <h4 className="text-sm font-bold text-slate-700 mb-4">Tester la configuration</h4>
                                            <div className="flex items-end gap-4">
                                                <div className="flex-1">
                                                    <label className="block text-xs font-bold text-slate-500 mb-2">Email de destination pour le test</label>
                                                    <input type="email" placeholder="votre.email@test.com" value={smtpConfig.recipient} onChange={e => setSmtpConfig({...smtpConfig, recipient: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                                </div>
                                                <button 
                                                    onClick={handleSmtpTest} 
                                                    disabled={smtpTestStatus.loading || !smtpConfig.host || !smtpConfig.recipient}
                                                    className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 px-6 rounded-xl transition-all disabled:opacity-50"
                                                >
                                                    {smtpTestStatus.loading ? 'Envoi...' : 'Envoyer Email Test'}
                                                </button>
                                            </div>
                                            {smtpTestStatus.message && (
                                                <div className={`mt-4 p-3 rounded-lg text-sm font-bold ${smtpTestStatus.type === 'success' ? 'bg-green-100 text-green-700' : smtpTestStatus.type === 'error' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                                                    {smtpTestStatus.message}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </section>
                            </div>
                        )}

                        {/* 3. WORKFLOW & AUTOMATION */}
                        {activeTab === 'workflow' && (
                            <div className="animate-fade-in">
                                <BusinessRulesManager />
                            </div>
                        )}

                        {/* 4. STATIONS */}
                        {activeTab === 'stations' && (
                            <div className="animate-fade-in">
                                <StationManager />
                            </div>
                        )}

                        {/* 5. USERS & RBAC */}
                        {activeTab === 'users' && (
                            <div className="animate-fade-in">
                                <RBACMatrix />
                            </div>
                        )}

                        {/* 6. PIM */}
                        {activeTab === 'pim' && (
                            <div className="animate-fade-in">
                                <ConfigDashboard />
                            </div>
                        )}

            </main>
        </div>
    );
}
