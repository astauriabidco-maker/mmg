import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { Square, Clock, List, LogOut } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function OperatorDashboard() {
    const { logout } = useAuth();
    const { stationId } = useParams();
    const STATION = stationId ? stationId.toUpperCase() : "PVC_DEBIT";

    const [queue, setQueue] = useState([]);
    const [currentTask, setCurrentTask] = useState(null);
    const [timer, setTimer] = useState(0);
    const ws = useRef(null);

    // Fetch Queue
    const fetchQueue = async () => {
        try {
            const res = await api.get(`/v2/planning/${STATION}`);
            setQueue(res.data);

            const active = res.data.find(t => t.status === "IN_PROGRESS" || t.status === "PAUSED");
            if (active) {
                setCurrentTask(active);
                // If PAUSED, timer should probably not increment or start from previous duration
            } else {
                setCurrentTask(null);
                setTimer(0);
            }
        } catch (err) {
            console.error("Error fetching queue", err);
        }
    };

    // WebSocket Connection
    useEffect(() => {
        fetchQueue();
        ws.current = new WebSocket(`ws://${window.location.host.split(':')[0]}:8000/ws/${Math.floor(Math.random() * 1000)}`);
        ws.current.onopen = () => console.log("WS Connected");
        ws.current.onmessage = (event) => {
            if (event.data === "refresh") fetchQueue();
        };
        return () => ws.current.close();
    }, []);

    // Timer Logic
    useEffect(() => {
        let interval;
        if (currentTask) {
            interval = setInterval(() => {
                setTimer(t => t + 1);
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [currentTask]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    const handleStart = async (task) => {
        try {
            await api.post(`/v2/planning/${task.id}/start`);
            setCurrentTask({ ...task, status: "IN_PROGRESS" });
        } catch (e) { console.error(e); }
    };

    const handleStop = async () => {
        if (!currentTask) return;
        try {
            await api.post(`/v2/planning/${currentTask.id}/stop`);
            setCurrentTask(null);
            setTimer(0);
        } catch (e) { console.error(e); }
    };

    return (
        <div className="flex h-screen bg-slate-100 overflow-hidden font-sans">
            {/* LEFT COLUMN: QUEUE */}
            <div className="w-1/3 bg-white border-r border-slate-200 flex flex-col z-10 shadow-xl">
                <div className="p-6 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm">
                    <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-3">
                        <div className="p-2 bg-blue-100 rounded-lg text-blue-600">
                            <List className="w-6 h-6" />
                        </div>
                        File d'Attente
                        <div className="ml-auto flex items-center gap-2">
                            <span className="bg-slate-200 text-slate-600 px-3 py-1 rounded-full text-xs font-bold">{queue.length}</span>
                            <button onClick={logout} className="p-2 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-full transition-colors" title="Déconnexion">
                                <LogOut className="w-5 h-5" />
                            </button>
                        </div>
                    </h2>
                    <p className="text-xs text-slate-400 mt-2 font-medium tracking-wide uppercase">Poste: {STATION}</p>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/30">
                    {queue.filter(t => t.status !== "DONE").map((item, index) => (
                        <div
                            key={item.id}
                            style={{ animationDelay: `${index * 50}ms` }}
                            onClick={() => !currentTask && handleStart(item)}
                            className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-300 animate-fade-in-up hover:scale-[1.02] ${currentTask?.id === item.id
                                ? 'border-blue-500 bg-blue-50 ring-4 ring-blue-100 shadow-lg'
                                : 'border-white bg-white shadow-sm hover:shadow-md hover:border-blue-200'
                                } ${currentTask && currentTask?.id !== item.id ? 'opacity-40 grayscale pointer-events-none' : ''}`}
                        >
                            <div className="flex flex-col">
                                <span className="font-bold text-lg text-slate-800">
                                    {item.order_reference}
                                </span>
                                <span className="text-[10px] text-slate-400 font-medium truncate max-w-[150px]">
                                    {item.order?.client_name || "Client Inconnu"}
                                </span>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                                <span className={`px-2 py-1 rounded-md text-[10px] font-black uppercase tracking-wider ${item.priority > 5 ? 'bg-orange-100 text-orange-600' : 'bg-slate-100 text-slate-500'
                                    }`}>
                                    Prio {item.priority}
                                </span>
                                <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                                    QTY: {item.order?.quantity || 1}
                                </span>
                            </div>
                            <div className="flex items-center gap-2 mt-2">
                                <div className="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                                    <div className="h-full bg-blue-500 w-1/3 rounded-full"></div>
                                </div>
                            </div>
                        </div>
                    ))}
                    {queue.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-64 text-slate-400 opacity-50">
                            <List className="w-16 h-16 mb-4" />
                            <p>Aucune commande</p>
                        </div>
                    )}
                </div>
            </div>

            {/* RIGHT COLUMN: ACTION */}
            <div className="w-2/3 flex flex-col items-center justify-center p-12 bg-slate-50 relative overflow-hidden">
                {/* Background Decorations */}
                <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-blue-200/20 rounded-full blur-[100px] translate-x-1/2 -translate-y-1/2 pointer-events-none"></div>
                <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-indigo-200/20 rounded-full blur-[100px] -translate-x-1/2 translate-y-1/2 pointer-events-none"></div>

                {currentTask ? (
                    <div className="w-full max-w-2xl text-center relative z-10 animate-fade-in-up">
                        <div className="mb-12">
                            <span className={`inline-flex items-center gap-2 px-5 py-2 rounded-full font-bold mb-6 shadow-sm ${currentTask.status === "PAUSED" ? "bg-orange-100 text-orange-700 animate-pulse" : "bg-blue-100 text-blue-700 animate-bounce"
                                }`}>
                                <span className={`w-2 h-2 rounded-full ${currentTask.status === "PAUSED" ? "bg-orange-600" : "bg-blue-600 animate-ping"
                                    }`}></span>
                                {currentTask.status === "PAUSED" ? "EN PAUSE" : "EN PRODUCTION"}
                            </span>
                            <h1 className="text-7xl font-black text-slate-900 mb-2 tracking-tighter">{currentTask.order_reference}</h1>
                            <p className="text-3xl text-slate-500 font-light tracking-wide">{STATION}</p>

                            <div className="flex justify-center gap-6 mt-6">
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Couleur</p>
                                    <p className="font-black text-slate-700">{currentTask.order?.color || "STANDARDISE"}</p>
                                </div>
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Dimensions</p>
                                    <p className="font-black text-slate-700">{currentTask.order?.width} x {currentTask.order?.height} mm</p>
                                </div>
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Quantité</p>
                                    <p className="font-black text-blue-600">{currentTask.order?.quantity || 1} PCE</p>
                                </div>
                            </div>

                            {currentTask.order?.client_name && (
                                <p className="mt-4 text-slate-400 font-medium italic">Client: {currentTask.order.client_name}</p>
                            )}
                        </div>

                        <div className="mb-16 relative">
                            <div className={`absolute inset-0 blur-[60px] rounded-full transform scale-150 ${currentTask.status === "PAUSED" ? "bg-orange-500/5" : "bg-blue-500/5"
                                }`}></div>
                            <div className={`relative text-[10rem] leading-none font-mono font-bold text-transparent bg-clip-text tracking-tighter drop-shadow-sm select-none ${currentTask.status === "PAUSED" ? "bg-gradient-to-br from-orange-400 to-amber-600" : "bg-gradient-to-br from-blue-600 to-indigo-600"
                                }`}>
                                {formatTime(timer)}
                            </div>
                        </div>

                        <div className="flex gap-4 justify-center">
                            {currentTask.status === "PAUSED" ? (
                                <button
                                    onClick={() => handleStart(currentTask)}
                                    className="group relative w-full max-w-sm bg-gradient-to-br from-emerald-500 to-green-600 hover:from-emerald-600 hover:to-green-700 active:scale-[0.98] text-white rounded-[2rem] py-10 shadow-2xl shadow-emerald-500/40 transition-all duration-300 flex items-center justify-center gap-6 overflow-hidden"
                                >
                                    <Clock className="w-16 h-16 relative z-10" />
                                    <span className="text-4xl font-black relative z-10 tracking-widest text-shadow-sm">REPRENDRE</span>
                                </button>
                            ) : (
                                <>
                                    <button
                                        onClick={() => {
                                            api.post(`/v2/planning/${currentTask.id}/pause`).then(() => {
                                                setCurrentTask({ ...currentTask, status: "PAUSED" });
                                            });
                                        }}
                                        className="bg-orange-100 hover:bg-orange-200 text-orange-600 rounded-[2rem] p-8 transition-colors"
                                    >
                                        <Clock className="w-10 h-10" />
                                    </button>

                                    <button
                                        onClick={handleStop}
                                        className="group relative flex-1 bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 active:scale-[0.98] text-white rounded-[2rem] py-10 shadow-2xl shadow-blue-500/40 transition-all duration-300 flex items-center justify-center gap-6 overflow-hidden"
                                    >
                                        <Square className="w-16 h-16 fill-current relative z-10" />
                                        <span className="text-5xl font-black relative z-10 tracking-widest text-shadow-sm">TERMINER</span>
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="text-center text-slate-400 animate-pulse-slow">
                        <div className="bg-white p-12 rounded-full inline-flex items-center justify-center mb-8 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.1)] ring-8 ring-slate-50">
                            <Clock className="w-32 h-32 text-slate-200" />
                        </div>
                        <h2 className="text-5xl font-light text-slate-700 tracking-tight">Poste Prêt</h2>
                        <p className="mt-4 text-xl text-slate-400 font-light">Sélectionnez une commande à gauche pour démarrer</p>
                    </div>
                )}
            </div>
        </div>
    );
}
