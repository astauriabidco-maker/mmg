import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
    ArrowDownToLine,
    ArrowLeftRight,
    ArrowUpFromLine,
    Barcode,
    Boxes,
    Camera,
    Check,
    ChevronLeft,
    ChevronRight,
    ClipboardCheck,
    Download,
    History,
    Home,
    LogOut,
    MapPin,
    Menu,
    PackageCheck,
    RefreshCw,
    ScanLine,
    Search,
    ShieldAlert,
    Wifi,
    WifiOff,
    X,
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const ACTION_META = {
    receive: {
        label: 'Réceptionner',
        title: 'Entrée en stock',
        helper: 'Réception fournisseur ou entrée contrôlée',
        icon: ArrowDownToLine,
        tone: 'emerald',
    },
    transfer: {
        label: 'Déplacer',
        title: 'Transfert interne',
        helper: 'Déplacer entre deux emplacements',
        icon: ArrowLeftRight,
        tone: 'blue',
    },
    issue: {
        label: 'Sortir',
        title: 'Sortie manuelle',
        helper: 'Sortie client ou externe avec motif',
        icon: ArrowUpFromLine,
        tone: 'orange',
    },
};

const toneClasses = {
    emerald: 'bg-emerald-600 text-white',
    blue: 'bg-blue-600 text-white',
    orange: 'bg-orange-500 text-white',
};

const formatQty = (value) => Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
const formatDate = (value) => value
    ? new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
    : '';

const errorMessage = (error, fallback) => error?.response?.data?.detail || error?.message || fallback;

function MobileHeader({ title, subtitle, online, onLogout, onDesktop }) {
    return (
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] backdrop-blur">
            <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-950 text-white">
                            <Boxes className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                            <h1 className="truncate text-lg font-black text-slate-950">{title}</h1>
                            <p className="truncate text-xs font-semibold text-slate-500">{subtitle}</p>
                        </div>
                    </div>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                    <span
                        className={`flex h-9 items-center gap-1 rounded-lg px-2 text-[10px] font-black uppercase ${
                            online ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                        }`}
                        title={online ? 'Connexion disponible' : 'Hors connexion'}
                    >
                        {online ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
                    </span>
                    <button onClick={onDesktop} className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100" title="Version bureau">
                        <Menu className="h-5 w-5" />
                    </button>
                    <button onClick={onLogout} className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100" title="Déconnexion">
                        <LogOut className="h-5 w-5" />
                    </button>
                </div>
            </div>
        </header>
    );
}

function BottomNavigation({ view, setView, canCount }) {
    const items = [
        { id: 'home', label: 'Accueil', Icon: Home },
        { id: 'scan', label: 'Scanner', Icon: ScanLine },
        { id: 'moves', label: 'Mouvements', Icon: History },
        ...(canCount ? [{ id: 'count', label: 'Inventaire', Icon: ClipboardCheck }] : []),
    ];
    return (
        <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_24px_rgba(15,23,42,0.08)]">
            <div className="mx-auto grid max-w-lg gap-1" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
                {items.map(({ id, label, Icon }) => {
                    const active = view === id;
                    return (
                        <button
                            key={id}
                            onClick={() => setView(id)}
                            className={`flex min-h-12 flex-col items-center justify-center gap-1 rounded-lg text-[10px] font-black ${
                                active ? 'bg-slate-950 text-white' : 'text-slate-500'
                            }`}
                        >
                            <Icon className="h-5 w-5" />
                            {label}
                        </button>
                    );
                })}
            </div>
        </nav>
    );
}

function ProductSearch({ variants, value, onChange, onSelect, autoFocus = false }) {
    const normalized = value.trim().toLowerCase();
    const results = normalized
        ? variants.filter((item) => item.searchText.includes(normalized)).slice(0, 20)
        : variants.slice(0, 12);

    return (
        <div className="space-y-3">
            <div className="relative">
                <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                <input
                    autoFocus={autoFocus}
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    className="h-14 w-full rounded-xl border border-slate-200 bg-white pl-12 pr-4 text-base font-bold text-slate-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    placeholder="Référence, code-barres, désignation..."
                    autoComplete="off"
                />
            </div>
            <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
                {results.map((item) => (
                    <button
                        key={item.id}
                        onClick={() => onSelect(item)}
                        className="flex min-h-16 w-full items-center gap-3 px-4 py-3 text-left active:bg-slate-100"
                    >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
                            <Barcode className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="truncate font-black text-slate-950">{item.reference}</p>
                            <p className="truncate text-xs font-semibold text-slate-500">{item.productName}</p>
                        </div>
                        <div className="text-right">
                            <p className="text-lg font-black text-slate-950">{formatQty(item.physical)}</p>
                            <p className="text-[10px] font-bold uppercase text-slate-400">{item.unit}</p>
                        </div>
                        <ChevronRight className="h-5 w-5 shrink-0 text-slate-300" />
                    </button>
                ))}
                {results.length === 0 && (
                    <div className="px-5 py-8 text-center">
                        <p className="font-black text-slate-700">Aucune référence trouvée</p>
                        <p className="mt-1 text-sm text-slate-500">Vérifiez le code ou utilisez la recherche manuelle.</p>
                    </div>
                )}
            </div>
        </div>
    );
}

