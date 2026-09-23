import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
    LayoutDashboard, Activity, ClipboardList, Settings, LogOut, X, Box, Archive,
    ShoppingCart, Truck, Users, UserCircle, FileText, BarChart3, CalendarDays,
    UserRoundCheck, ArrowRight, AlertTriangle, Package, MapPin, Layers,
    ClipboardCheck, Download, TrendingUp, ChevronDown
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { canAccessManagerView } from '../utils/roleNavigation';

export default function Sidebar({ activeView, setActiveView, isOpen, setIsOpen }) {
    const { logout, user } = useAuth();
    const routeLocation = useLocation();
    const routeParams = new URLSearchParams(routeLocation.search);
    const activeStockMenu = routeParams.get('stockMenu') || 'management-home';
    const [expandedMenus, setExpandedMenus] = useState({});
    const canAccess = (item) => {
        if (!canAccessManagerView(user, item.id)) return false;
        if (item.anyPermission) {
            const permissions = user?.permissions || [];
            return permissions.includes('*') || item.anyPermission.some(permission => permissions.includes(permission));
        }
        if (!item.permission) return true;
        const permissions = user?.permissions || [];
        return permissions.includes('*') || permissions.includes(item.permission);
    };
    const canAccessSubItem = (item) => {
        const permissions = user?.permissions || [];
        if (item.anyPermission) return permissions.includes('*') || item.anyPermission.some(permission => permissions.includes(permission));
        if (item.permission) return permissions.includes('*') || permissions.includes(item.permission);
        return true;
    };

    const menuCategories = [
        {
            title: 'Atelier & Production',
            items: [
                { id: 'dashboard', label: 'Tableau de Bord', icon: LayoutDashboard, type: 'internal' },
                { id: 'orders', label: 'Suivi Commandes', icon: ClipboardList, type: 'internal' },
                { id: 'workshop_supervisor', label: "Chef d'atelier", icon: Users, type: 'internal' },
                { id: 'live', label: 'Atelier Live', icon: Activity, type: 'internal' },
                { id: 'analytics_atelier', label: 'Analyse & Perf.', icon: BarChart3, type: 'internal' },
            ]
        },
        {
            title: 'Pilotage',
            items: [
                { id: 'schedule', label: 'Planning & Agenda', icon: CalendarDays, type: 'external', path: '/planning', permission: 'PLANNING_VIEW' },
                { id: 'planning_resources', label: 'Compétences & ressources', icon: UserRoundCheck, type: 'external', path: '/planning?settings=skills', permission: 'PLANNING_RESOURCE_MANAGE' },
            ]
        },
        {
            title: 'Commerce & Ventes',
            items: [
                { id: 'crm', label: 'CRM Avant-vente', icon: UserCircle, type: 'internal', permission: 'SALES_VIEW' },
                { id: 'sales', label: 'Commandes signées', icon: Users, type: 'internal', permission: 'SALES_VIEW' },
                { id: 'pos', label: 'Point de Vente (POS)', icon: ShoppingCart, type: 'external', path: '/pos', permission: 'SALES_EDIT' },
                { id: 'accounting', label: 'Facturation clients', icon: FileText, type: 'internal', permission: 'ACC_VIEW' },
            ]
        },
        {
            title: 'Supply Chain',
            items: [
                { id: 'stock_dashboard', label: 'Pilotage stock', icon: BarChart3, type: 'internal', anyPermission: ['STOCK_VIEW', 'inventory.approve_value'] },
                {
                    id: 'stock',
                    label: 'Gestion stock',
                    icon: Archive,
                    type: 'internal',
                    anyPermission: ['STOCK_VIEW', 'inventory.approve_value'],
                    subItems: [
                        { id: 'management-home', label: 'Parcours', icon: LayoutDashboard },
                        { id: 'workshop', label: 'Débit atelier', icon: ArrowRight },
                        { id: 'todo', label: 'À traiter', icon: AlertTriangle },
                        { id: 'risk', label: 'Stock à risque', icon: AlertTriangle },
                        { id: 'catalog', label: 'Catalogue', icon: Package },
                        { id: 'stock', label: 'Stock réel', icon: MapPin },
                        { id: 'services', label: 'Prestations', icon: FileText },
                        { id: 'drafts', label: 'Brouillons', icon: FileText },
                        { id: 'locations', label: 'Zones & emplacements', icon: MapPin },
                        { id: 'audit', label: 'Mouvements', icon: Layers },
                        { id: 'physical-inventory', label: 'Inventaire physique', icon: ClipboardCheck },
                        { id: 'import-export', label: 'Import / Export', icon: Download },
                        { id: 'valuation', label: 'Valorisation', icon: TrendingUp, anyPermission: ['inventory.approve_value'] },
                    ],
                },
                { id: 'purchases', label: 'Achats & Appro', icon: ShoppingCart, type: 'internal', permission: 'PURCHASES_VIEW' },
                { id: 'logistics', label: 'Logistique & Expédition', icon: Truck, type: 'internal' },
            ]
        },
        {
            title: 'Système',
            items: [
                { id: 'config', label: 'Paramètres & Accès', icon: Settings, type: 'internal' },
            ]
        }
    ];

    return (
        <>
            {/* Mobile Overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`
                fixed top-0 left-0 bottom-0 w-72 bg-slate-900 border-r border-slate-800 z-50 transform transition-transform duration-300 ease-in-out
                ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            `}>
                <div className="flex flex-col h-full">
                    {/* Header */}
                    <div className="p-6 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <Box className="w-6 h-6 text-white" />
                            </div>
                            <div>
                                <h2 className="text-white font-black tracking-tight leading-none uppercase">MMG</h2>
                                <p className="text-slate-500 text-[10px] font-bold tracking-widest uppercase mt-1">Atelier Connecté</p>
                            </div>
                        </div>
                        <button onClick={() => setIsOpen(false)} className="lg:hidden text-slate-400 p-2 hover:bg-slate-800 rounded-lg">
                            <X className="w-6 h-6" />
                        </button>
                    </div>

                    {/* Navigation */}
                    <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-6">
                        {menuCategories.map((category, catIndex) => (
                            <div key={catIndex} className="mb-8">
                                <h3 className="px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3">
                                    {category.title}
                                </h3>
                                <nav className="space-y-1">
                                    {category.items.filter(canAccess).map((item) => {
                                        const isSelected = activeView === item.id;
                                        const hasSubItems = item.subItems?.some(canAccessSubItem);
                                        const isExpanded = Boolean(expandedMenus[item.id]);
                                        const content = (
                                            <>
                                                <item.icon className={`w-5 h-5 ${isSelected ? 'text-white' : 'text-slate-500'}`} />
                                                {item.label}
                                            </>
                                        );
                                        const className = `
                                            w-full flex items-center gap-3 px-4 py-2.5 rounded-xl font-bold transition-all duration-200 text-sm
                                            ${isSelected
                                                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}
                                        `;

                                        if (item.type === 'external') {
                                            return (
                                                <Link
                                                    key={item.id}
                                                    to={item.path}
                                                    className={className}
                                                    onClick={() => { if (window.innerWidth < 1024) setIsOpen(false); }}
                                                >
                                                    {content}
                                                </Link>
                                            );
                                        }

                                        if (hasSubItems) {
                                            return (
                                                <div key={item.id}>
                                                    <div className={`flex items-center rounded-xl transition-all duration-200 ${
                                                        isSelected
                                                            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                                            : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                                                    }`}>
                                                        <Link
                                                            to={`/manager?view=${item.id}`}
                                                            state={{ view: item.id }}
                                                            onClick={() => {
                                                                if (setActiveView) setActiveView(item.id);
                                                                if (window.innerWidth < 1024 && setIsOpen) setIsOpen(false);
                                                            }}
                                                            className="flex min-w-0 flex-1 items-center gap-3 px-4 py-2.5 text-sm font-bold"
                                                        >
                                                            {content}
                                                        </Link>
                                                        <button
                                                            type="button"
                                                            onClick={(event) => {
                                                                event.preventDefault();
                                                                event.stopPropagation();
                                                                setExpandedMenus(prev => ({ ...prev, [item.id]: !prev[item.id] }));
                                                            }}
                                                            className={`mr-2 rounded-lg p-1.5 transition-colors ${isSelected ? 'text-white/80 hover:bg-white/10 hover:text-white' : 'text-slate-500 hover:bg-slate-700 hover:text-slate-200'}`}
                                                            aria-label={isExpanded ? `Replier ${item.label}` : `Déplier ${item.label}`}
                                                        >
                                                            <ChevronDown className={`h-4 w-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                                                        </button>
                                                    </div>
                                                    {isExpanded && isSelected && (
                                                        <div className="mt-2 ml-4 space-y-1 border-l border-slate-700/70 pl-3">
                                                            {item.subItems.filter(canAccessSubItem).map((subItem) => {
                                                                const SubIcon = subItem.icon;
                                                                const isSubSelected = activeStockMenu === subItem.id;
                                                                return (
                                                                    <Link
                                                                        key={subItem.id}
                                                                        to={`/manager?view=stock&stockMenu=${subItem.id}`}
                                                                        state={{ view: 'stock', stockMenu: subItem.id }}
                                                                        onClick={() => {
                                                                            if (window.innerWidth < 1024 && setIsOpen) setIsOpen(false);
                                                                        }}
                                                                        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-black transition-colors ${
                                                                            isSubSelected
                                                                                ? 'bg-slate-800 text-white'
                                                                                : 'text-slate-500 hover:bg-slate-800/70 hover:text-slate-200'
                                                                        }`}
                                                                    >
                                                                        <SubIcon className={`h-3.5 w-3.5 ${isSubSelected ? 'text-blue-300' : 'text-slate-600'}`} />
                                                                        <span className="truncate">{subItem.label}</span>
                                                                    </Link>
                                                                );
                                                            })}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        }

                                        return (
                                            <div key={item.id}>
                                                <Link
                                                    to={`/manager${item.id === 'dashboard' ? '' : `?view=${item.id}`}`}
                                                    state={{ view: item.id }}
                                                    onClick={() => {
                                                        if (setActiveView) setActiveView(item.id);
                                                        if (window.innerWidth < 1024 && setIsOpen) setIsOpen(false);
                                                    }}
                                                    className={className}
                                                >
                                                    {content}
                                                </Link>
                                            </div>
                                        );
                                    })}
                                </nav>
                            </div>
                        ))}
                    </div>

                    {/* Footer */}
                    <div className="p-4 border-t border-slate-800 space-y-2">
                        <button
                            onClick={logout}
                            className="w-full flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-red-500/10 hover:text-red-400 rounded-xl font-bold transition-all"
                        >
                            <LogOut className="w-5 h-5" />
                            Déconnexion
                        </button>
                    </div>
                </div>
            </aside>
        </>
    );
}
