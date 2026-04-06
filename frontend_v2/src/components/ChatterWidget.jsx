import React, { useState, useEffect } from 'react';
import { MessageSquare, Clock, Send, ShieldAlert, FileText } from 'lucide-react';
import api from '../services/api';

export default function ChatterWidget({ modelName, recordId }) {
    const [messages, setMessages] = useState([]);
    const [newMessage, setNewMessage] = useState('');
    const [isLoading, setIsLoading] = useState(true);

    const fetchChatter = async () => {
        if (!recordId) return;
        setIsLoading(true);
        try {
            const res = await api.get(`/v2/stock/chatter/${modelName}/${recordId}`);
            setMessages(res.data);
        } catch (e) {
            console.error("Error fetching chatter", e);
        }
        setIsLoading(false);
    };

    useEffect(() => {
        fetchChatter();
    }, [modelName, recordId]);

    const handleSend = async (e) => {
        e.preventDefault();
        if (!newMessage.trim()) return;

        try {
            await api.post('/v2/stock/chatter', {
                model_name: modelName,
                record_id: recordId,
                body: newMessage,
                is_system_log: false
            });
            setNewMessage('');
            fetchChatter();
        } catch (e) {
            console.error("Error posting message", e);
        }
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        const d = new Date(dateString);
        return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full max-h-[500px]">
            <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                <h3 className="font-black text-sm text-slate-800 flex items-center gap-2">
                    <MessageSquare className="w-4 h-4 text-slate-500" /> Historique & Audit Log
                </h3>
                <span className="text-xs font-bold text-slate-400 bg-white px-2 py-1 rounded-md border border-slate-200 shadow-sm">{messages.length} enregistrements</span>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50">
                {isLoading ? (
                    <div className="animate-pulse space-y-3">
                        <div className="h-10 bg-slate-200 rounded-lg w-full"></div>
                        <div className="h-10 bg-slate-200 rounded-lg w-3/4"></div>
                    </div>
                ) : messages.length === 0 ? (
                    <div className="text-center py-8">
                        <FileText className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                        <p className="text-xs font-bold text-slate-400 italic">Aucun historique pour le moment.</p>
                    </div>
                ) : (
                    messages.map(msg => (
                        <div key={msg.id} className={`p-3 rounded-xl border text-sm relative transition-all hover:-translate-y-0.5 hover:shadow-md ${msg.is_system_log ? 'bg-slate-100 border-slate-200 pl-4 border-l-4 border-l-slate-400' : 'bg-blue-50 border-blue-100 pl-4 border-l-4 border-l-blue-400'}`}>
                            <div className="flex items-center justify-between mb-1">
                                <span className="font-black text-xs flex items-center gap-1">
                                    {msg.is_system_log ? <ShieldAlert className="w-3 h-3 text-slate-500"/> : <MessageSquare className="w-3 h-3 text-blue-500"/>}
                                    <span className={msg.is_system_log ? 'text-slate-600' : 'text-blue-700'}>{msg.author}</span>
                                </span>
                                <span className="text-[10px] font-bold text-slate-400 flex items-center gap-1">
                                    <Clock className="w-3 h-3" /> {formatDate(msg.created_at)}
                                </span>
                            </div>
                            <p className={`font-medium leading-relaxed whitespace-pre-wrap ${msg.is_system_log ? 'text-slate-600 text-xs' : 'text-blue-900 text-sm'}`}>
                                {msg.body}
                            </p>
                        </div>
                    ))
                )}
            </div>

            <form onSubmit={handleSend} className="p-3 bg-white border-t border-slate-200 flex gap-2">
                <input 
                    type="text" 
                    value={newMessage}
                    onChange={(e) => setNewMessage(e.target.value)}
                    placeholder="Laisser une note explicative..." 
                    className="flex-1 px-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium outline-none focus:ring-2 focus:ring-blue-500 transition-shadow"
                />
                <button type="submit" disabled={!newMessage.trim()} className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl shadow border-b-2 border-blue-700 active:border-b-0 active:translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed transition-all">
                    <Send className="w-5 h-5" />
                </button>
            </form>
        </div>
    );
}
