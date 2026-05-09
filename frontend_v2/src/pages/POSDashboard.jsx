import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';
import { 
    Search, CreditCard, Banknote, ShoppingCart, Trash2, 
    X, Check, Lock, Unlock, MonitorSpeaker, ScanBarcode, Menu,
    Pause, Play, Printer, BarChart3
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
    const [parkedCarts, setParkedCarts] = useState([]);
    const [showReceipt, setShowReceipt] = useState(false);
    const [lastOrder, setLastOrder] = useState(null);
    
    // Session Open
    const [startingCash, setStartingCash] = useState('');

    // Report Dashboard
    const [showReport, setShowReport] = useState(false);
    const [reportData, setReportData] = useState(null);

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
        setCart(prev => {
            const existing = prev.find(i => i.variant_id === item.variant_id);
            if (existing) {
                return prev.map(i => i.variant_id === item.variant_id ? { ...i, quantity: i.quantity + 1 } : i);
            }
            return [...prev, { variant_id: item.variant_id, product_name: item.product_name, price: item.price, quantity: 1, stock: item.stock }];
        });
    };

    const updateQuantity = (id, delta) => {
        setCart(prev => prev.map(i => {
            if (i.variant_id === id) {
                const newQ = Math.max(0, i.quantity + delta);
                return { ...i, quantity: newQ };
            }
            return i;
        }).filter(i => i.quantity > 0));
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
        try {
            const payload = {
                items: cart.map(i => ({ variant_id: i.variant_id, quantity: i.quantity, price: i.price, product_name: i.product_name })),
                payment_method: paymentMethod,
                amount_paid: amountPaid ? parseFloat(amountPaid) : cartTotal
            };
            const res = await api.post('/v2/pos/checkout', payload);
            setLastOrder({...res.data, items: cart});
            setCart([]);
            setShowCheckout(false);
            setAmountPaid('');
            setShowReceipt(true);
        } catch (e) {
            alert("Erreur lors de l'encaissement.");
            console.error(e);
        }
    };

    const filteredItems = items.filter(i => 
        i.product_name.toLowerCase().includes(searchTerm.toLowerCase()) || 
        i.reference.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (i.barcode && i.barcode.includes(searchTerm))
    );

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
                </div>

                {/* Products Grid */}
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="mb-4 flex items-center gap-2 text-indigo-700 bg-indigo-50 p-2 rounded-lg inline-flex text-sm font-bold border border-indigo-100 shadow-sm">
                        <ScanBarcode className="w-4 h-4"/> Prêt à biper
                    </div>
                    {filteredItems.length === 0 ? (
                        <div className="text-center py-20 text-slate-400 font-bold text-lg">Aucun article trouvé</div>
                    ) : (
                        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                            {filteredItems.map(item => (
                                <div 
                                    key={item.variant_id} 
                                    onClick={() => addToCart(item)}
                                    className="bg-white border border-slate-200 p-4 rounded-2xl cursor-pointer hover:border-indigo-400 hover:shadow-lg active:scale-95 transition-all flex flex-col select-none"
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className="text-xs font-mono font-bold text-slate-400 bg-slate-50 px-2 py-1 rounded-md max-w-[70%] truncate">{item.reference}</span>
                                        <span className={`text-xs font-black px-2 py-1 rounded-full ${item.stock > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                            Stock: {Math.floor(item.stock)}
                                        </span>
                                    </div>
                                    <h3 className="font-bold text-slate-800 flex-1 break-words leading-tight">{item.product_name}</h3>
                                    <div className="mt-3 font-black text-xl text-indigo-600 block">{item.price.toFixed(2)} €</div>
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
                        </div>
                        <div className="text-xs font-medium text-slate-400">{session.opened_by_user}</div>
                    </div>
                    <div className="flex gap-2">
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
                        <button onClick={handleCloseSession} className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-rose-400 transition-colors" title="Fermer Caisse">
                            <Lock className="w-5 h-5"/>
                        </button>
                    </div>
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
                                    <div className="font-mono text-xs text-slate-400">{c.price.toFixed(2)} € / u</div>
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
                            
                            <div className="mb-6 grid grid-cols-2 gap-3">
                                <label className={`border-2 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${paymentMethod === 'CASH' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="CASH" checked={paymentMethod==='CASH'} onChange={()=>setPaymentMethod('CASH')} className="hidden" />
                                    <Banknote className="w-8 h-8 mb-2" />
                                    <span className="font-bold text-sm">Espèces</span>
                                </label>
                                <label className={`border-2 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${paymentMethod === 'CB' ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 hover:bg-slate-50 text-slate-600'}`}>
                                    <input type="radio" name="payment" value="CB" checked={paymentMethod==='CB'} onChange={()=>setPaymentMethod('CB')} className="hidden" />
                                    <CreditCard className="w-8 h-8 mb-2" />
                                    <span className="font-bold text-sm">Carte Banc.</span>
                                </label>
                            </div>

                            {paymentMethod === 'CASH' && (
                                <div className="mb-8">
                                    <label className="block text-xs font-black text-slate-400 mb-2 uppercase">Espèces reçues (€)</label>
                                    <input 
                                        type="number" 
                                        step="0.01"
                                        min={cartTotal.toString()}
                                        value={amountPaid}
                                        onChange={e => setAmountPaid(e.target.value)}
                                        className="w-full text-center text-3xl font-mono p-4 bg-slate-50 border border-slate-200 rounded-xl"
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

            </main>
        </div>
    );
}
