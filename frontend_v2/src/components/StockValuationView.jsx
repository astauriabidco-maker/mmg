import React, { useMemo } from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend } from 'recharts';
import { DollarSign, TrendingUp, Layers, MapPin } from 'lucide-react';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#64748b'];

export default function StockValuationView({ products, locations, quants }) {
    
    const valuationData = useMemo(() => {
        let totalValuation = 0;
        const byCategory = {};
        const byLocation = {};
        const variantsMap = {};

        // Find all internal locations
        const internalLocations = locations.filter(l => l.usage === 'internal');
        const internalLocIds = internalLocations.map(l => l.id);

        // Pre-map variants to their products
        const variantToProduct = {};
        products.forEach(p => {
            p.variants.forEach(v => {
                variantToProduct[v.id] = { product: p, variant: v };
            });
        });

        // Loop over all quants to aggregate
        quants.forEach(q => {
            if (!internalLocIds.includes(q.location_id)) return; // Only value internal stock
            if (q.quantity <= 0) return; // Ignore negative or empty
            
            const mapping = variantToProduct[q.variant_id];
            if (!mapping) return;
            const { product, variant } = mapping;
            const cost = parseFloat(variant.cost_price) || 0;
            if (cost <= 0) return;

            const value = q.quantity * cost;
            totalValuation += value;

            // By Category
            const cat = product.material_type || 'Autre';
            if (!byCategory[cat]) byCategory[cat] = 0;
            byCategory[cat] += value;

            // By Location
            const locName = locations.find(l => l.id === q.location_id)?.name || 'Inconnu';
            if (!byLocation[locName]) byLocation[locName] = 0;
            byLocation[locName] += value;

            // By Variant (Top Valuable)
            const varName = `${product.name} (${variant.reference})`;
            if (!variantsMap[varName]) variantsMap[varName] = { name: varName, value: 0, qty: 0 };
            variantsMap[varName].value += value;
            variantsMap[varName].qty += q.quantity;
        });

        const categoryData = Object.keys(byCategory).map(k => ({ name: k, value: byCategory[k] })).sort((a,b) => b.value - a.value);
        const locationData = Object.keys(byLocation).map(k => ({ name: k, value: byLocation[k] })).sort((a,b) => b.value - a.value);
        const topVariants = Object.values(variantsMap).sort((a,b) => b.value - a.value).slice(0, 10);

        return { totalValuation, categoryData, locationData, topVariants };
    }, [products, locations, quants]);

    const formatCurrency = (val) => val.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'});

    return (
        <div className="flex flex-col gap-6 w-full h-full p-4 pb-20 overflow-y-auto">
            
            {/* TOP CARDS */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 shrink-0">
                <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-6 shadow-xl text-white relative overflow-hidden border border-slate-700">
                    <div className="absolute -right-10 -top-10 w-32 h-32 bg-blue-500/20 rounded-full blur-2xl"></div>
                    <div className="relative z-10 flex flex-col">
                        <span className="text-sm font-black text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-2"><DollarSign className="w-4 h-4"/> Valorisation Globale</span>
                        <span className="text-4xl font-black">{formatCurrency(valuationData.totalValuation)}</span>
                    </div>
                </div>

                <div className="bg-white rounded-3xl p-6 shadow-lg border border-slate-100 flex flex-col justify-center">
                    <span className="text-sm font-black text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-2"><Layers className="w-4 h-4 text-emerald-500"/> Première Catégorie</span>
                    <span className="text-2xl font-black text-slate-800">
                        {valuationData.categoryData[0] ? valuationData.categoryData[0].name : 'N/A'}
                    </span>
                    <span className="text-sm font-bold text-slate-500">
                        {valuationData.categoryData[0] ? formatCurrency(valuationData.categoryData[0].value) : ''}
                    </span>
                </div>

                <div className="bg-white rounded-3xl p-6 shadow-lg border border-slate-100 flex flex-col justify-center">
                    <span className="text-sm font-black text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-2"><MapPin className="w-4 h-4 text-orange-500"/> Emplacement Majeur</span>
                    <span className="text-2xl font-black text-slate-800">
                        {valuationData.locationData[0] ? valuationData.locationData[0].name : 'N/A'}
                    </span>
                    <span className="text-sm font-bold text-slate-500">
                        {valuationData.locationData[0] ? formatCurrency(valuationData.locationData[0].value) : ''}
                    </span>
                </div>
            </div>

            {/* CHARTS */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 shrink-0">
                {/* CATEGORY PIE CHART */}
                <div className="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-6">Répartition par Catégorie (Matière)</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={valuationData.categoryData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({name, percent}) => `${name} ${(percent*100).toFixed(0)}%`}>
                                    {valuationData.categoryData.map((entry, index) => <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />)}
                                </Pie>
                                <Tooltip formatter={(value) => formatCurrency(value)} />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                {/* LOCATION BAR CHART */}
                <div className="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
                    <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-6">Valorisation par Emplacement</h3>
                    <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={valuationData.locationData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9"/>
                                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}}/>
                                <YAxis axisLine={false} tickLine={false} tick={{fill: '#94a3b8', fontSize: 12}} tickFormatter={(value) => `€${value/1000}k`}/>
                                <Tooltip formatter={(value) => formatCurrency(value)} cursor={{fill: '#f8fafc'}}/>
                                <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} barSize={40} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* TOP VARIANTS TABLE */}
            <div className="bg-white rounded-3xl p-6 shadow-lg border border-slate-100 mb-8 shrink-0">
                <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-6 flex items-center gap-2"><TrendingUp className="w-4 h-4"/> Top 10 Valeurs Immobilisées</h3>
                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="border-b border-slate-100 text-xs font-black text-slate-400 uppercase tracking-widest">
                                <th className="pb-3 px-4">Référence Produit</th>
                                <th className="pb-3 px-4 text-right">Qté Stock</th>
                                <th className="pb-3 px-4 text-right">Valeur Totale</th>
                                <th className="pb-3 px-4 text-right">% du Global</th>
                            </tr>
                        </thead>
                        <tbody>
                            {valuationData.topVariants.map((v, idx) => (
                                <tr key={idx} className="border-b border-slate-50 last:border-none hover:bg-slate-50/50 transition-colors">
                                    <td className="py-4 px-4">
                                        <div className="font-bold text-slate-800">{v.name}</div>
                                    </td>
                                    <td className="py-4 px-4 text-right font-black text-slate-500">{v.qty}</td>
                                    <td className="py-4 px-4 text-right font-black text-slate-800">{formatCurrency(v.value)}</td>
                                    <td className="py-4 px-4 text-right font-bold text-blue-500">
                                        {valuationData.totalValuation > 0 ? ((v.value / valuationData.totalValuation) * 100).toFixed(1) + '%' : '0%'}
                                    </td>
                                </tr>
                            ))}
                            {valuationData.topVariants.length === 0 && (
                                <tr>
                                    <td colSpan="4" className="py-8 text-center text-slate-400 font-bold">Aucune donnée disponible. Ajoutez des prix d'achats sur vos variantes.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>
    );
}
