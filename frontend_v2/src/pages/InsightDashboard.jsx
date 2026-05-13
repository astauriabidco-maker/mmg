import React, { useState, useRef, useEffect } from 'react';
import api from '../services/api';
import { Send, Bot, User, Sparkles } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line } from 'recharts';

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

export default function InsightDashboard() {
    const [messages, setMessages] = useState([
        { 
            id: 1, 
            sender: 'ai', 
            text: "Bonjour ! Je suis l'Insight Engine de MMG. Posez-moi des questions sur le **chiffre d'affaires**, les **produits vendus** ou la **production**.",
            widget: null
        }
    ]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSend = async (e) => {
        e.preventDefault();
        if (!input.trim()) return;

        const userMsg = { id: Date.now(), sender: 'user', text: input, widget: null };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const res = await api.post('/v2/analytics/ask', { query: userMsg.text });
            const data = res.data;
            
            setMessages(prev => [...prev, {
                id: Date.now(),
                sender: 'ai',
                text: data.message,
                widget: data.type !== 'text' ? { type: data.type, data: data.data } : null
            }]);
        } catch (error) {
            console.error(error);
            setMessages(prev => [...prev, {
                id: Date.now(),
                sender: 'ai',
                text: "Désolé, une erreur s'est produite lors de la connexion à mon moteur d'analyse.",
                widget: null
            }]);
        } finally {
            setLoading(false);
        }
    };

    const renderWidget = (widget) => {
        if (!widget) return null;

        return (
            <div className="mt-4 bg-white p-4 rounded-xl shadow-sm border border-slate-200 h-64 w-full text-slate-800">
                {widget.type === 'barchart' && (
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={widget.data}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip cursor={{fill: 'transparent'}} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                            <Bar dataKey="total" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={40} />
                        </BarChart>
                    </ResponsiveContainer>
                )}
                {widget.type === 'piechart' && (
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={widget.data}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={80}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {widget.data.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                        </PieChart>
                    </ResponsiveContainer>
                )}
                {widget.type === 'linechart' && (
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={widget.data}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }} />
                            <Line type="monotone" dataKey="reel" stroke="#ef4444" strokeWidth={3} dot={{r: 4}} activeDot={{r: 6}} name="Temps Réel (m)" />
                            <Line type="dashed" dataKey="objectif" stroke="#94a3b8" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Objectif (m)" />
                        </LineChart>
                    </ResponsiveContainer>
                )}
            </div>
        );
    };

    // Format text with bolding
    const formatText = (text) => {
        const parts = text.split(/(\*\*.*?\*\*)/g);
        return parts.map((part, i) => {
            if (part.startsWith('**') && part.endsWith('**')) {
                return <strong key={i} className="font-bold text-indigo-700">{part.slice(2, -2)}</strong>;
            }
            return part;
        });
    };

    return (
        <div className="p-8 h-[calc(100vh-80px)] flex flex-col max-w-5xl mx-auto">
            <div className="mb-6 flex justify-between items-center shrink-0">
                <div>
                    <h2 className="text-2xl font-black text-slate-800 flex items-center gap-2">
                        <Sparkles className="w-6 h-6 text-indigo-500" />
                        Insight Engine
                    </h2>
                    <p className="text-slate-500">Posez vos questions métiers en langage naturel, l'IA génère les analyses.</p>
                </div>
            </div>

            <div className="flex-1 bg-white border border-slate-200 rounded-3xl shadow-xl flex flex-col overflow-hidden">
                <div className="flex-1 p-6 overflow-y-auto space-y-6 bg-slate-50">
                    {messages.map(msg => (
                        <div key={msg.id} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`flex max-w-[80%] ${msg.sender === 'user' ? 'flex-row-reverse' : 'flex-row'} items-end gap-3`}>
                                <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-md ${msg.sender === 'user' ? 'bg-slate-800' : 'bg-indigo-600'}`}>
                                    {msg.sender === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5 text-white" />}
                                </div>
                                <div className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                                    <div className={`p-4 rounded-2xl shadow-sm text-sm leading-relaxed ${
                                        msg.sender === 'user' 
                                            ? 'bg-slate-800 text-white rounded-br-sm' 
                                            : 'bg-white text-slate-700 border border-slate-100 rounded-bl-sm'
                                    }`}>
                                        {formatText(msg.text)}
                                    </div>
                                    {renderWidget(msg.widget)}
                                </div>
                            </div>
                        </div>
                    ))}
                    {loading && (
                        <div className="flex justify-start">
                            <div className="flex items-end gap-3">
                                <div className="w-10 h-10 rounded-full bg-indigo-600 flex items-center justify-center shrink-0 shadow-md">
                                    <Bot className="w-5 h-5 text-white" />
                                </div>
                                <div className="bg-white p-4 rounded-2xl border border-slate-100 rounded-bl-sm flex gap-1 items-center h-12">
                                    <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                                    <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                                    <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
                                </div>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className="p-4 bg-white border-t border-slate-200 shrink-0">
                    <form onSubmit={handleSend} className="relative max-w-4xl mx-auto">
                        <input 
                            type="text" 
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder="Ex: Quel est le CA de la semaine ?"
                            className="w-full bg-slate-100 text-slate-800 font-medium rounded-full py-4 pl-6 pr-14 outline-none focus:ring-2 focus:ring-indigo-500 transition-all border border-transparent focus:border-indigo-300 focus:bg-white"
                            disabled={loading}
                        />
                        <button 
                            type="submit" 
                            disabled={!input.trim() || loading}
                            className="absolute right-2 top-2 bottom-2 aspect-square bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-full flex items-center justify-center transition-transform active:scale-95"
                        >
                            <Send className="w-5 h-5 ml-1" />
                        </button>
                    </form>
                    <div className="text-center mt-3 text-xs font-medium text-slate-400 flex justify-center items-center gap-2 flex-wrap">
                        <button onClick={() => setInput("Quel est le chiffre d'affaires ?")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">💰 CA</button>
                        <button onClick={() => setInput("Quels sont les produits les plus vendus ?")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">📦 Produits</button>
                        <button onClick={() => setInput("Analyse de la production et retards")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">🏭 Production</button>
                        <button onClick={() => setInput("État du stock et ruptures")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">📊 Inventaire</button>
                        <button onClick={() => setInput("Bilan des achats fournisseurs")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">🛒 Achats</button>
                        <button onClick={() => setInput("État des livraisons")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">🚚 Logistique</button>
                        <button onClick={() => setInput("Analyse du portefeuille clients et devis")} className="hover:text-indigo-500 transition-colors px-2 py-1 rounded-lg hover:bg-indigo-50">👥 CRM</button>
                    </div>
                </div>
            </div>
        </div>
    );
}
