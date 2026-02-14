import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Lock, Delete } from 'lucide-react';

export default function Login() {
    const [pin, setPin] = useState('');
    const [error, setError] = useState('');
    const { login } = useAuth();
    const navigate = useNavigate();

    const handleNum = (num) => {
        if (pin.length < 4) {
            setPin(prev => prev + num);
            setError('');
        }
    };

    const handleDelete = () => {
        setPin(prev => prev.slice(0, -1));
    };

    const handleSubmit = async () => {
        if (pin.length !== 4) return;

        // Simple PIN mapping for Kiosk mode (MVP)
        let username = 'admin'; // Default fallback
        if (pin === '1111') username = 'op_debit';
        if (pin === '2222') username = 'op_soudure';
        if (pin === '3333') username = 'op_assemblage';
        if (pin === '4444') username = 'op_vitrage';
        if (pin === '1234') username = 'admin'; // Explicit
        if (pin === '0000') username = 'manager';

        const success = await login(username, pin);
        if (success) {
            // Redirect based on role/station (handled by App.jsx or here)
            // Ideally, we check the role returned by login and redirect accordingly
            // For now, simpler:
            if (username === 'admin' || username === 'manager') {
                navigate('/manager');
            } else {
                // Determine station from username for redirection
                let station = 'PVC_DEBIT';
                if (username === 'op_soudure') station = 'PVC_SOUDURE';
                if (username === 'op_assemblage') station = 'PVC_ASSEMBLAGE';
                if (username === 'op_vitrage') station = 'PVC_VITRAGE';
                navigate(`/dashboard/${station}`);
            }
        } else {
            setError('Code PIN Incorrect');
            setPin('');
        }
    };

    return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
            <div className="bg-slate-800 p-8 rounded-2xl shadow-2xl w-full max-w-md border border-slate-700">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-600/20">
                        <Lock className="text-white w-8 h-8" />
                    </div>
                    <h1 className="text-2xl font-bold text-white mb-2">Atelier Connecté</h1>
                    <p className="text-slate-400">Entrez votre code PIN</p>
                </div>

                <div className="flex justify-center gap-4 mb-8">
                    {[0, 1, 2, 3].map((i) => (
                        <div
                            key={i}
                            className={`w-4 h-4 rounded-full transition-all duration-300 ${i < pin.length ? 'bg-blue-500 scale-125' : 'bg-slate-600'
                                }`}
                        />
                    ))}
                </div>

                {error && (
                    <div className="text-red-500 text-center mb-4 font-bold animate-pulse">
                        {error}
                    </div>
                )}

                <div className="grid grid-cols-3 gap-4 mb-6">
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((num) => (
                        <button
                            key={num}
                            onClick={() => handleNum(num)}
                            className="bg-slate-700 hover:bg-slate-600 text-white text-2xl font-bold py-6 rounded-xl transition-all active:scale-95 shadow-lg border border-slate-600"
                        >
                            {num}
                        </button>
                    ))}
                    <div className="col-start-2">
                        <button
                            onClick={() => handleNum(0)}
                            className="w-full bg-slate-700 hover:bg-slate-600 text-white text-2xl font-bold py-6 rounded-xl transition-all active:scale-95 shadow-lg border border-slate-600"
                        >
                            0
                        </button>
                    </div>
                    <div className="col-start-3">
                        <button
                            onClick={handleDelete}
                            className="w-full bg-slate-700 hover:bg-slate-600 text-red-400 text-2xl font-bold py-6 rounded-xl transition-all active:scale-95 shadow-lg border border-slate-600 flex items-center justify-center"
                        >
                            <Delete className="w-8 h-8" />
                        </button>
                    </div>
                </div>

                <button
                    onClick={handleSubmit}
                    disabled={pin.length !== 4}
                    className={`w-full py-4 rounded-xl text-lg font-bold transition-all ${pin.length === 4
                        ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30 active:scale-95'
                        : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                        }`}
                >
                    CONNEXION
                </button>
            </div>
        </div>
    );
}
