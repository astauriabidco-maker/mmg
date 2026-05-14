import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const token = localStorage.getItem('token');
        if (token) {
            const username = localStorage.getItem('username') || 'Operator';
            const role = localStorage.getItem('role');
            const stations = JSON.parse(localStorage.getItem('stations') || '[]');
            setUser({ username, role, stations });
            api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        }
        setLoading(false);
    }, []);

    const login = async (username, pin) => {
        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', pin); // API expects 'password' form field for OAuth2

            const res = await api.post('/token', formData);

            const { access_token, role, stations } = res.data;
            if (access_token) {
                localStorage.setItem('token', access_token);
                localStorage.setItem('username', username);
                localStorage.setItem('role', role);
                localStorage.setItem('stations', JSON.stringify(stations || []));

                api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
                setUser({ username, role, stations });
                return true;
            }
        } catch (e) {
            console.error("Login failed", e);
        }
        return false;
    };

    const logout = () => {
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        localStorage.removeItem('role');
        localStorage.removeItem('stations');
        delete api.defaults.headers.common['Authorization'];
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, login, logout, loading }}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