function ScannerOverlay({ onClose, onDetected }) {
    const videoRef = useRef(null);
    const controlsRef = useRef(null);
    const [error, setError] = useState('');

    useEffect(() => {
        let active = true;
        const start = async () => {
            if (!navigator.mediaDevices?.getUserMedia) {
                setError("La caméra n'est pas disponible sur cet appareil.");
                return;
            }
            try {
                const { BrowserMultiFormatReader } = await import('@zxing/browser');
                if (!active) return;
                const reader = new BrowserMultiFormatReader();
                const controls = await reader.decodeFromConstraints(
                    { video: { facingMode: { ideal: 'environment' } }, audio: false },
                    videoRef.current,
                    (result) => {
                        if (!active || !result) return;
                        controlsRef.current?.stop();
                        onDetected(result.getText());
                    },
                );
                if (!active) controls.stop();
                else controlsRef.current = controls;
            } catch (cameraError) {
                setError(cameraError?.name === 'NotAllowedError'
                    ? "Autorisez l'accès à la caméra dans les réglages du navigateur."
                    : "Impossible d'ouvrir la caméra.");
            }
        };
        start();
        return () => {
            active = false;
            controlsRef.current?.stop();
        };
    }, [onDetected]);

    return (
        <div className="fixed inset-0 z-[70] bg-slate-950">
            <video ref={videoRef} className="h-full w-full object-cover" playsInline muted />
            <div className="absolute inset-0 flex flex-col">
                <div className="flex items-center justify-between p-4 pt-[max(1rem,env(safe-area-inset-top))] text-white">
                    <div>
                        <p className="font-black">Scanner un article</p>
                        <p className="text-xs text-white/70">Placez le code dans le cadre</p>
                    </div>
                    <button onClick={onClose} className="flex h-11 w-11 items-center justify-center rounded-full bg-black/40">
                        <X className="h-6 w-6" />
                    </button>
                </div>
                <div className="flex flex-1 items-center justify-center p-8">
                    <div className="relative aspect-[4/3] w-full max-w-sm rounded-2xl border-2 border-white/80">
                        <div className="absolute left-4 right-4 top-1/2 h-0.5 animate-pulse bg-emerald-400 shadow-[0_0_18px_rgba(52,211,153,0.9)]" />
                    </div>
                </div>
                <div className="p-6 pb-[max(2rem,env(safe-area-inset-bottom))] text-center text-white">
                    {error ? (
                        <div className="rounded-xl bg-rose-500/20 p-4 text-sm font-bold text-rose-100">{error}</div>
                    ) : (
                        <p className="text-sm font-semibold text-white/80">EAN, Code 128, Code 39 ou QR code</p>
                    )}
                </div>
            </div>
        </div>
    );
}

