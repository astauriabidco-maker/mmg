import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Square, Clock, List, LogOut, ChevronDown, Repeat, AlertTriangle, CheckCircle2, Users } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function OperatorDashboard() {
    const { logout, user } = useAuth();
    const navigate = useNavigate();
    const { stationId } = useParams();

    // Support either code directly or object from context
    const stations = user?.stations || [];
    const currentStationObj = stations.find(s => s.code === (stationId || stations[0]?.code));
    const STATION = (stationId || stations[0]?.code || "PVC_DEBIT").toUpperCase();

    const [queue, setQueue] = useState([]);
    const [selectedTask, setSelectedTask] = useState(null); // The task being viewed
    const [currentTask, setCurrentTask] = useState(null);  // The task being worked on (IN_PROGRESS)
    const [timer, setTimer] = useState(0);
    const [isStationOpen, setIsStationOpen] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [showIssueModal, setShowIssueModal] = useState(false);
    const [issueNotes, setIssueNotes] = useState("");
    const ws = useRef(null);

    // Fetch Queue
    const fetchQueue = async () => {
        try {
            const res = await api.get(`/v2/planning/${STATION}`);
            setQueue(res.data);

            const active = res.data.find(t => t.status === "IN_PROGRESS");
            const pausedOrIssue = res.data.find(t => t.status === "PAUSED" || t.status === "ISSUE");

            if (active) {
                setCurrentTask(active);
                setSelectedTask(active);
            } else {
                setCurrentTask(null);
                setTimer(0);
                // If there was a selected task that is now in progress elsewhere or done, clear it?
                // Actually, let's keep selected task as is or auto-select the first if none
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
    }, [STATION]); // Re-connect/fetch if station changes

    // ... timer logic and handlers ...

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
            const updated = { ...task, status: "IN_PROGRESS" };
            setCurrentTask(updated);
            setSelectedTask(updated);
            fetchQueue();
        } catch (e) { console.error(e); }
    };

    const handleStop = async () => {
        if (!currentTask) return;
        try {
            await api.post(`/v2/planning/${currentTask.id}/stop`);
            setCurrentTask(null);
            setTimer(0);
            setShowConfirm(false);
            fetchQueue();
        } catch (e) { console.error(e); }
    };

    const handlePause = async () => {
        const task = currentTask || selectedTask;
        if (!task) return;
        try {
            await api.post(`/v2/planning/${task.id}/pause`);
            if (currentTask?.id === task.id) setCurrentTask(null);
            if (selectedTask?.id === task.id) setSelectedTask({ ...selectedTask, status: "PAUSED" });
            fetchQueue();
        } catch (e) { console.error(e); }
    };

    const handleReportIssue = async () => {
        const task = currentTask || selectedTask;
        if (!task || !issueNotes.trim()) return;
        try {
            await api.post(`/v2/planning/${task.id}/issue`, { notes: issueNotes });
            if (currentTask?.id === task.id) {
                setCurrentTask(null);
                setTimer(0);
            }
            if (selectedTask?.id === task.id) setSelectedTask({ ...selectedTask, status: "ISSUE", issue_notes: issueNotes });
            setShowIssueModal(false);
            setIssueNotes("");
            fetchQueue();
        } catch (e) { console.error(e); }
    };

    return (
        <div className="flex h-screen bg-slate-100 overflow-hidden font-sans">
            {/* LEFT COLUMN: QUEUE */}
            <div className="w-1/3 bg-white border-r border-slate-200 flex flex-col z-10 shadow-xl">
                <div className="p-6 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm relative">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] text-slate-400 font-black tracking-widest uppercase">Poste Actuel</span>
                        <div className="flex gap-2">
                            <button onClick={logout} className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-500 rounded-lg transition-colors" title="Déconnexion">
                                <LogOut className="w-4 h-4" />
                            </button>
                        </div>
                    </div>

                    <div className="relative">
                        <button
                            onClick={() => setIsStationOpen(!isStationOpen)}
                            className="w-full flex items-center justify-between p-3 bg-white border-2 border-slate-100 rounded-xl hover:border-blue-500 transition-all group"
                        >
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-600 group-hover:text-white transition-colors">
                                    <Repeat className="w-5 h-5" />
                                </div>
                                <div className="text-left">
                                    <p className="text-xs font-bold text-slate-400 leading-none mb-1">{currentStationObj?.material || "???"}</p>
                                    <p className="font-black text-slate-800 leading-none">{currentStationObj?.display_name || STATION}</p>
                                </div>
                            </div>
                            {stations.length > 1 && <ChevronDown className={`w-5 h-5 text-slate-400 transition-transform ${isStationOpen ? 'rotate-180' : ''}`} />}
                        </button>

                        {isStationOpen && stations.length > 1 && (
                            <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-2xl border border-slate-100 py-2 z-50 animate-in fade-in zoom-in-95 duration-200">
                                {stations.map(s => (
                                    <button
                                        key={s.id}
                                        onClick={() => {
                                            navigate(`/dashboard/${s.code}`);
                                            setIsStationOpen(false);
                                        }}
                                        className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors ${s.code === STATION ? 'bg-blue-50/50' : ''}`}
                                    >
                                        <div className={`w-2 h-2 rounded-full ${s.code === STATION ? 'bg-blue-500' : 'bg-slate-200'}`}></div>
                                        <div className="text-left">
                                            <p className="text-[10px] font-bold text-slate-400 uppercase">{s.material}</p>
                                            <p className={`text-sm font-bold ${s.code === STATION ? 'text-blue-600' : 'text-slate-700'}`}>{s.display_name}</p>
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-slate-50/30">
                    {queue.map((item, index) => (
                        <div
                            key={item.id}
                            style={{ animationDelay: `${index * 50}ms` }}
                            onClick={() => setSelectedTask(item)}
                            className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-300 animate-fade-in-up hover:scale-[1.02] ${selectedTask?.id === item.id
                                ? 'border-blue-500 bg-blue-50 ring-4 ring-blue-100 shadow-lg'
                                : item.status === "PAUSED" ? "border-orange-200 bg-orange-50/30 shadow-none opacity-80"
                                    : item.status === "ISSUE" ? "border-red-200 bg-red-50/30 shadow-none opacity-80"
                                        : 'border-white bg-white shadow-sm hover:shadow-md hover:border-blue-200'
                                } ${currentTask && currentTask?.id !== item.id ? 'opacity-40 grayscale pointer-events-none' : ''}`}
                        >
                            <div className="flex justify-between items-start">
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
                                    {item.status !== "PENDING" && item.status !== "IN_PROGRESS" && (
                                        <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase ${item.status === "PAUSED" ? "bg-orange-500 text-white" : "bg-red-500 text-white"
                                            }`}>
                                            {item.status === "PAUSED" ? "PAUSE" : "PROBLÈME"}
                                        </span>
                                    )}
                                    {item.status === "IN_PROGRESS" && item.assigned_to && (
                                        <span className="px-2 py-0.5 rounded text-[8px] font-black uppercase bg-blue-500 text-white shadow-sm flex items-center gap-1">
                                            <Users className="w-2 h-2"/> {item.assigned_to}
                                        </span>
                                    )}
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

                {selectedTask ? (
                    <div className="w-full max-w-2xl text-center relative z-10 animate-fade-in-up">
                        <div className="mb-12">
                            <span className={`inline-flex items-center gap-2 px-5 py-2 rounded-full font-bold mb-6 shadow-sm ${selectedTask.status === "PAUSED" ? "bg-orange-100 text-orange-700" :
                                selectedTask.status === "ISSUE" ? "bg-red-100 text-red-700" :
                                    selectedTask.status === "IN_PROGRESS" ? "bg-blue-100 text-blue-700 animate-bounce" : "bg-slate-100 text-slate-700"
                                }`}>
                                <span className={`w-2 h-2 rounded-full ${selectedTask.status === "PAUSED" ? "bg-orange-600" :
                                    selectedTask.status === "ISSUE" ? "bg-red-600" :
                                        selectedTask.status === "IN_PROGRESS" ? "bg-blue-600 animate-ping" : "bg-slate-400"
                                    }`}></span>
                                {selectedTask.status === "PAUSED" ? "EN PAUSE" :
                                    selectedTask.status === "ISSUE" ? "PROBLÈME SIGNALÉ" :
                                        selectedTask.status === "IN_PROGRESS" ? "EN PRODUCTION" : "PRÊT À DÉMARRER"}
                            </span>
                            <h1 className="text-7xl font-black text-slate-900 mb-2 tracking-tighter">{selectedTask.order_reference}</h1>
                            <p className="text-3xl text-slate-500 font-light tracking-wide">{STATION}</p>
                            
                            {selectedTask.status === "IN_PROGRESS" && selectedTask.assigned_to && (
                                <div className="mt-4 inline-flex items-center gap-2 bg-blue-50 border border-blue-100 text-blue-700 px-4 py-2 rounded-full font-bold text-sm">
                                    <Users className="w-4 h-4"/>
                                    Pris en charge par : {selectedTask.assigned_to}
                                </div>
                            )}

                            <div className="flex justify-center gap-6 mt-6">
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Couleur</p>
                                    <p className="font-black text-slate-700">{selectedTask.order?.color || "STANDARDISE"}</p>
                                </div>
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Dimensions</p>
                                    <p className="font-black text-slate-700">{selectedTask.order?.width} x {selectedTask.order?.height} mm</p>
                                </div>
                                <div className="bg-white px-6 py-3 rounded-2xl shadow-sm border border-slate-100 text-left">
                                    <p className="text-[10px] uppercase font-bold text-slate-400 mb-1">Quantité</p>
                                    <p className="font-black text-blue-600">{selectedTask.order?.quantity || 1} PCE</p>
                                </div>
                            </div>
                            
                            {/* SCHEMA TECHNIQUE SVG */}
                            <div className="mt-8 flex justify-center opacity-80 mix-blend-multiply">
                                {selectedTask.order?.width && selectedTask.order?.height && (
                                    <div className="relative border-2 border-dashed border-slate-300 p-8 rounded-2xl bg-white flex items-center justify-center shadow-inner">
                                        <div className="absolute -top-3 bg-slate-100 text-slate-500 text-[10px] font-bold px-2 rounded-full border border-slate-200">L {selectedTask.order.width}mm</div>
                                        <div className="absolute -left-3 -rotate-90 bg-slate-100 text-slate-500 text-[10px] font-bold px-2 rounded-full border border-slate-200">H {selectedTask.order.height}mm</div>
                                        <svg 
                                            width={Math.min(200, (selectedTask.order.width / selectedTask.order.height) * 200)} 
                                            height={Math.min(200, (selectedTask.order.height / selectedTask.order.width) * 200)} 
                                            viewBox="0 0 100 100" 
                                            preserveAspectRatio="none"
                                            className="overflow-visible"
                                        >
                                            {/* Cadre Extérieur */}
                                            <rect x="0" y="0" width="100" height="100" fill="none" stroke="#64748b" strokeWidth="4" />
                                            {/* Cadre Intérieur (Ouvrant) */}
                                            <rect x="5" y="5" width="90" height="90" fill="#f8fafc" stroke="#94a3b8" strokeWidth="2" />
                                            {/* Poignée (Droite) */}
                                            <rect x="85" y="45" width="4" height="10" fill="#cbd5e1" rx="1" />
                                            {/* Vitrage (Effet Reflet) */}
                                            <polygon points="10,90 90,10 90,90" fill="#e2e8f0" opacity="0.4" />
                                        </svg>
                                    </div>
                                )}
                            </div>

                            {selectedTask.status === "ISSUE" && selectedTask.issue_notes && (
                                <div className="mt-8 p-4 bg-red-50 border border-red-100 rounded-2xl text-left flex items-start gap-4">
                                    <AlertTriangle className="w-6 h-6 text-red-500 flex-shrink-0 mt-1" />
                                    <div>
                                        <p className="text-[10px] uppercase font-black text-red-400 mb-1 tracking-widest">Notes du Problème</p>
                                        <p className="text-red-700 font-medium">{selectedTask.issue_notes}</p>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="mb-16 relative">
                            <div className={`absolute inset-0 blur-[60px] rounded-full transform scale-150 ${selectedTask.status === "PAUSED" ? "bg-orange-500/5" :
                                selectedTask.status === "ISSUE" ? "bg-red-500/5" : "bg-blue-500/5"
                                }`}></div>
                            <div className={`relative text-[10rem] leading-none font-mono font-bold text-transparent bg-clip-text tracking-tighter drop-shadow-sm select-none ${selectedTask.status === "PAUSED" ? "bg-gradient-to-br from-orange-400 to-amber-600" :
                                selectedTask.status === "ISSUE" ? "bg-gradient-to-br from-red-400 to-red-600" : "bg-gradient-to-br from-blue-600 to-indigo-600"
                                }`}>
                                {formatTime(timer)}
                            </div>
                        </div>

                        <div className="w-full flex justify-center mt-8">
                            {selectedTask.status !== "IN_PROGRESS" && selectedTask.status !== "PAUSED" ? (
                                <button
                                    onClick={() => handleStart(selectedTask)}
                                    className="w-full max-w-md bg-emerald-500 hover:bg-emerald-600 text-white rounded-3xl py-10 transition-all flex items-center justify-center gap-6 shadow-2xl shadow-emerald-200 active:scale-95 group"
                                >
                                    <Clock className="w-16 h-16 group-hover:rotate-12 transition-transform" />
                                    <span className="text-5xl font-black tracking-tighter">DÉMARRER</span>
                                </button>
                            ) : (
                                <div className="grid grid-cols-12 gap-4 w-full max-w-3xl">
                                    {/* Problem Button */}
                                    <button
                                        onClick={() => setShowIssueModal(true)}
                                        className="col-span-3 bg-red-50 hover:bg-red-100 text-red-600 rounded-3xl py-6 transition-all flex flex-col items-center justify-center gap-2 border-2 border-transparent hover:border-red-200"
                                    >
                                        <AlertTriangle className="w-8 h-8" />
                                        <span className="text-xs font-black uppercase tracking-widest">Problème</span>
                                    </button>

                                    {/* Pause/Resume Button */}
                                    {selectedTask.status === "PAUSED" ? (
                                        <button
                                            onClick={() => handleStart(selectedTask)}
                                            className="col-span-4 bg-emerald-500 hover:bg-emerald-600 text-white rounded-3xl py-6 transition-all flex flex-col items-center justify-center gap-2 shadow-lg shadow-emerald-200"
                                        >
                                            <Clock className="w-8 h-8" />
                                            <span className="text-xs font-black uppercase tracking-widest">Reprendre</span>
                                        </button>
                                    ) : (
                                        <button
                                            onClick={handlePause}
                                            className="col-span-4 bg-orange-100 hover:bg-orange-200 text-orange-600 rounded-3xl py-6 transition-all flex flex-col items-center justify-center gap-2 border-2 border-transparent hover:border-orange-200"
                                        >
                                            <Clock className="w-8 h-8" />
                                            <span className="text-xs font-black uppercase tracking-widest">Pause</span>
                                        </button>
                                    )}

                                    {/* Finish Button */}
                                    <button
                                        onClick={() => setShowConfirm(true)}
                                        className="col-span-5 bg-gradient-to-br from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white rounded-3xl py-6 transition-all flex items-center justify-center gap-4 shadow-xl shadow-blue-200 active:scale-95"
                                    >
                                        <CheckCircle2 className="w-10 h-10" />
                                        <span className="text-2xl font-black tracking-tighter">TERMINER</span>
                                    </button>
                                </div>
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

            {/* MODAL: CONFIRMATION TERMINER */}
            {showConfirm && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[100] flex items-center justify-center p-6 animate-in fade-in duration-300">
                    <div className="bg-white rounded-[2.5rem] w-full max-w-lg p-10 shadow-2xl animate-in zoom-in-95 duration-300">
                        <div className="flex flex-col items-center text-center">
                            <div className="w-24 h-24 bg-blue-50 rounded-full flex items-center justify-center mb-6">
                                <CheckCircle2 className="w-12 h-12 text-blue-500" />
                            </div>
                            <h3 className="text-3xl font-black text-slate-800 mb-3 tracking-tight">Confirmation</h3>
                            <p className="text-slate-500 mb-8 max-w-[300px]">
                                Voulez-vous vraiment marquer la commande <span className="font-bold text-slate-800">{currentTask?.order_reference}</span> comme terminée sur ce poste ?
                            </p>
                            <div className="flex gap-4 w-full">
                                <button
                                    onClick={() => setShowConfirm(false)}
                                    className="flex-1 px-8 py-5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-black rounded-3xl transition-all tracking-widest uppercase text-xs"
                                >
                                    Annuler
                                </button>
                                <button
                                    onClick={handleStop}
                                    className="flex-1 px-8 py-5 bg-blue-500 hover:bg-blue-600 text-white font-black rounded-3xl shadow-xl shadow-blue-200 transition-all tracking-widest uppercase text-xs"
                                >
                                    Oui, Terminer
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* MODAL: SIGNALER PROBLEME */}
            {showIssueModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[100] flex items-center justify-center p-6 animate-in fade-in duration-300">
                    <div className="bg-white rounded-[2.5rem] w-full max-w-lg p-10 shadow-2xl animate-in zoom-in-95 duration-300">
                        <div className="flex flex-col">
                            <div className="flex items-center gap-4 mb-6">
                                <div className="p-3 bg-red-50 text-red-500 rounded-2xl">
                                    <AlertTriangle className="w-8 h-8" />
                                </div>
                                <h3 className="text-3xl font-black text-slate-800 tracking-tight">Signaler un Problème</h3>
                            </div>
                            <p className="text-slate-500 mb-6 font-medium">
                                Quel est le problème pour la commande <span className="font-bold text-slate-900 border-b-2 border-red-200">{selectedTask?.order_reference || currentTask?.order_reference}</span> ?
                            </p>

                            <div className="grid grid-cols-2 gap-3 mb-6">
                                {["Casse Vitrage", "Défaut Profilé", "Erreur Dimensions", "Manque Quincaillerie"].map(prob => (
                                    <button
                                        key={prob}
                                        type="button"
                                        onClick={() => setIssueNotes(prob)}
                                        className={`px-4 py-3 rounded-xl border-2 transition-all font-bold text-xs ${issueNotes === prob
                                            ? "border-red-500 bg-red-50 text-red-700 shadow-sm"
                                            : "border-slate-100 bg-slate-50 text-slate-600 hover:border-red-200"
                                            }`}
                                    >
                                        {prob}
                                    </button>
                                ))}
                            </div>

                            <textarea
                                value={issueNotes}
                                onChange={(e) => setIssueNotes(e.target.value)}
                                placeholder="Ou décrivez ici d'autres détails..."
                                className="w-full h-32 p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-red-500 focus:bg-white transition-all outline-none resize-none mb-8 text-slate-700 font-medium"
                            ></textarea>

                            <div className="flex gap-4 w-full">
                                <button
                                    onClick={() => setShowIssueModal(false)}
                                    className="px-6 py-5 bg-slate-100 hover:bg-slate-200 text-slate-600 font-black rounded-3xl transition-all tracking-widest uppercase text-xs"
                                >
                                    Annuler
                                </button>
                                <button
                                    onClick={handleReportIssue}
                                    disabled={!issueNotes.trim()}
                                    className="flex-1 px-8 py-5 bg-red-500 hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-black rounded-3xl shadow-xl shadow-red-200 transition-all tracking-widest uppercase text-xs"
                                >
                                    Envoyer le Signalement
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
