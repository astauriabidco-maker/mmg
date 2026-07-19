import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Lock, Delete } from 'lucide-react';

export default function Login() {
    const [pin, setPin] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [isKioskMode, setIsKioskMode] = useState(true);
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

    const handleSubmit = async (e) => {
        if (e) e.preventDefault();

        const loginUsername = username.trim();
        if (!loginUsername) return;
        if (isKioskMode && pin.length !== 4) return;
        const loginPassword = isKioskMode ? pin : password;
        if (!loginPassword) return;

        const success = await login(loginUsername, loginPassword);
        if (success) {
            if (loginUsername === 'admin' || loginUsername === 'manager') {
                navigate('/manager');
            } else {
                let station = 'PVC_DEBIT';
                if (loginUsername === 'op_soudure') station = 'PVC_SOUDURE';
                if (loginUsername === 'op_assemblage') station = 'PVC_ASSEMBLAGE';
                if (loginUsername === 'op_vitrage') station = 'PVC_VITRAGE';
                navigate(`/dashboard/${station}`);
            }
        } else {
            setError('Identifiants incorrects');
            setPin('');
            setPassword('');
        }
    };

    return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
            <div className="bg-slate-800 p-8 rounded-2xl shadow-2xl w-full max-w-md border border-slate-700">
                <div className="text-center mb-8">
                    <div className="w-16 h-16 bg-blue-600 rounded-full flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-600/20">
                        <Lock className="text-white w-8 h-8" />
                    </div>
                    <h1 className="text-2xl font-bold text-white mb-2">MMG Industrie</h1>
                    <p className="text-slate-400">
                        {isKioskMode ? "Atelier: Entrez votre code PIN" : "Bureau: Connectez-vous"}
                    </p>
                </div>
                
                <div className="flex bg-slate-700 p-1 rounded-xl mb-8">
                    <button 
                        onClick={() => { setIsKioskMode(true); setError(''); }}
                        className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${isKioskMode ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                    >
                        Atelier (PIN)
                    </button>
                    <button 
                        onClick={() => { setIsKioskMode(false); setError(''); }}
                        className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${!isKioskMode ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                    >
                        Bureau (Login)
                    </button>
                </div>

                {error && (
                    <div className="text-red-500 text-center mb-4 font-bold animate-pulse">
                        {error}
                    </div>
                )}

                {isKioskMode ? (
                    <>
                        <div className="mb-6">
                            <label className="block text-slate-400 text-sm font-bold mb-2">Identifiant</label>
                            <input
                                type="text"
                                value={username}
                                onChange={(e) => { setUsername(e.target.value); setError(''); }}
                                className="w-full bg-slate-700 border border-slate-600 text-white rounded-xl p-4 outline-none focus:border-blue-500 transition-colors"
                                placeholder="ex: op_debit"
                            />
                        </div>

                        <div className="flex justify-center gap-4 mb-8">
                            {[0, 1, 2, 3].map((i) => (
                                <div
                                    key={i}
                                    className={`w-4 h-4 rounded-full transition-all duration-300 ${i < pin.length ? 'bg-blue-500 scale-125' : 'bg-slate-600'}`}
                                />
                            ))}
                        </div>

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
                        onClick={() => handleSubmit()}
                        disabled={pin.length !== 4 || !username.trim()}
                        className={`w-full py-4 rounded-xl text-lg font-bold transition-all ${pin.length === 4 && username.trim()
                            ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30 active:scale-95'
                            : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                            }`}
                    >
                        CONNEXION
                    </button>
                </>
                ) : (
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-slate-400 text-sm font-bold mb-2">Nom d'utilisateur</label>
                        <input 
                            type="text" 
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="w-full bg-slate-700 border border-slate-600 text-white rounded-xl p-4 outline-none focus:border-blue-500 transition-colors"
                            placeholder="ex: admin"
                        />
                    </div>
                    <div>
                        <label className="block text-slate-400 text-sm font-bold mb-2">Mot de passe</label>
                        <input 
                            type="password" 
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="w-full bg-slate-700 border border-slate-600 text-white rounded-xl p-4 outline-none focus:border-blue-500 transition-colors"
                            placeholder="••••••••"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={!username || !password}
                        className={`w-full py-4 mt-4 rounded-xl text-lg font-bold transition-all ${username && password
                            ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/30 active:scale-95'
                            : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                            }`}
                    >
                        SE CONNECTER
                    </button>
                </form>
                )}
            </div>
        </div>
    );
}
