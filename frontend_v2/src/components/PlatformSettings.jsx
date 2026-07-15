import React, { useState } from 'react';
import {
    Settings, Users, Network, BrainCircuit, Box, Shield,
    Building2, Database, Save, CheckCircle2
} from 'lucide-react';
import StationManager from './StationManager';
import OperatorManager from './OperatorManager';
import RBACMatrix from './RBACMatrix';
import BusinessRulesManager from './BusinessRulesManager';
import ConfigDashboard from '../pages/ConfigDashboard';

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

    const handleSmtpTest = async () => {
        setSmtpTestStatus({ loading: true, message: 'Test en cours...', type: 'info' });
        try {
            const res = await fetch('/api/v2/config/test-smtp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(smtpConfig)
            });
            const data = await res.json();
            if (res.ok) {
                setSmtpTestStatus({ loading: false, message: 'Succès: ' + data.message, type: 'success' });
            } else {
                setSmtpTestStatus({ loading: false, message: 'Erreur: ' + data.detail, type: 'error' });
            }
        } catch (e) {
            setSmtpTestStatus({ loading: false, message: 'Erreur réseau', type: 'error' });
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
        <div className="max-w-7xl mx-auto flex gap-8 animate-fade-in">
            {/* LEFT SIDEBAR MENU */}
            <div className="w-80 shrink-0 space-y-2">
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-200 mb-6">
                    <div className="flex items-center gap-3 mb-2">
                        <div className="w-10 h-10 bg-indigo-100 rounded-xl flex items-center justify-center text-indigo-600">
                            <Settings className="w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-lg font-black text-slate-800">Paramètres</h2>
                            <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Utilisateurs, atelier, référentiels</p>
                        </div>
                    </div>
                </div>

                <nav className="bg-white p-4 rounded-3xl shadow-sm border border-slate-200 space-y-1">
                    {tabs.map(tab => {
                        const Icon = tab.icon;
                        const isActive = activeTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`w-full flex items-start gap-3 px-4 py-3 rounded-2xl text-sm font-bold transition-all ${
                                    isActive 
                                    ? 'bg-indigo-50 text-indigo-700 shadow-sm' 
                                    : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                                }`}
                            >
                                <Icon className={`w-5 h-5 mt-0.5 ${isActive ? 'text-indigo-600' : 'text-slate-400'}`} />
                                <span className="text-left">
                                    <span className="block">{tab.label}</span>
                                    <span className="block text-[11px] leading-snug font-bold text-slate-400 mt-0.5">{tab.helper}</span>
                                </span>
                            </button>
                        );
                    })}
                </nav>
            </div>

            {/* MAIN CONTENT AREA */}
            <div className="flex-1">
                <div className="bg-white rounded-3xl shadow-sm border border-slate-200 min-h-[700px]">
                    {/* TOP BAR */}
                    <div className="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50 rounded-t-3xl">
                        <h2 className="text-xl font-black text-slate-800 flex items-center gap-2">
                            {tabs.find(t => t.id === activeTab)?.label}
                        </h2>
                        {['general', 'ai', 'workflow'].includes(activeTab) && (
                            <button 
                                onClick={handleSave}
                                className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold shadow-md shadow-indigo-500/20 flex items-center gap-2 transition-all active:scale-95"
                            >
                                {isSaving ? <CheckCircle2 className="w-4 h-4 animate-pulse" /> : <Save className="w-4 h-4" />}
                                {isSaving ? "Enregistré" : "Enregistrer"}
                            </button>
                        )}
                    </div>

                    {/* CONTENT BODY */}
                    <div className="p-8">
                        
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
                                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-4">WhatsApp Business API</h3>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Phone Number ID</label>
                                            <input type="text" placeholder="Ex: 1047583920" className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 mb-2">Access Token</label>
                                            <input type="password" placeholder="EAAL..." className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500" />
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
                            <div className="space-y-12 animate-fade-in">
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                    <div className="rounded-2xl border border-blue-100 bg-blue-50 p-5">
                                        <p className="text-[11px] font-black uppercase tracking-widest text-blue-500 mb-2">1. Comptes</p>
                                        <h3 className="font-black text-slate-900">Créer un utilisateur</h3>
                                        <p className="text-sm font-semibold text-slate-600 mt-1">Identifiant, PIN ou mot de passe, coordonnées.</p>
                                    </div>
                                    <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5">
                                        <p className="text-[11px] font-black uppercase tracking-widest text-amber-600 mb-2">2. Profil</p>
                                        <h3 className="font-black text-slate-900">Choisir un rôle métier</h3>
                                        <p className="text-sm font-semibold text-slate-600 mt-1">Opérateur, Débit, Qualité, Chef d'atelier, Manager.</p>
                                    </div>
                                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5">
                                        <p className="text-[11px] font-black uppercase tracking-widest text-emerald-600 mb-2">3. Stations</p>
                                        <h3 className="font-black text-slate-900">Affecter les postes</h3>
                                        <p className="text-sm font-semibold text-slate-600 mt-1">Le technicien ne voit que ses stations sur tablette atelier.</p>
                                    </div>
                                </div>
                                <OperatorManager />
                                <div className="border-t border-slate-100 pt-12">
                                    <div className="mb-6">
                                        <p className="text-[11px] font-black uppercase tracking-widest text-slate-400">Droits avancés</p>
                                        <h3 className="text-xl font-black text-slate-900">Matrice des profils et permissions</h3>
                                        <p className="text-sm font-semibold text-slate-500 mt-1">
                                            À modifier seulement si un profil métier doit voir ou exécuter une action spécifique.
                                        </p>
                                    </div>
                                    <RBACMatrix />
                                </div>
                            </div>
                        )}

                        {/* 6. PIM */}
                        {activeTab === 'pim' && (
                            <div className="animate-fade-in">
                                <ConfigDashboard />
                            </div>
                        )}

                    </div>
                </div>
            </div>
        </div>
    );
}
