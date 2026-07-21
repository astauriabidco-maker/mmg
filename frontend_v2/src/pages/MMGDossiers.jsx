import React, { useState, useEffect } from 'react';
import api, { API_BASE_URL } from '../services/api';
import {
    Search,
    FileText,
    ChevronRight,
    CheckCircle2,
    X,
    Calendar,
    User,
    Phone,
    Mail,
    MapPin,
    Maximize,
    ArrowRightCircle,
    Loader2,
    Plus,
    ChevronLeft,
    Camera,
    PenTool,
    AlertTriangle,
    ShieldAlert,
    Menu,
    Upload
} from 'lucide-react';
import Sidebar from '../components/Sidebar';
import { Link } from 'react-router-dom';

const MMGDossiers = ({ isEmbedded = false }) => {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [dossiers, setDossiers] = useState([]);
    const [clients, setClients] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedDossier, setSelectedDossier] = useState(null);
    const [importingId, setImportingId] = useState(null);
    const [activeTab, setActiveTab] = useState('tech'); // tech, sales, media
    const [sendingQuote, setSendingQuote] = useState(false);
    const [isNewClient, setIsNewClient] = useState(false);
    const [clientSearch, setClientSearch] = useState('');
    const [isSameAddress, setIsSameAddress] = useState(true);

    // Entry Form State
    const [isEntryFormOpen, setIsEntryFormOpen] = useState(false);
    const [formStep, setFormStep] = useState(1);
    const [formData, setFormData] = useState({
        client: {
            name: '',
            contact: '',
            address: '',
            site_address: '',
            email: '',
            client_type: 'PARTICULIER'
        },
        measurements: { width_mm: '', height_mm: '', passage_height_mm: '' },
        options: { sill_height_mm: '', transom_height_mm: '', shutter_type: 'gauche' },
        configuration: {
            view: 'interior',
            opening_type: 'tirant',
            opening_side: 'gauche',
            sash_count: 1,
            material: 'ALU',
            product_series: 'Standard',
            color_ral: '7016',
            is_bicolor: false,
            texture: 'Lisse',
            glazing_type: '4/16/4',
            installation_type: 'Neuf',
            hardware_type: 'Standard',
            is_pmr_compliant: false,
            doublage_thickness: '100',
            keep_existing_frame: false,
            ventilation: 'Aucune',
            shape: 'Rectangulaire',
            soubassement_type: 'Vitré'
        },
        logistics: {
            floor_number: 0,
            access_difficulty: 'Standard',
            environment: 'Standard'
        },
        annexes: {
            volet_roulant: 'Aucun',
            volet_battant: 'Aucun',
            moustiquaire: false,
            frais_pose: 'Aucun',
            livraison: false
        },
        photos: [],
        signature: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==" // Mock signature for agency
    });

    useEffect(() => {
        fetchDossiers();
        fetchClients();
    }, []);

    const fetchClients = async () => {
        try {
            const res = await api.get('/v2/partners/clients');
            setClients(res.data);
        } catch (err) {
            console.error("Error fetching clients", err);
        }
    };

    const fetchDossiers = async () => {
        try {
            const res = await api.get('/v2/mmg/');
            setDossiers(res.data);
        } catch (err) {
            console.error("Error fetching dossiers", err);
        } finally {
            setLoading(false);
        }
    };

    const handleImport = async (id) => {
        setImportingId(id);
        try {
            await api.patch(`/v2/mmg/${id}/status`, { status: 'VALIDATED' });
            fetchDossiers();
        } catch (err) {
            alert("Erreur lors de l'import");
        } finally {
            setImportingId(null);
        }
    };

    const handleFormSubmit = async () => {
        setLoading(true);
        try {
            // Normalise le payload vers le contrat MMGCreate du backend :
            // floats requis, '' -> null pour les optionnels (sinon 422).
            const toFloatOrNull = (v) => (v === '' || v === null || v === undefined ? null : Number(v));
            const payload = {
                ...formData,
                measurements: {
                    width_mm: Number(formData.measurements.width_mm) || 0,
                    height_mm: Number(formData.measurements.height_mm) || 0,
                    passage_height_mm: Number(formData.measurements.passage_height_mm) || 0,
                },
                options: {
                    sill_height_mm: toFloatOrNull(formData.options.sill_height_mm),
                    transom_height_mm: toFloatOrNull(formData.options.transom_height_mm),
                    shutter_type: formData.options.shutter_type || null,
                },
                photos: (formData.photos || []).filter(p => typeof p === 'string' && p.includes('base64,')),
            };
            await api.post('/v2/mmg/', payload);
            setIsEntryFormOpen(false);
            fetchDossiers();
            alert("Dossier créé avec succès !");
        } catch (err) {
            console.error("Error submitting form", err);
            alert("Erreur lors de la création du dossier");
        } finally {
            setLoading(false);
        }
    };

    const updateClient = (field, value) => {
        setFormData({ ...formData, client: { ...formData.client, [field]: value } });
    };

    const updateMeasurements = (field, value) => {
        setFormData({ ...formData, measurements: { ...formData.measurements, [field]: value } });
    };

    const updateOptions = (field, value) => {
        setFormData({ ...formData, options: { ...formData.options, [field]: value } });
    };

    const updateConfig = (field, value) => {
        let newConfig = { ...formData.configuration, [field]: value };

        // Material-Dependent Series Logic
        if (field === 'material') {
            if (value === 'ALU') newConfig.product_series = 'Standard';
            else if (value === 'PVC') newConfig.product_series = 'Classic';
            else if (value === 'BOIS') newConfig.product_series = 'Chêne';

            // PVC Color Restriction
            if (value === 'PVC' && !['9016', '1013', '7016'].includes(newConfig.color_ral)) {
                newConfig.color_ral = '9016'; // Default White for PVC
            }
        }

        setFormData({ ...formData, configuration: newConfig });
    };

    const updateAnnexes = (field, value) => {
        setFormData({ ...formData, annexes: { ...formData.annexes, [field]: value } });
    };

    const updateLogistics = (field, value) => {
        let newLogistics = { ...formData.logistics, [field]: value };

        // AEV Consistency: If coastal or high-rise, suggest Performance series
        if ((field === 'environment' && value === 'Bord de mer') || (field === 'floor_number' && value > 4)) {
            if (formData.configuration.product_series !== 'Performance') {
                // We don't force it here to avoid annoying user, but warnings will show
            }
        }

        setFormData({ ...formData, logistics: newLogistics });
    };

    const getIndustrialWarnings = () => {
        let warnings = [];
        const { configuration, measurements, options, logistics } = formData;

        // 1. Glazing Security
        if (options.sill_height_mm < 900) {
            warnings.push({
                type: 'security',
                msg: "Allège basse (< 900mm) : Vitrage de sécurité (44.2 ou trempé) recommandé.",
                target: 'glazing'
            });
        }

        // 2. AEV / Exposure
        if (logistics.environment === 'Bord de mer' || logistics.floor_number > 4) {
            if (configuration.product_series !== 'Performance') {
                warnings.push({
                    type: 'aev',
                    msg: "Exposition sévère (Bord de mer ou Étage > 4) : Gamme Performance fortement recommandée.",
                    target: 'series'
                });
            }
        }

        // 3. Dimensional Guardrails
        if (configuration.material === 'PVC' && measurements.width_mm > 1600) {
            warnings.push({
                type: 'dim',
                msg: "Dimensions PVC importantes (> 1600mm) : Renforts acier obligatoires.",
                target: 'dim'
            });
        }
        if (configuration.material === 'ALU' && measurements.width_mm > 2400) {
            warnings.push({
                type: 'dim',
                msg: "Format XXL ALU (> 2400mm) : Vérifier l'accessibilité pour vitrage monobloc.",
                target: 'dim'
            });
        }

        // 4. PMR Auto-check
        if (configuration.is_pmr_compliant && options.sill_height_mm > 20) {
            warnings.push({
                type: 'pmr',
                msg: "Conformité PMR : Le seuil ne doit pas dépasser 20mm.",
                target: 'sill'
            });
        }

        return warnings;
    };

    const viewDetails = async (id) => {
        try {
            const res = await api.get(`/v2/mmg/${id}`);
            setSelectedDossier(res.data);
            setActiveTab('tech'); // Reset to tech tab on view
        } catch (err) {
            alert("Erreur lors de l'récupération des détails");
        }
    };

    const handleSendQuote = async (id) => {
        setSendingQuote(true);
        try {
            await api.post(`/v2/mmg/${id}/send-quote`);
            alert("Devis envoyé au client avec succès !");
            fetchDossiers();
            viewDetails(id); // Refresh details
        } catch (err) {
            alert("Erreur lors de l'envoi du devis");
        } finally {
            setSendingQuote(false);
        }
    };

    if (loading) return (
        <div className="flex items-center justify-center min-h-screen bg-slate-50">
            <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
        </div>
    );

    return (
        <div className={`min-h-screen bg-slate-50 flex font-sans ${isEmbedded ? 'h-[calc(100vh-100px)] min-h-[0]' : ''}`}>
            {!isEmbedded && (
                <Sidebar
                    activeView={"mmg"}
                    isOpen={isSidebarOpen}
                    setIsOpen={setIsSidebarOpen}
                />
            )}
            <main className={`flex-1 transition-all duration-300 overflow-y-auto ${!isEmbedded ? 'lg:ml-72' : ''}`}>
                <div className={`${isEmbedded ? 'w-full p-6' : 'p-8 max-w-7xl mx-auto'}`}>
                    {!isEmbedded && (
                        <header className="mb-10 flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden p-2 bg-white border border-slate-200 rounded-lg text-slate-500">
                                    <Menu className="w-6 h-6" />
                                </button>
                                <div>
                                    <h1 className="text-4xl font-bold text-slate-900 tracking-tight">Métrés & Dossiers Techniques</h1>
                                    <p className="text-slate-500 mt-2">Gestion des relevés sur chantiers et spécifications de production</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <Link
                                    to="/upload"
                                    className="flex items-center gap-2 px-6 py-3 bg-white border-2 border-slate-200 text-slate-700 font-bold rounded-2xl hover:bg-slate-50 transition-all"
                                    title="Importer un fichier PDF de production (Dossier MMG)"
                                >
                                    <Upload className="w-5 h-5" />
                                    Dossier (PDF)
                                </Link>
                                <button
                                    onClick={() => {
                                        setIsEntryFormOpen(true);
                                        setFormStep(1);
                                    }}
                                    className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-500 shadow-lg shadow-blue-500/20 active:scale-95 transition-all"
                                >
                                    <Plus className="w-5 h-5" />
                                    Saisie Manuelle
                                </button>
                            </div>
                        </header>
                    )}
                    
                    {isEmbedded && (
                        <div className="mb-6 flex items-center justify-between">
                            <div>
                                <h2 className="text-2xl font-black text-slate-900">Dossiers Techniques</h2>
                                <p className="text-slate-500 text-sm">Convertissez vos prises de côtes en devis commerciaux.</p>
                            </div>
                            <button
                                onClick={() => {
                                    setIsEntryFormOpen(true);
                                    setFormStep(1);
                                }}
                                className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-500 shadow-lg shadow-blue-500/20 active:scale-95 transition-all"
                            >
                                <Plus className="w-5 h-5" />
                                Nouvelle Prise de Côte (Métré)
                            </button>
                        </div>
                    )}
                    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="text-slate-400 text-xs font-bold uppercase tracking-wider border-b border-slate-50 bg-slate-50/50">
                                <th className="py-4 px-6">Référence</th>
                                <th className="py-4 px-6">Client</th>
                                <th className="py-4 px-6">Date</th>
                                <th className="py-4 px-6">Statut</th>
                                <th className="py-4 px-6 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {dossiers.map((d) => (
                                <tr key={d.id} className="border-b border-slate-50 hover:bg-slate-50/30 transition-colors group">
                                    <td className="py-4 px-6 font-bold text-slate-700">{d.reference}</td>
                                    <td className="py-4 px-6">
                                        <div className="font-medium text-slate-900">{d.client_name}</div>
                                    </td>
                                    <td className="py-4 px-6 text-slate-500">
                                        <div className="flex items-center gap-2">
                                            <Calendar className="w-4 h-4" />
                                            {new Date(d.created_at).toLocaleDateString('fr-FR')}
                                        </div>
                                    </td>
                                    <td className="py-4 px-6">
                                        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${d.status === 'SENT'
                                            ? 'bg-blue-100 text-blue-700'
                                            : 'bg-emerald-100 text-emerald-700'
                                            }`}>
                                            <span className={`w-1.5 h-1.5 rounded-full ${d.status === 'SENT' ? 'bg-blue-500' : 'bg-emerald-500 animate-pulse'}`}></span>
                                            {d.status === 'SENT' ? 'REÇU' : 'VALIDÉ'}
                                        </span>
                                    </td>
                                    <td className="py-4 px-6 text-right">
                                        <div className="flex items-center justify-end gap-3">
                                            <button
                                                onClick={() => viewDetails(d.id)}
                                                className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                                                title="Voir Détails"
                                            >
                                                <Maximize className="w-5 h-5" />
                                            </button>
                                            <button
                                                onClick={() => handleImport(d.id)}
                                                disabled={d.status === 'VALIDATED' || importingId === d.id}
                                                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl font-bold transition-all ${d.status === 'VALIDATED'
                                                    ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                                    : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-500/20 active:scale-95'
                                                    }`}
                                            >
                                                {importingId === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRightCircle className="w-4 h-4" />}
                                                Importer
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {dossiers.length === 0 && (
                        <div className="py-20 text-center flex flex-col items-center gap-4">
                            <div className="p-4 bg-slate-50 rounded-full">
                                <FileText className="w-12 h-12 text-slate-300" />
                            </div>
                            <p className="text-slate-400 italic font-medium">Aucun dossier MMG reçu</p>
                        </div>
                    )}
                </div>
            </div>

            {/* DETAIL MODAL */}
            {selectedDossier && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-sm">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden relative">
                        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-600 rounded-xl text-white">
                                    <FileText className="w-6 h-6" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-slate-900">MMG {selectedDossier.reference}</h2>
                                    <p className="text-slate-500 text-sm">Détails du dossier technique</p>
                                </div>
                            </div>
                            <button
                                onClick={() => setSelectedDossier(null)}
                                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition-colors"
                            >
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        <div className="p-8 max-h-[70vh] overflow-y-auto">
                            {/* Tabs Navigation */}
                            <div className="flex gap-1 bg-slate-100 p-1 rounded-2xl mb-8">
                                {[
                                    { id: 'tech', label: 'Technique', icon: PenTool },
                                    { id: 'sales', label: 'Options Devis', icon: ArrowRightCircle },
                                    { id: 'media', label: 'Photos & Signature', icon: Camera }
                                ].map(tab => (
                                    <button
                                        key={tab.id}
                                        onClick={() => setActiveTab(tab.id)}
                                        className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-bold transition-all ${activeTab === tab.id ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                                    >
                                        <tab.icon className="w-4 h-4" />
                                        {tab.label}
                                    </button>
                                ))}
                            </div>

                            {activeTab === 'tech' && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                    {/* Section Client */}
                                    <div className="space-y-4">
                                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                            <User className="w-4 h-4" /> Information Client
                                        </h3>
                                        <div className="bg-slate-50 p-6 rounded-3xl space-y-3">
                                            <div className="flex justify-between items-start">
                                                <p className="font-bold text-slate-800 text-lg uppercase">{selectedDossier.client_name}</p>
                                                <span className="text-[10px] bg-slate-200 text-slate-600 px-2 py-1 rounded-md font-black">{selectedDossier.client_type}</span>
                                            </div>
                                            <div className="space-y-2">
                                                <p className="text-slate-600 flex items-center gap-2 text-sm"><Phone className="w-4 h-4 text-slate-400" /> {selectedDossier.client_contact}</p>
                                                <p className="text-slate-600 flex items-center gap-2 text-sm"><Mail className="w-4 h-4 text-slate-400" /> {selectedDossier.client_email}</p>
                                                <p className="text-slate-600 flex items-center gap-2 text-sm"><MapPin className="w-4 h-4 text-slate-400" /> {selectedDossier.client_address}</p>
                                                {selectedDossier.site_address && (
                                                    <p className="text-blue-600 flex items-center gap-2 text-sm font-medium pt-1 border-t border-blue-50">
                                                        <MapPin className="w-4 h-4 text-blue-400 shrink-0" /> Chantier : {selectedDossier.site_address}
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Dimensions & Config */}
                                    <div className="space-y-4">
                                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                            <Maximize className="w-4 h-4" /> Mesures & Ouverture
                                        </h3>
                                        <div className="bg-slate-900 rounded-3xl p-6 text-white">
                                            <div className="grid grid-cols-2 gap-6 mb-6">
                                                <div className="bg-white/5 p-4 rounded-2xl border border-white/10">
                                                    <p className="text-[10px] text-slate-400 uppercase font-bold mb-1">Largeur L</p>
                                                    <p className="text-2xl font-black text-blue-400">{selectedDossier.width} mm</p>
                                                </div>
                                                <div className="bg-white/5 p-4 rounded-2xl border border-white/10">
                                                    <p className="text-[10px] text-slate-400 uppercase font-bold mb-1">Hauteur H</p>
                                                    <p className="text-2xl font-black text-indigo-400">{selectedDossier.height} mm</p>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-3 gap-2">
                                                <div className="text-center bg-white/5 py-3 rounded-xl">
                                                    <p className="text-[8px] text-slate-500 uppercase font-bold">Type</p>
                                                    <p className="text-xs font-bold capitalize">{selectedDossier.opening_type}</p>
                                                </div>
                                                <div className="text-center bg-white/5 py-3 rounded-xl">
                                                    <p className="text-[8px] text-slate-500 uppercase font-bold">Vantaux</p>
                                                    <p className="text-xs font-bold">{selectedDossier.sash_count}</p>
                                                </div>
                                                <div className="text-center bg-white/5 py-3 rounded-xl">
                                                    <p className="text-[8px] text-slate-500 uppercase font-bold">Vue</p>
                                                    <p className="text-xs font-bold capitalize">{selectedDossier.view_type}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Choix Techniques */}
                                    <div className="md:col-span-2 space-y-4">
                                        <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest">Spécifications de Fabrication</h3>
                                        <div className="grid grid-cols-4 gap-4">
                                            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Matériau</p>
                                                <p className="font-black text-slate-700">{selectedDossier.material || 'ALU'}</p>
                                            </div>
                                            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Pose</p>
                                                <p className="font-black text-slate-700">
                                                    {selectedDossier.installation_type || 'Neuf'}
                                                    {selectedDossier.installation_type === 'Neuf' ? ` (${selectedDossier.doublage_thickness}mm)` : ''}
                                                    {selectedDossier.installation_type === 'Reno' && selectedDossier.keep_existing_frame ? ' (Dormant conservé)' : ''}
                                                </p>
                                            </div>
                                            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">RAL</p>
                                                <p className="font-black text-slate-700">{selectedDossier.color_ral || '7016'}</p>
                                            </div>
                                            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Vitrage</p>
                                                <p className="font-black text-slate-700">{selectedDossier.glazing_type || '4/16/4'}</p>
                                            </div>
                                        </div>

                                        {/* Technical Alerts for Engineers */}
                                        {(selectedDossier.sill_height < 900 || selectedDossier.environment === 'Bord de mer' || (selectedDossier.material === 'PVC' && selectedDossier.width > 1600)) && (
                                            <div className="bg-rose-50 border border-rose-100 p-4 rounded-2xl space-y-2 mt-4">
                                                <p className="text-[10px] font-bold text-rose-500 uppercase tracking-widest">Points d'Attention Technique</p>
                                                {selectedDossier.sill_height < 900 && (
                                                    <p className="text-xs font-bold text-rose-700 flex items-center gap-2">
                                                        <ShieldAlert className="w-4 h-4" /> Sécurité : Allège basse ({selectedDossier.sill_height}mm) - Vérifier vitrage 44.2
                                                    </p>
                                                )}
                                                {selectedDossier.environment === 'Bord de mer' && selectedDossier.product_series !== 'Performance' && (
                                                    <p className="text-xs font-bold text-rose-700 flex items-center gap-2">
                                                        <AlertTriangle className="w-4 h-4" /> AEV : Exposition maritime avec gamme {selectedDossier.product_series}
                                                    </p>
                                                )}
                                                {selectedDossier.material === 'PVC' && selectedDossier.width > 1600 && (
                                                    <p className="text-xs font-bold text-rose-700 flex items-center gap-2">
                                                        <Maximize className="w-4 h-4" /> Structure : Largeur PVC ({selectedDossier.width}mm) - Renforts obligatoires
                                                    </p>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {activeTab === 'sales' && (
                                <div className="space-y-6">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                        <div className="bg-blue-50 border border-blue-100 p-6 rounded-3xl space-y-4">
                                            <h4 className="font-bold text-blue-800 flex items-center gap-2">
                                                <CheckCircle2 className="w-5 h-5" /> Config Commerciale
                                            </h4>
                                            <div className="space-y-3">
                                                <div className="flex justify-between border-b border-blue-100 pb-2">
                                                    <span className="text-sm text-blue-600">Gamme Produit :</span>
                                                    <span className="font-bold text-blue-900">{selectedDossier.product_series || 'Standard'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-blue-100 pb-2">
                                                    <span className="text-sm text-blue-600">Texture :</span>
                                                    <span className="font-bold text-blue-900">{selectedDossier.texture || 'Lisse'} {selectedDossier.is_bicolor ? '(Bicolore)' : ''}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-blue-100 pb-2">
                                                    <span className="text-sm text-blue-600">Quincaillerie :</span>
                                                    <span className="font-bold text-blue-900">{selectedDossier.hardware_type || 'Standard'}</span>
                                                </div>
                                                <div className="flex justify-between">
                                                    <span className="text-sm text-blue-600">Acces. PMR :</span>
                                                    <span className={`font-bold ${selectedDossier.is_pmr_compliant ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                        {selectedDossier.is_pmr_compliant ? 'OUI (Seuil Plat)' : 'NON'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="bg-orange-50 border border-orange-100 p-6 rounded-3xl space-y-4">
                                            <h4 className="font-bold text-orange-800 flex items-center gap-2">
                                                <MapPin className="w-5 h-5" /> Logistique Chantier
                                            </h4>
                                            <div className="space-y-3">
                                                <div className="flex justify-between border-b border-orange-100 pb-2">
                                                    <span className="text-sm text-orange-600">Étage :</span>
                                                    <span className="font-bold text-orange-900">{selectedDossier.floor_number || 0}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-orange-100 pb-2">
                                                    <span className="text-sm text-orange-600">Difficulté :</span>
                                                    <span className="font-bold text-orange-900">{selectedDossier.access_difficulty || 'Standard'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-orange-100 pb-2">
                                                    <span className="text-sm text-orange-600">Environnement :</span>
                                                    <span className="font-bold text-orange-900">{selectedDossier.environment || 'Standard'}</span>
                                                </div>
                                                <div className="flex justify-between pt-2">
                                                    <span className="text-sm text-orange-600">Soubassement :</span>
                                                    <span className="font-bold text-orange-900">{selectedDossier.sill_height || 0} mm</span>
                                                </div>
                                                <div className="flex justify-between">
                                                    <span className="text-sm text-orange-600">Imposte :</span>
                                                    <span className="font-bold text-orange-900">{selectedDossier.transom_height || 0} mm</span>
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Configuration fine persistée (plus-values du devis) */}
                                    {selectedDossier.configuration && (
                                        <div className="bg-violet-50 border border-violet-100 p-6 rounded-3xl space-y-4">
                                            <h4 className="font-bold text-violet-800 flex items-center gap-2">
                                                <PenTool className="w-5 h-5" /> Options & Plus-values (configurateur)
                                            </h4>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Forme :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.shape || 'Rectangulaire'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Ventilation :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.ventilation || 'Aucune'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Soubassement :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.soubassement_type || 'Vitré'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Volet Roulant :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.annexes?.volet_roulant || 'Aucun'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Volet Battant :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.annexes?.volet_battant || 'Aucun'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Prestation de Pose :</span>
                                                    <span className="font-bold text-violet-900">{selectedDossier.configuration.annexes?.frais_pose || 'Aucun'}</span>
                                                </div>
                                                <div className="flex justify-between border-b border-violet-100 pb-2">
                                                    <span className="text-sm text-violet-600">Moustiquaire :</span>
                                                    <span className={`font-bold ${selectedDossier.configuration.annexes?.moustiquaire ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                        {selectedDossier.configuration.annexes?.moustiquaire ? 'OUI' : 'NON'}
                                                    </span>
                                                </div>
                                                <div className="flex justify-between pb-2">
                                                    <span className="text-sm text-violet-600">Livraison Chantier :</span>
                                                    <span className={`font-bold ${selectedDossier.configuration.annexes?.livraison ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                        {selectedDossier.configuration.annexes?.livraison ? 'OUI' : 'NON'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <div className="bg-slate-900 p-8 rounded-3xl text-center space-y-4">
                                        <p className="text-slate-400 text-sm">Prêt pour l'envoi au client ? Tous les champs commerciaux sont renseignés.</p>
                                        <button
                                            onClick={() => handleSendQuote(selectedDossier.id)}
                                            disabled={sendingQuote}
                                            className="w-full py-4 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-2xl shadow-xl shadow-blue-500/20 transition-all active:scale-95 flex items-center justify-center gap-3"
                                        >
                                            {sendingQuote ? <Loader2 className="w-6 h-6 animate-spin" /> : <Mail className="w-6 h-6" />}
                                            Générer & Envoyer le Devis au Client
                                        </button>
                                        {selectedDossier.quote_sent_at && (
                                            <p className="text-emerald-400 text-xs font-bold">
                                                Dernier devis envoyé le {new Date(selectedDossier.quote_sent_at).toLocaleString('fr-FR')}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            )}

                            {activeTab === 'media' && (
                                <div className="space-y-6">
                                    <div className="grid grid-cols-2 gap-4">
                                        {(selectedDossier.photos || []).map((p, idx) => (
                                            <div key={idx} className="aspect-video bg-slate-100 rounded-2xl overflow-hidden border border-slate-200">
                                                <img src={`${API_BASE_URL}${p}`} alt="Photo Chantier" className="w-full h-full object-cover" />
                                            </div>
                                        ))}
                                    </div>
                                    <div className="p-6 bg-slate-50 rounded-3xl border border-slate-100">
                                        <p className="text-[10px] text-slate-400 font-bold uppercase mb-4">Signature Client</p>
                                        {selectedDossier.signature ? (
                                            <img src={`${API_BASE_URL}${selectedDossier.signature}`} alt="Signature" className="max-h-32 mx-auto" />
                                        ) : (
                                            <p className="text-slate-400 italic text-center">Aucune signature</p>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                        <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-3">
                            <button
                                onClick={() => setSelectedDossier(null)}
                                className="px-6 py-3 bg-white border border-slate-200 text-slate-600 font-bold rounded-2xl hover:bg-slate-50 transition-all active:scale-95"
                            >
                                Fermer
                            </button>
                            <button
                                onClick={() => {
                                    handleImport(selectedDossier.id);
                                    setSelectedDossier(null);
                                }}
                                disabled={selectedDossier.status === 'VALIDATED'}
                                className={`px-8 py-3 rounded-2xl font-bold transition-all shadow-lg active:scale-95 ${selectedDossier.status === 'VALIDATED'
                                    ? 'bg-slate-300 text-white cursor-not-allowed shadow-none'
                                    : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-500/20'
                                    }`}
                            >
                                Valider et Importer dans Proges
                            </button>
                        </div>
                    </div>
                </div>
            )}
            {/* NEW DOSSIER MODAL (Agency Entry) */}
            {isEntryFormOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-sm">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden relative flex flex-col max-h-[90vh]">
                        {/* Header */}
                        <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-600 rounded-xl text-white">
                                    <Plus className="w-6 h-6" />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-slate-900">Nouveau Métré (Prise de Côte)</h2>
                                    <p className="text-slate-500 text-sm">Étape {formStep} sur 6</p>
                                </div>
                            </div>
                            <button onClick={() => setIsEntryFormOpen(false)} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        {/* Form Content */}
                        <div className="p-8 overflow-y-auto flex-1 text-slate-900">
                            {formStep === 1 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-blue-600 font-bold mb-4">
                                        <User className="w-5 h-5" />
                                        <h3>Information Client</h3>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="md:col-span-2 relative z-50">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Rechercher un client</label>
                                            <div className="relative">
                                                <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                                <input 
                                                    type="text"
                                                    className="w-full pl-12 pr-4 py-4 bg-slate-50 border-0 rounded-2xl focus:ring-2 focus:ring-blue-500 transition-all font-bold text-slate-900 shadow-inner"
                                                    placeholder="Tapez un nom ou téléphone..."
                                                    value={clientSearch}
                                                    onChange={(e) => {
                                                        setClientSearch(e.target.value);
                                                        setIsNewClient(false);
                                                        if (formData.client.name) {
                                                            setFormData({...formData, client: {...formData.client, name: ''}});
                                                        }
                                                    }}
                                                />
                                            </div>

                                            {/* Dropdown Suggestions */}
                                            {clientSearch && !formData.client.name && !isNewClient && (
                                                <div className="absolute top-full mt-2 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">
                                                    {clients.filter(c => c.name.toLowerCase().includes(clientSearch.toLowerCase()) || (c.phone && c.phone.includes(clientSearch))).map(c => (
                                                        <button 
                                                            key={c.id} 
                                                            className="w-full text-left px-6 py-4 hover:bg-slate-50 border-b border-slate-100 last:border-0 transition-colors flex items-center justify-between"
                                                            onClick={() => {
                                                                setFormData({
                                                                    ...formData, 
                                                                    client: { 
                                                                        name: c.name,
                                                                        contact: c.phone || '',
                                                                        email: c.email || '',
                                                                        address: c.address || '',
                                                                        site_address: c.address || '',
                                                                        client_type: c.client_type || 'PARTICULIER'
                                                                    }
                                                                });
                                                                setClientSearch('');
                                                                setIsSameAddress(true);
                                                            }}
                                                        >
                                                            <div>
                                                                <p className="font-bold text-slate-900">{c.name}</p>
                                                                <p className="text-xs text-slate-500">{c.phone} • {c.email}</p>
                                                            </div>
                                                            <ChevronRight className="w-4 h-4 text-slate-300" />
                                                        </button>
                                                    ))}
                                                    <button 
                                                        className="w-full text-left px-6 py-4 bg-blue-50 hover:bg-blue-100 text-blue-700 font-bold transition-colors flex items-center gap-2"
                                                        onClick={() => {
                                                            setIsNewClient(true);
                                                            updateClient('name', clientSearch);
                                                            setClientSearch('');
                                                        }}
                                                    >
                                                        <Plus className="w-5 h-5"/> Créer le nouveau client "{clientSearch}"
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        {/* Fiche Résumé Client Existant */}
                                        {!isNewClient && formData.client.name && (
                                            <div className="md:col-span-2 bg-gradient-to-r from-blue-50 to-indigo-50/30 p-6 rounded-2xl border border-blue-100 flex items-center justify-between shadow-sm relative overflow-hidden group">
                                                <div className="absolute top-0 right-0 p-4 opacity-10 scale-150 transform translate-x-4 -translate-y-4">
                                                    <User className="w-24 h-24 text-blue-600"/>
                                                </div>
                                                <div className="relative z-10">
                                                    <div className="flex items-center gap-3 mb-1">
                                                        <h4 className="font-black text-xl text-blue-900">{formData.client.name}</h4>
                                                        <span className="text-[10px] font-black text-blue-600 bg-blue-200/50 px-2 py-1 rounded-md uppercase tracking-widest">{formData.client.client_type}</span>
                                                    </div>
                                                    <div className="flex items-center gap-4 text-sm font-medium text-blue-700/80">
                                                        <span className="flex items-center gap-1"><Phone className="w-4 h-4"/> {formData.client.contact}</span>
                                                        <span className="flex items-center gap-1"><Mail className="w-4 h-4"/> {formData.client.email}</span>
                                                    </div>
                                                </div>
                                                <button onClick={() => {
                                                    setFormData({...formData, client: {...formData.client, name: ''}});
                                                    setIsNewClient(false);
                                                }} className="relative z-10 bg-white/50 hover:bg-white text-blue-600 p-2 rounded-xl transition-all shadow-sm">
                                                    <X className="w-5 h-5"/>
                                                </button>
                                            </div>
                                        )}

                                        {/* Formulaire Nouveau Client */}
                                        {isNewClient && (
                                            <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-50 p-6 rounded-3xl border border-slate-100">
                                                <div className="md:col-span-2 flex items-center justify-between mb-2">
                                                    <h4 className="font-black text-slate-800">Création Fiche Client</h4>
                                                    <button onClick={() => setIsNewClient(false)} className="text-xs font-bold text-slate-400 hover:text-slate-600 flex items-center gap-1">
                                                        <X className="w-4 h-4"/> Annuler
                                                    </button>
                                                </div>
                                                
                                                <div className="md:col-span-2">
                                                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Type de Client</label>
                                                    <div className="flex gap-2">
                                                        {['PARTICULIER', 'PRO'].map(t => (
                                                            <button
                                                                key={t}
                                                                onClick={() => updateClient('client_type', t)}
                                                                className={`flex-1 p-3 rounded-xl font-black transition-all ${formData.client.client_type === t ? 'bg-slate-900 text-white shadow-md' : 'bg-white text-slate-400 border border-slate-200'}`}
                                                            >
                                                                {t}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>

                                                <div className="md:col-span-2">
                                                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Nom / Raison Sociale</label>
                                                    <input
                                                        type="text"
                                                        className="w-full p-4 bg-white border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 font-bold text-slate-900 shadow-sm"
                                                        value={formData.client.name}
                                                        onChange={(e) => updateClient('name', e.target.value)}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Téléphone</label>
                                                    <input
                                                        type="text"
                                                        className="w-full p-4 bg-white border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 font-bold text-slate-900 shadow-sm"
                                                        value={formData.client.contact}
                                                        onChange={(e) => updateClient('contact', e.target.value)}
                                                    />
                                                </div>
                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Email</label>
                                                    <input
                                                        type="email"
                                                        className="w-full p-4 bg-white border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 font-bold text-slate-900 shadow-sm"
                                                        value={formData.client.email}
                                                        onChange={(e) => updateClient('email', e.target.value)}
                                                    />
                                                </div>
                                                <div className="md:col-span-2">
                                                    <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Adresse de Facturation</label>
                                                    <input
                                                        type="text"
                                                        className="w-full p-4 bg-white border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 font-bold text-slate-900 shadow-sm"
                                                        value={formData.client.address}
                                                        onChange={(e) => {
                                                            updateClient('address', e.target.value);
                                                            if (isSameAddress) updateClient('site_address', e.target.value);
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        )}

                                        {/* Adresse du Chantier */}
                                        {(formData.client.name) && (
                                            <div className="md:col-span-2 mt-4 space-y-4">
                                                <label className="flex items-center gap-3 cursor-pointer group">
                                                    <div className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center transition-all ${isSameAddress ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 bg-white'}`}>
                                                        {isSameAddress && <CheckCircle2 className="w-4 h-4" />}
                                                    </div>
                                                    <span className="font-bold text-slate-700 group-hover:text-slate-900">L'adresse du chantier est identique à l'adresse de facturation</span>
                                                    <input 
                                                        type="checkbox" 
                                                        className="hidden"
                                                        checked={isSameAddress}
                                                        onChange={(e) => {
                                                            setIsSameAddress(e.target.checked);
                                                            if (e.target.checked) updateClient('site_address', formData.client.address);
                                                            else updateClient('site_address', '');
                                                        }}
                                                    />
                                                </label>

                                                {!isSameAddress && (
                                                    <div className="animate-in slide-in-from-top-4 fade-in duration-300">
                                                        <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2 text-blue-600">Adresse Spécifique du Chantier</label>
                                                        <div className="relative">
                                                            <MapPin className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-blue-400" />
                                                            <input
                                                                type="text"
                                                                className="w-full pl-12 pr-4 py-4 bg-blue-50/50 border border-blue-100 rounded-2xl focus:ring-2 focus:ring-blue-500 transition-all font-bold text-blue-900 shadow-inner"
                                                                value={formData.client.site_address}
                                                                onChange={(e) => updateClient('site_address', e.target.value)}
                                                                placeholder="Lieu exact de la pose ..."
                                                            />
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {formStep === 2 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-blue-600 font-bold mb-4">
                                        <CheckCircle2 className="w-5 h-5" />
                                        <h3>Choix Techniques</h3>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Matériau</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.configuration.material}
                                                onChange={(e) => updateConfig('material', e.target.value)}
                                            >
                                                <option value="ALU">ALU - Aluminium</option>
                                                <option value="PVC">PVC - Polychlorure</option>
                                                <option value="ACIER">ACIER</option>
                                                <option value="BOIS">BOIS</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">
                                                {formData.configuration.material === 'BOIS' ? 'Essence de Bois' : 'Gamme / Série'}
                                            </label>
                                            <select
                                                className="w-full p-4 bg-blue-50 border-0 rounded-2xl font-bold text-blue-700"
                                                value={formData.configuration.product_series}
                                                onChange={(e) => updateConfig('product_series', e.target.value)}
                                            >
                                                {formData.configuration.material === 'ALU' && (
                                                    <>
                                                        <option value="Standard">Standard (Classique)</option>
                                                        <option value="Premium">Premium (Minimalist)</option>
                                                        <option value="Performance">Performance (RT2025)</option>
                                                    </>
                                                )}
                                                {formData.configuration.material === 'PVC' && (
                                                    <>
                                                        <option value="Classic">Classic (Eco)</option>
                                                        <option value="Comfort">Comfort (Renforcé)</option>
                                                        <option value="High-Tech">High-Tech (82mm)</option>
                                                    </>
                                                )}
                                                {formData.configuration.material === 'BOIS' && (
                                                    <>
                                                        <option value="Chêne">Chêne</option>
                                                        <option value="Sapin">Sapin</option>
                                                        <option value="Moabi">Moabi exotique</option>
                                                    </>
                                                )}
                                                {!['ALU', 'PVC', 'BOIS'].includes(formData.configuration.material) && (
                                                    <option value="Standard">Standard</option>
                                                )}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Type de Pose</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.configuration.installation_type}
                                                onChange={(e) => updateConfig('installation_type', e.target.value)}
                                            >
                                                <option value="Neuf">Pose à Neuf (Applique)</option>
                                                <option value="Reno">Rénovation (Dépose totale)</option>
                                                <option value="Tunnel">Tunnel (Tuner)</option>
                                                <option value="Feuillure">En Feuillure</option>
                                            </select>
                                        </div>
                                        {formData.configuration.installation_type === 'Neuf' && (
                                            <div>
                                                <label className="block text-xs font-bold text-indigo-600 uppercase mb-1">Épaisseur Doublage (mm)</label>
                                                <select
                                                    className="w-full p-4 bg-indigo-50 border-0 rounded-2xl font-bold text-indigo-700"
                                                    value={formData.configuration.doublage_thickness || '100'}
                                                    onChange={(e) => updateConfig('doublage_thickness', e.target.value)}
                                                >
                                                    <option value="70">70 mm</option>
                                                    <option value="100">100 mm (Standard)</option>
                                                    <option value="120">120 mm</option>
                                                    <option value="140">140 mm</option>
                                                    <option value="160">160 mm</option>
                                                </select>
                                            </div>
                                        )}
                                        {formData.configuration.installation_type === 'Reno' && (
                                            <div className="flex items-center gap-3 p-4 bg-orange-50 rounded-2xl border border-orange-100">
                                                <input
                                                    type="checkbox"
                                                    className="w-5 h-5 accent-orange-600"
                                                    checked={formData.configuration.keep_existing_frame || false}
                                                    onChange={(e) => updateConfig('keep_existing_frame', e.target.checked)}
                                                />
                                                <span className="text-xs font-bold text-orange-800 uppercase">Conservation dormant existant ?</span>
                                            </div>
                                        )}
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Couleur (RAL)</label>
                                            <div className="flex gap-2">
                                                <input
                                                    type="text"
                                                    className="flex-1 p-4 bg-slate-50 border-0 rounded-2xl focus:ring-2 focus:ring-blue-500 font-bold text-slate-700"
                                                    value={formData.configuration.color_ral}
                                                    onChange={(e) => updateConfig('color_ral', e.target.value)}
                                                    placeholder="7016"
                                                />
                                                <button
                                                    onClick={() => updateConfig('is_bicolor', !formData.configuration.is_bicolor)}
                                                    className={`px-4 rounded-2xl font-bold transition-all ${formData.configuration.is_bicolor ? 'bg-orange-100 text-orange-600' : 'bg-slate-100 text-slate-400'}`}
                                                >
                                                    Bicolore
                                                </button>
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Texture Finition</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.configuration.texture}
                                                onChange={(e) => updateConfig('texture', e.target.value)}
                                            >
                                                <option value="Lisse">Lisse (Satiné/Brillant)</option>
                                                <option value="Grainé">Grainé (Texturé)</option>
                                                <option value="Sablé">Sablé (Mat/Fin)</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Quincaillerie (Hardware)</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.configuration.hardware_type}
                                                onChange={(e) => updateConfig('hardware_type', e.target.value)}
                                            >
                                                <option value="Standard">Standard</option>
                                                <option value="Security">Sécurité (RC2/3)</option>
                                                <option value="Design">Design (Invisibles)</option>
                                            </select>
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Options Complémentaires</label>
                                            <div className="flex gap-4">
                                                <label className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl flex-1 cursor-pointer">
                                                    <input
                                                        type="checkbox"
                                                        checked={formData.configuration.is_pmr_compliant}
                                                        onChange={(e) => updateConfig('is_pmr_compliant', e.target.checked)}
                                                        className="w-5 h-5 accent-blue-600"
                                                    />
                                                    <span className="font-bold text-slate-700 tracking-tight">Accessibilité PMR (Seuil plat)</span>
                                                </label>
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Grille de Ventilation</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.configuration.ventilation}
                                                onChange={(e) => updateConfig('ventilation', e.target.value)}
                                            >
                                                <option value="Aucune">Aucune (Non ventilé)</option>
                                                <option value="Standard">Aérateur Standard (30m³/h)</option>
                                                <option value="Acoustique">Aérateur Acoustique (Renforcé)</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {formStep === 3 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-slate-900 font-bold mb-4">
                                        <PenTool className="w-5 h-5" />
                                        <h3>Configuration Ouverture</h3>
                                    </div>
                                    <div className="grid grid-cols-1 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Type d'Ouverture</label>
                                            <div className="flex gap-2">
                                                {['tirant', 'poussant'].map(type => (
                                                    <button
                                                        key={type}
                                                        onClick={() => updateConfig('opening_type', type)}
                                                        className={`flex-1 p-4 rounded-2xl font-bold capitalize transition-all ${formData.configuration.opening_type === type ? 'bg-slate-900 text-white shadow-xl' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                                                            }`}
                                                    >
                                                        {type}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Côté</label>
                                                <select
                                                    className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                    value={formData.configuration.opening_side}
                                                    onChange={(e) => updateConfig('opening_side', e.target.value)}
                                                >
                                                    <option value="gauche">Gauche</option>
                                                    <option value="droite">Droite</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Vantaux</label>
                                                <select
                                                    className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                    value={formData.configuration.sash_count}
                                                    onChange={(e) => updateConfig('sash_count', parseInt(e.target.value))}
                                                >
                                                    <option value={1}>1</option>
                                                    <option value={2}>2</option>
                                                    <option value={3}>3</option>
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {formStep === 4 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-indigo-600 font-bold mb-4">
                                        <Maximize className="w-5 h-5" />
                                        <h3>Prise de Mesures (mm)</h3>
                                    </div>
                                    <div className="grid grid-cols-2 gap-6">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Largeur L</label>
                                            <input
                                                type="number"
                                                className="w-full p-6 text-2xl font-black bg-blue-50 border-0 rounded-3xl focus:ring-2 focus:ring-blue-500 text-blue-900"
                                                value={formData.measurements.width_mm}
                                                onChange={(e) => updateMeasurements('width_mm', parseFloat(e.target.value) || 0)}
                                                placeholder="1200"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Hauteur H</label>
                                            <input
                                                type="number"
                                                className="w-full p-6 text-2xl font-black bg-indigo-50 border-0 rounded-3xl focus:ring-2 focus:ring-indigo-500 text-indigo-900"
                                                value={formData.measurements.height_mm}
                                                onChange={(e) => updateMeasurements('height_mm', parseFloat(e.target.value) || 0)}
                                                placeholder="2150"
                                            />
                                        </div>
                                        {getIndustrialWarnings().filter(w => w.target === 'dim').map((w, i) => (
                                            <div key={i} className="col-span-2 flex items-center gap-3 p-4 bg-amber-50 rounded-2xl border border-amber-100 text-amber-800 text-xs font-bold animate-pulse">
                                                <AlertTriangle className="w-5 h-5 shrink-0" />
                                                {w.msg}
                                            </div>
                                        ))}
                                        <div className="col-span-2">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Hauteur de passage HP</label>
                                            <input
                                                type="number"
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl focus:ring-2 focus:ring-slate-500 font-bold text-lg text-slate-900"
                                                value={formData.measurements.passage_height_mm}
                                                onChange={(e) => updateMeasurements('passage_height_mm', parseFloat(e.target.value) || 0)}
                                                placeholder="2050"
                                            />
                                        </div>
                                        <div className="col-span-2">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Forme Spéciale (Architecturale)</label>
                                            <select
                                                className="w-full p-4 bg-indigo-50 border-0 rounded-2xl font-bold text-indigo-700"
                                                value={formData.configuration.shape}
                                                onChange={(e) => updateConfig('shape', e.target.value)}
                                            >
                                                <option value="Rectangulaire">Standard (Rectangulaire/Carré)</option>
                                                <option value="Cintré">Cintré (Arc de cercle)</option>
                                                <option value="Trapèze">Trapèze (Sous pente)</option>
                                                <option value="Triangle">Triangle</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {formStep === 5 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-violet-600 font-bold mb-4">
                                        <Plus className="w-5 h-5" />
                                        <h3>Options & Prestations</h3>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Volet Roulant</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.annexes.volet_roulant}
                                                onChange={(e) => updateAnnexes('volet_roulant', e.target.value)}
                                            >
                                                <option value="Aucun">Aucun Volet</option>
                                                <option value="Manuel">Volet Roulant Manuel (Sangle/Treuil)</option>
                                                <option value="Electrique">Volet Roulant Électrique Filaire</option>
                                                <option value="Solaire">Volet Roulant Électrique Solaire (Autonome)</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Volet Battant (Alternative)</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.annexes.volet_battant}
                                                onChange={(e) => updateAnnexes('volet_battant', e.target.value)}
                                                disabled={formData.annexes.volet_roulant !== 'Aucun'}
                                            >
                                                <option value="Aucun">Aucun Volet Battant</option>
                                                <option value="1 Vantail">1 Vantail</option>
                                                <option value="2 Vantaux">2 Vantaux</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Prestation de Pose</label>
                                            <select
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                value={formData.annexes.frais_pose}
                                                onChange={(e) => updateAnnexes('frais_pose', e.target.value)}
                                            >
                                                <option value="Aucun">Fourniture Seule (Pas de pose)</option>
                                                <option value="Standard">Pose Standard (Neuf)</option>
                                                <option value="Renovation">Pose Rénovation (Dépose totale)</option>
                                                <option value="Complexe">Pose Complexe (Nacelle/Grande Hauteur)</option>
                                            </select>
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-2">Prestations Supplémentaires</label>
                                            <div className="flex gap-4">
                                                <label className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl flex-1 cursor-pointer hover:bg-slate-100 transition-colors">
                                                    <input
                                                        type="checkbox"
                                                        checked={formData.annexes.moustiquaire}
                                                        onChange={(e) => updateAnnexes('moustiquaire', e.target.checked)}
                                                        className="w-5 h-5 accent-violet-600"
                                                    />
                                                    <span className="font-bold text-slate-700 tracking-tight">Moustiquaire Intégrée</span>
                                                </label>
                                                <label className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl flex-1 cursor-pointer hover:bg-slate-100 transition-colors">
                                                    <input
                                                        type="checkbox"
                                                        checked={formData.annexes.livraison}
                                                        onChange={(e) => updateAnnexes('livraison', e.target.checked)}
                                                        className="w-5 h-5 accent-violet-600"
                                                    />
                                                    <span className="font-bold text-slate-700 tracking-tight">Livraison sur Chantier</span>
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {formStep === 6 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-emerald-600 font-bold mb-4">
                                        <CheckCircle2 className="w-5 h-5" />
                                        <h3>Options & Volet</h3>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Hauteur Soubassement (mm)</label>
                                            <div className="flex gap-2">
                                                <input
                                                    type="number"
                                                    className="w-2/3 p-4 bg-slate-50 border-0 rounded-2xl focus:ring-2 focus:ring-blue-500 font-medium text-slate-900"
                                                    value={formData.options.sill_height_mm}
                                                    onChange={(e) => updateOptions('sill_height_mm', parseFloat(e.target.value) || 0)}
                                                    placeholder="Facultatif"
                                                />
                                                <select
                                                    className="w-1/3 p-4 bg-slate-50 border-0 rounded-2xl font-bold text-slate-700"
                                                    value={formData.configuration.soubassement_type}
                                                    onChange={(e) => updateConfig('soubassement_type', e.target.value)}
                                                    disabled={!formData.options.sill_height_mm}
                                                >
                                                    <option value="Vitré">Vitré</option>
                                                    <option value="Plein">Plein</option>
                                                </select>
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Hauteur Imposte (mm)</label>
                                            <input
                                                type="number"
                                                className="w-full p-4 bg-slate-50 border-0 rounded-2xl focus:ring-2 focus:ring-blue-500 font-medium text-slate-900"
                                                value={formData.options.transom_height_mm}
                                                onChange={(e) => updateOptions('transom_height_mm', parseFloat(e.target.value) || 0)}
                                                placeholder="Facultatif"
                                            />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Position Volet Monobloc</label>
                                            <div className="flex gap-2">
                                                {['gauche', 'droite', 'centre', 'none'].map(pos => (
                                                    <button
                                                        key={pos}
                                                        onClick={() => updateOptions('shutter_type', pos)}
                                                        className={`flex-1 p-4 rounded-2xl font-bold capitalize transition-all ${formData.options.shutter_type === pos
                                                            ? 'bg-emerald-600 text-white shadow-lg'
                                                            : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                                                            }`}
                                                    >
                                                        {pos}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                        <div className="mt-4 pt-4 border-t border-slate-100 md:col-span-2">
                                            <label className="block text-xs font-bold text-blue-600 uppercase mb-4 tracking-wider">Logistique, Environnement & Sécurité</label>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div>
                                                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Environnement / Exposition</label>
                                                    <select
                                                        className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold"
                                                        value={formData.logistics.environment}
                                                        onChange={(e) => updateLogistics('environment', e.target.value)}
                                                    >
                                                        <option value="Standard">Standard (Urbain/Campagne)</option>
                                                        <option value="Bord de mer">Bord de mer (Moins de 10km côte)</option>
                                                        <option value="Zone ventée">Zone ventée (Montagne/Plaine)</option>
                                                        <option value="Urbain Dense">Urbain Dense (Immeubles)</option>
                                                    </select>
                                                </div>
                                                <div>
                                                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Étage</label>
                                                    <input
                                                        type="number"
                                                        className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold"
                                                        value={formData.logistics.floor_number}
                                                        onChange={(e) => updateLogistics('floor_number', parseInt(e.target.value) || 0)}
                                                    />
                                                </div>
                                                <div className="md:col-span-2">
                                                    <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Difficulté d'Accès</label>
                                                    <select
                                                        className="w-full p-4 bg-slate-50 border-0 rounded-2xl font-bold"
                                                        value={formData.logistics.access_difficulty}
                                                        onChange={(e) => updateLogistics('access_difficulty', e.target.value)}
                                                    >
                                                        <option value="Standard">Standard (Accès facile)</option>
                                                        <option value="Crane">Grutage nécessaire</option>
                                                        <option value="Manue">Manutention difficile</option>
                                                        <option value="Forbidden">Centre-ville (Accès restreint)</option>
                                                    </select>
                                                </div>
                                                {getIndustrialWarnings().filter(w => ['security', 'aev', 'pmr'].includes(w.type)).map((w, i) => (
                                                    <div key={i} className="md:col-span-2 flex items-center gap-3 p-4 bg-rose-50 rounded-2xl border border-rose-100 text-rose-800 text-xs font-bold">
                                                        <ShieldAlert className="w-5 h-5 shrink-0" />
                                                        {w.msg}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {formStep === 7 && (
                                <div className="space-y-6">
                                    <div className="flex items-center gap-2 text-emerald-600 font-bold mb-4">
                                        <CheckCircle2 className="w-5 h-5" />
                                        <h3>Récapitulatif & Validation</h3>
                                    </div>
                                    <div className="bg-slate-900 rounded-3xl p-6 text-white space-y-4">
                                        <div className="grid grid-cols-2 gap-4 border-b border-slate-800 pb-4">
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Client</p>
                                                <p className="font-bold">{formData.client.name}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Type</p>
                                                <p className="font-bold">{formData.client.client_type}</p>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4 border-b border-slate-800 pb-4">
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Dimensions</p>
                                                <p className="font-bold text-emerald-400">{formData.measurements.width_mm} x {formData.measurements.height_mm} mm</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Pose</p>
                                                <p className="font-bold">{formData.configuration.installation_type}</p>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4 border-b border-slate-800 pb-4">
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Gamme</p>
                                                <p className="font-bold text-blue-400">{formData.configuration.product_series}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Hardware</p>
                                                <p className="font-bold">{formData.configuration.hardware_type}</p>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4 border-b border-slate-800 pb-4">
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Finition</p>
                                                <p className="font-bold">{formData.configuration.color_ral} ({formData.configuration.texture}) {formData.configuration.is_bicolor ? '+ Bicolore' : ''}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Logistique</p>
                                                <p className="font-bold">Étage {formData.logistics.floor_number} | {formData.logistics.access_difficulty}</p>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">PMR</p>
                                                <p className="font-bold">{formData.configuration.is_pmr_compliant ? 'OUI' : 'NON'}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] font-bold text-slate-500 uppercase">Matériau</p>
                                                <p className="font-bold">{formData.configuration.material}</p>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="bg-slate-50 p-6 rounded-3xl border border-slate-100 space-y-4">
                                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                            <ShieldAlert className="w-4 h-4" /> Contrôles Industriels
                                        </h4>
                                        {getIndustrialWarnings().length > 0 ? (
                                            <div className="space-y-2">
                                                {getIndustrialWarnings().map((w, i) => (
                                                    <p key={i} className="text-rose-600 text-sm font-bold flex items-center gap-2">
                                                        <AlertTriangle className="w-4 h-4 shrink-0" />
                                                        {w.msg}
                                                    </p>
                                                ))}
                                            </div>
                                        ) : (
                                            <p className="text-emerald-600 text-sm font-bold flex items-center gap-2">
                                                <CheckCircle2 className="w-4 h-4" /> Toutes les spécifications sont conformes aux limites techniques.
                                            </p>
                                        )}
                                    </div>
                                    <p className="text-[10px] text-slate-500 italic text-center px-8">
                                        Vérifiez bien toutes les informations avant de créer le dossier technique.
                                    </p>
                                </div>
                            )}
                        </div>

                        {/* Footer / Navigation */}
                        <div className="p-6 border-t border-slate-100 bg-slate-50/50 flex justify-between items-center">
                            <button
                                onClick={() => formStep > 1 && setFormStep(formStep - 1)}
                                disabled={formStep === 1}
                                className={`flex items-center gap-2 px-6 py-3 font-bold rounded-2xl transition-all ${formStep === 1 ? 'text-slate-300' : 'text-slate-600 hover:bg-slate-200'
                                    }`}
                            >
                                <ChevronLeft className="w-5 h-5" />
                                Précédent
                            </button>

                            {formStep < 7 ? (
                                <button
                                    onClick={() => setFormStep(formStep + 1)}
                                    className="px-8 py-3 bg-blue-600 text-white font-bold rounded-2xl hover:bg-blue-500 shadow-lg shadow-blue-500/20"
                                >
                                    Suivant
                                </button>
                            ) : (
                                <button
                                    onClick={handleFormSubmit}
                                    className="px-10 py-4 bg-emerald-600 text-white font-black rounded-3xl hover:bg-emerald-500 shadow-xl shadow-emerald-500/30 flex items-center gap-2 active:scale-95 transition-all text-slate-900"
                                >
                                    <CheckCircle2 className="w-6 h-6" />
                                    Créer le Dossier
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </main>
    </div>
    );
};

export default MMGDossiers;
