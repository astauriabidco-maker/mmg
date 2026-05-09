import React, { useState, useEffect, useRef } from 'react';
import { Truck, MapPin, Phone, CheckCircle, Package, ArrowLeft, PenTool } from 'lucide-react';
import api from '../services/api';
import SignaturePad from 'react-signature-canvas';

export default function DriverDashboard() {
    const [routes, setRoutes] = useState([]);
    const [selectedRoute, setSelectedRoute] = useState(null);
    const [selectedNote, setSelectedNote] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    
    // For signature modal
    const [showSignatureModal, setShowSignatureModal] = useState(false);
    const sigCanvas = useRef(null);

    useEffect(() => {
        fetchRoutes();
    }, []);

    const fetchRoutes = async () => {
        setIsLoading(true);
        try {
            const res = await api.get('/v2/logistics/routes');
            // Filter to show IN_TRANSIT routes primarily
            const activeRoutes = res.data.filter(r => r.status === "IN_TRANSIT" || r.status === "PLANNED");
            setRoutes(activeRoutes);
        } catch (error) {
            console.error("Error fetching routes", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleConfirmDelivery = async () => {
        if (sigCanvas.current.isEmpty()) {
            alert("Le client doit signer pour valider la livraison.");
            return;
        }
        
        const signatureBase64 = sigCanvas.current.getTrimmedCanvas().toDataURL('image/png');
        
        try {
            await api.post(`/v2/logistics/notes/${selectedNote.id}/deliver`, {
                signature: signatureBase64
            });
            setShowSignatureModal(false);
            setSelectedNote(null);
            
            // Re-fetch to update local state
            await fetchRoutes();
            
            // Re-apply selection if route was selected
            if(selectedRoute) {
                const res = await api.get('/v2/logistics/routes');
                const updatedRoute = res.data.find(r => r.id === selectedRoute.id);
                setSelectedRoute(updatedRoute);
            }
            
        } catch (error) {
            alert("Erreur lors de la confirmation de livraison");
        }
    };

    const clearSignature = () => {
        sigCanvas.current.clear();
    };

    if (isLoading && routes.length === 0) {
        return <div className="min-h-screen bg-slate-50 flex items-center justify-center font-bold text-slate-500">Chargement...</div>;
    }

    return (
        <div className="min-h-screen bg-slate-50 pb-20">
            {/* Header */}
            <header className="bg-slate-900 text-white p-4 shadow-lg sticky top-0 z-30">
                <div className="flex items-center gap-3">
                    {selectedRoute ? (
                        <button onClick={() => setSelectedRoute(null)} className="p-2 bg-slate-800 rounded-full hover:bg-slate-700">
                            <ArrowLeft className="w-5 h-5"/>
                        </button>
                    ) : (
                        <div className="w-10 h-10 bg-blue-600 rounded-full flex items-center justify-center">
                            <Truck className="w-5 h-5" />
                        </div>
                    )}
                    <div>
                        <h1 className="text-lg font-black tracking-tight">{selectedRoute ? selectedRoute.reference : "Mes Tournées"}</h1>
                        <p className="text-[10px] text-blue-300 font-bold uppercase tracking-widest">
                            {selectedRoute ? `${selectedRoute.notes.filter(n => n.status === "DELIVERED").length}/${selectedRoute.notes.length} Livraisons effectuées` : "Interface Chauffeur"}
                        </p>
                    </div>
                </div>
            </header>

            <main className="p-4 max-w-md mx-auto">
                {/* 1. ROUTE LIST */}
                {!selectedRoute && (
                    <div className="space-y-4 animate-fade-in">
                        {routes.length === 0 ? (
                            <div className="text-center p-10 bg-white rounded-2xl shadow-sm border border-slate-200">
                                <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
                                <h3 className="font-black text-slate-800">Aucune tournée</h3>
                                <p className="text-slate-500 text-sm mt-1">Vous n'avez aucune tournée en cours.</p>
                            </div>
                        ) : (
                            routes.map(route => {
                                const total = route.notes.length;
                                const delivered = route.notes.filter(n => n.status === "DELIVERED").length;
                                const progress = total > 0 ? (delivered / total) * 100 : 0;
                                
                                return (
                                    <div 
                                        key={route.id} 
                                        onClick={() => setSelectedRoute(route)}
                                        className="bg-white rounded-2xl p-5 shadow-md border-b-4 border-blue-500 cursor-pointer active:scale-95 transition-transform"
                                    >
                                        <div className="flex justify-between items-start mb-3">
                                            <h3 className="font-black text-xl text-slate-800">{route.reference}</h3>
                                            <span className={`px-2 py-1 rounded text-[10px] font-black uppercase ${route.status === 'IN_TRANSIT' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
                                                {route.status === 'IN_TRANSIT' ? 'En Route' : 'Prévue'}
                                            </span>
                                        </div>
                                        <p className="text-sm font-bold text-slate-500 flex items-center gap-2 mb-4">
                                            <Truck className="w-4 h-4" /> {route.vehicle}
                                        </p>
                                        
                                        <div className="w-full bg-slate-100 rounded-full h-2 mb-1">
                                            <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${progress}%` }}></div>
                                        </div>
                                        <p className="text-xs text-right font-bold text-slate-400">{delivered} / {total} Livrés</p>
                                    </div>
                                )
                            })
                        )}
                    </div>
                )}

                {/* 2. DELIVERY NOTES FOR SELECTED ROUTE */}
                {selectedRoute && (
                    <div className="space-y-4 animate-fade-in-up">
                        {selectedRoute.notes.map((note, index) => (
                            <div key={note.id} className={`bg-white rounded-2xl p-5 shadow-sm border ${note.status === 'DELIVERED' ? 'border-emerald-200 bg-emerald-50/30' : 'border-slate-200'}`}>
                                <div className="flex justify-between items-start mb-2">
                                    <span className="text-xs font-black text-slate-400 bg-slate-100 px-2 py-1 rounded">Étape {index + 1}</span>
                                    {note.status === "DELIVERED" ? (
                                        <span className="text-[10px] font-black bg-emerald-100 text-emerald-700 px-2 py-1 rounded flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3"/> LIVRÉ
                                        </span>
                                    ) : (
                                        <span className="text-[10px] font-black bg-orange-100 text-orange-700 px-2 py-1 rounded">EN ATTENTE</span>
                                    )}
                                </div>
                                
                                <h3 className="font-black text-xl text-slate-800 mb-1">{note.client_name}</h3>
                                <p className="text-slate-600 text-sm mb-3 flex items-start gap-2">
                                    <MapPin className="w-4 h-4 text-slate-400 mt-0.5 shrink-0"/> 
                                    <span>{note.delivery_address || "Adresse non spécifiée"}</span>
                                </p>
                                
                                {note.contact_phone && (
                                    <a href={`tel:${note.contact_phone}`} className="inline-flex items-center gap-2 text-blue-600 bg-blue-50 px-3 py-1.5 rounded-lg text-sm font-bold mb-4">
                                        <Phone className="w-4 h-4"/> Appeler le client
                                    </a>
                                )}

                                {note.status !== "DELIVERED" && (
                                    <button 
                                        onClick={() => {
                                            setSelectedNote(note);
                                            setShowSignatureModal(true);
                                        }}
                                        className="w-full py-4 bg-slate-900 text-white rounded-xl font-black text-lg flex items-center justify-center gap-2 shadow-lg active:scale-95 transition-transform"
                                    >
                                        <CheckCircle className="w-6 h-6"/> Marquer Livré
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </main>

            {/* SIGNATURE MODAL */}
            {showSignatureModal && selectedNote && (
                <div className="fixed inset-0 bg-slate-900/90 backdrop-blur-sm z-50 flex flex-col justify-end">
                    <div className="bg-white rounded-t-[2rem] w-full p-6 animate-fade-in-up pb-10">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-xl font-black text-slate-800">Signature Client</h3>
                            <button onClick={() => setShowSignatureModal(false)} className="text-slate-400 font-bold p-2">Fermer</button>
                        </div>
                        
                        <p className="text-sm text-slate-500 mb-4 font-bold">
                            Je soussigné, confirme la bonne réception des menuiseries concernant la commande <span className="text-slate-800">{selectedNote.reference}</span>.
                        </p>

                        <div className="border-2 border-dashed border-slate-300 rounded-2xl mb-4 bg-slate-50 relative overflow-hidden">
                            <div className="absolute top-4 left-4 text-slate-300 pointer-events-none flex items-center gap-2 font-bold text-sm">
                                <PenTool className="w-4 h-4"/> Signez ici
                            </div>
                            <SignaturePad 
                                ref={sigCanvas}
                                canvasProps={{
                                    className: "w-full h-48 cursor-crosshair"
                                }}
                            />
                        </div>

                        <div className="flex gap-4">
                            <button 
                                onClick={clearSignature}
                                className="px-6 py-4 bg-slate-100 text-slate-600 font-bold rounded-xl"
                            >
                                Effacer
                            </button>
                            <button 
                                onClick={handleConfirmDelivery}
                                className="flex-1 py-4 bg-emerald-500 text-white font-black text-lg rounded-xl shadow-lg shadow-emerald-500/30"
                            >
                                Valider
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
