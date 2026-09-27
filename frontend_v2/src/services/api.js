import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';
const SAME_ORIGIN_API_BASE_URL = '/api';

const api = axios.create({
    baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error?.config;
        const isNetworkError = error?.message === 'Network Error' && !error?.response;
        const canRetrySameOrigin = (
            isNetworkError &&
            originalRequest &&
            !originalRequest._sameOriginRetry &&
            originalRequest.baseURL !== SAME_ORIGIN_API_BASE_URL &&
            typeof window !== 'undefined'
        );

        if (canRetrySameOrigin) {
            originalRequest._sameOriginRetry = true;
            originalRequest.baseURL = SAME_ORIGIN_API_BASE_URL;
            return api(originalRequest);
        }

        const status = error?.response?.status;
        const url = error?.config?.url || '';
        if (status === 401 && !url.endsWith('/token')) {
            localStorage.removeItem('token');
            localStorage.removeItem('username');
            localStorage.removeItem('role');
            localStorage.removeItem('roles');
            localStorage.removeItem('stations');
            delete api.defaults.headers.common['Authorization'];
            window.dispatchEvent(new Event('mmg-auth-expired'));
        }
        return Promise.reject(error);
    }
);

export { API_BASE_URL };
export default api;