function VariantSheet({ item, locations, permissions, onClose, onAction }) {
    const stockRows = item.stockRows.filter((row) => row.location?.usage === 'internal');
    return (
        <div className="fixed inset-0 z-50 flex items-end bg-slate-950/50">
            <div className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white pb-[max(1.5rem,env(safe-area-inset-bottom))] shadow-2xl">
                <div className="sticky top-0 flex items-start justify-between border-b border-slate-100 bg-white px-5 py-4">
                    <div className="min-w-0">
                        <p className="font-mono text-xs font-bold text-blue-700">{item.reference}</p>
                        <h2 className="mt-1 text-xl font-black text-slate-950">{item.productName}</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-500">{item.supplier || 'Fournisseur non renseigné'} · {item.unit}</p>
                    </div>
                    <button onClick={onClose} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                        <X className="h-5 w-5" />
                    </button>
                </div>
                <div className="space-y-5 p-5">
                    <div className="grid grid-cols-3 gap-2">
                        <div className="rounded-xl bg-slate-950 p-3 text-white">
                            <p className="text-[9px] font-black uppercase text-slate-400">Physique</p>
                            <p className="mt-1 text-xl font-black">{formatQty(item.physical)}</p>
                        </div>
                        <div className="rounded-xl bg-orange-50 p-3 text-orange-800">
                            <p className="text-[9px] font-black uppercase">Réservé</p>
                            <p className="mt-1 text-xl font-black">{formatQty(item.reserved)}</p>
                        </div>
                        <div className="rounded-xl bg-emerald-50 p-3 text-emerald-800">
                            <p className="text-[9px] font-black uppercase">Disponible</p>
                            <p className="mt-1 text-xl font-black">{formatQty(item.available)}</p>
                        </div>
                    </div>

                    <section>
                        <h3 className="mb-2 text-xs font-black uppercase tracking-wider text-slate-400">Par emplacement</h3>
                        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
                            {stockRows.map((row) => (
                                <div key={row.id} className="flex items-center gap-3 px-4 py-3">
                                    <MapPin className="h-5 w-5 text-slate-400" />
                                    <div className="min-w-0 flex-1">
                                        <p className="truncate font-bold text-slate-800">{row.location?.name}</p>
                                        <p className="text-xs text-slate-500">Disponible {formatQty(row.available_quantity ?? row.quantity)}</p>
                                    </div>
                                    <p className="text-lg font-black text-slate-950">{formatQty(row.quantity)}</p>
                                </div>
                            ))}
                            {stockRows.length === 0 && <p className="px-4 py-6 text-center text-sm font-semibold text-slate-500">Aucun stock interne.</p>}
                        </div>
                    </section>

                    <section>
                        <h3 className="mb-2 text-xs font-black uppercase tracking-wider text-slate-400">Actions autorisées</h3>
                        <div className="grid grid-cols-3 gap-2">
                            {permissions.receive && (
                                <button onClick={() => onAction('receive', item)} className="flex min-h-20 flex-col items-center justify-center gap-2 rounded-xl bg-emerald-600 p-2 text-xs font-black text-white">
                                    <ArrowDownToLine className="h-6 w-6" /> Entrée
                                </button>
                            )}
                            {permissions.transfer && (
                                <button onClick={() => onAction('transfer', item)} className="flex min-h-20 flex-col items-center justify-center gap-2 rounded-xl bg-blue-600 p-2 text-xs font-black text-white">
                                    <ArrowLeftRight className="h-6 w-6" /> Déplacer
                                </button>
                            )}
                            {permissions.issue && (
                                <button onClick={() => onAction('issue', item)} className="flex min-h-20 flex-col items-center justify-center gap-2 rounded-xl bg-orange-500 p-2 text-xs font-black text-white">
                                    <ArrowUpFromLine className="h-6 w-6" /> Sortir
                                </button>
                            )}
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}

function StockActionSheet({ type, item, locations, online, onClose, onSubmit, pending }) {
    const meta = ACTION_META[type];
    const Icon = meta.icon;
    const internalLocations = locations.filter((location) => location.usage === 'internal');
    const sourceRows = item.stockRows.filter((row) => row.location?.usage === 'internal' && Number(row.available_quantity ?? row.quantity) > 0);
    const [form, setForm] = useState({
        sourceId: sourceRows[0]?.location_id ? String(sourceRows[0].location_id) : '',
        destinationId: type === 'receive' && internalLocations.length === 1 ? String(internalLocations[0].id) : '',
        quantity: '',
        reason: '',
        documentReference: '',
    });
    const sourceRow = sourceRows.find((row) => String(row.location_id) === form.sourceId);
    const available = Number(sourceRow?.available_quantity ?? sourceRow?.quantity ?? 0);
    const quantity = Number(form.quantity);
    const valid = online
        && quantity > 0
        && (type === 'receive' ? Boolean(form.destinationId) : Boolean(form.sourceId))
        && (type !== 'transfer' || (Boolean(form.destinationId) && form.destinationId !== form.sourceId))
        && (type !== 'issue' || form.reason.trim().length >= 3)
        && (type === 'receive' || quantity <= available);

    return (
        <div className="fixed inset-0 z-[60] flex items-end bg-slate-950/50">
            <div className="w-full rounded-t-2xl bg-white pb-[max(1.5rem,env(safe-area-inset-bottom))]">
                <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
                    <div className="flex items-center gap-3">
                        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${toneClasses[meta.tone]}`}>
                            <Icon className="h-6 w-6" />
                        </div>
                        <div>
                            <h2 className="text-lg font-black text-slate-950">{meta.title}</h2>
                            <p className="text-xs font-semibold text-slate-500">{item.reference}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
                        <X className="h-5 w-5" />
                    </button>
                </div>
                <div className="max-h-[72vh] space-y-4 overflow-y-auto p-5">
                    {!online && (
                        <div className="flex gap-3 rounded-xl bg-rose-50 p-4 text-sm font-bold text-rose-800">
                            <WifiOff className="h-5 w-5 shrink-0" />
                            Mouvement bloqué hors connexion pour éviter une double écriture.
                        </div>
                    )}

                    {type !== 'receive' && (
                        <label className="block">
                            <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Depuis</span>
                            <select
                                value={form.sourceId}
                                onChange={(event) => setForm({ ...form, sourceId: event.target.value })}
                                className="h-14 w-full rounded-xl border border-slate-200 bg-white px-4 font-bold"
                            >
                                <option value="">Choisir l'emplacement</option>
                                {sourceRows.map((row) => (
                                    <option key={row.location_id} value={row.location_id}>
                                        {row.location?.name} · disponible {formatQty(row.available_quantity ?? row.quantity)}
                                    </option>
                                ))}
                            </select>
                        </label>
                    )}

                    {type !== 'issue' && (
                        <label className="block">
                            <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Vers</span>
                            <select
                                value={form.destinationId}
                                onChange={(event) => setForm({ ...form, destinationId: event.target.value })}
                                className="h-14 w-full rounded-xl border border-slate-200 bg-white px-4 font-bold"
                            >
                                <option value="">Choisir l'emplacement</option>
                                {internalLocations.map((location) => (
                                    <option key={location.id} value={location.id} disabled={String(location.id) === form.sourceId}>
                                        {location.name}
                                    </option>
                                ))}
                            </select>
                        </label>
                    )}

                    <label className="block">
                        <span className="mb-1.5 flex justify-between text-xs font-black uppercase text-slate-500">
                            Quantité
                            {type !== 'receive' && <span>Maximum {formatQty(available)}</span>}
                        </span>
                        <input
                            type="number"
                            inputMode="decimal"
                            min="0"
                            max={type === 'receive' ? undefined : available}
                            step="any"
                            value={form.quantity}
                            onChange={(event) => setForm({ ...form, quantity: event.target.value })}
                            className="h-16 w-full rounded-xl border border-slate-200 px-4 text-2xl font-black outline-none focus:border-blue-500"
                            placeholder="0"
                        />
                    </label>

                    {type === 'issue' && (
                        <label className="block">
                            <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Motif obligatoire</span>
                            <textarea
                                value={form.reason}
                                onChange={(event) => setForm({ ...form, reason: event.target.value })}
                                className="min-h-24 w-full rounded-xl border border-slate-200 p-4 font-semibold outline-none focus:border-blue-500"
                                placeholder="Client, chantier, casse, régularisation..."
                            />
                        </label>
                    )}

                    <label className="block">
                        <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Document lié (optionnel)</span>
                        <input
                            value={form.documentReference}
                            onChange={(event) => setForm({ ...form, documentReference: event.target.value })}
                            className="h-14 w-full rounded-xl border border-slate-200 px-4 font-bold outline-none focus:border-blue-500"
                            placeholder="BC, BL, dossier, intervention..."
                        />
                    </label>
                </div>
                <div className="px-5">
                    <button
                        disabled={!valid || pending}
                        onClick={() => onSubmit({ ...form, quantity })}
                        className={`flex h-14 w-full items-center justify-center gap-2 rounded-xl text-base font-black ${
                            valid && !pending ? toneClasses[meta.tone] : 'cursor-not-allowed bg-slate-200 text-slate-400'
                        }`}
                    >
                        {pending ? <RefreshCw className="h-5 w-5 animate-spin" /> : <Check className="h-5 w-5" />}
                        {pending ? 'Enregistrement...' : `Confirmer : ${meta.label}`}
                    </button>
                </div>
            </div>
        </div>
    );
}

export default function StockMobileDashboard() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [view, setView] = useState('home');
    const [search, setSearch] = useState('');
    const [selectedItem, setSelectedItem] = useState(null);
    const [action, setAction] = useState(null);
    const [scannerOpen, setScannerOpen] = useState(false);
    const [online, setOnline] = useState(navigator.onLine);
    const [notice, setNotice] = useState(null);
    const [installPrompt, setInstallPrompt] = useState(null);
    const [selectedSessionId, setSelectedSessionId] = useState(null);
    const [countSearch, setCountSearch] = useState('');
    const [countItem, setCountItem] = useState(null);
    const [countLocationId, setCountLocationId] = useState('');
    const [countQuantity, setCountQuantity] = useState('');
    const scanBuffer = useRef('');
    const scanTimer = useRef(null);

    const can = (permission) => user?.permissions?.includes('*') || user?.permissions?.includes(permission);
    const permissions = {
        view: can('STOCK_VIEW'),
        receive: can('stock.receive'),
        transfer: can('stock.transfer'),
        issue: can('stock.adjust'),
        count: can('inventory.count'),
    };

    const productsQuery = useQuery({
        queryKey: ['mobile-stock-products'],
        queryFn: async () => (await api.get('/v2/stock/products')).data,
        enabled: permissions.view,
        staleTime: 30_000,
    });
    const locationsQuery = useQuery({
        queryKey: ['mobile-stock-locations'],
        queryFn: async () => (await api.get('/v2/stock/locations')).data,
        enabled: permissions.view,
        staleTime: 60_000,
    });
    const quantsQuery = useQuery({
        queryKey: ['mobile-stock-quants'],
        queryFn: async () => (await api.get('/v2/stock/quants')).data,
        enabled: permissions.view,
        staleTime: 15_000,
    });
    const movesQuery = useQuery({
        queryKey: ['mobile-stock-moves'],
        queryFn: async () => (await api.get('/v2/stock/transactions')).data,
        enabled: permissions.view,
        staleTime: 15_000,
    });
    const sessionsQuery = useQuery({
        queryKey: ['mobile-stock-inventory-sessions'],
        queryFn: async () => (await api.get('/v2/stock/inventory-sessions')).data,
        enabled: permissions.count,
        staleTime: 15_000,
    });

    const products = productsQuery.data || [];
    const locations = locationsQuery.data || [];
    const quants = quantsQuery.data || [];
    const moves = movesQuery.data || [];
    const sessions = sessionsQuery.data || [];
    const internalLocations = locations.filter((location) => location.usage === 'internal');
    const supplierLocation = locations.find((location) => location.usage === 'supplier');
    const customerLocation = locations.find((location) => location.usage === 'customer');

    const variants = useMemo(() => products
        .filter((product) => (product.catalog_status || 'ACTIVE') === 'ACTIVE' && (product.product_type || 'stockable') !== 'service')
        .flatMap((product) => product.variants.map((variant) => {
            const stockRows = quants.filter((quant) => quant.variant_id === variant.id);
            const internalRows = stockRows.filter((quant) => quant.location?.usage === 'internal');
            const physical = internalRows.reduce((sum, quant) => sum + Number(quant.quantity || 0), 0);
            const reserved = internalRows.reduce((sum, quant) => sum + Number(quant.reserved_quantity || 0), 0);
            const available = internalRows.reduce((sum, quant) => sum + Number(quant.available_quantity ?? quant.quantity ?? 0), 0);
            return {
                ...variant,
                product,
                productName: product.name,
                supplier: product.supplier,
                unit: product.unit || 'pce',
                physical,
                reserved,
                available,
                stockRows,
                searchText: [
                    variant.reference,
                    variant.barcode,
                    variant.supplier_reference,
                    product.reference_base,
                    product.name,
                    product.supplier,
                ].filter(Boolean).join(' ').toLowerCase(),
            };
        })), [products, quants]);

    const openSessions = sessions.filter((session) => ['draft', 'counting'].includes(session.status));
    const selectedSession = openSessions.find((session) => session.id === selectedSessionId) || null;
    const lowStock = variants.filter((item) => item.available <= Number(item.min_threshold || 0));
    const totalPhysical = variants.reduce((sum, item) => sum + item.physical, 0);
    const loading = productsQuery.isLoading || locationsQuery.isLoading || quantsQuery.isLoading;

    const refresh = async () => {
        await Promise.all([
            productsQuery.refetch(),
            locationsQuery.refetch(),
            quantsQuery.refetch(),
            movesQuery.refetch(),
            permissions.count ? sessionsQuery.refetch() : Promise.resolve(),
        ]);
        setNotice({ type: 'success', text: 'Données actualisées.' });
    };

    const movementMutation = useMutation({
        mutationFn: async ({ type, item, form }) => {
            if (!online) throw new Error('Connexion requise pour enregistrer un mouvement.');
            const payload = {
                variant_id: item.id,
                quantity: form.quantity,
                document_reference: form.documentReference.trim() || null,
                source_screen: 'stock.mobile_pwa',
            };
            if (type === 'receive') {
                Object.assign(payload, {
                    location_id: supplierLocation?.id || null,
                    location_dest_id: Number(form.destinationId),
                    notes: 'Réception stock depuis PWA mobile',
                    reason: 'Réception mobile contrôlée',
                    document_type: 'mobile_stock_reception',
                });
            } else if (type === 'transfer') {
                Object.assign(payload, {
                    location_id: Number(form.sourceId),
                    location_dest_id: Number(form.destinationId),
                    notes: 'Transfert interne depuis PWA mobile',
                    reason: 'Rangement ou transfert mobile',
                    document_type: 'mobile_stock_transfer',
                });
            } else {
                Object.assign(payload, {
                    location_id: Number(form.sourceId),
                    location_dest_id: customerLocation?.id || null,
                    notes: `Sortie stock mobile - ${form.reason.trim()}`,
                    reason: form.reason.trim(),
                    document_type: 'mobile_stock_issue',
                });
            }
            return api.post('/v2/stock/transaction', payload);
        },
        onSuccess: async (_, variables) => {
            setAction(null);
            setSelectedItem(null);
            setNotice({ type: 'success', text: `${ACTION_META[variables.type].label} enregistré et tracé.` });
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: ['mobile-stock-products'] }),
                queryClient.invalidateQueries({ queryKey: ['mobile-stock-quants'] }),
                queryClient.invalidateQueries({ queryKey: ['mobile-stock-moves'] }),
            ]);
        },
        onError: (error) => setNotice({ type: 'error', text: errorMessage(error, "Le mouvement n'a pas été enregistré.") }),
    });

    const countMutation = useMutation({
        mutationFn: async () => {
            if (!online) throw new Error('Connexion requise pour enregistrer un comptage.');
            if (!selectedSession || !countItem || !countLocationId || countQuantity === '') throw new Error('Comptage incomplet.');
            return api.post(`/v2/stock/inventory-sessions/${selectedSession.id}/lines`, {
                variant_id: countItem.id,
                location_id: Number(countLocationId),
                counted_quantity: Number(countQuantity),
                notes: 'Comptage depuis PWA stock mobile',
            });
        },
        onSuccess: async () => {
            setNotice({ type: 'success', text: `Comptage de ${countItem.reference} enregistré.` });
            setCountItem(null);
            setCountSearch('');
            setCountQuantity('');
            await queryClient.invalidateQueries({ queryKey: ['mobile-stock-inventory-sessions'] });
        },
        onError: (error) => setNotice({ type: 'error', text: errorMessage(error, "Le comptage n'a pas été enregistré.") }),
    });

    useEffect(() => {
        const handleOnline = () => setOnline(true);
        const handleOffline = () => setOnline(false);
        const handleInstall = (event) => {
            event.preventDefault();
            setInstallPrompt(event);
        };
        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);
        window.addEventListener('beforeinstallprompt', handleInstall);
        return () => {
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
            window.removeEventListener('beforeinstallprompt', handleInstall);
        };
    }, []);

    useEffect(() => {
        const handleHardwareScan = (event) => {
            const target = event.target;
            if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
            if (event.key === 'Enter' && scanBuffer.current.length >= 3) {
                const code = scanBuffer.current;
                scanBuffer.current = '';
                const match = variants.find((item) => [item.barcode, item.reference, item.supplier_reference].filter(Boolean).some((value) => String(value).toLowerCase() === code.toLowerCase()));
                setView('scan');
                setSearch(code);
                if (match) setSelectedItem(match);
                return;
            }
            if (event.key.length === 1) {
                scanBuffer.current += event.key;
                clearTimeout(scanTimer.current);
                scanTimer.current = setTimeout(() => { scanBuffer.current = ''; }, 180);
            }
        };
        window.addEventListener('keydown', handleHardwareScan);
        return () => {
            window.removeEventListener('keydown', handleHardwareScan);
            clearTimeout(scanTimer.current);
        };
    }, [variants]);

    useEffect(() => {
        if (selectedSession?.location_id) setCountLocationId(String(selectedSession.location_id));
    }, [selectedSession?.id, selectedSession?.location_id]);

    const handleDetected = (code) => {
        setScannerOpen(false);
        const match = variants.find((item) => [item.barcode, item.reference, item.supplier_reference].filter(Boolean).some((value) => String(value).toLowerCase() === code.toLowerCase()));
        if (match) {
            if (view === 'count' && selectedSession) {
                setCountSearch(code);
                setCountItem(match);
            } else if (action && !action.item) {
                setView('scan');
                setSearch(code);
                setAction({ ...action, item: match });
            } else {
                setView('scan');
                setSearch(code);
                setSelectedItem(match);
            }
        } else {
            if (view === 'count') setCountSearch(code);
            else {
                setView('scan');
                setSearch(code);
            }
            setNotice({ type: 'error', text: `Aucun article actif ne correspond au code ${code}.` });
        }
    };

    const startAction = (type, item = null) => {
        setSelectedItem(null);
        setAction({ type, item });
        if (!item) {
            setView('scan');
            setNotice({ type: 'info', text: `Scannez ou recherchez l'article à ${ACTION_META[type].label.toLowerCase()}.` });
        }
    };

    const selectForCurrentContext = (item) => {
        if (action && !action.item) {
            setAction({ ...action, item });
            return;
        }
        setSelectedItem(item);
    };

    const installApp = async () => {
        if (!installPrompt) {
            setNotice({ type: 'info', text: "Sur iPhone/iPad : Partager puis « Sur l'écran d'accueil ». Sur Android : menu du navigateur puis « Installer »." });
            return;
        }
        installPrompt.prompt();
        await installPrompt.userChoice;
        setInstallPrompt(null);
    };

    if (!permissions.view) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
                <div className="w-full max-w-sm rounded-2xl bg-white p-6 text-center shadow-lg">
                    <ShieldAlert className="mx-auto h-12 w-12 text-rose-500" />
                    <h1 className="mt-4 text-xl font-black text-slate-950">Accès stock requis</h1>
                    <p className="mt-2 text-sm font-semibold text-slate-500">Votre profil ne possède pas la permission STOCK_VIEW.</p>
                    <button onClick={() => navigate('/dashboard')} className="mt-5 h-12 w-full rounded-xl bg-slate-950 font-black text-white">Retour</button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-[100dvh] bg-slate-100 pb-24 font-sans text-slate-950">
            <MobileHeader
                title={view === 'home' ? 'Stock mobile' : view === 'scan' ? 'Scanner & rechercher' : view === 'moves' ? 'Mouvements' : 'Inventaire physique'}
                subtitle={`${user?.username || 'Utilisateur'} · MMG`}
                online={online}
                onLogout={logout}
                onDesktop={() => navigate('/stock')}
            />

            {!online && (
                <div className="sticky top-[73px] z-20 flex items-center justify-center gap-2 bg-rose-600 px-4 py-2 text-xs font-black text-white">
                    <WifiOff className="h-4 w-4" />
                    Hors connexion · écritures désactivées
                </div>
            )}

            {notice && (
                <div className={`fixed inset-x-4 top-24 z-[80] mx-auto flex max-w-md items-start gap-3 rounded-xl p-4 text-sm font-bold shadow-xl ${
                    notice.type === 'error' ? 'bg-rose-600 text-white' : notice.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-blue-600 text-white'
                }`}>
                    <span className="flex-1">{notice.text}</span>
                    <button onClick={() => setNotice(null)}><X className="h-5 w-5" /></button>
                </div>
            )}

            <main className="mx-auto max-w-lg p-4">
                {loading ? (
                    <div className="flex min-h-72 items-center justify-center">
                        <RefreshCw className="h-8 w-8 animate-spin text-blue-600" />
                    </div>
                ) : view === 'home' ? (
                    <div className="space-y-5">
                        <section className="rounded-2xl bg-slate-950 p-5 text-white">
                            <div className="flex items-start justify-between">
                                <div>
                                    <p className="text-xs font-black uppercase tracking-wider text-slate-400">Situation magasin</p>
                                    <p className="mt-2 text-3xl font-black">{variants.length} références</p>
                                    <p className="mt-1 text-sm font-semibold text-slate-300">{formatQty(totalPhysical)} unités physiques</p>
                                </div>
                                <button onClick={refresh} className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10" title="Actualiser">
                                    <RefreshCw className="h-5 w-5" />
                                </button>
                            </div>
                            <div className="mt-5 grid grid-cols-2 gap-2">
                                <button onClick={() => navigate('/stock')} className="rounded-xl bg-white/10 p-3 text-left">
                                    <p className="text-[10px] font-black uppercase text-slate-400">Stock à risque</p>
                                    <p className="mt-1 text-xl font-black">{lowStock.length}</p>
                                </button>
                                <button onClick={() => permissions.count && setView('count')} className="rounded-xl bg-white/10 p-3 text-left">
                                    <p className="text-[10px] font-black uppercase text-slate-400">Inventaires ouverts</p>
                                    <p className="mt-1 text-xl font-black">{openSessions.length}</p>
                                </button>
                            </div>
                        </section>

                        <section>
                            <div className="mb-3 flex items-end justify-between">
                                <div>
                                    <h2 className="text-lg font-black">Actions rapides</h2>
                                    <p className="text-xs font-semibold text-slate-500">Selon vos permissions</p>
                                </div>
                                <button onClick={() => setScannerOpen(true)} className="flex h-10 items-center gap-2 rounded-lg bg-blue-50 px-3 text-xs font-black text-blue-700">
                                    <Camera className="h-4 w-4" /> Scanner
                                </button>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                {permissions.receive && (
                                    <button onClick={() => startAction('receive')} className="min-h-28 rounded-xl bg-emerald-600 p-4 text-left text-white shadow-sm">
                                        <ArrowDownToLine className="h-7 w-7" />
                                        <p className="mt-4 font-black">Réceptionner</p>
                                        <p className="mt-1 text-xs font-semibold text-emerald-100">Entrée contrôlée</p>
                                    </button>
                                )}
                                {permissions.transfer && (
                                    <button onClick={() => startAction('transfer')} className="min-h-28 rounded-xl bg-blue-600 p-4 text-left text-white shadow-sm">
                                        <ArrowLeftRight className="h-7 w-7" />
                                        <p className="mt-4 font-black">Déplacer</p>
                                        <p className="mt-1 text-xs font-semibold text-blue-100">Entre emplacements</p>
                                    </button>
                                )}
                                {permissions.issue && (
                                    <button onClick={() => startAction('issue')} className="min-h-28 rounded-xl bg-orange-500 p-4 text-left text-white shadow-sm">
                                        <ArrowUpFromLine className="h-7 w-7" />
                                        <p className="mt-4 font-black">Sortir</p>
                                        <p className="mt-1 text-xs font-semibold text-orange-100">Motif obligatoire</p>
                                    </button>
                                )}
                                {permissions.count && (
                                    <button onClick={() => setView('count')} className="min-h-28 rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                                        <ClipboardCheck className="h-7 w-7 text-violet-600" />
                                        <p className="mt-4 font-black">Compter</p>
                                        <p className="mt-1 text-xs font-semibold text-slate-500">Inventaire physique</p>
                                    </button>
                                )}
                            </div>
                        </section>

                        <section className="rounded-2xl border border-slate-200 bg-white p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h2 className="font-black">Installer sur ce mobile</h2>
                                    <p className="mt-1 text-xs font-semibold text-slate-500">Accès plein écran depuis l'accueil</p>
                                </div>
                                <button onClick={installApp} className="flex h-11 items-center gap-2 rounded-xl bg-slate-950 px-4 text-xs font-black text-white">
                                    <Download className="h-4 w-4" /> Installer
                                </button>
                            </div>
                        </section>

                        <section>
                            <div className="mb-3 flex items-center justify-between">
                                <h2 className="text-lg font-black">Derniers mouvements</h2>
                                <button onClick={() => setView('moves')} className="text-xs font-black text-blue-700">Tout voir</button>
                            </div>
                            <MovementList moves={moves.slice(0, 5)} />
                        </section>
                    </div>
                ) : view === 'scan' ? (
                    <div className="space-y-4">
                        <button onClick={() => setScannerOpen(true)} className="flex h-16 w-full items-center justify-center gap-3 rounded-xl bg-blue-600 font-black text-white shadow-sm">
                            <Camera className="h-6 w-6" /> Ouvrir la caméra
                        </button>
                        <p className="text-center text-xs font-semibold text-slate-500">Les lecteurs Bluetooth/USB fonctionnent aussi directement.</p>
                        <ProductSearch variants={variants} value={search} onChange={setSearch} onSelect={selectForCurrentContext} autoFocus />
                    </div>
                ) : view === 'moves' ? (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h2 className="text-xl font-black">Traçabilité récente</h2>
                                <p className="text-xs font-semibold text-slate-500">100 derniers mouvements</p>
                            </div>
                            <button onClick={() => movesQuery.refetch()} className="flex h-11 w-11 items-center justify-center rounded-xl bg-white text-slate-600 shadow-sm">
                                <RefreshCw className={`h-5 w-5 ${movesQuery.isFetching ? 'animate-spin' : ''}`} />
                            </button>
                        </div>
                        <MovementList moves={moves} />
                    </div>
                ) : (
                    <InventoryMobile
                        sessions={openSessions}
                        selectedSession={selectedSession}
                        setSelectedSessionId={setSelectedSessionId}
                        variants={variants}
                        locations={internalLocations}
                        search={countSearch}
                        setSearch={setCountSearch}
                        item={countItem}
                        setItem={setCountItem}
                        locationId={countLocationId}
                        setLocationId={setCountLocationId}
                        quantity={countQuantity}
                        setQuantity={setCountQuantity}
                        onSubmit={() => countMutation.mutate()}
                        pending={countMutation.isPending}
                        online={online}
                        onScan={() => setScannerOpen(true)}
                    />
                )}
            </main>

            <BottomNavigation view={view} setView={setView} canCount={permissions.count} />

            {scannerOpen && <ScannerOverlay onClose={() => setScannerOpen(false)} onDetected={handleDetected} />}
            {selectedItem && !action && (
                <VariantSheet
                    item={selectedItem}
                    locations={locations}
                    permissions={permissions}
                    onClose={() => setSelectedItem(null)}
                    onAction={(type, item) => setAction({ type, item })}
                />
            )}
            {action?.item && (
                <StockActionSheet
                    type={action.type}
                    item={action.item}
                    locations={locations}
                    online={online}
                    pending={movementMutation.isPending}
                    onClose={() => setAction(null)}
                    onSubmit={(form) => movementMutation.mutate({ type: action.type, item: action.item, form })}
                />
            )}
        </div>
    );
}

