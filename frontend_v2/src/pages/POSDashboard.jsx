import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import { 
    Search, CreditCard, Banknote, ShoppingCart, Trash2, 
    X, Check, Lock, Unlock, MonitorSpeaker, ScanBarcode, Menu,
    Pause, Play, Printer, BarChart3, ArrowRightLeft, FileText, Landmark, Settings
} from 'lucide-react';
import Sidebar from '../components/Sidebar';

export default function POSDashboard() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);
    
    // Items & Search
    const [items, setItems] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    
    // Cart
    const [cart, setCart] = useState([]);
    
    // Checkout Modal
    const [showCheckout, setShowCheckout] = useState(false);
    const [amountPaid, setAmountPaid] = useState('');
    const [paymentMethod, setPaymentMethod] = useState('CASH');
    
    // Pro Features
    const [selectedCategory, setSelectedCategory] = useState('ALL');
    const [selectedClient, setSelectedClient] = useState('');
    const [parkedCarts, setParkedCarts] = useState([]);
    const [showReceipt, setShowReceipt] = useState(false);
    const [lastOrder, setLastOrder] = useState(null);
    
    // Operator Lock (PIN)
    const [isLocked, setIsLocked] = useState(true);
    const [pinBuffer, setPinBuffer] = useState('');
    const [operatorName, setOperatorName] = useState('Anonyme');
    
    // Session Open
    const [startingCash, setStartingCash] = useState('');

    // Report Dashboard
    const [showReport, setShowReport] = useState(false);
    const [reportData, setReportData] = useState(null);

    // Industrialization V2 Features
    const [isOffline, setIsOffline] = useState(!navigator.onLine);
    const [offlineQueue, setOfflineQueue] = useState([]);
    const [isRefundMode, setIsRefundMode] = useState(false);
    
    const [editingItem, setEditingItem] = useState(null);
    const [editPrice, setEditPrice] = useState('');
    const [editStock, setEditStock] = useState('');

    const [showMovement, setShowMovement] = useState(false);
    const [movementType, setMovementType] = useState('OUT');
    const [movementAmount, setMovementAmount] = useState('');
    const [movementReason, setMovementReason] = useState('');

    const [showInvoicePayment, setShowInvoicePayment] = useState(false);
    const [pendingInvoices, setPendingInvoices] = useState([]);
    const [selectedInvoice, setSelectedInvoice] = useState(null);
    const [invoicePaymentAmount, setInvoicePaymentAmount] = useState('');
    const [invoicePaymentMethod, setInvoicePaymentMethod] = useState('CASH');

    const [showSettings, setShowSettings] = useState(false);
    const [posSettings, setPosSettings] = useState({
        storeName: 'MMG - Atelier Principal',
        storeAddress: '123 Rue de la Production',
        ticketFooter: 'Merci de votre visite !',
        autoPrint: true
    });

    useEffect(() => {
        const savedSettings = localStorage.getItem('pos_settings');
        if (savedSettings) {
            setPosSettings(JSON.parse(savedSettings));
        }

        const handleOnline = () => setIsOffline(false);
        const handleOffline = () => setIsOffline(true);
        window.addEventListener('online', handleOnline);
        window.addEventListener('offline', handleOffline);
        return () => {
            window.removeEventListener('online', handleOnline);
            window.removeEventListener('offline', handleOffline);
        };
    }, []);

    // Auto-Sync offline queue
    useEffect(() => {
        if (!isOffline && offlineQueue.length > 0) {
            const syncQueue = async () => {
                const q = [...offlineQueue];
                setOfflineQueue([]);
                for (let payload of q) {
                    try {
                        await api.post('/v2/pos/checkout', payload);
                    } catch(e) {
                        console.error('Failed to sync ticket', e);
                    }
                }
                alert(`${q.length} tickets synchronisés avec succès !`);
            };
            syncQueue();
        }
    }, [isOffline, offlineQueue]);

    const fetchReport = async () => {
        if (!session) return;
        try {
            const res = await api.get(`/v2/pos/sessions/${session.id}/report`);
            setReportData(res.data);
            setShowReport(true);
        } catch(e) {
            console.error(e);
        }
    };

    const searchInputRef = useRef(null);

    useEffect(() => {
        checkSession();
        fetchItems();
    }, []);

    // --- BARCODE SCANNER LOGIC ---
    useEffect(() => {
        let buffer = '';
        let timeout = null;

        const handleKeyDown = (e) => {
            // Ignore if typing in an input field (except body)
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

            if (e.key === 'Enter') {
                if (buffer.length > 2) {
                    handleScan(buffer);
                }
                buffer = '';
            } else {
                buffer += e.key;
                clearTimeout(timeout);
                timeout = setTimeout(() => { buffer = ''; }, 100); // 100ms max between keys for barcode scanner
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [items, cart]);

    const handleScan = (code) => {
        const item = items.find(i => i.barcode === code);
        if (item) {
            addToCart(item);
        } else {
            // Optional: alert or visual beep for missed item
            console.warn("Item scanned not found: ", code);
        }
    };

    const checkSession = async () => {
        try {
            const res = await api.get('/v2/pos/sessions/active');
            setSession(res.data);
        } catch (e) {
            setSession(null);
        } finally {
            setLoading(false);
        }
    };

    const fetchItems = async () => {
        try {
            const res = await api.get('/v2/pos/items');
            setItems(res.data);
        } catch (e) {
            console.error(e);
        }
    };

    const handleOpenSession = async (e) => {
        e.preventDefault();
        try {
            const res = await api.post(`/v2/pos/sessions/open?starting_cash=${startingCash || 0}`);
            setSession(res.data);
            setStartingCash('');
        } catch (e) {
            alert("Erreur lors de l'ouverture de caisse");
        }
    };

    const handleCloseSession = async () => {
        const actual = prompt("Montant compté en caisse ?");
        if (actual !== null) {
            try {
                const res = await api.post(`/v2/pos/sessions/${session.id}/close?closing_cash=${actual}`);
                alert(`Caisse fermée. \nAttendu: ${res.data.expected}€ \nCompté: ${res.data.actual}€`);
                setSession(null);
            } catch (e) {
                alert("Erreur");
            }
        }
    };

    // --- CART LOGIC ---
    const addToCart = (item) => {
        const qtyToAdd = isRefundMode ? -1 : 1;
        setCart(prev => {
            const existing = prev.find(i => i.variant_id === item.variant_id);
            if (existing) {
                return prev.map(i => i.variant_id === item.variant_id ? { ...i, quantity: i.quantity + qtyToAdd } : i);
            }
            return [...prev, { variant_id: item.variant_id, product_name: item.product_name, price: item.price, quantity: qtyToAdd, stock: item.stock }];
        });
        if(isRefundMode) setIsRefundMode(false); // Reset after scan
    };

    const updateQuantity = (id, delta) => {
        setCart(prev => prev.map(i => {
            if (i.variant_id === id) {
                // If refund mode, allow negative. Otherwise restrict to > 0 unless removing
                const newQ = i.quantity + delta;
                return { ...i, quantity: newQ };
            }
            return i;
        }).filter(i => i.quantity !== 0));
    };
    
    const updateCartItemPrice = (id, newPrice) => {
        setCart(prev => prev.map(i => i.variant_id === id ? { ...i, price: parseFloat(newPrice) || 0 } : i));
    };

    const cartTotal = cart.reduce((acc, curr) => acc + (curr.price * curr.quantity), 0);
    
    const parkCart = () => {
        if(cart.length === 0) return;
        setParkedCarts(prev => [...prev, { id: Date.now(), items: [...cart], total: cartTotal }]);
        setCart([]);
    };
    
    const resumeCart = (id) => {
        const p = parkedCarts.find(c => c.id === id);
        if(p) {
            if(cart.length > 0) {
                // Park current before resuming
                setParkedCarts(prev => [...prev.filter(c => c.id !== id), { id: Date.now(), items: [...cart], total: cartTotal }]);
            } else {
                setParkedCarts(prev => prev.filter(c => c.id !== id));
            }
            setCart(p.items);
        }
    };

    const handleCheckout = async (e) => {
        e.preventDefault();
        const payload = {
            items: cart.map(i => ({ variant_id: i.variant_id, quantity: i.quantity, price: i.price, product_name: i.product_name })),
            payment_method: paymentMethod,
            amount_paid: amountPaid ? parseFloat(amountPaid) : cartTotal,
            seller_name: operatorName
        };

        if (isOffline) {
            setOfflineQueue(prev => [...prev, payload]);
            setLastOrder({...payload, reference: `OFFLINE-${Date.now()}`, date: new Date(), amount_total: cartTotal, amount_return: (payload.amount_paid - cartTotal)});
            setCart([]);
            setShowCheckout(false);
            setAmountPaid('');
            setShowReceipt(true);
            return;
        }

        try {
            const res = await api.post('/v2/pos/checkout', payload);
            setLastOrder({...res.data, items: cart});
            setCart([]);
            setShowCheckout(false);
            setAmountPaid('');
            setShowReceipt(true);
            // Optionally auto-lock after checkout
            // setIsLocked(true);
        } catch (e) {
            alert("Erreur lors de l'encaissement.");
            console.error(e);
        }
    };
    
    const saveZeroUIEdit = async (e) => {
        e.preventDefault();
        if(!editingItem) return;
        try {
            await api.put(`/v2/pos/items/${editingItem.variant_id}?price=${editPrice}&stock=${editStock}`);
            setItems(prev => prev.map(i => i.variant_id === editingItem.variant_id ? { ...i, price: parseFloat(editPrice), stock: parseFloat(editStock) } : i));
            setEditingItem(null);
        } catch(err) {
            alert("Erreur lors de la mise à jour");
        }
    };

    const handleCashMovement = async (e) => {
        e.preventDefault();
        try {
            await api.post(`/v2/pos/sessions/${session.id}/movements`, {
                movement_type: movementType,
                amount: parseFloat(movementAmount),
                reason: movementReason,
                author: operatorName
            });
            setShowMovement(false);
            setMovementAmount('');
            setMovementReason('');
            alert('Mouvement enregistré avec succès');
        } catch(err) {
            alert('Erreur lors du mouvement');
            console.error(err);
        }
    };

    const openInvoiceModal = async () => {
        try {
            const res = await api.get('/v2/pos/invoices/pending');
            setPendingInvoices(res.data);
            setShowInvoicePayment(true);
        } catch(e) {
            console.error(e);
        }
    };

    const handleInvoicePayment = async (e) => {
        e.preventDefault();
        if(!selectedInvoice) return;
        try {
            await api.post(`/v2/pos/invoices/${selectedInvoice.id}/pay`, {
                amount: parseFloat(invoicePaymentAmount),
                method: invoicePaymentMethod,
                author: operatorName
            });
            setShowInvoicePayment(false);
            setSelectedInvoice(null);
            setInvoicePaymentAmount('');
            alert('Facture encaissée avec succès');
        } catch(err) {
            alert('Erreur lors de l\'encaissement de la facture');
            console.error(err);
        }
    };

    const savePosSettings = (e) => {
        e.preventDefault();
        localStorage.setItem('pos_settings', JSON.stringify(posSettings));
        setShowSettings(false);
        alert('Paramètres du terminal sauvegardés.');
    };

    const handlePinEntry = (num) => {
        if (pinBuffer.length < 4) {
            const newPin = pinBuffer + num;
            setPinBuffer(newPin);
            if (newPin.length === 4) {
                // Mock PIN validation
                if (newPin === '1234') { setOperatorName('Manager (1234)'); setIsLocked(false); }
                else if (newPin === '0000') { setOperatorName('Vendeur 1 (0000)'); setIsLocked(false); }
                else { alert('Code PIN invalide. (Essayez 1234 ou 0000)'); }
                setPinBuffer('');
            }
        }
    };

    const filteredItems = items.filter(i => {
        const matchesSearch = i.product_name.toLowerCase().includes(searchTerm.toLowerCase()) || 
            i.reference.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (i.barcode && i.barcode.includes(searchTerm));
        const matchesCategory = selectedCategory === 'ALL' || i.category === selectedCategory;
        return matchesSearch && matchesCategory;
    });

    const categories = ['ALL', ...new Set(items.map(i => i.category || 'Général'))];

    if (loading) return <div className="p-8 text-center">Chargement module caisse...</div>;

    if (!session) {
        return (
            <div className="min-h-screen bg-slate-50 flex">
                <Sidebar activeView="pos" isOpen={isSidebarOpen} setIsOpen={setIsSidebarOpen} />
                <main className="flex-1 lg:ml-72 transition-all duration-300 relative flex items-center justify-center bg-slate-900 border-l border-slate-800">
                    <div className="bg-white p-10 rounded-3xl shadow-2xl max-w-sm w-full text-center">
                        <MonitorSpeaker className="w-16 h-16 text-indigo-500 mx-auto mb-6" />
                        <h2 className="text-2xl font-black mb-2 text-slate-800">Caisse Fermée</h2>
                        <p className="text-slate-500 mb-8 font-medium">Veuillez ouvrir une session pour démarrer les ventes au comptoir.</p>
                        <form onSubmit={handleOpenSession}>
                            <label className="block text-left text-sm font-bold text-slate-700 mb-2">Fond de caisse initial (€)</label>
                            <input 
                                type="number" 
                                required
                                value={startingCash}
                                onChange={(e) => setStartingCash(e.target.value)}
                                className="w-full text-center text-2xl p-4 bg-slate-50 border border-slate-200 rounded-xl mb-6 font-mono"
                                placeholder="0.00"
                            />
                            <button type="submit" className="w-full py-4 bg-indigo-600 hover:bg-indigo-500 text-white font-black rounded-xl text-lg flex items-center justify-center gap-2 transition-colors shadow-lg shadow-indigo-500/30">
                                <Unlock className="w-5 h-5"/> Ouvrir la Session
                            </button>
                        </form>
                    </div>
                </main>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 flex overflow-hidden">
            <Sidebar activeView="pos" isOpen={isSidebarOpen} setIsOpen={setIsSidebarOpen} />
            <main className="flex-1 lg:ml-72 transition-all duration-300 h-screen flex flex-col md:flex-row relative">
                
                {/* L E F T   P A N E - Products */}
                <div className="flex-1 flex flex-col overflow-hidden relative">
                    {/* Header Search & Mobile Toggle */}
                    <div className="bg-white px-6 py-4 border-b border-slate-200 flex justify-between items-center z-10 shadow-sm shrink-0">
                        <div className="flex items-center gap-4 flex-1">
                            <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-lg shrink-0">
                                <Menu className="w-6 h-6" />
                            </button>
                            <div className="bg-slate-100 flex items-center px-4 py-2 rounded-xl border border-transparent focus-within:border-indigo-300 focus-within:bg-white transition-colors w-full max-w-lg">
                                <Search className="w-5 h-5 text-slate-400 mr-2 shrink-0" />
                            <input 
                                ref={searchInputRef}
                                type="text"
                                placeholder="Recherche produit ou Scan douchette..."
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                className="bg-transparent border-none outline-none font-bold text-slate-700 w-full"
                            />
                            {searchTerm && <button onClick={() => setSearchTerm('')}><X className="w-4 h-4 text-slate-400"/></button>}
                        </div>
                    </div>

                    {/* Category Filters */}
                    <div className="bg-white px-6 py-2 border-b border-slate-200 flex gap-2 overflow-x-auto shrink-0 hide-scrollbar">
                        {categories.map(cat => (
                            <button 
                                key={cat}
                                onClick={() => setSelectedCategory(cat)}
                                className={`px-4 py-1.5 rounded-full text-sm font-bold whitespace-nowrap transition-colors ${selectedCategory === cat ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                            >
                                {cat === 'ALL' ? 'Toutes les catégories' : cat}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Products Grid */}
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-indigo-700 bg-indigo-50 p-2 rounded-lg inline-flex text-sm font-bold border border-indigo-100 shadow-sm">
                            <ScanBarcode className="w-4 h-4"/> Prêt à biper
                        </div>
                        <button 
                            onClick={() => setIsRefundMode(!isRefundMode)}
                            className={`px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-colors ${isRefundMode ? 'bg-rose-500 text-white shadow-lg shadow-rose-500/30' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-200'}`}
                        >
                            {isRefundMode ? <><Check className="w-4 h-4"/> Mode Retour Actif</> : 'Activer Mode Retour'}
                        </button>
                    </div>
                    {filteredItems.length === 0 ? (
                        <div className="text-center py-20 text-slate-400 font-bold text-lg">Aucun article trouvé</div>
                    ) : (
                        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-24">
                            {filteredItems.map(item => (
                                <div 
                                    key={item.variant_id} 
                                    className="bg-white border border-slate-200 p-4 rounded-2xl cursor-pointer hover:border-indigo-400 hover:shadow-lg active:scale-95 transition-all flex flex-col select-none relative group"
                                >
                                    <div onClick={() => addToCart(item)} className="absolute inset-0 z-0"></div>
                                    <div className="flex justify-between items-start mb-2 relative z-10 pointer-events-none">
                                        <span className="text-xs font-mono font-bold text-slate-400 bg-slate-50 px-2 py-1 rounded-md max-w-[70%] truncate">{item.reference}</span>
                                        <span className={`text-xs font-black px-2 py-1 rounded-full ${item.stock > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                            Stock: {Math.floor(item.stock)}
                                        </span>
                                    </div>
                                    <h3 className="font-bold text-slate-800 flex-1 break-words leading-tight relative z-10 pointer-events-none mt-2">{item.product_name}</h3>
                                    <div className="mt-3 font-black text-xl text-indigo-600 flex justify-between items-center relative z-10">
                                        <span className="pointer-events-none">{item.price.toFixed(2)} €</span>
                                        
                                        {/* Zero-UI Manager Edit Button */}
                                        {operatorName.toLowerCase().includes('manager') && (
                                            <button 
                                                onClick={(e) => { e.stopPropagation(); setEditingItem(item); setEditPrice(item.price); setEditStock(item.stock); }}
                                                className="opacity-0 group-hover:opacity-100 p-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-all"
                                                title="Modifier (Manager)"
                                            >
                                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* R I G H T   P A N E - Cart */}
            <div className="w-full md:w-[450px] bg-white border-l border-slate-200 flex flex-col shadow-xl z-20 shrink-0 h-full">
                {/* User / Session Top */}
                <div className="p-4 bg-slate-800 text-white flex justify-between items-center shrink-0">
                    <div>
                        <div className="font-bold text-sm text-indigo-300 flex items-center gap-2">
                            Session {session.reference}
                            {isOffline && <span className="px-2 py-0.5 bg-rose-500 text-white text-[10px] font-black rounded-full uppercase">Hors-Ligne ({offlineQueue.length})</span>}
                        </div>
                        <div className="text-xs font-medium text-emerald-400">Opérateur: {operatorName}</div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => setShowSettings(true)} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-slate-300 transition-colors" title="Paramètres Caisse">
                            <Settings className="w-5 h-5"/>
                        </button>
                        <button onClick={openInvoiceModal} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-blue-400 transition-colors" title="Encaisser Facture">
                            <FileText className="w-5 h-5"/>
                        </button>
                        <button onClick={() => setShowMovement(true)} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-emerald-400 transition-colors" title="Mouvements Espèces">
                            <ArrowRightLeft className="w-5 h-5"/>
                        </button>
                        <button onClick={fetchReport} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors" title="Mini Dashboard">
                            <BarChart3 className="w-5 h-5"/>
                        </button>
                        {parkedCarts.length > 0 && (
                            <div className="group relative">
                                <button className="p-2 bg-indigo-500 hover:bg-indigo-400 rounded-lg text-white transition-colors flex items-center gap-1" title="Tickets en attente">
                                    <Pause className="w-5 h-5"/>
                                    <span className="text-xs font-bold bg-white text-indigo-600 px-1.5 py-0.5 rounded-md">{parkedCarts.length}</span>
                                </button>
                                <div className="absolute right-0 top-full mt-2 w-64 bg-white rounded-xl shadow-2xl border border-slate-200 hidden group-hover:block z-50 p-2">
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 px-2 pt-1">Tickets en attente</h4>
                                    {parkedCarts.map(p => (
                                        <div key={p.id} className="flex justify-between items-center p-2 hover:bg-slate-50 rounded-lg border border-slate-100 mb-1">
                                            <div>
                                                <div className="text-sm font-bold text-slate-800">{p.items.length} articles</div>
                                                <div className="text-xs text-indigo-600 font-black">{p.total.toFixed(2)} €</div>
                                            </div>
                                            <button onClick={() => resumeCart(p.id)} className="p-2 bg-indigo-50 text-indigo-600 rounded-md hover:bg-indigo-100"><Play className="w-4 h-4"/></button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                        <button onClick={() => setIsLocked(true)} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white transition-colors" title="Verrouiller Caisse">
                            <Lock className="w-5 h-5"/>
                        </button>
                        <button onClick={handleCloseSession} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-rose-400 transition-colors" title="Fermeture Définitive (Z)">
                            <X className="w-5 h-5"/>
                        </button>
                    </div>
                </div>

                {/* Client Linking */}
                <div className="px-4 py-3 bg-white border-b border-slate-200 shrink-0 flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-400 uppercase">Client :</span>
                    <select 
                        value={selectedClient} 
                        onChange={(e) => setSelectedClient(e.target.value)}
                        className="flex-1 bg-slate-50 border border-slate-200 text-slate-700 text-sm font-bold rounded-lg p-2 outline-none cursor-pointer"
                    >
                        <option value="">Passager (Anonyme)</option>
                        <option value="artisan_jean">Artisan Jean D.</option>
                        <option value="entreprise_dupont">Entreprise Dupont BTP</option>
                    </select>
                </div>

                {/* Ticket Items */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50">
                    {cart.length === 0 ? (
                        <div className="h-full flex flex-col items-center justify-center text-slate-300">
                            <ShoppingCart className="w-16 h-16 border-2 p-3 rounded-full mb-4 border-dashed border-slate-300" />
                            <span className="font-bold">Panier vide</span>
                        </div>
                    ) : (
                        cart.map((c, idx) => (
                            <div key={idx} className="bg-white border border-slate-100 p-3 flex flex-col rounded-xl shadow-sm">
                                <div className="flex justify-between font-bold text-sm text-slate-800 mb-2">
                                    <span className="truncate pr-2">{c.product_name}</span>
                                    <span className="shrink-0">{(c.price * c.quantity).toFixed(2)} €</span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-1">
                                        <input 
                                            type="number" 
                                            value={c.price} 
                                            onChange={(e) => updateCartItemPrice(c.variant_id, e.target.value)}
                                            className="w-16 text-xs font-mono text-slate-600 p-1 border border-slate-200 rounded text-right bg-white"
                                        />
                                        <span className="text-xs text-slate-400">€ / u</span>
                                    </div>
                                    <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
                                        <button onClick={()=>updateQuantity(c.variant_id, -1)} className="w-7 h-7 bg-white text-slate-600 rounded-md font-bold shadow-sm hover:text-red-500">-</button>
                                        <span className="font-black text-slate-800 min-w-[30px] text-center">{c.quantity}</span>
                                        <button onClick={()=>updateQuantity(c.variant_id, 1)} className="w-7 h-7 bg-white text-slate-600 rounded-md font-bold shadow-sm hover:text-emerald-500">+</button>
                                    </div>
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Footer Totals & Pay */}
                <div className="bg-white p-6 border-t border-slate-200 shrink-0 shadow-[0_-10px_20px_-10px_rgba(0,0,0,0.05)]">
                    <div className="flex justify-between items-end mb-4">
                        <span className="font-black text-slate-400 uppercase tracking-wider text-sm">TOTAL A PAYER</span>
                        <span className="font-black text-4xl text-slate-800 tracking-tighter">{cartTotal.toFixed(2)} <span className="text-xl">€</span></span>
                    </div>
                    <div className="flex gap-2">
                        <button 
                            disabled={cart.length === 0}
                            onClick={parkCart}
                            className="px-4 py-5 bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-600 font-bold rounded-2xl transition-colors shadow-sm"
                            title="Mettre en attente"
                        >
                            <Pause className="w-6 h-6"/>
                        </button>
                        <button 
                            disabled={cart.length === 0}
                            onClick={() => setShowCheckout(true)}
                            className="flex-1 py-5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xl font-black rounded-2xl flex items-center justify-center gap-3 transition-all shadow-xl shadow-indigo-500/30"
                        >
                            <ShoppingCart className="w-6 h-6"/> ENCAISSER
                        </button>
                    </div>
                </div>
            </div>

            {/* C H E C K O U T   M O D A L */}
            {showCheckout && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl overflow-hidden max-w-md w-full flex flex-col animate-in zoom-in-95 duration-200">
                        <div className="px-6 py-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                            <h3 className="font-black text-xl flex items-center gap-2 text-slate-800">
                                Clôture du Ticket
                            </h3>
                            <button onClick={() => setShowCheckout(false)} className="bg-white border border-slate-200 hover:bg-slate-100 p-2 rounded-full text-slate-500 shadow-sm"><X className="w-5 h-5"/></button>
                        </div>

                        <form onSubmit={handleCheckout} className="p-6">
                            <div className="text-center mb-8">
                                <div className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-1">Montant</div>
                                <div className="text-5xl font-black text-indigo-600">{cartTotal.toFixed(2)} €</div>
                            </div>
                            
                            <div className="mb-6 grid grid-cols-2 md:grid-cols-5 gap-3">
                                <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${paymentMethod === 'CASH' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="CASH" checked={paymentMethod==='CASH'} onChange={()=>setPaymentMethod('CASH')} className="hidden" />
                                    <Banknote className="w-6 h-6 mb-1" />
                                    <span className="font-bold text-xs">Espèces</span>
                                </label>
                                <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${paymentMethod === 'CB' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="CB" checked={paymentMethod==='CB'} onChange={()=>setPaymentMethod('CB')} className="hidden" />
                                    <CreditCard className="w-6 h-6 mb-1" />
                                    <span className="font-bold text-xs">Carte</span>
                                </label>
                                <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${paymentMethod === 'MOBO' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="MOBO" checked={paymentMethod==='MOBO'} onChange={()=>setPaymentMethod('MOBO')} className="hidden" />
                                    <svg className="w-6 h-6 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                                    <span className="font-bold text-xs">Mobile</span>
                                </label>
                                <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${paymentMethod === 'CHEQUE' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="CHEQUE" checked={paymentMethod==='CHEQUE'} onChange={()=>setPaymentMethod('CHEQUE')} className="hidden" />
                                    <FileText className="w-6 h-6 mb-1" />
                                    <span className="font-bold text-xs">Chèque</span>
                                </label>
                                <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${paymentMethod === 'TRANSFER' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="TRANSFER" checked={paymentMethod==='TRANSFER'} onChange={()=>setPaymentMethod('TRANSFER')} className="hidden" />
                                    <Landmark className="w-6 h-6 mb-1" />
                                    <span className="font-bold text-xs">Virement</span>
                                </label>
                            </div>

                            {paymentMethod === 'CASH' && (
                                <div className="mb-8">
                                    <label className="block text-xs font-black text-slate-400 mb-2 uppercase">Espèces reçues (€)</label>
                                    <div className="flex gap-2 mb-3">
                                        {[10, 20, 50].map(val => (
                                            <button 
                                                key={val} 
                                                type="button"
                                                onClick={() => setAmountPaid(val.toString())} 
                                                className="flex-1 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-lg text-sm transition-colors border border-slate-200"
                                            >
                                                {val} €
                                            </button>
                                        ))}
                                        <button 
                                            type="button"
                                            onClick={() => setAmountPaid(cartTotal.toString())} 
                                            className="flex-[1.5] py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-bold rounded-lg text-sm transition-colors border border-indigo-200"
                                        >
                                            Montant Exact
                                        </button>
                                    </div>
                                    <input 
                                        type="number" 
                                        step="0.01"
                                        min={cartTotal.toString()}
                                        value={amountPaid}
                                        onChange={e => setAmountPaid(e.target.value)}
                                        className="w-full text-center text-3xl font-mono p-4 bg-slate-50 border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500"
                                        placeholder={cartTotal.toFixed(2)}
                                    />
                                    {amountPaid && parseFloat(amountPaid) >= cartTotal && (
                                        <div className="mt-3 flex justify-between font-bold text-sm bg-emerald-50 text-emerald-700 p-3 rounded-lg border border-emerald-100">
                                            A rendre : <span>{(parseFloat(amountPaid) - cartTotal).toFixed(2)} €</span>
                                        </div>
                                    )}
                                </div>
                            )}

                            <button type="submit" className="w-full py-4 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-black text-lg flex justify-center items-center gap-2 shadow-lg">
                                Ваlider et Vendre
                            </button>
                        </form>
                    </div>
                </div>
            )}
            
            {/* R E C E I P T   M O D A L */}
            {showReceipt && lastOrder && (
                <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl overflow-hidden max-w-sm w-full flex flex-col">
                        <div className="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                            <h3 className="font-black text-lg text-slate-800">Ticket Enregistré</h3>
                            <button onClick={() => setShowReceipt(false)} className="bg-white border border-slate-200 hover:bg-slate-100 p-2 rounded-full text-slate-500 shadow-sm"><X className="w-5 h-5"/></button>
                        </div>
                        
                        {/* Printable Area (80mm width approximation ~ 300px) */}
                        <div id="printable-receipt" className="p-6 bg-white font-mono text-xs text-slate-800 mx-auto w-[300px]">
                            <div className="text-center font-bold text-lg mb-2">MMG INDUSTRIE</div>
                            <div className="text-center mb-4 text-[10px]">123 Avenue de l'Atelier<br/>75000 PARIS<br/>TVA: FR123456789</div>
                            
                            <div className="border-b border-dashed border-slate-300 pb-2 mb-2">
                                <div>Ticket: {lastOrder.reference}</div>
                                <div>Date: {new Date(lastOrder.date).toLocaleString()}</div>
                                <div>Vendeur: {session.opened_by_user}</div>
                            </div>
                            
                            <div className="border-b border-dashed border-slate-300 pb-2 mb-2 space-y-1">
                                {lastOrder.items.map((it, idx) => (
                                    <div key={idx} className="flex justify-between">
                                        <div className="max-w-[180px] truncate">{it.quantity}x {it.product_name}</div>
                                        <div>{(it.price * it.quantity).toFixed(2)}</div>
                                    </div>
                                ))}
                            </div>
                            
                            <div className="text-right font-bold text-sm mb-1">
                                TOTAL TTC: {lastOrder.amount_total.toFixed(2)} €
                            </div>
                            <div className="text-right text-[10px] text-slate-500 mb-2">
                                TVA ({lastOrder.tax_rate}%): {(lastOrder.amount_total - (lastOrder.amount_total / (1 + lastOrder.tax_rate/100))).toFixed(2)} €
                            </div>
                            
                            <div className="border-t border-dashed border-slate-300 pt-2 text-[10px]">
                                <div className="flex justify-between"><span>Payé par {lastOrder.payment_method}</span> <span>{lastOrder.amount_paid.toFixed(2)} €</span></div>
                                <div className="flex justify-between"><span>Rendu</span> <span>{lastOrder.amount_return.toFixed(2)} €</span></div>
                            </div>
                            
                            <div className="mt-4 text-center">
                                <div className="text-[8px] text-slate-400 mt-2">Certifié NF525</div>
                            </div>
                        </div>
                        
                        <div className="p-4 bg-slate-50 border-t border-slate-200 flex gap-3">
                            <button onClick={() => setShowReceipt(false)} className="flex-1 py-3 bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 font-bold rounded-xl transition-colors">
                                Nouveau Client
                            </button>
                            <button 
                                onClick={() => {
                                    const printContent = document.getElementById('printable-receipt').innerHTML;
                                    const printWindow = window.open('', '', 'width=350,height=600');
                                    printWindow.document.write('<html><head><title>Print Receipt</title>');
                                    printWindow.document.write('<style>body { font-family: monospace; font-size: 12px; margin: 0; padding: 10px; width: 80mm; } .text-center{text-align:center;} .flex{display:flex;} .justify-between{justify-content:space-between;} .border-b{border-bottom:1px dashed #ccc;} .border-t{border-top:1px dashed #ccc;} .pb-2{padding-bottom:8px;} .pt-2{padding-top:8px;} .mb-2{margin-bottom:8px;} .mb-4{margin-bottom:16px;} .mt-4{margin-top:16px;} .font-bold{font-weight:bold;} .text-lg{font-size:16px;} .text-sm{font-size:14px;}</style>');
                                    printWindow.document.write('</head><body>');
                                    printWindow.document.write(printContent);
                                    printWindow.document.write('</body></html>');
                                    printWindow.document.close();
                                    printWindow.print();
                                    printWindow.close();
                                }}
                                className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl flex items-center justify-center gap-2 shadow-lg"
                            >
                                <Printer className="w-5 h-5"/> Imprimer
                            </button>
                        </div>
                    </div>
                </div>
            )}
            
            {/* R E P O R T   M O D A L */}
            {showReport && reportData && (
                <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col max-h-[90vh]">
                        <div className="p-6 bg-slate-800 text-white flex justify-between items-center shrink-0">
                            <div>
                                <h3 className="text-xl font-black flex items-center gap-2">
                                    <BarChart3 className="w-6 h-6 text-indigo-400"/>
                                    Rapport de Session
                                </h3>
                                <p className="text-slate-400 text-sm mt-1">{reportData.session_reference}</p>
                            </div>
                            <button onClick={() => setShowReport(false)} className="text-slate-400 hover:text-white p-2 rounded-full hover:bg-slate-700 transition-colors">
                                <X className="w-6 h-6" />
                            </button>
                        </div>
                        
                        <div className="p-6 overflow-y-auto">
                            <div className="grid grid-cols-2 gap-4 mb-6">
                                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
                                    <div className="text-xs font-bold text-slate-500 uppercase">Fond initial</div>
                                    <div className="text-xl font-black text-slate-800">{reportData.starting_cash.toFixed(2)} €</div>
                                </div>
                                <div className="bg-indigo-50 p-4 rounded-2xl border border-indigo-100">
                                    <div className="text-xs font-bold text-indigo-500 uppercase">Chiffre d'Affaires</div>
                                    <div className="text-xl font-black text-indigo-700">{reportData.total_sales.toFixed(2)} €</div>
                                </div>
                            </div>

                            <div className="space-y-3 mb-6">
                                <div className="flex justify-between items-center p-3 bg-white border border-slate-200 rounded-xl">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-emerald-100 text-emerald-600 rounded-lg"><Banknote className="w-5 h-5"/></div>
                                        <span className="font-bold text-slate-700">Espèces Encaissées</span>
                                    </div>
                                    <span className="font-black text-lg text-slate-800">{reportData.total_cash_collected.toFixed(2)} €</span>
                                </div>
                                <div className="flex justify-between items-center p-3 bg-white border border-slate-200 rounded-xl">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-blue-100 text-blue-600 rounded-lg"><CreditCard className="w-5 h-5"/></div>
                                        <span className="font-bold text-slate-700">Cartes Bancaires</span>
                                    </div>
                                    <span className="font-black text-lg text-slate-800">{reportData.total_cb_collected.toFixed(2)} €</span>
                                </div>
                            </div>

                            <div className="bg-slate-800 text-white p-5 rounded-2xl flex justify-between items-center mb-6 shadow-lg shadow-slate-800/20">
                                <div>
                                    <div className="text-sm font-bold text-slate-400">Total Espèces Attendu (Tiroir)</div>
                                    <div className="text-2xl font-black text-emerald-400">{reportData.expected_cash_in_drawer.toFixed(2)} €</div>
                                </div>
                                <div className="text-right">
                                    <div className="text-sm font-bold text-slate-400">Tickets émis</div>
                                    <div className="text-xl font-black">{reportData.ticket_count}</div>
                                </div>
                            </div>

                            <div className="flex gap-4 mb-6">
                                <div className="flex-1 bg-emerald-50 p-3 rounded-xl border border-emerald-100 flex justify-between items-center">
                                    <span className="text-xs font-bold text-emerald-700 uppercase">Entrées Cash</span>
                                    <span className="font-black text-emerald-800">+{reportData.cash_in?.toFixed(2) || '0.00'} €</span>
                                </div>
                                <div className="flex-1 bg-rose-50 p-3 rounded-xl border border-rose-100 flex justify-between items-center">
                                    <span className="text-xs font-bold text-rose-700 uppercase">Sorties Cash</span>
                                    <span className="font-black text-rose-800">-{reportData.cash_out?.toFixed(2) || '0.00'} €</span>
                                </div>
                            </div>

                            {reportData.top_products.length > 0 && (
                                <div>
                                    <h4 className="font-bold text-slate-800 mb-3 text-sm uppercase tracking-wide">Top Articles Vendus</h4>
                                    <div className="space-y-2">
                                        {reportData.top_products.map((p, idx) => (
                                            <div key={idx} className="flex justify-between items-center text-sm border-b border-slate-100 pb-2">
                                                <span className="text-slate-600">{p.name}</span>
                                                <span className="font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded-md">{p.qty}x</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* P I N   L O C K   O V E R L A Y */}
            {isLocked && (
                <div className="fixed inset-0 bg-slate-900/90 backdrop-blur-md z-[300] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-10 max-w-sm w-full text-center animate-in zoom-in-95 duration-200">
                        <Lock className="w-16 h-16 text-indigo-500 mx-auto mb-4" />
                        <h2 className="text-2xl font-black mb-2 text-slate-800">Caisse Verrouillée</h2>
                        <p className="text-slate-500 mb-8 font-medium">Entrez votre code vendeur pour scanner</p>
                        
                        <div className="flex justify-center gap-3 mb-8">
                            {[0,1,2,3].map(i => (
                                <div key={i} className={`w-4 h-4 rounded-full ${pinBuffer.length > i ? 'bg-indigo-600' : 'bg-slate-200'}`}></div>
                            ))}
                        </div>

                        <div className="grid grid-cols-3 gap-4">
                            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(num => (
                                <button 
                                    key={num} 
                                    onClick={() => handlePinEntry(num.toString())}
                                    className="h-16 rounded-2xl bg-slate-50 hover:bg-slate-100 text-2xl font-black text-slate-700 transition-colors border border-slate-200"
                                >
                                    {num}
                                </button>
                            ))}
                            <div className="h-16"></div>
                            <button 
                                onClick={() => handlePinEntry('0')}
                                className="h-16 rounded-2xl bg-slate-50 hover:bg-slate-100 text-2xl font-black text-slate-700 transition-colors border border-slate-200"
                            >
                                0
                            </button>
                            <button 
                                onClick={() => setPinBuffer('')}
                                className="h-16 rounded-2xl bg-rose-50 hover:bg-rose-100 text-rose-500 font-bold transition-colors border border-rose-200 flex items-center justify-center"
                            >
                                <X className="w-8 h-8" />
                            </button>
                        </div>
                        
                        <div className="mt-8 text-xs text-slate-400">
                            Codes de test: <br/> 1234 (Manager) / 0000 (Vendeur)
                        </div>
                    </div>
                </div>
            )}

            {/* Z E R O - U I   E D I T   M O D A L */}
            {editingItem && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[400] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-sm w-full animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-black text-lg text-slate-800 flex items-center gap-2">
                                <svg className="w-5 h-5 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                                Édition Rapide
                            </h3>
                            <button onClick={() => setEditingItem(null)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5"/></button>
                        </div>
                        <p className="text-sm font-bold text-slate-600 mb-4 truncate">{editingItem.product_name}</p>
                        
                        <form onSubmit={saveZeroUIEdit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Prix de Vente (€)</label>
                                <input type="number" step="0.01" value={editPrice} onChange={e=>setEditPrice(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xl font-mono font-bold" />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Stock Actuel</label>
                                <input type="number" step="1" value={editStock} onChange={e=>setEditStock(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-xl font-mono font-bold" />
                            </div>
                            <button type="submit" className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-white font-bold rounded-xl shadow-lg mt-2 transition-colors">
                                Enregistrer
                            </button>
                        </form>
                    </div>
                </div>
            )}

            {/* M O V E M E N T   M O D A L */}
            {showMovement && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[400] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-sm w-full animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-lg text-slate-800 flex items-center gap-2">
                                <ArrowRightLeft className="w-5 h-5 text-indigo-500" />
                                Mouvement Caisse
                            </h3>
                            <button onClick={() => setShowMovement(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5"/></button>
                        </div>
                        
                        <form onSubmit={handleCashMovement} className="space-y-5">
                            <div className="flex gap-2 p-1 bg-slate-100 rounded-xl">
                                <button type="button" onClick={() => setMovementType('OUT')} className={`flex-1 py-2 font-bold text-sm rounded-lg transition-all ${movementType === 'OUT' ? 'bg-white text-rose-600 shadow-sm' : 'text-slate-500'}`}>Sortie</button>
                                <button type="button" onClick={() => setMovementType('IN')} className={`flex-1 py-2 font-bold text-sm rounded-lg transition-all ${movementType === 'IN' ? 'bg-white text-emerald-600 shadow-sm' : 'text-slate-500'}`}>Entrée</button>
                            </div>
                            
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Montant (€)</label>
                                <input 
                                    type="number" step="0.01" required 
                                    value={movementAmount} onChange={e=>setMovementAmount(e.target.value)} 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-3xl text-center font-mono font-black text-slate-800 outline-none focus:border-indigo-400" 
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-1">Motif</label>
                                <input 
                                    type="text" required placeholder="Ex: Achat café, Dépôt banque..."
                                    value={movementReason} onChange={e=>setMovementReason(e.target.value)} 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold outline-none focus:border-indigo-400" 
                                />
                            </div>
                            
                            <button type="submit" className={`w-full py-4 text-white font-black rounded-xl shadow-lg mt-2 transition-colors flex justify-center items-center gap-2 ${movementType === 'IN' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-rose-600 hover:bg-rose-500'}`}>
                                Valider {movementType === 'IN' ? "l'entrée" : "le retrait"}
                            </button>
                        </form>
                    </div>
                </div>
            )}

            {/* I N V O I C E   P A Y M E N T   M O D A L */}
            {showInvoicePayment && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[400] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-2xl w-full flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-6 shrink-0">
                            <h3 className="font-black text-xl text-slate-800 flex items-center gap-2">
                                <FileText className="w-6 h-6 text-blue-500" />
                                Encaisser une Facture
                            </h3>
                            <button onClick={() => {setShowInvoicePayment(false); setSelectedInvoice(null);}} className="text-slate-400 hover:text-slate-600 bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        
                        {!selectedInvoice ? (
                            <div className="overflow-y-auto pr-2 space-y-3">
                                {pendingInvoices.length === 0 ? (
                                    <div className="text-center py-10 text-slate-400 font-bold">Aucune facture en attente</div>
                                ) : (
                                    pendingInvoices.map(inv => (
                                        <div 
                                            key={inv.id} 
                                            onClick={() => {setSelectedInvoice(inv); setInvoicePaymentAmount(inv.due_amount.toString());}}
                                            className="p-4 border border-slate-200 rounded-xl hover:border-blue-400 hover:shadow-md cursor-pointer transition-all flex justify-between items-center bg-white"
                                        >
                                            <div>
                                                <div className="font-bold text-slate-800 flex items-center gap-2">
                                                    {inv.reference} <span className="px-2 py-0.5 bg-rose-100 text-rose-700 text-xs rounded-full">A régler</span>
                                                </div>
                                                <div className="text-sm text-slate-500 mt-1">{inv.client_name}</div>
                                            </div>
                                            <div className="text-right">
                                                <div className="font-black text-xl text-blue-600">{inv.due_amount.toFixed(2)} €</div>
                                                <div className="text-xs text-slate-400">sur {inv.total.toFixed(2)} €</div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        ) : (
                            <form onSubmit={handleInvoicePayment} className="space-y-6">
                                <div className="p-4 bg-blue-50 border border-blue-100 rounded-xl flex justify-between items-center">
                                    <div>
                                        <div className="text-sm font-bold text-blue-600 uppercase">Facture Sélectionnée</div>
                                        <div className="text-xl font-black text-slate-800">{selectedInvoice.reference} - {selectedInvoice.client_name}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-xs font-bold text-slate-500 uppercase">Reste à payer</div>
                                        <div className="text-2xl font-black text-rose-600">{selectedInvoice.due_amount.toFixed(2)} €</div>
                                    </div>
                                </div>
                                
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                                    <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${invoicePaymentMethod === 'CASH' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                        <input type="radio" name="inv_payment" value="CASH" checked={invoicePaymentMethod==='CASH'} onChange={()=>setInvoicePaymentMethod('CASH')} className="hidden" />
                                        <Banknote className="w-6 h-6 mb-1" />
                                        <span className="font-bold text-xs">Espèces</span>
                                    </label>
                                    <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${invoicePaymentMethod === 'CB' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                        <input type="radio" name="inv_payment" value="CB" checked={invoicePaymentMethod==='CB'} onChange={()=>setInvoicePaymentMethod('CB')} className="hidden" />
                                        <CreditCard className="w-6 h-6 mb-1" />
                                        <span className="font-bold text-xs">Carte Bancaire</span>
                                    </label>
                                    <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${invoicePaymentMethod === 'MOBO' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                        <input type="radio" name="inv_payment" value="MOBO" checked={invoicePaymentMethod==='MOBO'} onChange={()=>setInvoicePaymentMethod('MOBO')} className="hidden" />
                                        <svg className="w-6 h-6 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                                        <span className="font-bold text-xs">Mobile Money</span>
                                    </label>
                                    <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${invoicePaymentMethod === 'CHEQUE' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                        <input type="radio" name="inv_payment" value="CHEQUE" checked={invoicePaymentMethod==='CHEQUE'} onChange={()=>setInvoicePaymentMethod('CHEQUE')} className="hidden" />
                                        <FileText className="w-6 h-6 mb-1" />
                                        <span className="font-bold text-xs">Chèque</span>
                                    </label>
                                    <label className={`border-2 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer transition-all text-center ${invoicePaymentMethod === 'TRANSFER' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                        <input type="radio" name="inv_payment" value="TRANSFER" checked={invoicePaymentMethod==='TRANSFER'} onChange={()=>setInvoicePaymentMethod('TRANSFER')} className="hidden" />
                                        <Landmark className="w-6 h-6 mb-1" />
                                        <span className="font-bold text-xs">Virement</span>
                                    </label>
                                </div>
                                
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Montant de l'encaissement (€)</label>
                                    <input 
                                        type="number" step="0.01" required max={selectedInvoice.due_amount.toString()}
                                        value={invoicePaymentAmount} onChange={e=>setInvoicePaymentAmount(e.target.value)} 
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-4 text-3xl text-center font-mono font-black text-slate-800 outline-none focus:border-blue-400" 
                                    />
                                    <p className="text-center text-xs text-slate-400 mt-2">Le montant peut être inférieur au reste à payer (paiement partiel).</p>
                                </div>
                                
                                <div className="flex gap-3">
                                    <button type="button" onClick={() => setSelectedInvoice(null)} className="flex-1 py-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl transition-colors">Retour</button>
                                    <button type="submit" className="flex-[2] py-4 bg-blue-600 hover:bg-blue-500 text-white font-black rounded-xl shadow-lg transition-colors flex justify-center items-center gap-2">
                                        Valider l'encaissement
                                    </button>
                                </div>
                            </form>
                        )}
                    </div>
                </div>
            )}

            {/* P O S   S E T T I N G S   M O D A L */}
            {showSettings && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[400] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-6 max-w-md w-full animate-in zoom-in-95 duration-200">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-xl text-slate-800 flex items-center gap-2">
                                <Settings className="w-6 h-6 text-slate-500" />
                                Configuration Terminal
                            </h3>
                            <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-slate-600 bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        
                        <form onSubmit={savePosSettings} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Nom de l'Enseigne</label>
                                <input 
                                    type="text" value={posSettings.storeName} 
                                    onChange={e=>setPosSettings({...posSettings, storeName: e.target.value})} 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold outline-none focus:border-slate-400" 
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Adresse sur Ticket</label>
                                <input 
                                    type="text" value={posSettings.storeAddress} 
                                    onChange={e=>setPosSettings({...posSettings, storeAddress: e.target.value})} 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold outline-none focus:border-slate-400" 
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 uppercase mb-1">Message Pied de Page (Ticket)</label>
                                <input 
                                    type="text" value={posSettings.ticketFooter} 
                                    onChange={e=>setPosSettings({...posSettings, ticketFooter: e.target.value})} 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold outline-none focus:border-slate-400" 
                                />
                            </div>
                            
                            <label className="flex items-center gap-3 p-4 border border-slate-200 rounded-xl cursor-pointer hover:bg-slate-50 mt-2">
                                <input 
                                    type="checkbox" 
                                    checked={posSettings.autoPrint}
                                    onChange={e=>setPosSettings({...posSettings, autoPrint: e.target.checked})}
                                    className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <div>
                                    <div className="font-bold text-slate-800">Impression Automatique</div>
                                    <div className="text-xs text-slate-500">Lancer l'impression du ticket après chaque encaissement.</div>
                                </div>
                            </label>
                            
                            <button type="submit" className="w-full py-4 bg-slate-800 hover:bg-slate-700 text-white font-black rounded-xl shadow-lg mt-4 transition-colors flex justify-center items-center gap-2">
                                Enregistrer la configuration locale
                            </button>
                        </form>
                    </div>
                </div>
            )}

            </main>
        </div>
    );
}
