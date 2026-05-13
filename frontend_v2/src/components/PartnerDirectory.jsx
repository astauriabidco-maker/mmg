import React, { useState, useEffect } from 'react';
import { Search, Plus, Mail, Phone, MapPin, Building2, UserCircle, Edit, Trash2 } from 'lucide-react';
import api from '../services/api';

export default function PartnerDirectory({ type = "CLIENT" }) {
    const [partners, setPartners] = useState([]);
    const [searchTerm, setSearchTerm] = useState('');
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingPartner, setEditingPartner] = useState(null);

    const endpoint = type === 'CLIENT' ? '/v2/partners/clients' : '/v2/partners/suppliers';
    const title = type === 'CLIENT' ? 'Annuaire Clients' : 'Annuaire Fournisseurs';

    const fetchPartners = async () => {
        try {
            const res = await api.get(endpoint);
            setPartners(res.data);
        } catch (error) {
            console.error("Erreur chargement partenaires", error);
        }
    };

    useEffect(() => {
        fetchPartners();
    }, [type]);

    const handleSave = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);
        
        try {
            if (editingPartner) {
                await api.put(`${endpoint}/${editingPartner.id}`, data);
            } else {
                await api.post(endpoint, data);
            }
            fetchPartners();
            setIsModalOpen(false);
            setEditingPartner(null);
        } catch (error) {
            alert("Erreur lors de l'enregistrement.");
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Supprimer ce partenaire ?")) return;
        try {
            await api.delete(`${endpoint}/${id}`);
            fetchPartners();
        } catch (error) {
            alert("Erreur lors de la suppression.");
        }
    };

    const filteredPartners = partners.filter(p => 
        p.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
        (p.contact_name && p.contact_name.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (p.phone && p.phone.includes(searchTerm))
    );

    return (
        <div className="flex-1 flex flex-col h-full bg-slate-50/50">
            {/* Header */}
            <div className="bg-white px-8 py-6 border-b border-slate-200 flex justify-between items-center z-10 shrink-0">
                <div>
                    <h2 className="text-2xl font-black text-slate-800 tracking-tight flex items-center gap-3">
                        <UserCircle className={`w-8 h-8 ${type === 'CLIENT' ? 'text-indigo-600' : 'text-emerald-600'}`} />
                        {title}
                    </h2>
                    <p className="text-slate-500 font-medium text-sm mt-1">Gérez votre base de contacts et informations légales.</p>
                </div>
                <div className="flex items-center gap-4">
                    <div className="relative">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                        <input 
                            type="text" 
                            placeholder="Rechercher un contact..." 
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="w-64 bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                    </div>
                    <button 
                        onClick={() => { setEditingPartner(null); setIsModalOpen(true); }}
                        className={`px-4 py-2.5 rounded-xl font-bold text-white shadow-md flex items-center gap-2 transition-all hover:scale-105 active:scale-95 ${type === 'CLIENT' ? 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-500/20' : 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/20'}`}
                    >
                        <Plus className="w-4 h-4"/> Nouveau
                    </button>
                </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto p-8">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                    {filteredPartners.map(partner => (
                        <div key={partner.id} className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm hover:shadow-xl hover:border-indigo-300 transition-all group flex flex-col">
                            <div className="flex justify-between items-start mb-4">
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center font-black text-xl shadow-inner ${type === 'CLIENT' ? 'bg-indigo-50 text-indigo-600' : 'bg-emerald-50 text-emerald-600'}`}>
                                    {partner.name.charAt(0).toUpperCase()}
                                </div>
                                <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <button onClick={() => { setEditingPartner(partner); setIsModalOpen(true); }} className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg">
                                        <Edit className="w-4 h-4" />
                                    </button>
                                    <button onClick={() => handleDelete(partner.id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                            
                            <div className="flex-1">
                                <h3 className="font-black text-lg text-slate-900 truncate" title={partner.name}>{partner.name}</h3>
                                {partner.contact_name && <p className="text-sm font-bold text-slate-500 mt-1">{partner.contact_name}</p>}
                                
                                <div className="mt-4 space-y-2">
                                    {partner.email && (
                                        <div className="flex items-center gap-2 text-sm text-slate-600">
                                            <Mail className="w-4 h-4 text-slate-400 shrink-0" />
                                            <a href={`mailto:${partner.email}`} className="truncate hover:text-blue-600 font-medium">{partner.email}</a>
                                        </div>
                                    )}
                                    {partner.phone && (
                                        <div className="flex items-center gap-2 text-sm text-slate-600">
                                            <Phone className="w-4 h-4 text-slate-400 shrink-0" />
                                            <a href={`tel:${partner.phone}`} className="truncate hover:text-blue-600 font-medium">{partner.phone}</a>
                                        </div>
                                    )}
                                    {partner.address && (
                                        <div className="flex items-start gap-2 text-sm text-slate-600">
                                            <MapPin className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                                            <span className="line-clamp-2 font-medium">{partner.address}</span>
                                        </div>
                                    )}
                                    {partner.tax_id && (
                                        <div className="flex items-center gap-2 text-sm text-slate-600 mt-3 pt-3 border-t border-slate-100">
                                            <Building2 className="w-4 h-4 text-slate-400 shrink-0" />
                                            <span className="font-bold">SIRET: {partner.tax_id}</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-3xl p-8 max-w-lg w-full animate-fade-in shadow-2xl">
                        <h3 className="text-xl font-black text-slate-800 mb-6">
                            {editingPartner ? 'Modifier le partenaire' : 'Nouveau partenaire'}
                        </h3>
                        <form onSubmit={handleSave} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-500 mb-1">Nom de l'entreprise ou du particulier *</label>
                                <input name="name" defaultValue={editingPartner?.name} required className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1">Contact (Nom Prénom)</label>
                                    <input name="contact_name" defaultValue={editingPartner?.contact_name} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1">Téléphone</label>
                                    <input name="phone" defaultValue={editingPartner?.phone} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 mb-1">Email</label>
                                <input type="email" name="email" defaultValue={editingPartner?.email} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-500 mb-1">Adresse physique</label>
                                <input name="address" defaultValue={editingPartner?.address} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-500 mb-1">Numéro SIRET / TVA</label>
                                    <input name="tax_id" defaultValue={editingPartner?.tax_id} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500" />
                                </div>
                                {type === 'CLIENT' && (
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 mb-1">Type de Client</label>
                                        <select name="customer_type" defaultValue={editingPartner?.customer_type || "B2B"} className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 font-bold outline-none focus:ring-2 focus:ring-indigo-500">
                                            <option value="B2B">Professionnel (B2B)</option>
                                            <option value="B2C">Particulier (B2C)</option>
                                        </select>
                                    </div>
                                )}
                            </div>

                            <div className="flex gap-4 mt-8 pt-4 border-t border-slate-100">
                                <button type="button" onClick={() => setIsModalOpen(false)} className="flex-1 py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl transition-colors">
                                    Annuler
                                </button>
                                <button type="submit" className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl transition-colors shadow-md">
                                    Enregistrer
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
