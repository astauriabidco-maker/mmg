import React, { useState } from 'react';
import { X, Scissors, BrainCircuit, Plus, Trash2, ArrowRight } from 'lucide-react';
import api from '../services/api';

export default function CuttingOptimizerModal({ onClose }) {
    const [pieces, setPieces] = useState([1200, 1500, 800, 2100, 3200, 450, 1500]);
    const [newPiece, setNewPiece] = useState('');
    const [barLength, setBarLength] = useState(6000);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);

    const handleOptimize = async () => {
        setLoading(true);
        try {
            const res = await api.post('/v2/planning/optimize-cutting', {
                pieces: pieces.map(Number),
                bar_length: Number(barLength)
            });
            if (res.data && res.data.bars) {
                setResult(res.data);
            } else {
                console.error("Invalid response from server:", res.data);
                alert("Erreur: Le serveur n'a pas retourné le format attendu.");
                setResult(null);
            }
        } catch (err) {
            console.error(err);
            alert("Erreur lors de l'optimisation. Vérifiez qu'aucune pièce n'est plus grande que la barre.");
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    const addPiece = (e) => {
        e.preventDefault();
        if (newPiece && !isNaN(newPiece)) {
            setPieces([...pieces, Number(newPiece)]);
            setNewPiece('');
            setResult(null);
        }
    };

    const removePiece = (idx) => {
        const newP = [...pieces];
        newP.splice(idx, 1);
        setPieces(newP);
        setResult(null);
    };

    return (
        <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col overflow-hidden animate-fade-in">
                
                {/* Header */}
                <div className="bg-slate-900 p-6 flex justify-between items-center text-white shrink-0">
                    <div>
                        <h2 className="text-2xl font-black flex items-center gap-3">
                            <Scissors className="w-6 h-6 text-indigo-400" />
                            Directeur de Production IA
                        </h2>
                        <p className="text-slate-400 text-sm mt-1">Optimisation des plans de coupe (Bin Packing 1D)</p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-white">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 flex flex-col lg:flex-row gap-6 bg-slate-50">
                    
                    {/* Left Column: Input */}
                    <div className="w-full lg:w-1/3 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col h-full shrink-0">
                        <h3 className="font-bold text-slate-800 mb-4 uppercase tracking-widest text-xs flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-blue-500"></div> Données d'entrée
                        </h3>
                        
                        <div className="mb-6">
                            <label className="block text-xs font-bold text-slate-500 mb-2">Longueur Barre Standard (mm)</label>
                            <input 
                                type="number" 
                                value={barLength} 
                                onChange={e => {setBarLength(e.target.value); setResult(null);}}
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-mono font-bold text-slate-800 outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                        </div>

                        <div className="flex-1 flex flex-col min-h-0">
                            <label className="block text-xs font-bold text-slate-500 mb-2">Pièces requises (mm)</label>
                            <form onSubmit={addPiece} className="flex gap-2 mb-3">
                                <input 
                                    type="number" 
                                    value={newPiece} 
                                    onChange={e => setNewPiece(e.target.value)}
                                    placeholder="Ex: 1250"
                                    className="flex-1 bg-slate-50 border border-slate-200 rounded-xl p-2 font-mono text-sm outline-none focus:ring-2 focus:ring-indigo-500"
                                />
                                <button type="submit" className="p-2 bg-indigo-100 hover:bg-indigo-200 text-indigo-700 rounded-xl transition-colors">
                                    <Plus className="w-5 h-5" />
                                </button>
                            </form>
                            
                            <div className="flex-1 overflow-y-auto bg-slate-50 border border-slate-200 rounded-xl p-2 space-y-1">
                                {pieces.map((p, idx) => (
                                    <div key={idx} className="flex justify-between items-center bg-white border border-slate-100 p-2 rounded-lg text-sm">
                                        <span className="font-mono font-bold text-slate-700">{p} mm</span>
                                        <button onClick={() => removePiece(idx)} className="text-red-400 hover:text-red-600 p-1">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                                {pieces.length === 0 && (
                                    <p className="text-center text-xs text-slate-400 py-4 font-medium">Aucune pièce. Ajoutez-en ci-dessus.</p>
                                )}
                            </div>
                        </div>

                        <button 
                            onClick={handleOptimize}
                            disabled={pieces.length === 0 || loading}
                            className="mt-6 w-full py-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-300 text-white rounded-xl font-black shadow-lg shadow-indigo-500/30 flex items-center justify-center gap-2 transition-all active:scale-95"
                        >
                            {loading ? <BrainCircuit className="w-5 h-5 animate-pulse" /> : <BrainCircuit className="w-5 h-5" />}
                            {loading ? "Calcul IA en cours..." : "Lancer l'Optimisation IA"}
                        </button>
                    </div>

                    {/* Right Column: Results */}
                    <div className="flex-1 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex flex-col min-h-[400px]">
                        <h3 className="font-bold text-slate-800 mb-4 uppercase tracking-widest text-xs flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-emerald-500"></div> Plan de Coupe
                        </h3>

                        {!result ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                                <BrainCircuit className="w-20 h-20 text-slate-100 mb-4" />
                                <p className="font-medium text-center">Renseignez vos pièces à gauche<br/>et lancez l'IA pour générer le plan.</p>
                            </div>
                        ) : (
                            <div className="flex-1 flex flex-col h-full">
                                <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 mb-6 flex items-start gap-4 shrink-0">
                                    <div className="bg-indigo-500 text-white p-2 rounded-lg"><Sparkles className="w-6 h-6" /></div>
                                    <div>
                                        <p className="text-indigo-900 font-bold text-sm leading-relaxed">{result.ai_message}</p>
                                        <div className="flex gap-4 mt-2">
                                            <span className="text-xs font-black bg-white text-indigo-700 px-2 py-1 rounded shadow-sm border border-indigo-100">Barres : {result.total_bars_required}</span>
                                            <span className="text-xs font-black bg-white text-emerald-600 px-2 py-1 rounded shadow-sm border border-emerald-100">Chute globale : {result.total_waste_percentage}%</span>
                                        </div>
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto space-y-4 pr-2">
                                    {result.bars && result.bars.map(bar => (
                                        <div key={bar.bar_id} className="border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                                            <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex justify-between items-center text-xs font-bold">
                                                <span className="text-slate-700 uppercase tracking-widest">Barre #{bar.bar_id}</span>
                                                <span className="text-slate-500">Chute: <span className="text-red-500">{bar.waste} mm</span> ({Math.round(100 - bar.utilization)}%)</span>
                                            </div>
                                            <div className="p-4 bg-white">
                                                {/* Visual Representation */}
                                                <div className="h-8 bg-slate-100 rounded flex overflow-hidden border border-slate-200 mb-3">
                                                    {bar.cuts.map((cut, i) => {
                                                        const pct = (cut / barLength) * 100;
                                                        return (
                                                            <div 
                                                                key={i} 
                                                                style={{ width: `${pct}%` }} 
                                                                className="h-full bg-blue-500 border-r border-blue-600 flex items-center justify-center text-[10px] font-bold text-white overflow-hidden whitespace-nowrap"
                                                                title={`${cut} mm`}
                                                            >
                                                                {pct > 5 ? cut : ''}
                                                            </div>
                                                        );
                                                    })}
                                                    {/* Waste */}
                                                    <div className="flex-1 bg-red-100/50 flex items-center justify-center text-[10px] text-red-400 font-bold">
                                                        {bar.waste}
                                                    </div>
                                                </div>
                                                {/* Text Representation */}
                                                <div className="flex flex-wrap gap-2">
                                                    {bar.cuts.map((cut, i) => (
                                                        <div key={i} className="text-xs font-mono bg-blue-50 text-blue-700 px-2 py-1 rounded border border-blue-100">
                                                            {cut} mm
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