function MovementList({ moves }) {
    if (!moves.length) {
        return <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm font-semibold text-slate-500">Aucun mouvement récent.</div>;
    }
    return (
        <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
            {moves.map((move) => {
                const inbound = move.location_to_name && !move.location_from_name;
                const outbound = move.location_from_name && !move.location_to_name;
                const Icon = inbound ? ArrowDownToLine : outbound ? ArrowUpFromLine : ArrowLeftRight;
                return (
                    <div key={move.id} className="flex items-start gap-3 px-4 py-3">
                        <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                            inbound ? 'bg-emerald-50 text-emerald-700' : outbound ? 'bg-orange-50 text-orange-700' : 'bg-blue-50 text-blue-700'
                        }`}>
                            <Icon className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-black text-slate-950">{move.item_name}</p>
                            <p className="mt-0.5 truncate text-xs font-semibold text-slate-500">{move.transaction_type}</p>
                            <p className="mt-1 text-[10px] font-bold uppercase text-slate-400">{formatDate(move.created_at)} · {move.author}</p>
                        </div>
                        <p className="shrink-0 font-black text-slate-950">{formatQty(move.quantity_change)}</p>
                    </div>
                );
            })}
        </div>
    );
}

function InventoryMobile({
    sessions,
    selectedSession,
    setSelectedSessionId,
    variants,
    locations,
    search,
    setSearch,
    item,
    setItem,
    locationId,
    setLocationId,
    quantity,
    setQuantity,
    onSubmit,
    pending,
    online,
    onScan,
}) {
    if (!selectedSession) {
        return (
            <div className="space-y-4">
                <div>
                    <h2 className="text-xl font-black">Campagnes ouvertes</h2>
                    <p className="text-xs font-semibold text-slate-500">Choisissez la zone à compter.</p>
                </div>
                <div className="space-y-3">
                    {sessions.map((session) => {
                        const counted = session.lines.filter((line) => line.counted_quantity !== null && line.counted_quantity !== undefined).length;
                        return (
                            <button
                                key={session.id}
                                onClick={() => setSelectedSessionId(session.id)}
                                className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="font-black text-slate-950">{session.name}</p>
                                        <p className="mt-1 text-xs font-semibold text-slate-500">{session.location?.name || 'Toutes zones'} · {session.reference}</p>
                                    </div>
                                    <ChevronRight className="h-5 w-5 text-slate-400" />
                                </div>
                                <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
                                    <div className="h-full bg-violet-600" style={{ width: `${session.lines.length ? Math.round((counted / session.lines.length) * 100) : 0}%` }} />
                                </div>
                                <p className="mt-2 text-xs font-bold text-slate-500">{counted} / {session.lines.length} lignes comptées</p>
                            </button>
                        );
                    })}
                    {!sessions.length && (
                        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
                            <ClipboardCheck className="mx-auto h-10 w-10 text-slate-300" />
                            <p className="mt-3 font-black text-slate-700">Aucune campagne ouverte</p>
                            <p className="mt-1 text-sm text-slate-500">Le chef de stock crée et cadre la campagne depuis la version bureau.</p>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    const countedLines = selectedSession.lines.filter((line) => line.counted_quantity !== null && line.counted_quantity !== undefined);
    const allowedLocationIds = (() => {
        if (!selectedSession.location_id) return new Set(locations.map((location) => location.id));
        const collect = (parentId) => [
            parentId,
            ...locations
                .filter((location) => location.parent_id === parentId)
                .flatMap((location) => collect(location.id)),
        ];
        return new Set(collect(selectedSession.location_id));
    })();
    return (
        <div className="space-y-4">
            <button onClick={() => setSelectedSessionId(null)} className="flex items-center gap-2 text-sm font-black text-slate-600">
                <ChevronLeft className="h-5 w-5" /> Campagnes
            </button>
            <section className="rounded-2xl bg-violet-700 p-5 text-white">
                <p className="text-xs font-black uppercase text-violet-200">Comptage en cours</p>
                <h2 className="mt-1 text-xl font-black">{selectedSession.name}</h2>
                <p className="mt-1 text-sm font-semibold text-violet-100">{selectedSession.location?.name || 'Toutes zones'}</p>
                <div className="mt-4 flex items-center justify-between text-xs font-bold">
                    <span>{countedLines.length} / {selectedSession.lines.length} lignes</span>
                    {selectedSession.blind_counting && <span className="rounded-full bg-white/15 px-2 py-1">Comptage aveugle</span>}
                </div>
            </section>

            {!item ? (
                <>
                    <button onClick={onScan} className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-slate-950 font-black text-white">
                        <Camera className="h-5 w-5" /> Scanner l'article
                    </button>
                    <ProductSearch variants={variants} value={search} onChange={setSearch} onSelect={setItem} />
                </>
            ) : (
                <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <p className="font-mono text-xs font-bold text-violet-700">{item.reference}</p>
                            <h3 className="mt-1 font-black text-slate-950">{item.productName}</h3>
                        </div>
                        <button onClick={() => setItem(null)} className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100"><X className="h-4 w-4" /></button>
                    </div>
                    <label className="block">
                        <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Emplacement compté</span>
                        <select value={locationId} onChange={(event) => setLocationId(event.target.value)} className="h-14 w-full rounded-xl border border-slate-200 bg-white px-4 font-bold">
                            <option value="">Choisir l'emplacement</option>
                            {locations
                                .filter((location) => allowedLocationIds.has(location.id))
                                .map((location) => <option key={location.id} value={location.id}>{location.name}</option>)}
                        </select>
                    </label>
                    <label className="block">
                        <span className="mb-1.5 block text-xs font-black uppercase text-slate-500">Quantité réellement comptée</span>
                        <input
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="any"
                            value={quantity}
                            onChange={(event) => setQuantity(event.target.value)}
                            className="h-20 w-full rounded-xl border-2 border-violet-200 text-center text-4xl font-black outline-none focus:border-violet-600"
                            placeholder="0"
                        />
                    </label>
                    <button
                        disabled={!online || !locationId || quantity === '' || Number(quantity) < 0 || pending}
                        onClick={onSubmit}
                        className="flex h-14 w-full items-center justify-center gap-2 rounded-xl bg-violet-700 font-black text-white disabled:bg-slate-200 disabled:text-slate-400"
                    >
                        {pending ? <RefreshCw className="h-5 w-5 animate-spin" /> : <PackageCheck className="h-5 w-5" />}
                        Enregistrer le comptage
                    </button>
                </section>
            )}

            <section>
                <h3 className="mb-2 text-xs font-black uppercase tracking-wider text-slate-400">Dernières lignes comptées</h3>
                <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
                    {countedLines.slice(-8).reverse().map((line) => (
                        <div key={line.id} className="flex items-center gap-3 px-4 py-3">
                            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-50 text-emerald-700"><Check className="h-5 w-5" /></div>
                            <div className="min-w-0 flex-1">
                                <p className="truncate font-bold">{line.variant?.reference || `Variante #${line.variant_id}`}</p>
                                <p className="text-xs text-slate-500">{line.location?.name}</p>
                            </div>
                            <p className="text-lg font-black">{formatQty(line.counted_quantity)}</p>
                        </div>
                    ))}
                    {!countedLines.length && <p className="px-4 py-6 text-center text-sm font-semibold text-slate-500">Aucun comptage enregistré.</p>}
                </div>
            </section>
        </div>
    );
}
