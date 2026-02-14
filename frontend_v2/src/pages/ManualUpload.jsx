import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { Upload, FileText, CheckCircle, AlertCircle, ArrowLeft } from 'lucide-react';

export default function ManualUpload() {
    const navigate = useNavigate();
    const [file, setFile] = useState(null);
    const [status, setStatus] = useState('idle'); // idle, uploading, success, error
    const [message, setMessage] = useState('');

    const handleFileChange = (e) => {
        setFile(e.target.files[0]);
        setStatus('idle');
    };

    const handleUpload = async () => {
        if (!file) return;

        setStatus('uploading');
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await api.post('/v2/ingest/upload', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data',
                },
            });
            setStatus('success');
            setMessage(response.data.message || 'Fichier déposé avec succès.');
            setFile(null);
        } catch (e) {
            console.error(e);
            setStatus('error');
            setMessage('Échec de l\'envoi du fichier. Veuillez réessayer.');
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 p-8 font-sans">
            <div className="max-w-2xl mx-auto">
                <button
                    onClick={() => navigate('/manager')}
                    className="flex items-center gap-2 text-slate-500 hover:text-slate-800 transition-colors mb-8 group"
                >
                    <ArrowLeft className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
                    Retour au Dashboard
                </button>

                <div className="bg-white p-10 rounded-3xl shadow-xl border border-slate-100">
                    <div className="text-center mb-10">
                        <div className="w-20 h-20 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                            <Upload className="text-blue-600 w-10 h-10" />
                        </div>
                        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Dépôt de Commande</h1>
                        <p className="text-slate-500 mt-2">Uploadez vos fichiers PDF ou TXT pour traitement OCR</p>
                    </div>

                    <div className="space-y-6">
                        <div
                            className={`border-4 border-dashed rounded-3xl p-12 text-center transition-all ${file ? 'border-green-200 bg-green-50' : 'border-slate-100 hover:border-blue-200 hover:bg-blue-50'
                                }`}
                        >
                            <input
                                type="file"
                                id="file-upload"
                                className="hidden"
                                accept=".pdf,.txt"
                                onChange={handleFileChange}
                            />
                            <label htmlFor="file-upload" className="cursor-pointer block">
                                {file ? (
                                    <div className="flex flex-col items-center">
                                        <FileText className="w-16 h-16 text-green-500 mb-4" />
                                        <p className="text-green-700 font-bold text-lg">{file.name}</p>
                                        <p className="text-green-600/60 text-sm">Prêt pour l'envoi</p>
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center">
                                        <Upload className="w-16 h-16 text-slate-300 mb-4" />
                                        <p className="text-slate-600 font-bold text-lg">Cliquez pour choisir un fichier</p>
                                        <p className="text-slate-400 text-sm">PDF ou TXT uniquement</p>
                                    </div>
                                )}
                            </label>
                        </div>

                        {status === 'success' && (
                            <div className="bg-green-100 text-green-700 p-4 rounded-xl flex items-center gap-3 animate-fade-in">
                                <CheckCircle className="w-6 h-6 shrink-0" />
                                <p className="font-semibold">{message}</p>
                            </div>
                        )}

                        {status === 'error' && (
                            <div className="bg-red-100 text-red-700 p-4 rounded-xl flex items-center gap-3 animate-fade-in">
                                <AlertCircle className="w-6 h-6 shrink-0" />
                                <p className="font-semibold">{message}</p>
                            </div>
                        )}

                        <button
                            onClick={handleUpload}
                            disabled={!file || status === 'uploading'}
                            className={`w-full py-5 rounded-2xl text-xl font-black transition-all shadow-lg ${!file || status === 'uploading'
                                    ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                    : 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-500/30 active:scale-[0.98]'
                                }`}
                        >
                            {status === 'uploading' ? 'ENVOI EN COURS...' : 'DÉPOSER LA COMMANDE'}
                        </button>
                    </div>
                </div>

                <div className="mt-10 bg-amber-50 border border-amber-100 p-6 rounded-2xl flex gap-4">
                    <AlertCircle className="text-amber-500 w-6 h-6 shrink-0" />
                    <div>
                        <p className="text-amber-800 font-bold mb-1">Note pour les commerciaux</p>
                        <p className="text-amber-700 text-sm leading-relaxed">
                            Une fois le fichier déposé, l'OCR traitera les données sous 10 secondes. La commande apparaîtra ensuite automatiquement dans le planning de production.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
